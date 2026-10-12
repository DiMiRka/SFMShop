from fastapi import APIRouter, Depends

from payment.api.dependencies import payment_service
from payment.core.security import require_service_token
from payment.schemas import IdempotencyKey, TopUpRequest, WalletResponse

wallets_router = APIRouter(prefix="/wallets", tags=["wallets"], dependencies=[Depends(require_service_token)])


@wallets_router.get("/{user_id}", summary="Баланс пользователя", response_model=WalletResponse)
async def get_wallet(user_id: int, service: payment_service):
    return WalletResponse(user_id=user_id, balance=await service.get_balance(user_id))


@wallets_router.post("/{user_id}/top-up", summary="Пополнить баланс", response_model=WalletResponse)
async def top_up(user_id: int, request: TopUpRequest, idempotency_key: IdempotencyKey, service: payment_service):
    return await service.top_up(idempotency_key, user_id, request.amount)
