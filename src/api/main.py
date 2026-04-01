from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
import uvicorn
from starlette.testclient import TestClient

from src.database.connection import *
from src.schemas import OrderCreate, UserCreate, ProductCreate


app = FastAPI()


@app.get("/products", status_code=200)
async def get_products(limit: int = 10, offset: int = 0):
    try:
        with connect_to_db() as conn:
            return get_all_products_db(conn, limit, offset)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении товаров: {e}")


@app.get("/products/{product_id}", status_code=200)
async def get_product(product_id: int):
    try:
        with connect_to_db() as conn:
            product = get_product_db(conn, product_id)

            if product is None:
                raise HTTPException(status_code=404, detail="Товар не найден")
        return product
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Ошибка при получении товара")


@app.post("/products", status_code=201)
async def create_product(product: ProductCreate):
    try:
        with connect_to_db() as conn:
            product_id = add_product_db(conn, product)
        return {"id": product_id, "message": "Товар добавлен"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при создании товара: {e}")


@app.put("/products/{product_id}", status_code=200)
async def put_product(product_id: int, product: ProductCreate):
    try:
        with connect_to_db() as conn:
            product = update_product_db(conn, product_id, product)

            if product is None:
                raise HTTPException(status_code=404, detail="Товар не найден")

        return {"id": product_id, "message": "Товар обновлен"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при обновлении товара: {e}")


@app.delete("/products/{product_id}", status_code=200)
async def delete_product(product_id: int):
    try:
        with connect_to_db() as conn:
            product = delete_product_db(conn, product_id)

        if product is None:
            raise HTTPException(status_code=404, detail="Товар не найден")

        return {"message": "Товар удален"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении товара: {e}")


@app.get("/users", status_code=200)
async def get_users():
    try:
        with connect_to_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, name, email FROM users")
                users = cursor.fetchall()

            return users
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении пользователей: {e}")


@app.get("/users/{user_id}", status_code=200)
async def get_user(user_id: int):
    try:
        with connect_to_db() as conn:
            user = get_user_by_id_db(conn, user_id)

            if user is None:
                raise HTTPException(status_code=404, detail="Пользователь не найден")

        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении пользователя: {e}")


@app.post("/users", status_code=201)
async def create_new_user(user: UserCreate):
    try:
        with connect_to_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (name, email) VALUES (%s, %s) RETURNING id",
                    (user.name, user.email)
                )
                user_id = cursor.fetchone()[0]

            conn.commit()

        return {
            "id": user_id,
            "name": user.name,
            "email": user.email
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка создания пользователя {e}")


@app.post("/orders", status_code=201)
async def post_order(order: OrderCreate):
    try:
        with connect_to_db() as conn:
            order = create_order_db(conn, order.user_id, order.product_id, order.quantity)
        return order
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при создании заказа: {e}")


def test_api():
    client = TestClient(app)

    response = client.get("/products")
    assert response.status_code == 200
    print("GET /products: OK")
    print("--------------------------------------------")

    response = client.get("/products/5")
    assert response.status_code == 200
    print("GET /products/1: OK")
    print("--------------------------------------------")

    response = client.post("/products",
                           json=ProductCreate(name="Телевизор", price=1000, quantity=2).model_dump())
    assert response.status_code == 201
    print("POST /products: OK")
    print("--------------------------------------------")

    response = client.put("/products/5", json=ProductCreate(name="Монитор", price=1000, quantity=2).model_dump())
    assert response.status_code == 200
    print("PUT /products/5: OK")
    print("--------------------------------------------")

    response = client.get("/users")
    assert response.status_code == 200
    print("GET /users: OK")
    print("--------------------------------------------")

    response = client.get("/users/1")
    assert response.status_code == 200
    print("GET /users/1: OK")
    print("--------------------------------------------")

    response = client.post("/orders", json=OrderCreate(user_id=2, product_id=2, quantity=2).model_dump())
    assert response.status_code == 201
    print("POST /users: OK")


if __name__ == "__main__":
    test_api()
    uvicorn.run("main:app", reload=True)
