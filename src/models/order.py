class Order:
    def __init__(self, user, products, order_id=None, created_at=None):
        self.user = user
        self.products = products
        self.order_id = order_id
        self.created_at = created_at

    def calculate_total(self):
        return OrderCalculator.calculate_total(self)

    def calculate_discount(self, discount_percent: float):
        return OrderCalculator.calculate_discount(self, discount_percent)

    @staticmethod
    def calculate_delivery(weight, distance):
        return OrderCalculator.calculate_delivery(weight, distance)


class OrderCalculator:

    @staticmethod
    def calculate_total(order: Order) -> float:
        total = 0
        for product in order.products:
            total += product.get_total_price()
        return total

    @staticmethod
    def calculate_discount(order: Order, discount_percent: float) -> float:
        total = OrderCalculator.calculate_total(order)
        return total * (1 - discount_percent / 100)

    @staticmethod
    def calculate_delivery(weight: float, distance: float) -> float:
        base_price = 100
        weight_price = weight * 10
        distance_price = distance * 5

        return base_price + distance_price + weight_price


class OrderValidator:

    @staticmethod
    def validate(order: Order) -> bool:
        if not order.products:
            raise ValueError('Заказ не может быть пустым')
        if not order.user:
            raise ValueError('Заказ должен иметь пользователя')
        for product in order.products:
            if product.quantity <= 0:
                raise ValueError('Количество товара должно быть положительным')
        return True
