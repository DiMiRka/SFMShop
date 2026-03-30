from fastapi import FastAPI, HTTPException
import uvicorn
from src.database.connection import *
from src.schemas import OrderCreate, UserCreate


app = FastAPI()


@app.get("/products")
async def get_products(limit: int = 10, offset: int = 0):
    with connect_to_db() as conn:
        return get_all_products(conn, limit, offset)


@app.get("/products/{product_id}")
async def get_product(product_id: int):
    with connect_to_db() as conn:
        product = get_product_db(conn, product_id)

        if product is None:
            raise HTTPException(status_code=404, detail="Товар не найден")
        return product


@app.post("/orders", status_code=201)
async def post_order(order: OrderCreate):
    with connect_to_db() as conn:
        order = create_order(conn, order.user_id, order.product_id, order.quantity)
        return order


@app.get("/users")
async def get_users():
    with connect_to_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name, email FROM users")
            users = cursor.fetchall()

            return users


@app.get("/users/{user_id}")
async def get_user(user_id: int):
    with connect_to_db() as conn:
        user = get_user_by_id(conn, user_id)

        if user is None:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        return user


@app.post("/users", status_code=201)
async def create_new_user(user: UserCreate):
    with connect_to_db() as conn:
        try:
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

        except Exception:
            conn.rollback()
            raise HTTPException(status_code=500, detail="Ошибка создания пользователя")


if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
