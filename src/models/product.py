class Product:
    def __init__(self, name, price, quantity):
        self.name = name
        self.price = price
        self.quantity = quantity

        try:
            if price < 0:
                self.price = 0
                raise ValueError('Цена не может быть отрицательной')
            else:
                self.price = price
        except ValueError as e:
            print(e)

    def get_total_price(self) -> float:
        return self.price * self.quantity

    def __str__(self):
        return f"Товар: {self.name}, Цена: {self.price} руб., Количество: {self.quantity}"

    def __repr__(self):
        return f"Product('{self.name}', {self.price}, {self.quantity})"

    def __lt__(self, other):
        if isinstance(other, Product):
            return self.name < other.name and self.price < other.price
        else:
            return NotImplemented

    def __eq__(self, other):
        if isinstance(other, Product):
            return self.name == other.name and self.price == other.price
        else:
            return NotImplemented
