from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sfmshop.clients.llm import ToolSpec
from sfmshop.core.permissions import order_owner_filter
from sfmshop.database.models import User
from sfmshop.schemas.assistant import GetMyOrderArgs, GetProductArgs, ListMyOrdersArgs, SearchProductsArgs, ToolArgs
from sfmshop.services.order_service import OrderService
from sfmshop.services.product_service import ProductService


@dataclass(frozen=True)
class ToolContext:
    user: User
    products: ProductService
    orders: OrderService


@dataclass
class ToolOutput:
    data: Any
    product_ids: set[int] = field(default_factory=set)
    order_ids: set[int] = field(default_factory=set)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[ToolArgs]
    handler: Callable[[ToolContext, Any], Awaitable[ToolOutput]]

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.args_model.model_json_schema())


def money(value: Any) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.01")))


def iso(value: Any) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def order_summary(order: dict) -> dict:
    return {
        "id": order["id"],
        "status": order["status"],
        "total": money(order["total"]),
        "created_at": iso(order["created_at"]),
        "items": [
            {"product_id": item["product_id"], "quantity": item["quantity"], "total": money(item["total"])}
            for item in order["items"]
        ],
    }


async def search_products(ctx: ToolContext, args: SearchProductsArgs) -> ToolOutput:
    products = await ctx.products.search_products(
        name_query=args.query,
        min_price=args.min_price,
        max_price=args.max_price,
        in_stock=args.in_stock,
        limit=args.limit,
    )
    return ToolOutput(data=products, product_ids={p["id"] for p in products})


async def get_product(ctx: ToolContext, args: GetProductArgs) -> ToolOutput:
    product = await ctx.products.get_product_by_id(args.product_id)
    return ToolOutput(data=product, product_ids={product["id"]})


async def list_my_orders(ctx: ToolContext, args: ListMyOrdersArgs) -> ToolOutput:
    orders = await ctx.orders.get_all_orders(order_owner_filter(ctx.user), args.limit, 0, newest_first=True)
    data = [order_summary(order) for order in orders]
    return ToolOutput(
        data=data,
        order_ids={order["id"] for order in data},
        product_ids={item["product_id"] for order in data for item in order["items"]},
    )


async def get_my_order(ctx: ToolContext, args: GetMyOrderArgs) -> ToolOutput:
    order = order_summary(await ctx.orders.get_order_by_id(args.order_id, order_owner_filter(ctx.user)))
    return ToolOutput(
        data=order,
        order_ids={order["id"]},
        product_ids={item["product_id"] for item in order["items"]},
    )


TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in [
        Tool(
            name="search_products",
            description="Поиск товаров каталога по подстроке в названии, диапазону цены и наличию. "
                        "Цены в рублях, строкой",
            args_model=SearchProductsArgs,
            handler=search_products,
        ),
        Tool(
            name="get_product",
            description="Товар каталога по id: название, цена, остаток на складе, средний рейтинг и число отзывов",
            args_model=GetProductArgs,
            handler=get_product,
        ),
        Tool(
            name="list_my_orders",
            description="Последние заказы текущего пользователя, новые первыми: сумма, дата, позиции",
            args_model=ListMyOrdersArgs,
            handler=list_my_orders,
        ),
        Tool(
            name="get_my_order",
            description="Заказ текущего пользователя по id. Чужой или несуществующий заказ — ошибка «не найден»",
            args_model=GetMyOrderArgs,
            handler=get_my_order,
        ),
    ]
}
