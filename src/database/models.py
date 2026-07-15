from decimal import Decimal
from datetime import datetime
from typing import List

from sqlalchemy import Integer, String, ForeignKey, CheckConstraint, DECIMAL, Text, func
from sqlalchemy.orm import DeclarativeBase, relationship, mapped_column, Mapped

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(20), nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False, server_default='password')
    email: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    age: Mapped[int] = mapped_column(Integer, CheckConstraint("age >= 18", name="check_user_age"), nullable=False)
    balance: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=0.0)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    orders: Mapped[List["Order"]] = relationship(back_populates="user", passive_deletes=True)
    reviews: Mapped[List["Review"]] = relationship(back_populates="user", passive_deletes=True)


class Product(Base):
    __tablename__ = 'products'

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(20), nullable=False)
    price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    items: Mapped[List["OrderItem"]] = relationship(back_populates="product", passive_deletes=True)
    reviews: Mapped[List["Review"]] = relationship(back_populates="product", passive_deletes=True)


class Order(Base):
    __tablename__ = 'orders'

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    total: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
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

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[int] = mapped_column(CheckConstraint("rating >= 1 AND rating <= 5"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="reviews")
    product: Mapped["Product"] = relationship(back_populates="reviews")
