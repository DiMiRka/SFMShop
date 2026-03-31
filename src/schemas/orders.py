from src.schemas.base import Base


class OrderCreate(Base):
    user_id: int
    product_id: int
    quantity: int
