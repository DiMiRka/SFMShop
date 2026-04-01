import psycopg2
from fastapi import HTTPException

from src.models import Product, Order, OrderCalculator, User
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


def create_user_db(conn, name, email):
    try:
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO users (name, email) VALUES (%s, %s)", (name, email))
        print(f"Пользователь добавлен: {name}, {email}")
        print("------------")
        conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
        print(f"Ошибка при создании пользователя: {e}")


def get_user_by_id_db(conn, user_id):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()

            if user is not None:
                return {"id": user[0], "name": user[1], "email": user[2]}
            else:
                return None
    except psycopg2.Error as e:
        print(f"Ошибка при получении пользователя: {e}")
        return None


def create_order_db(conn, user_id, product_id, quantity):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
            product_db = cursor.fetchone()
            if product_db is None:
                raise HTTPException(status_code=404, detail="Товар не найден")
            product = Product(name=product_db[1], price=product_db[2], quantity=quantity)

            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user_db = cursor.fetchone()
            if user_db is None:
                raise HTTPException(status_code=404, detail="Пользователь не найден")
            user = User(name=user_db[1], email=user_db[2])
            user.id = user_db[0]

            order = Order(order_id=1, user=user, products=[product])

            total = OrderCalculator.calculate_total(order)

            cursor.execute(
                "INSERT INTO orders (user_id, total) VALUES (%s, %s) RETURNING id",
                (user_id, total)
            )
            order_id = cursor.fetchone()[0]
            order.id = order_id

            cursor.execute(
                "INSERT INTO order_items (order_id, product_id, quantity) VALUES (%s, %s, %s)",
                (order_id, product_id, quantity)
            )
        conn.commit()
        return {
            "order_id": order_id,
            "user_id": user_id,
            "product_id": product_id,
            "quantity": quantity,
            "total": float(total)
        }

    except psycopg2.Error as e:
        conn.rollback()
        print(f"Ошибка при создании заказа: {e}")
    except Exception as e:
        conn.rollback()
        print(f"Ошибка при создании заказа: {e}")


def delete_order_db(conn, order_id):
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM orders WHERE id = %s",
                (order_id,)
            )
            deleted_rows = cursor.rowcount

        conn.commit()

        print(f"Удалено заказов: {deleted_rows}")
        return deleted_rows

    except psycopg2.Error as e:
        conn.rollback()
        print(f"Ошибка при удалении заказа: {e}")
        return 0


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
