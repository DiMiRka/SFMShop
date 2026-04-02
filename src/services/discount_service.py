from abc import ABC, abstractmethod


class DiscountStrategy(ABC):
    @abstractmethod
    def apply(self, price: float):
        pass


class PercentDiscount(DiscountStrategy):
    def __init__(self, percent: float):
        self.percent = percent

    def apply(self, price: float):
        return price * (1 - self.percent / 100)


class FixedDiscount(DiscountStrategy):
    def __init__(self, amount: float):
        self.amount = amount

    def apply(self, price: float):
        return price - self.amount


class PercentDiscountUser(DiscountStrategy):
    def __init__(self, percent: float):
        self.percent = percent

    def apply(self, balance: float):
        return balance * (1 + self.percent / 100)


class FixedDiscountUser(DiscountStrategy):
    def __init__(self, amount: float):
        self.amount = amount

    def apply(self, balance: float):
        return balance * (1 + self.amount / 100)
