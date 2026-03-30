import psycopg2


def get_orders_with_products(conn, user_id):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    orders.id AS order_id,
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
            print("------------")

    except psycopg2.Error as e:
        print(f"Ошибка при получении товаров пользователя: {e}")


def get_orders_count_by_users(conn):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    users.id,
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
                SELECT 
                    orders.id AS order_id,
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
                SELECT 
                    users.id,
                    users.name,
                    COUNT(orders.id) AS orders_count,
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
                SELECT 
                    products.id,
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
            return cursor.fetchall()

    except psycopg2.Error as e:
        print(f"Ошибка при получении топ товаров: {e}")
