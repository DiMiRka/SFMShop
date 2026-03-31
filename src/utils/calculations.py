import time
from random import randrange


class Product:
    def __init__(self, product_id, name, price, quantity):
        self.product_id = product_id
        self.name = name
        self.price = price
        self.quantity = quantity


class Order:
    def __init__(self, order_id: int, items: list):
        self.order_id = order_id
        self.items = items


test_orders = [
    Order(i,
          [Product(1, "Телевизор",
                   randrange(500, 50000, 100),
                   randrange(1, 9, 1))
           for _ in range(randrange(1, 5, 1))
           ]) for i in range(500_000)]


def lead_time(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"Функция {func.__name__} выполнилась за {execution_time:.4f} секунд")
        return execution_time
    return wrapper


@lead_time
def calculate_total_orders(orders):
    total = 0
    for order in orders:
        for item in order.items:
            total += item.price * item.quantity
    return total


@lead_time
def calculate_total_orders_optimized(orders):
    return sum(item.price * item.quantity for order in orders for item in order.items)


result_1 = calculate_total_orders(test_orders)
result_2 = calculate_total_orders_optimized(test_orders)
result = result_1 - result_2
print(f"Разница выполнения между изначальной функцией и оптимизированной равна {result:.4f} секунд")
print("---------------------------------------------------------------")

test_products = [Product(product_id=i, name="Монитор",
                         price=randrange(500, 50000, 100),
                         quantity=randrange(1, 9, 1))
                 for i in range(1_500_000)]


@lead_time
def find_product(products, product_id):
    for product in products:
        if product.product_id == product_id:
            return product
    return None


def create_products_index(products):
    return {product.product_id: product for product in products}


@lead_time
def find_product_optimized(products, product_id):
    return products.get(product_id)


result_1 = find_product(test_products, 1_400_000)
products_index = create_products_index(test_products)
result_2 = find_product_optimized(products_index, 1_400_000)
result = result_1 - result_2
print(f"Разница выполнения между изначальной функцией и оптимизированной равна {result:.4f} секунд")
