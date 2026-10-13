import json

import httpx2
import openai
import pytest
from pydantic import BaseModel, ConfigDict

from sfmshop.clients.llm import (AnthropicLLMClient, AssistantMessage, OpenAILLMClient, ToolCall, ToolResult,
                                 ToolResultsMessage, ToolSpec, UserMessage, create_llm_client)
from sfmshop.clients.llm.openai import strict_schema
from sfmshop.core.config import AppSettings
from sfmshop.core.exceptions import LLMUnavailableError
from sfmshop.schemas.assistant import AssistantResponse, SearchProductsArgs
from tests.test_assistant_service import SearchRepo, make_service


pytestmark = pytest.mark.anyio


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str


TOOLS = [ToolSpec(
    name="get_product",
    description="Товар по id",
    input_schema={
        "type": "object",
        "properties": {"product_id": {"type": "integer", "minimum": 1, "title": "Product Id"}},
        "required": ["product_id"],
        "additionalProperties": False,
    },
)]


def response_body(output, status="completed", incomplete_reason=None):
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 1760000000,
        "model": "gpt-5.5",
        "status": status,
        "incomplete_details": {"reason": incomplete_reason} if incomplete_reason else None,
        "output": output,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
    }


def text_item(text):
    return {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}]}


def call_item(name, arguments, call_id="call_1"):
    return {"type": "function_call", "id": "fc_1", "call_id": call_id, "name": name,
            "arguments": json.dumps(arguments), "status": "completed"}


REASONING = {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "opaque"}
ERROR_BODY = {"error": {"message": "slow down", "type": "rate_limit_error", "code": None, "param": None}}


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(json.loads(request.content))
        status, body = self.responses.pop(0)
        return httpx2.Response(status, json=body, headers={"retry-after-ms": "1"})


def make_client(transport, max_retries=2):
    return OpenAILLMClient(
        api_key="test-key",
        model="gpt-5.5",
        max_tokens=512,
        timeout=5,
        max_retries=max_retries,
        http_client=openai.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(transport)),
    )


def walk(schema):
    yield schema
    for value in schema.values():
        if isinstance(value, dict):
            yield from walk(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield from walk(item)


def test_strict_schema_requires_every_field_and_moves_unsupported_constraints_to_description():
    schema = strict_schema(SearchProductsArgs.model_json_schema())

    objects = [node for node in walk(schema) if "properties" in node]
    assert objects and all(node["required"] == list(node["properties"]) for node in objects)
    assert all(node["additionalProperties"] is False for node in objects)
    assert not any(key in node for node in walk(schema) for key in ("title", "default", "maxLength", "pattern"))

    props = schema["properties"]
    assert props["limit"]["minimum"] == 1 and props["limit"]["maximum"] == 20
    assert "по умолчанию 10" in props["limit"]["description"]
    string_variant, null_variant = props["query"]["anyOf"]
    assert string_variant == {"type": "string", "description": "maxLength: 100"}
    assert null_variant == {"type": "null"}


async def test_request_shape_and_tool_round_trip():
    transport = Transport([
        (200, response_body([REASONING, call_item("get_product", {"product_id": 7})])),
        (200, response_body([text_item('{"answer": "done"}')])),
    ])
    client = make_client(transport)

    first = await client.complete("system prompt", [UserMessage("покажи товар 7")], TOOLS, Answer)

    assert first.stop_reason == "tool_use"
    assert first.tool_calls == [ToolCall(id="call_1", name="get_product", arguments={"product_id": 7})]

    messages = [
        UserMessage("покажи товар 7"),
        AssistantMessage(first),
        ToolResultsMessage([ToolResult("call_1", '{"error": "Товар не найден"}', is_error=True)]),
    ]
    second = await client.complete("system prompt", messages, TOOLS, Answer)

    assert second.stop_reason == "end_turn" and second.text == '{"answer": "done"}'

    request = transport.requests[0]
    assert request["model"] == "gpt-5.5"
    assert request["instructions"] == "system prompt"
    assert request["input"] == [{"role": "user", "content": "покажи товар 7"}]
    assert request["max_output_tokens"] == 512
    assert request["store"] is False
    assert request["include"] == ["reasoning.encrypted_content"]
    [tool] = request["tools"]
    assert tool == {"type": "function", "name": "get_product", "description": "Товар по id", "strict": True,
                    "parameters": {"type": "object", "properties": {"product_id": {"type": "integer", "minimum": 1}},
                                   "required": ["product_id"], "additionalProperties": False}}
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["name"] == "Answer" and request["text"]["format"]["strict"] is True

    history = transport.requests[1]["input"]
    assert history[0] == {"role": "user", "content": "покажи товар 7"}
    assert history[1]["type"] == "reasoning" and history[1]["encrypted_content"] == "opaque"
    assert history[2]["type"] == "function_call" and history[2]["call_id"] == "call_1"
    assert history[3] == {"type": "function_call_output", "call_id": "call_1",
                          "output": '{"error": "Товар не найден"}'}


async def test_history_without_raw_output_is_rebuilt_from_neutral_types():
    transport = Transport([(200, response_body([text_item('{"answer": "ok"}')]))])
    client = make_client(transport)
    previous = (await make_client(Transport([
        (200, response_body([call_item("get_product", {"product_id": 7})])),
    ])).complete("s", [UserMessage("q")], TOOLS, Answer))
    rebuilt = AssistantMessage(type(previous)(stop_reason="tool_use", text="", tool_calls=previous.tool_calls))

    await client.complete("s", [UserMessage("q"), rebuilt], TOOLS, Answer)

    assert transport.requests[0]["input"][1] == {
        "type": "function_call", "call_id": "call_1", "name": "get_product", "arguments": '{"product_id": 7}',
    }


@pytest.mark.parametrize("body, stop_reason", [
    (response_body([{"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
                     "content": [{"type": "refusal", "refusal": "Не могу помочь"}]}]), "refusal"),
    (response_body([text_item('{"answ')], status="incomplete", incomplete_reason="max_output_tokens"), "max_tokens"),
    (response_body([text_item("")], status="incomplete", incomplete_reason="content_filter"), "other"),
])
async def test_refusal_and_incomplete_answers_map_to_neutral_stop_reasons(body, stop_reason):
    client = make_client(Transport([(200, body)]))

    result = await client.complete("system", [UserMessage("привет")], TOOLS, Answer)

    assert result.stop_reason == stop_reason


async def test_rate_limit_is_retried_and_single_result_returned():
    transport = Transport([(429, ERROR_BODY), (200, response_body([text_item('{"answer": "ok"}')]))])

    result = await make_client(transport).complete("system", [UserMessage("привет")], TOOLS, Answer)

    assert len(transport.requests) == 2
    assert result.stop_reason == "end_turn" and result.tool_calls == []


async def test_server_errors_after_retries_raise_llm_unavailable(log_messages):
    transport = Transport([(500, ERROR_BODY), (500, ERROR_BODY)])

    with pytest.raises(LLMUnavailableError):
        await make_client(transport, max_retries=1).complete("system", [UserMessage("привет")], TOOLS, Answer)

    assert len(transport.requests) == 2
    assert "llm_unavailable" in log_messages


async def test_connection_error_raises_llm_unavailable():
    def transport(request):
        raise httpx2.ConnectError("network down")

    with pytest.raises(LLMUnavailableError):
        await make_client(transport, max_retries=0).complete("system", [UserMessage("привет")], TOOLS, Answer)


async def test_assistant_runs_full_tool_loop_on_openai_without_changes():
    transport = Transport([
        (200, response_body([call_item("search_products", {
            "query": "key", "min_price": None, "max_price": "5000", "in_stock": True, "limit": 5,
        })])),
        (200, response_body([text_item(json.dumps({
            "answer": "Нашёл клавиатуру за 4500 ₽", "product_ids": [3], "order_ids": [],
        }))])),
    ])
    repo = SearchRepo()

    response = await make_service(make_client(transport), product_rep=repo).ask("найди клавиатуры до 5000")

    assert response == AssistantResponse(answer="Нашёл клавиатуру за 4500 ₽", product_ids=[3], order_ids=[])
    assert repo.filters["name_query"] == "key" and repo.filters["in_stock"] is True
    tool_output = transport.requests[1]["input"][-1]
    assert tool_output["type"] == "function_call_output" and tool_output["call_id"] == "call_1"
    assert json.loads(tool_output["output"])[0]["id"] == 3
    assert transport.requests[0]["text"]["format"]["name"] == "AssistantResponse"


def test_provider_and_default_model_come_from_settings():
    openai_client = create_llm_client(AppSettings(_env_file=None, llm_provider="openai", openai_api_key="key"))
    assert isinstance(openai_client, OpenAILLMClient) and openai_client.model == "gpt-5.5"

    custom = create_llm_client(AppSettings(_env_file=None, llm_provider="openai", openai_api_key="key",
                                           llm_model="gpt-5.4-mini"))
    assert isinstance(custom, OpenAILLMClient) and custom.model == "gpt-5.4-mini"

    anthropic_client = create_llm_client(AppSettings(_env_file=None, anthropic_api_key="key"))
    assert isinstance(anthropic_client, AnthropicLLMClient) and anthropic_client.model == "claude-opus-5-5"

    assert create_llm_client(AppSettings(_env_file=None, llm_provider="openai", openai_api_key=None)) is None


def test_strict_schema_closes_nested_objects_from_plain_models():
    class Item(BaseModel):
        product_id: int
        note: str | None = None

    class Basket(BaseModel):
        items: list[Item]

    schema = strict_schema(Basket.model_json_schema())
    item = schema["$defs"]["Item"]

    assert schema["additionalProperties"] is False and schema["required"] == ["items"]
    assert item["additionalProperties"] is False and item["required"] == ["product_id", "note"]
