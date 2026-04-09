from abc import ABC, abstractmethod

from src.models.exceptions import InvalidOrderError
from src.schemas import OrderCreate
from src.services.product_service import ProductCalculator
from src.services.discount_service import DiscountStrategy
from src.database import get_user_balance_db, get_user_email_db, create_order_db


# class OrderCalculator:
#     @staticmethod
#     def calculate_total(order: Order) -> float:
#         return sum([ProductCalculator.calculate_total(product) for product in order.products])
#
#     @staticmethod
#     def apply_discount(order: Order, discount: DiscountStrategy) -> float:
#         total = OrderCalculator.calculate_total(order)
#         return discount.apply(total)
#
#
# class OrderValidator:
#     @staticmethod
#     def validate(order: Order):
#         if not order.user:
#             raise InvalidOrderError("Пользователь не существует")
#         if not order.products:
#             raise InvalidOrderError("Заказ невалиден: пустой список товаров")
#
#
# class NotificationService(ABC):
#     @abstractmethod
#     def send(self, order: Order):
#         pass
#
#
# class Database(ABC):
#     @abstractmethod
#     def save(self, order: Order):
#         pass
#
#
# class OrderService:
#     def __init__(self, notification_service: NotificationService, database: Database):
#         self.notification_service = notification_service
#         self.database = database
#
#     async def process_order(self, order: Order, discount: DiscountStrategy = None):
#         OrderValidator.validate(order)
#         total = OrderCalculator.calculate_total(order)
#         if discount:
#             total = OrderCalculator.apply_discount(order, discount)
#         self.notification_service.send(order)
#         self.database.save(order)
#         return total
#
#
# async def validate_order_data(order_data):
#     if not order_data.get("user_id"):
#         raise ValueError("Нет user_id")
#     if not order_data.get("items"):
#         raise ValueError("Нет товаров")
#     if len(order_data.get("items", [])) == 0:
#         raise ValueError("Список товаров пуст")
#
#     for item in order_data["items"]:
#         if not item.get("price"):
#             raise ValueError("Нет цены товара")
#         if not item.get("quantity"):
#             raise ValueError("Нет количества")
#         if item["price"] < 0:
#             raise ValueError("Цена не может быть отрицательной")
#         if item["quantity"] <= 0:
#             raise ValueError("Количество должно быть положительным")
#
#
# async def calculate_order_total(items):
#     total = 0
#     for item in items:
#         total += item["price"] * item["quantity"]
#     return total
#
#
# async def calculate_discount(total):
#     if total > 10000:
#         return 0.15
#     elif total > 5000:
#         return 0.10
#     elif total > 1000:
#         return 0.05
#     return 0
#
#
# async def check_user_balance(conn, user_id, required_amount):
#     user_balance = get_user_balance_db(conn, user_id)
#     if user_balance < required_amount:
#         raise ValueError("Недостаточно средств")
#     return True
#
#
# async def create_order(conn, user_id, product_id, total):
#     order_id = create_order_db(conn, order=OrderCreate(db, user_id, product_id, total))
#     return order_id
#
#
# async def send_email(email, message):
#     print(f"Отправлено сообщение на Email{email}: {message}")
#
#
# async def notify_user(conn, user_id, order_id, total):
#     user_email = get_user_email_db(conn, user_id)
#     await send_email(user_email, f"Заказ #{order_id} оформлен на сумму {total}")
#
#
# async def log_order_processing(order_id, user_id, total):
#     print(f"Заказ {order_id} обработан: пользователь {user_id}, сумма {total}")
#
#
# async def process_order(conn, order_data):
#     await validate_order_data(order_data)
#
#     total = calculate_order_total(order_data["items"])
#
#     discount_rate = calculate_discount(total)
#     final_total = total * (1 - discount_rate)
#
#     await check_user_balance(conn, order_data["user_id"], final_total)
#
#     order_id = create_order(conn, order_data["user_id"], order_data["items"], final_total)
#
#     await notify_user(conn, order_data["user_id"], order_id, final_total)
#
#     await log_order_processing(order_id, order_data["user_id"], final_total)
#
#     return {
#         "order_id": order_id,
#         "total": final_total,
#         "discount": discount_rate
#     }
