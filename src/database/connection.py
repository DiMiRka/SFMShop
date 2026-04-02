import psycopg2
from fastapi import HTTPException

from src.models import Product, Order, User
from src.services.order_service import OrderCalculator
from src.schemas import ProductCreate


def connect_to_db():
    try:
        conn = psycopg2.connect(host="localhost",
                                dbname="sfmshop",
                                user="postgres",
                                password="dima-784512")

        return conn
    except psycopg2.Error as e:
        print(f"Ошибка подключения к БД: {e}")
        return None


def get_product_db(conn, product_id: int):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
            product_db = cursor.fetchone()
            product = Product(product_db[1], product_db[2], product_db[3])
            product.id = product_db[0]
            if product is None:
                return None
            return product.__dict__
    except psycopg2.Error as e:
        print(f"Ошибка при получении товара: {e}")


def add_product_db(conn, product: ProductCreate):
    try:
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO products (name, price, quantity)"
                           "VALUES (%s, %s, %s)"
                           "RETURNING id",
                           (product.name, product.price, product.quantity))
            print(f"Товар добавлен: {product.name}, {product.price}, {product.quantity}")
            product_id = cursor.fetchone()[0]
            conn.commit()
            return {"id": product_id, "message": "Товар добавлен"}
    except psycopg2.Error as e:
        conn.rollback()
        print(f"Ошибка при добавлении товара: {e}")


def get_all_products_db(conn, limit: int, offset: int):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM products")
            all_products = cursor.fetchall()

            products = []
            for data in all_products:
                product = Product(name=data[1], price=data[2], quantity=data[3])
                product.id = data[0]
                products.append(product.__dict__)

            total = len(all_products)
            paginated_products = products[offset:offset+limit]

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "products": paginated_products
        }
    except psycopg2.Error as e:
        print(f"Ошибка при получении товаров: {e}")


def update_product_db(conn, product_id, product: ProductCreate):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
            product_db = cursor.fetchone()
            if product_db is None:
                return None

            cursor.execute("UPDATE products "
                           "SET name = %s, price = %s, quantity = %s "
                           "WHERE id = %s",
                           (product.name, product.price, product.quantity, product_id))

            return {"id": product_id, "message": "Товар обновлен"}
    except psycopg2.Error as e:
        print(f"Ошибка при обновлении товара: {e}")


def delete_product_db(conn, product_id):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
            product = cursor.fetchone()
            if product is None:
                return None

            cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
            return product
    except psycopg2.Error as e:
        print(f"Ошибка при удалении товара: {e}")


def update_product_price_db(conn, product_id, new_price):
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE products SET price = %s WHERE id = %s",
                           (new_price, product_id))
        print(f"Цена обновлена: {new_price}")
        conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
        print(f"Ошибка при обновлении цены: {e}")


def get_user_orders_db(conn, user_id):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM orders WHERE user_id = %s", (user_id,))
            orders = cursor.fetchall()
        print(f"Все заказы пользователя {user_id}")
        for order in orders:
            print(order)
    except psycopg2.Error as e:
        print(f"Ошибка при получении заказов: {e}")
