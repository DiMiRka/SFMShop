from src.models.exceptions import NegativePriceError, InsufficientStockError


class Product:
    def __init__(self, name, price, quantity):
        self.name = name
        self.price = price
        self.quantity = quantity
        if price < 0:
            self.price = 0
            raise NegativePriceError('Цена не может быть отрицательной')
        else:
            self.price = price

    def __str__(self):
        return f"Товар: {self.name}, Цена: {self.price} руб., Количество: {self.quantity}"

    def __repr__(self):
        return f"Product('{self.name}', {self.price}, {self.quantity})"

    def __lt__(self, other):
        if isinstance(other, Product):
            return self.price < other.price
        else:
            return NotImplemented

    def __eq__(self, other):
        if isinstance(other, Product):
            return self.name == other.name and self.price == other.price
        else:
            return NotImplemented

    def sell(self, amount: int):
        if self.quantity < amount:
            raise InsufficientStockError(f"Товара недостаточно. На складе: {self.quantity}, требуется: {amount}")
        self.quantity = self.quantity - amount

    def get_total_price(self) -> float:
        return self.price * self.quantity

    def set_price(self, price: float):
        if price > 0:
            self.price = price
        else:
            raise NegativePriceError('Цена не может быть отрицательной')
