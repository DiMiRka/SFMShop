import psycopg2


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
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
        return cursor.fetchone()


def add_product(conn, name, price, quantity):
    try:
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO products (name, price, quantity) VALUES (%s, %s, %s)", (name, price, quantity))
            print(f"Товар добавлен: {name}, {price}, {quantity}")
            conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
        print(f"Ошибка при добавлении товара: {e}")


def get_all_products(conn, limit: int, offset: int):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM products LIMIT %s OFFSET %s",
                           (limit, offset))
            products = cursor.fetchall()
        print("Все товары:")
        for product in products:
            print(product)
        print("------------")

        return products
    except psycopg2.Error as e:
        print(f"Ошибка при получении товаров: {e}")


def update_product_price(conn, product_id, new_price):
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE products SET price = %s WHERE id = %s",
                           (new_price, product_id))
        print(f"Цена обновлена: {new_price}")
        conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
        print(f"Ошибка при обновлении цены: {e}")


def create_user(conn, name, email):
    try:
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO users (name, email) VALUES (%s, %s)", (name, email))
        print(f"Пользователь добавлен: {name}, {email}")
        print("------------")
        conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
        print(f"Ошибка при создании пользователя: {e}")


def get_user_by_id(conn, user_id):
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


def delete_order(conn, order_id):
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


def create_order(conn, user_id, product_id, quantity):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT price FROM products WHERE id = %s", (product_id,))
            product = cursor.fetchone()
            total = product[0] * quantity

            cursor.execute(
                "INSERT INTO orders (user_id, total) VALUES (%s, %s) RETURNING id",
                (user_id, total)
            )
            order_id = cursor.fetchone()[0]

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


def get_user_orders(conn, user_id):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM orders WHERE user_id = %s", (user_id,))
            orders = cursor.fetchall()
        print(f"Все заказы пользователя {user_id}")
        for order in orders:
            print(order)
    except psycopg2.Error as e:
        print(f"Ошибка при получении заказов: {e}")

