from fastapi import APIRouter, Request, status

from sfmshop.core.config import app_settings
from sfmshop.core.dependencies import assistant_service
from sfmshop.core.limiter import limiter, user_or_ip
from sfmshop.schemas.assistant import AssistantRequest, AssistantResponse

assistant_router = APIRouter(prefix="/assistant", tags=["assistant"])


@assistant_router.post("", summary="Задать вопрос ИИ-ассистенту магазина",
                       response_model=AssistantResponse, status_code=status.HTTP_200_OK)
@limiter.limit(app_settings.rate_limit_assistant, key_func=user_or_ip)
async def ask_assistant(request: Request, service: assistant_service, payload: AssistantRequest):
    return await service.ask(payload.message)
