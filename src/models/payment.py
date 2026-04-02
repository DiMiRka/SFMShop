from abc import ABC, abstractmethod

from src.models.mixins import LoggableMixin, SerializableMixin


class Payment(ABC):
    def __init__(self, amount):
        self.amount = amount

    @abstractmethod
    def process_payment(self):
        raise NotImplementedError("Метод должен быть переопределен")


class CardPayment(Payment, LoggableMixin, SerializableMixin):
    def __init__(self, amount: int, card_number: str):
        super().__init__(amount)
        self.__card_number = card_number
        self.log(f"Создан платеж: {amount}")

    def process_payment(self):
        return f"Оплата картой {self.__card_number[-4]}: {self.amount} руб."

    def to_json(self):
        return {"type": "CardPayment", "amount": self.amount}


class PayPalPayment(Payment, LoggableMixin, SerializableMixin):
    def __init__(self, amount: int, email: str):
        super().__init__(amount)
        self.email = email
        self.log(f"Создан платеж: {amount}")

    def process_payment(self):
        return f"Оплата PayPal ({self.email}): {self.amount} руб."

    def to_json(self):
        return {"type": "PayPalPayment", "amount": self.amount}
