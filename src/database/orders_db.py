import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_REPEATABLE_READ
from fastapi import HTTPException

from src.models import Product, Order, User
from src.models.exceptions import InsufficientStockError, BusinessLogicError
from src.services.order_service import OrderCalculator


def create_order_db(conn, user_id, product_id, quantity):
    conn.set_isolation_level(ISOLATION_LEVEL_REPEATABLE_READ)
    try:
        with conn.cursor() as cursor:

            cursor.execute("SELECT * FROM products WHERE id = %s FOR UPDATE", (product_id,))
            product_db = cursor.fetchone()
            if product_db is None:
                raise HTTPException(status_code=404, detail="Товар не найден")
            product = Product(name=product_db[1], price=product_db[2], quantity=quantity)
            new_quantity = product_db[3] - quantity
            if new_quantity < 0:
                raise InsufficientStockError("Недостаточно товара на складе")
            cursor.execute("UPDATE products SET quantity = %s WHERE id = %s",
                           (new_quantity, product_id,))

            cursor.execute("SELECT * FROM users WHERE id = %s FOR UPDATE", (user_id,))
            user_db = cursor.fetchone()
            if user_db is None:
                raise HTTPException(status_code=404, detail="Пользователь не найден")
            user = User(name=user_db[1], email=user_db[2])
            user.id = user_db[0]

            order = Order(order_id=1, user=user, products=[product])

            total = OrderCalculator.calculate_total(order)

            user_balance = user_db[4] - total
            if user_balance < 0:
                raise BusinessLogicError("Недостаточно средств на балансе пользователя")

            cursor.execute("UPDATE users SET balance = %s WHERE id = %s", (user_balance, user_db[0]))

            cursor.execute(
                "INSERT INTO orders (user_id, total) VALUES (%s, %s) RETURNING id",
                (user_id, total)
            )
            order_id = cursor.fetchone()[0]
            order.id = order_id

            cursor.execute(
                """INSERT INTO order_items (order_id, product_id, quantity, price) 
                   VALUES (%s, %s, %s, %s)""",
                (order_id, product_id, quantity, product_db[2])
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
            cursor.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
            order = cursor.fetchone()
            if order is None:
                raise HTTPException(status_code=404, detail="Заказ не найден")

            cursor.execute(
                "DELETE FROM orders WHERE id = %s",
                (order_id,)
            )
        conn.commit()
        return {"id": order_id, "message": "Заказ удален"}

    except psycopg2.Error as e:
        conn.rollback()
        print(f"Ошибка при удалении заказа: {e}")
