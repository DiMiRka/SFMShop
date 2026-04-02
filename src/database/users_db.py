import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_READ_COMMITTED, ISOLATION_LEVEL_REPEATABLE_READ, \
    ISOLATION_LEVEL_SERIALIZABLE
from fastapi import HTTPException
from src.models.exceptions import BusinessLogicError


def create_user_db(conn, name, email, age, balance):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                           INSERT INTO users (name, email, age, balance)
                           VALUES (%s, %s, %s, %s)""", (name, email, age, balance))
        conn.commit()
    except psycopg2.Error:
        conn.rollback()


def get_user_by_id_db(conn, user_id):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()

            return user
    except psycopg2.Error as e:
        print(f"Ошибка при получении пользователя: {e}")
        return None


def get_user_balance(conn, user_id):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
            balance = cursor.fetchone()
        print(balance)
        return balance
    except psycopg2.Error as e:
        print(f"Ошибка при получении баланса пользователя: {e}")


def get_user_email(conn, user_id):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT email FROM users WHERE id = %s", (user_id,))
            email = cursor.fetchone()
        return email
    except psycopg2.Error as e:
        print(f"Ошибка при получении Email пользователя: {e}")


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


def transfer_money(conn, from_user_id: int, to_user_id: int, amount: int):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (from_user_id,))
            from_user = cursor.fetchone()
            if from_user is None:
                raise HTTPException(status_code=404, detail="Отправитель не найден")
            from_balance = from_user.balance - amount
            if from_balance < 0:
                conn.rollback()
                raise BusinessLogicError("Недостаточно средств на балансе")

            cursor.execute("SELECT * FROM users WHERE id = %s", (to_user_id,))
            to_user = cursor.fetchone()
            if to_user is None:
                raise HTTPException(status_code=404, detail="Получатель не найден")
            to_balance = to_user.balance + amount

            cursor.execute("UPDATE users SET balance = %s WHERE id = %s", (from_balance, from_user_id))
            cursor.execute("UPDATE users SET balance = %s WHERE id = %s", (to_balance, to_user_id))

        conn.commit()
    except psycopg2.Error as e:
        print(f"Ошибкам при переводе средств: {e}")


def read_user_balance(conn, user_id):
    conn.set_isolation_level(ISOLATION_LEVEL_READ_COMMITTED)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
            balance = cursor.fetchone()
        return balance
    except psycopg2.Error as e:
        print(f"Ошибка при получении баланса пользователя: {e}")


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
        conn.rollback()
        print(f"Ошибка при расчете выручки: {e}")


def critical_financial_operation(conn, from_user_id, to_user_id, amount):
    conn.set_isolation_level(ISOLATION_LEVEL_SERIALIZABLE)
    try:
        with conn.cursor() as cur:
            # Проверка баланса
            cur.execute("SELECT balance FROM users WHERE id = %s", (from_user_id,))
            balance = cur.fetchone()[0]

            if balance < amount:
                raise ValueError("Недостаточно средств")

            # Списание
            cur.execute(
                "UPDATE users SET balance = balance - %s WHERE id = %s",
                (amount, from_user_id)
            )

            # Зачисление
            cur.execute(
                "UPDATE users SET balance = balance + %s WHERE id = %s",
                (amount, to_user_id)
            )
            return True

    except psycopg2.Error:
        conn.rollback()
        raise
    except ValueError:
        conn.rollback()
        raise
