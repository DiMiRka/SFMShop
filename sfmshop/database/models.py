from decimal import Decimal
from datetime import datetime
from typing import List

from sqlalchemy import (BigInteger, CheckConstraint, DECIMAL, DateTime, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, false, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship, mapped_column, Mapped
from pgvector.sqlalchemy import VECTOR

from sfmshop.core.order_status import OrderStatus


EMBEDDING_DIMENSIONS = 1536


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(20), nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False, server_default='password')
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    age: Mapped[int] = mapped_column(Integer, CheckConstraint("age >= 18", name="check_user_age"), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    is_admin: Mapped[bool] = mapped_column(default=False, server_default=false(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    orders: Mapped[List["Order"]] = relationship(back_populates="user", passive_deletes=True)
    reviews: Mapped[List["Review"]] = relationship(back_populates="user", passive_deletes=True)


class Product(Base):
    __tablename__ = 'products'
    __table_args__ = (
        Index("ix_products_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
    )

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    items: Mapped[List["OrderItem"]] = relationship(back_populates="product", passive_deletes=True)
    reviews: Mapped[List["Review"]] = relationship(back_populates="product", passive_deletes=True)


class ProductEmbedding(Base):
    __tablename__ = 'product_embeddings'
    __table_args__ = (
        Index("ix_product_embeddings_embedding_hnsw", "embedding", postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey('products.id', ondelete='CASCADE', onupdate='CASCADE'), primary_key=True)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_DIMENSIONS), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class MarketplaceListing(Base):
    __tablename__ = 'marketplace_listings'
    __table_args__ = (
        UniqueConstraint("marketplace", "offer_id", name="uq_marketplace_listings_offer"),
        UniqueConstraint("marketplace", "product_id", name="uq_marketplace_listings_product"),
    )

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey('products.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    marketplace: Mapped[str] = mapped_column(String(20), nullable=False)
    offer_id: Mapped[str] = mapped_column(String(100), nullable=False)
    external_product_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    external_size_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    synced_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    synced_price: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 2), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ImportedOrder(Base):
    __tablename__ = 'marketplace_orders'
    __table_args__ = (
        UniqueConstraint("marketplace", "external_id", name="uq_marketplace_orders_external"),
        Index("ix_marketplace_orders_ordered_at", "marketplace", "ordered_at"),
    )

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True)
    marketplace: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    total: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    items: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Order(Base):
    __tablename__ = 'orders'

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    total: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint(f"status IN ({', '.join(repr(s.value) for s in OrderStatus)})", name="check_order_status"),
        nullable=False,
        default=OrderStatus.PENDING,
        server_default=OrderStatus.PENDING.value,
    )
    payment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="orders", passive_deletes=True)
    items: Mapped[List["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan", passive_deletes=True)


class OrderItem(Base):
    __tablename__ = 'order_items'

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    quantity: Mapped[int]
    total: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(back_populates="items")


class Review(Base):
    __tablename__ = 'reviews'
    __table_args__ = (UniqueConstraint('product_id', 'user_id', name='uq_reviews_product_user'),)

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[int] = mapped_column(CheckConstraint("rating >= 1 AND rating <= 5", name="check_review_rating"),
                                        nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="reviews")
    product: Mapped["Product"] = relationship(back_populates="reviews")
