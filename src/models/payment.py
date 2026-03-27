from abc import ABC, abstractmethod


class Payment(ABC):
    def __init__(self, amount):
        self.amount = amount

    @abstractmethod
    def process_payment(self):
        raise NotImplementedError("Метод должен быть переопределен")


class CardPayment(Payment):
    def __init__(self, amount: int, card_number: str):
        super().__init__(amount)
        self.__card_number = card_number

    def process_payment(self):
        return f"Оплата картой {self.__card_number[-4]}: {self.amount} руб."


class PayPalPayment(Payment):
    def __init__(self, amount: int, email: str):
        super().__init__(amount)
        self.email = email

    def process_payment(self):
        return f"Оплата PayPal ({self.email}): {self.amount} руб."
