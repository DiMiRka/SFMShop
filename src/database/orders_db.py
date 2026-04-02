import psycopg2
from fastapi import HTTPException

from src.models import Product, Order, User
from src.services.order_service import OrderCalculator


def save_order_db(conn, user_id, product_id, quantity):
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