from collections.abc import Callable
from decimal import Decimal
from email.message import EmailMessage
from html import escape

from loguru import logger
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from sfmshop.clients.email_client import EmailClient
from sfmshop.core.metrics import EMAILS
from sfmshop.database.models import Order
from sfmshop.repositories.order_repository import OrderRepository
from sfmshop.services.cache_service import CacheService


SENT_MARK_TTL = 7 * 24 * 3600


def rub(amount: Decimal) -> str:
    return f"{amount:.2f} ₽"


def build_order_paid_email(order: Order) -> EmailMessage:
    lines = [(item.product.name, item.quantity, item.total) for item in order.items]

    text = "\n".join(
        [f"Здравствуйте, {order.user.name}!", "", f"Заказ №{order.id} оплачен.", ""]
        + [f"- {name} × {quantity}: {rub(total)}" for name, quantity, total in lines]
        + ["", f"Итого: {rub(order.total)}", "", "Спасибо за покупку в SFMShop!"]
    )
    rows = "".join(
        f"<tr><td>{escape(name)}</td><td>{quantity}</td><td>{rub(total)}</td></tr>"
        for name, quantity, total in lines
    )
    html = (
        f"<p>Здравствуйте, {escape(order.user.name)}!</p>"
        f"<p>Заказ №{order.id} оплачен.</p>"
        f"<table><tr><th>Товар</th><th>Кол-во</th><th>Сумма</th></tr>{rows}</table>"
        f"<p><b>Итого: {rub(order.total)}</b></p>"
        "<p>Спасибо за покупку в SFMShop!</p>"
    )

    message = EmailMessage()
    message["To"] = order.user.email
    message["Subject"] = f"Заказ №{order.id} оплачен"
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    return message


class OrderNotifier:
    def __init__(
            self,
            session_factory: Callable[[], AsyncSession],
            cache: CacheService,
            email: EmailClient | None):
        self.session_factory = session_factory
        self.cache = cache
        self.email = email

    async def order_paid(self, order_id: int) -> None:
        if self.email is None:
            EMAILS.labels("disabled").inc()
            logger.info(f"Email for order id={order_id} skipped: SMTP is not configured")
            return

        mark = f"notification:order_paid:{order_id}"
        if await self._already_sent(mark):
            EMAILS.labels("duplicate").inc()
            logger.info(f"Email for order id={order_id} already sent")
            return

        async with self.session_factory() as session:
            order = await OrderRepository(session).get_with_products_and_user(order_id)
            if order is None or order.user is None:
                EMAILS.labels("skipped").inc()
                logger.warning(f"Email for order id={order_id} skipped: order or user not found")
                return
            message = build_order_paid_email(order)

        try:
            await self.email.send(message)
        except Exception:
            EMAILS.labels("failed").inc()
            raise

        EMAILS.labels("sent").inc()
        logger.info(f"Email for order id={order_id} sent")
        await self._mark_sent(mark)

    async def _already_sent(self, mark: str) -> bool:
        try:
            return await self.cache.get(mark) is not None
        except RedisError as exc:
            logger.warning(f"notification_mark_unavailable error={exc!r}")
            return False

    async def _mark_sent(self, mark: str) -> None:
        try:
            await self.cache.set(mark, True, ttl=SENT_MARK_TTL)
        except RedisError as exc:
            logger.warning(f"notification_mark_unavailable error={exc!r}")
