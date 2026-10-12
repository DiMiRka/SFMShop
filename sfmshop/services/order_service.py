from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from loguru import logger

from sfmshop.core.actor import Actor
from sfmshop.repositories import OrderRepository, UserRepository, ProductRepository
from sfmshop.services.cache_service import CacheService
from sfmshop.services.queue_producer import QueueProducer
from sfmshop.core.metrics import ORDERS_CREATED
from sfmshop.core.order_status import OrderStatus, can_transition, ensure_transition
from sfmshop.database.models import Order
from sfmshop.schemas import OrderResponse, OrderCreate, ProductUpdate, OrderInDB, OrderItemsInDB
if TYPE_CHECKING:
    from sfmshop.clients.payment_client import PaymentClient
from sfmshop.core.exceptions import (InsufficientStockError, InvalidOrderStatusError, NotFoundError,
                                     PaymentUnavailableError, ValidationError)


class OrderService:
    def __init__(
            self,
            order_rep: OrderRepository,
            user_rep: UserRepository,
            product_rep: ProductRepository,
            cache: CacheService,
            queue: QueueProducer,
            payments: PaymentClient | None = None):
        self.order_rep = order_rep
        self.user_rep = user_rep
        self.product_rep = product_rep
        self.cache = cache
        self.queue = queue
        self.payments = payments

    async def get_all_orders(
            self,
            user_id: int | None,
            limit: int = 100,
            offset: int = 0,
            newest_first: bool = False) -> list[dict]:
        async def fetch():
            if user_id is None:
                orders = await self.order_rep.get_all(limit, offset, newest_first=newest_first)
            else:
                orders = await self.order_rep.get_user_orders(user_id, limit, offset, newest_first=newest_first)

            return [self._to_response(order) for order in orders]

        owner_key = "all" if user_id is None else user_id
        order_key = ":desc" if newest_first else ""
        return await self.cache.get_or_set_cache(f"orders:{owner_key}:{limit}:{offset}{order_key}", fetch)

    async def get_order_by_id(self, order_id: int, user_id: int | None) -> dict:
        async def fetch():
            order = await self.order_rep.get_by_id(order_id)

            if not order:
                logger.warning(f"Order id={order_id} not found")
                raise NotFoundError("Заказ не найден")

            return self._to_response(order)

        order_data = await self.cache.get_or_set_cache(f"order:{order_id}", fetch)

        if user_id is not None and order_data["user_id"] != user_id:
            logger.warning(f"User id={user_id} tried to access order id={order_id}")
            raise NotFoundError("Заказ не найден")

        return order_data

    async def create_order(self, user_id: int, order: OrderCreate, *, actor: Actor) -> dict:
        if not order.items:
            raise ValidationError("Empty order")

        quantity: list[int] = []
        product_ids: list[int] = []

        for item in order.items:
            item_quantity = item.quantity
            if item_quantity <= 0:
                logger.warning("create order: quantity must be positive.")
                raise ValidationError("Количество должно быть положительным")

            quantity.append(item_quantity)
            product_ids.append(item.product_id)

        async with self.order_rep.db.begin():

            if not await self.user_rep.get_by_id(user_id):
                logger.warning(f"User id={user_id} not found")
                raise NotFoundError("Пользователь не найден")

            result = await self.product_rep.get_by_ids_for_update(product_ids)
            products_db = {p.id: p for p in result}

            order_items_db: list[tuple[int, int, Decimal]] = []
            total = Decimal("0")

            for idx, product_id in enumerate(product_ids):
                product_db = products_db.get(product_id)

                if not product_db:
                    logger.warning(f"Product id={product_id} not found")
                    raise NotFoundError("Товар не найден")

                if product_db.quantity < quantity[idx]:
                    raise InsufficientStockError("Недостаточно товара на складе")

                product_db.quantity -= quantity[idx]

                product_total: Decimal = product_db.price * quantity[idx]

                total += product_total

                order_items_db.append((product_db.id, quantity[idx], product_total))

            order_data = OrderInDB(user_id=user_id, items=[], total=total).model_dump(exclude_unset=True)

            order_db_id = await self.order_rep.create(order_data)

            for product_id, item_quantity, product_total in order_items_db:
                data = OrderItemsInDB(
                    order_id=order_db_id,
                    product_id=product_id,
                    quantity=item_quantity,
                    total=product_total,
                ).model_dump(exclude_unset=True)
                await self.order_rep.create_order_item(data)

        ORDERS_CREATED.inc()

        await self.queue.publish_event("order_exchange", "order.created",
                                       self._event(order_db_id, user_id, product_ids, actor))

        try:
            return await self.pay_order(order_db_id, user_id, actor=actor)
        except PaymentUnavailableError:
            logger.warning(f"Order id={order_db_id} stays pending: payment service unavailable")
            async with self.order_rep.db.begin():
                return self._to_response(await self._get_for_update(order_db_id, user_id))

    async def pay_order(self, order_id: int, user_id: int | None, *, actor: Actor) -> dict:
        async with self.order_rep.db.begin():
            order = await self._get_for_update(order_id, user_id)
            ensure_transition(order.status, OrderStatus.PAID)
            owner_id, total = order.user_id, order.total

        payment = await self._require_payments().charge(order_id, owner_id, total)
        paid = payment.status == "success"
        target = OrderStatus.PAID if paid else OrderStatus.FAILED

        async with self.order_rep.db.begin():
            latest = await self.order_rep.get_by_id_for_update(order_id)

            if latest is None:
                recorded = applicable = False
            else:
                recorded = latest.status == OrderStatus.PAID and latest.payment_id == payment.payment_id
                applicable = not recorded and can_transition(latest.status, target)
                if applicable:
                    latest.status = target
                    latest.payment_id = payment.payment_id
                result = self._to_response(latest)

        if recorded:
            return result

        if latest is None or not applicable:
            if paid and payment.payment_id is not None:
                logger.warning(f"Order id={order_id} changed during payment, refunding payment id={payment.payment_id}")
                await self._require_payments().refund(payment.payment_id)
            raise InvalidOrderStatusError("Заказ изменился во время оплаты, повторите запрос")

        routing_key = "order.paid" if paid else "order.payment_failed"
        await self.queue.publish_event("order_exchange", routing_key,
                                       self._event(order_id, owner_id, self._product_ids(latest), actor))

        return result

    async def cancel_order(self, order_id: int, user_id: int | None, *, actor: Actor) -> dict:
        async with self.order_rep.db.begin():
            order = await self._get_for_update(order_id, user_id)
            ensure_transition(order.status, OrderStatus.CANCELLED)

            await self._return_stock(order)
            order.status = OrderStatus.CANCELLED

            result = self._to_response(order)

        await self.queue.publish_event("order_exchange", "order.cancelled",
                                       self._event(order_id, order.user_id, self._product_ids(order), actor))

        return result

    async def delete_order(self, order_id: int, *, actor: Actor):
        async with self.order_rep.db.begin():
            order = await self._get_for_update(order_id, None)
            seen_status, owner_id, payment_id = order.status, order.user_id, order.payment_id

        if seen_status == OrderStatus.PAID and payment_id is not None:
            await self._require_payments().refund(payment_id)

        async with self.order_rep.db.begin():
            order = await self._get_for_update(order_id, None)

            if order.status != seen_status:
                raise InvalidOrderStatusError("Заказ изменился во время удаления, повторите запрос")

            if order.status != OrderStatus.CANCELLED:
                await self._return_stock(order)

            product_ids = self._product_ids(order)

            await self.order_rep.delete(order)

        await self.queue.publish_event("order_exchange", "order.deleted",
                                       self._event(order_id, owner_id, product_ids, actor))

        return {"id": order_id, "message": "Заказ удален"}

    def _require_payments(self) -> PaymentClient:
        if self.payments is None:
            raise PaymentUnavailableError("Сервис оплаты не настроен")
        return self.payments

    async def _get_for_update(self, order_id: int, user_id: int | None) -> Order:
        order = await self.order_rep.get_by_id_for_update(order_id)

        if not order or (user_id is not None and order.user_id != user_id):
            logger.warning(f"Order id={order_id} not found for user id={user_id}")
            raise NotFoundError("Заказ не найден")

        return order

    async def _return_stock(self, order: Order) -> None:
        products = await self.product_rep.get_by_ids_for_update(self._product_ids(order))
        products_db = {p.id: p for p in products}

        for item in order.items:
            product_db = products_db[item.product_id]
            data = ProductUpdate(quantity=product_db.quantity + item.quantity).model_dump(exclude_unset=True)
            await self.product_rep.update(product_db, data)

    @staticmethod
    def _product_ids(order: Order) -> list[int]:
        return [item.product_id for item in order.items]

    @staticmethod
    def _event(order_id: int, user_id: int, product_ids: list[int], actor: Actor) -> dict:
        return {"order_ids": order_id, "user_ids": user_id, "product_ids": product_ids, **actor.event_fields()}

    @staticmethod
    def _to_response(order: Order) -> dict:
        return OrderResponse.model_validate(order).model_dump(mode="json")
