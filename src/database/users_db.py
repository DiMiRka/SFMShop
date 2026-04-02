import psycopg2
from fastapi import HTTPException
from src.models.exceptions import BusinessLogicError

def create_user_db(conn, name, email, age, balance):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                           INSERT INTO users (name, email, age, balance)
                           VALUES (%s, %s, %s, %s)""", (name, email, age, balance))
        conn.commit()
    except psycopg2.Error as e:
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
        print (balance)
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

            cursor.execute("SELECT * FROM users WHERE id = %s" , (to_user_id,))
            to_user = cursor.fetchone()
            if to_user is None:
                raise HTTPException(status_code=404, detail="Получатель не найден")
            to_balance = to_user.balance + amount

            cursor.execute("UPDATE users SET balance = %s WHERE id = %s", (from_balance, from_user_id))
            cursor.execute("UPDATE users SET balance = %s WHERE id = %s", (to_balance, to_user_id))

        conn.commit()
    except psycopg2.Error as e:
        print(f"Ошибкам при переводе средств: {e}")
