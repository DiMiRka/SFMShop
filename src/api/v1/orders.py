from fastapi import APIRouter, status, BackgroundTasks
from typing import List


from src.schemas import OrderCreate, OrderResponse
from src.core.dependencies import current_user, order_write_service, order_read_service
from src.services.notifications_service import EmailNotification, send_notification

orders_router = APIRouter(prefix="/orders", tags=['orders'])


@orders_router.get("/", summary="Получить все заказы",
                   response_model=List[OrderResponse], status_code=status.HTTP_200_OK)
async def get_orders(cu: current_user, service: order_read_service, limit: int = 100, offset: int = 0):
    return await service.get_all_orders(limit, offset)


@orders_router.get("/{order_id}", summary="Получить заказ", status_code=status.HTTP_200_OK)
async def get_order(cu: current_user, service: order_read_service, order_id: int):
    return await service.get_order_by_id(order_id)


@orders_router.post("/", summary="Создать новый заказ", status_code=status.HTTP_201_CREATED)
async def post_order(
        cu: current_user,
        service: order_write_service,
        order: OrderCreate,
        background_tasks: BackgroundTasks):

    result = await service.create_order(order)

    background_tasks.add_task(
        send_notification(
            EmailNotification(),
            f"Заказ {result["order_id"]} успешно создан"
        )
    )

    return result


@orders_router.delete("/{order_id}", summary="Удалить заказ", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(cu: current_user, service: order_write_service, order_id: int):
    return await service.delete_order(order_id)
