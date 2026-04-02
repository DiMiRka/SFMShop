import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_REPEATABLE_READ, ISOLATION_LEVEL_SERIALIZABLE
from datetime import datetime


def get_orders_with_products(conn, user_id):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                           SELECT orders.id     AS order_id,
                                  products.name AS product_name,
                                  order_items.quantity,
                                  order_items.price
                           FROM orders
                                    INNER JOIN order_items ON orders.id = order_items.order_id
                                    INNER JOIN products ON products.id = order_items.product_id
                           WHERE orders.user_id = %s
                           """, (user_id,))

            orders = cursor.fetchall()
            print("Заказы пользователя:")
            for order in orders:
                print(order)
        return orders

    except psycopg2.Error as e:
        print(f"Ошибка при получении товаров пользователя: {e}")


def get_orders_count_by_users(conn):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                           SELECT users.id,
                                  users.name,
                                  COUNT(orders.id) AS orders_count
                           FROM users
                                    LEFT JOIN orders ON users.id = orders.user_id
                           GROUP BY users.id, users.name
                           ORDER BY orders_count DESC
                           """)
            orders = cursor.fetchall()

            print("Количество заказов пользователей")
            for order in orders:
                print(order)
            print("------------")

            return orders

    except psycopg2.Error as e:
        print(f"Ошибка при подсчете заказов: {e}")


def get_products_sorted_by_price(conn):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                           SELECT id, name, price, quantity
                           FROM products
                           ORDER BY price DESC
                           """)

            products = cursor.fetchall()
            print("Продукты по убыванию цены:")
            for product in products:
                print(product)
            print("------------")
            return products

    except psycopg2.Error as e:
        print(f"Ошибка при получении товаров: {e}")


def get_user_order_history(conn, user_id):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                           SELECT orders.id     AS order_id,
                                  orders.created_at,
                                  products.name AS product_name,
                                  products.price,
                                  order_items.quantity
                           FROM orders
                                    INNER JOIN order_items ON orders.id = order_items.order_id
                                    INNER JOIN products ON products.id = order_items.product_id
                           WHERE orders.user_id = %s
                           ORDER BY orders.created_at DESC
                           """, (user_id,))
            orders = cursor.fetchall()
            print("История заказов пользователя:")
            for order in orders:
                print(order)
            print("------------")
            return orders

    except psycopg2.Error as e:
        print(f"Ошибка при получении истории заказов: {e}")


def get_order_statistics(conn):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                           SELECT users.id,
                                  users.name,
                                  COUNT(orders.id)  AS orders_count,
                                  SUM(orders.total) AS total_amount
                           FROM users
                                    LEFT JOIN orders ON users.id = orders.user_id
                           GROUP BY users.id, users.name
                           ORDER BY total_amount DESC
                           """)
            orders = cursor.fetchall()
            print("Статистика заказов пользователей")
            for order in orders:
                print(order)
            print("------------")
            return orders

    except psycopg2.Error as e:
        print(f"Ошибка при получении статистики: {e}")


def get_top_products(conn, limit=5):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                           SELECT products.id,
                                  products.name,
                                  SUM(order_items.quantity) AS total_sold
                           FROM products
                                    INNER JOIN order_items ON products.id = order_items.product_id
                           GROUP BY products.id, products.name
                           ORDER BY total_sold DESC
                           LIMIT %s
                           """, (limit,))
            products = cursor.fetchall()
            print("Популярные товары:")
            for product in products:
                print(product)
            print("------------")
            return products

    except psycopg2.Error as e:
        print(f"Ошибка при получении топ товаров: {e}")


def generate_sales_report(conn, start_date: datetime):
    conn.set_isolation_level(ISOLATION_LEVEL_REPEATABLE_READ)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT SUM(total) FROM orders WHERE created_at >= %s",
                           (start_date,))
            total = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM orders WHERE created_at >= %s",
                           (start_date,))
            count = cursor.fetchone()[0] or 0

            return {"total": total, "count": count}

    except psycopg2.Error as e:
        print(f"шибка при генерации отчета: {e}")


def calculate_total_revenue(conn, start_date, end_date):
    conn.set_isolation_level(ISOLATION_LEVEL_REPEATABLE_READ)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""SELECT COALESCE(SUM(total), 0)
                              FROM orders
                              WHERE created_at BETWEEN %s AND %s""",
                           (start_date, end_date))
            total = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM orders "
                "WHERE created_at BETWEEN %s AND %s",
                (start_date, end_date)
            )
            count = cursor.fetchone()[0]

        return {
            "total": float(total),
            "count": count,
            "average": float(total) / count if count > 0 else 0}

    except psycopg2.Error as e:
        print(f"Ошибка при расчете выручки: {e}")


def critical_financial_operation(conn, from_user_id, to_user_id, amount):
    conn.set_isolation_level(ISOLATION_LEVEL_SERIALIZABLE)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE id = %s FOR UPDATE", (from_user_id,))
            balance = cursor.fetchone()[0]

            if balance < amount:
                raise ValueError("Недостаточно средств")

            cursor.execute(
                "UPDATE users SET balance = balance - %s WHERE id = %s",
                (amount, from_user_id)
            )

            cursor.execute(
                "UPDATE users SET balance = balance + %s WHERE id = %s",
                (amount, to_user_id)
            )
        conn.commit()
        return True

    except psycopg2.Error:
        conn.rollback()
        raise
    except ValueError:
        conn.rollback()
        raise

import time
from src.database.connection import connect_to_db


def measure_query_performance():
    with connect_to_db() as conn:
        with conn.cursor() as cur:
            start_time = time.time()
            cur.execute("SELECT * FROM products WHERE name = %s", ("Ноутбук",))
            result = cur.fetchone()
            time_without_index = time.time() - start_time

            cur.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)")
            conn.commit()

            start_time = time.time()
            cur.execute("SELECT * FROM products WHERE name = %s", ("Ноутбук",))
            result = cur.fetchone()
            time_with_index = time.time() - start_time

            print(f"Поиск товара по имени Без индекса: {time_without_index:.4f} сек")
            print(f"Поиск товара по имени С индексом: {time_with_index:.4f} сек")
            print(f"Поиск товара по имени Ускорение: {time_without_index / time_with_index:.2f}x")

            start_time = time.time()
            cur.execute("SELECT * FROM orders WHERE user_id = %s", (2,))
            result = cur.fetchone()
            time_without_index = time.time() - start_time

            cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)")
            conn.commit()

            start_time = time.time()
            cur.execute("SELECT * FROM orders WHERE user_id = %s", (2,))
            result = cur.fetchone()
            time_with_index = time.time() - start_time

            print(f"Поиск заказа по id пользователя Без индекса: {time_without_index:.4f} сек")
            print(f"Поиск заказа по id пользователя С индексом: {time_with_index:.4f} сек")
            print(f"Поиск заказа по id пользователя Ускорение: {time_without_index / time_with_index:.2f}x")

            start_time = time.time()
            cur.execute("SELECT * FROM users WHERE email = %s", ("dima@example.com",))
            result = cur.fetchone()
            time_without_index = time.time() - start_time

            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
            conn.commit()

            start_time = time.time()
            cur.execute("SELECT * FROM users WHERE email = %s", ("dima@example.com",))
            result = cur.fetchone()
            time_with_index = time.time() - start_time

            print(f"Поиск пользователя по email Без индекса: {time_without_index:.4f} сек")
            print(f"Поиск пользователя по email С индексом: {time_with_index:.4f} сек")
            print(f"Поиск пользователя по email Ускорение: {time_without_index / time_with_index:.2f}x")

measure_query_performance()
