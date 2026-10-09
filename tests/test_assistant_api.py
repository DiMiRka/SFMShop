import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from limits import parse

from sfmshop.api.main import sfmshop_app as app
from sfmshop.clients.llm import LLMResult
from sfmshop.core import dependencies
from sfmshop.core.config import app_settings
from sfmshop.core.limiter import limiter
from sfmshop.core.exceptions import LLMUnavailableError


client = TestClient(app)

QUESTION = {"message": "найди товары до 5000 в наличии"}


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    limiter.reset()
    monkeypatch.setattr(app.state, "llm_client", None, raising=False)
    yield
    app.dependency_overrides.clear()
    limiter.reset()


class AnswerLLM:
    async def complete(self, system, messages, tools, response_schema):
        return LLMResult(stop_reason="end_turn", text=json.dumps({
            "answer": "Подходящих товаров нет", "product_ids": [], "order_ids": [],
        }))

    async def close(self):
        pass


class UnavailableLLM(AnswerLLM):
    async def complete(self, system, messages, tools, response_schema):
        raise LLMUnavailableError("ИИ-ассистент временно недоступен")


def login():
    async def user():
        return SimpleNamespace(id=1, is_admin=False)

    async def service():
        return MagicMock()

    app.dependency_overrides[dependencies.get_current_user] = user
    app.dependency_overrides[dependencies.get_product_read_service] = service
    app.dependency_overrides[dependencies.get_order_read_service] = service


def test_assistant_requires_token():
    app.state.llm_client = AnswerLLM()

    response = client.post("/v1/assistant", json=QUESTION)

    assert response.status_code == 401


def test_assistant_answers_by_schema():
    login()
    app.state.llm_client = AnswerLLM()

    response = client.post("/v1/assistant", json=QUESTION)

    assert response.status_code == 200
    assert response.json() == {"answer": "Подходящих товаров нет", "product_ids": [], "order_ids": []}


def test_assistant_without_api_key_returns_503():
    login()

    response = client.post("/v1/assistant", json=QUESTION)

    assert response.status_code == 503
    assert response.json() == {"detail": "ИИ-ассистент не настроен"}


def test_assistant_returns_503_when_provider_is_unavailable():
    login()
    app.state.llm_client = UnavailableLLM()

    response = client.post("/v1/assistant", json=QUESTION)

    assert response.status_code == 503
    assert response.json() == {"detail": "ИИ-ассистент временно недоступен"}


@pytest.mark.parametrize("body", [{"message": ""}, {"message": "x" * 1001}, {}])
def test_assistant_rejects_invalid_message(body):
    login()
    app.state.llm_client = AnswerLLM()

    response = client.post("/v1/assistant", json=body)

    assert response.status_code == 422


def test_assistant_is_rate_limited():
    login()
    app.state.llm_client = AnswerLLM()

    allowed = parse(app_settings.rate_limit_assistant).amount

    statuses = [client.post("/v1/assistant", json=QUESTION).status_code for _ in range(allowed + 1)]

    assert statuses == [200] * allowed + [429]


async def token_for(user_id):
    from sfmshop.core.security import create_access_token

    return await create_access_token({"sub": str(user_id)})


@pytest.mark.anyio
async def test_assistant_limit_is_counted_per_user_not_per_ip():
    login()
    app.state.llm_client = AnswerLLM()
    allowed = parse(app_settings.rate_limit_assistant).amount
    first = {"Authorization": f"Bearer {await token_for(1)}"}
    second = {"Authorization": f"Bearer {await token_for(2)}"}

    first_statuses = [client.post("/v1/assistant", json=QUESTION, headers=first).status_code
                      for _ in range(allowed + 1)]
    second_status = client.post("/v1/assistant", json=QUESTION, headers=second).status_code

    assert first_statuses == [200] * allowed + [429]
    assert second_status == 200
