from fastapi import FastAPI, HTTPException
import uvicorn

from src.database import (read_db_dependency, write_db_dependency, get_all_products_db, get_product_db,
                          add_product_db, update_product_db, delete_product_db, get_users_db, get_user_by_id_db,
                          create_user_db, create_order_db)
from src.schemas import OrderCreate, UserCreate, ProductCreate, ProductUpdate


app = FastAPI()


@app.get("/products", status_code=200)
async def get_products(db: read_db_dependency, limit: int = 10, offset: int = 0):
    try:
        return await get_all_products_db(db, limit, offset)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении товаров: {e}")


@app.get("/products/{product_id}", status_code=200)
async def get_product(db: read_db_dependency, product_id: int):
    try:
        return await get_product_db(db, product_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Ошибка при получении товара")


@app.post("/products", status_code=201)
async def create_product(db: write_db_dependency, product: ProductCreate):
    try:
        return await add_product_db(db, product)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при создании товара: {e}")


@app.put("/products/{product_id}", status_code=200)
async def put_product(db: write_db_dependency, product_id: int, product: ProductUpdate):
    try:
        return await update_product_db(db, product_id, product)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при обновлении товара: {e}")


@app.delete("/products/{product_id}", status_code=200)
async def delete_product(db: write_db_dependency, product_id: int):
    try:
        return await delete_product_db(db, product_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении товара: {e}")


@app.get("/users", status_code=200)
async def get_users(db: read_db_dependency):
    try:
        return await get_users_db(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении пользователей: {e}")


@app.get("/users/{user_id}", status_code=200)
async def get_user(db: read_db_dependency, user_id: int):
    try:
        return await get_user_by_id_db(db, user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении пользователя: {e}")


@app.post("/users", status_code=201)
async def create_new_user(db: write_db_dependency, user: UserCreate):
    try:
        return await create_user_db(db, user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка создания пользователя {e}")


@app.post("/orders", status_code=201)
async def post_order(db: write_db_dependency, order: OrderCreate):
    try:
        return await create_order_db(db, order)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при создании заказа: {e}")


if __name__ == "__main__":
    # test_api()
    uvicorn.run("main:app", reload=True)
