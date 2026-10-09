from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse

from payment_service.payment.api.dependencies import payment_service
from payment_service.payment.core.security import require_service_token
from payment_service.payment.database.models import PaymentStatus
from payment_service.payment.schemas import ChargeRequest, IdempotencyKey, PaymentDeclined, PaymentDetail, PaymentShort

payments_router = APIRouter(prefix="/payments", tags=["payments"], dependencies=[Depends(require_service_token)])


@payments_router.post(
    "", summary="Списать деньги за заказ", response_model=PaymentShort, status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"model": PaymentDeclined}},
)
async def charge(request: ChargeRequest, idempotency_key: IdempotencyKey, service: payment_service, response: Response):
    payment, created = await service.charge(idempotency_key, request)

    if payment.status == PaymentStatus.FAILED:
        body = PaymentDeclined.model_validate(payment, from_attributes=True)
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=body.model_dump(mode="json"))

    if not created:
        response.status_code = status.HTTP_200_OK
    return payment


@payments_router.get("/{payment_id}", summary="Получить платёж", response_model=PaymentDetail)
async def get_payment(payment_id: int, service: payment_service):
    return await service.get_payment(payment_id)


@payments_router.post("/{payment_id}/refund", summary="Вернуть деньги за платёж", response_model=PaymentDetail)
async def refund(payment_id: int, service: payment_service):
    return await service.refund(payment_id)
