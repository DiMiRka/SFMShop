from decimal import Decimal
from pydantic import ConfigDict, Field, model_validator

from sfmshop.schemas.base import Base


class AssistantRequest(Base):
    message: str = Field(..., min_length=1, max_length=1000)


class AssistantResponse(Base):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(..., description="Ответ пользователю")
    product_ids: list[int] = Field(..., description="id товаров, упомянутых в ответе")
    order_ids: list[int] = Field(..., description="id заказов, упомянутых в ответе")


class ToolArgs(Base):
    model_config = ConfigDict(extra="forbid")


class SearchProductsArgs(ToolArgs):
    query: str | None = Field(None, max_length=100, description="Подстрока в названии товара")
    min_price: Decimal | None = Field(None, ge=0, description="Минимальная цена в рублях")
    max_price: Decimal | None = Field(None, ge=0, description="Максимальная цена в рублях")
    in_stock: bool = Field(False, description="Только товары в наличии")
    limit: int = Field(10, ge=1, le=20, description="Сколько товаров вернуть")

    @model_validator(mode="after")
    def check_price_range(self):
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price больше max_price")
        return self


class GetProductArgs(ToolArgs):
    product_id: int = Field(..., ge=1)


class ListMyOrdersArgs(ToolArgs):
    limit: int = Field(5, ge=1, le=20, description="Сколько последних заказов вернуть")


class GetMyOrderArgs(ToolArgs):
    order_id: int = Field(..., ge=1)
