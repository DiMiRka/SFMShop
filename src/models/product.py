from src.models.mixins import LoggableMixin, SerializableMixin
from src.models.descriptors import PositiveNumber


class Product(LoggableMixin, SerializableMixin):
    price = PositiveNumber('_price')
    quantity = PositiveNumber('_quantity')

    def __init__(self, name, price, quantity):
        self.name = name
        self.price = price
        self.quantity = quantity
        self.log(f'Создан товар: {name}')

    def to_json(self):
        return {'name': self.name, 'price': self.price, 'quantity': self.quantity}

    def get_total_price(self):
        return self.price * self.quantity
