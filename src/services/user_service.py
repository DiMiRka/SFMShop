from abc import ABC, abstractmethod

from src.models import User
from src.services.discount_service import DiscountStrategy


class UserValidation:
    @staticmethod
    def validate(user: User) -> bool:
        if not user.name:
            raise ValueError("Имя не может быть пустым")
        if "@" not in user.email:
            raise ValueError("Email должен содержать @")
        if user.age < 18:
            raise ValueError("Пользователь должен быть старше 18 лет")
        if user.balance < 0:
            raise ValueError("Баланс не может быть отрицательным")
        return True


class UserCalculator:
    @staticmethod
    def calculate_total(user: User) -> float:
        total = 0
        for order in user.orders:
            total += order.total
        return total

    @staticmethod
    def apply_discount(user: User, discount: DiscountStrategy):
        total = UserCalculator.calculate_total(user)
        return discount.apply(total)


class NotificationService(ABC):
    @abstractmethod
    def send(self, user: User, message: str):
        pass


class EmailNotificationService(NotificationService):
    def send(self, user: User, message: str):
        print(f"Отправка email на {user.email}: {message}")


class Database(ABC):
    @abstractmethod
    def save(self, user: User):
        pass


class PostgresqlDatabase(Database):
    def save(self, user: User):
        print(f"Сохранение пользователя {user.id} в PostgreSQL")


class UserService:
    def __init__(self, notification_service: NotificationService, database: Database):
        self.notification_service = notification_service
        self.database = database

    def register_user(self, user: User):
        UserValidation.validate(user)
        self.notification_service.send(user, f"Добро пожаловать, {user.name}!")
        self.database.save(user)

    @staticmethod
    def generate_user_report(user: User):
        report = f"Пользователь: {user.name}\n"
        report += f"Email: {user.email}\n"
        report += f"Всего заказов: {len(user.orders)}\n"
        report += f"Потрачено: {UserCalculator.calculate_total(user)}\n"
        return report
