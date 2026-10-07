import json

import anthropic
import httpx2
import pytest
from pydantic import BaseModel, ConfigDict

from src.clients.llm import (AnthropicLLMClient, AssistantMessage, LLMResult, ToolCall, ToolResult,
                             ToolResultsMessage, ToolSpec, UserMessage, create_llm_client)
from src.core.config import AppSettings
from src.models.exceptions import LLMUnavailableError


pytestmark = pytest.mark.anyio


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str


TOOLS = [ToolSpec(
    name="get_product",
    description="Товар по id",
    input_schema={
        "type": "object",
        "properties": {"product_id": {"type": "integer"}},
        "required": ["product_id"],
        "additionalProperties": False,
    },
)]


def message_body(content, stop_reason="end_turn"):
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(json.loads(request.content))
        status, body = self.responses.pop(0)
        return httpx2.Response(status, json=body, headers={"retry-after-ms": "1"})


def make_client(transport, max_retries=2):
    return AnthropicLLMClient(
        api_key="test-key",
        model="claude-opus-5-5",
        max_tokens=512,
        timeout=5,
        max_retries=max_retries,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(transport)),
    )


ERROR_BODY = {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}


async def test_rate_limit_is_retried_and_single_result_returned():
    transport = Transport([
        (429, ERROR_BODY),
        (200, message_body([{"type": "text", "text": '{"answer": "ok"}'}])),
    ])
    client = make_client(transport)

    result = await client.complete("system", [UserMessage("привет")], TOOLS, Answer)

    assert len(transport.requests) == 2
    assert result.stop_reason == "end_turn"
    assert result.text == '{"answer": "ok"}'
    assert result.tool_calls == []
    await client.close()


async def test_server_errors_after_retries_raise_llm_unavailable(log_messages):
    transport = Transport([(500, ERROR_BODY), (500, ERROR_BODY)])
    client = make_client(transport, max_retries=1)

    with pytest.raises(LLMUnavailableError):
        await client.complete("system", [UserMessage("привет")], TOOLS, Answer)

    assert len(transport.requests) == 2
    assert "llm_unavailable" in log_messages


async def test_connection_error_raises_llm_unavailable():
    def transport(request):
        raise httpx2.ConnectError("network down")

    client = make_client(transport, max_retries=0)

    with pytest.raises(LLMUnavailableError):
        await client.complete("system", [UserMessage("привет")], TOOLS, Answer)


async def test_request_shape_and_tool_round_trip():
    transport = Transport([
        (200, message_body([
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "tool_use", "id": "toolu_1", "name": "get_product", "input": {"product_id": 7}},
        ], stop_reason="tool_use")),
        (200, message_body([{"type": "text", "text": '{"answer": "done"}'}])),
    ])
    client = make_client(transport)

    first = await client.complete("system prompt", [UserMessage("покажи товар 7")], TOOLS, Answer)

    assert first.stop_reason == "tool_use"
    assert first.tool_calls == [ToolCall(id="toolu_1", name="get_product", arguments={"product_id": 7})]

    messages = [
        UserMessage("покажи товар 7"),
        AssistantMessage(first),
        ToolResultsMessage([ToolResult("toolu_1", '{"error": "Товар не найден"}', is_error=True)]),
    ]
    second = await client.complete("system prompt", messages, TOOLS, Answer)

    assert second.text == '{"answer": "done"}'

    request = transport.requests[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["max_tokens"] == 512
    assert request["system"] == "system prompt"
    assert request["messages"] == [{"role": "user", "content": "покажи товар 7"}]
    assert request["tools"][0]["name"] == "get_product"
    assert request["tools"][0]["strict"] is True
    schema = request["output_config"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["answer"]
    assert request["fallbacks"] == "default"

    follow_up = transport.requests[1]["messages"]
    assert follow_up[1]["role"] == "assistant"
    assert [block["type"] for block in follow_up[1]["content"]] == ["thinking", "tool_use"]
    assert follow_up[2] == {
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": "toolu_1",
            "content": '{"error": "Товар не найден"}',
            "is_error": True,
        }],
    }


async def test_refusal_and_unknown_stop_reasons_are_normalized():
    transport = Transport([
        (200, message_body([], stop_reason="refusal")),
        (200, message_body([], stop_reason="pause_turn")),
    ])
    client = make_client(transport)

    assert (await client.complete("s", [UserMessage("x")], TOOLS, Answer)).stop_reason == "refusal"
    assert (await client.complete("s", [UserMessage("x")], TOOLS, Answer)).stop_reason == "other"


def test_assistant_message_without_raw_content_is_rebuilt_from_tool_calls():
    result = LLMResult(
        stop_reason="tool_use",
        text="Ищу",
        tool_calls=[ToolCall(id="t1", name="get_product", arguments={"product_id": 1})],
    )

    assert AnthropicLLMClient._to_param(AssistantMessage(result)) == {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Ищу"},
            {"type": "tool_use", "id": "t1", "name": "get_product", "input": {"product_id": 1}},
        ],
    }

    with pytest.raises(TypeError):
        AnthropicLLMClient._to_param(object())


def test_create_llm_client_by_provider_setting():
    assert create_llm_client(AppSettings(_env_file=None, anthropic_api_key=None)) is None
    assert isinstance(create_llm_client(AppSettings(_env_file=None, anthropic_api_key="key")), AnthropicLLMClient)

    with pytest.raises(ValueError):
        create_llm_client(AppSettings(_env_file=None, llm_provider="unknown"))
