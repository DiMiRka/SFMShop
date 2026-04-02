import psycopg2


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
