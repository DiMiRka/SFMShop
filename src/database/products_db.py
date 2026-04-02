import psycopg2
from fastapi import HTTPException
from src.models import Product
from src.schemas import ProductCreate


def get_product_db(conn, product_id: int):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
            product_db = cursor.fetchone()
            product = Product(product_db[1], product_db[2], product_db[3])
            product.id = product_db[0]
            if product_db is None:
                raise HTTPException(status_code=404, detail="Товар не найден")
            return product_db
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
                raise HTTPException(status_code=404, detail="Товар не найден")

            cursor.execute("UPDATE products "
                           "SET name = %s, price = %s, quantity = %s "
                           "WHERE id = %s",
                           (product.name, product.price, product.quantity, product_id))
            conn.commit()
            return {"id": product_id, "message": "Товар обновлен"}
    except psycopg2.Error as e:
        print(f"Ошибка при обновлении товара: {e}")


def delete_product_db(conn, product_id):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
            product = cursor.fetchone()
            if product is None:
                raise HTTPException(status_code=404, detail="Товар не найден")

            cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
        conn.commit()
        return {"id": product_id, "message": "Товар удален"}
    except psycopg2.Error as e:
        print(f"Ошибка при удалении товара: {e}")


def update_product_price_db(conn, product_id, new_price):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
            product = cursor.fetchone()
            if product is None:
                raise HTTPException(status_code=404, detail="Товар не найден")

            cursor.execute("UPDATE products SET price = %s WHERE id = %s",
                           (new_price, product_id))
        conn.commit()
        return {"id": product_id, "message": "Стоимость обновлена"}
    except psycopg2.Error as e:
        conn.rollback()
        print(f"Ошибка при обновлении цены: {e}")
