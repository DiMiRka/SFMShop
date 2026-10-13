import json
from typing import Any, cast

import openai
from pydantic import BaseModel

from sfmshop.clients.llm.base import (AssistantMessage, LLMMessage, LLMResult, StopReason, ToolCall, ToolResultsMessage,
                                      ToolSpec, UserMessage)
from sfmshop.core.exceptions import LLMUnavailableError
from sfmshop.services.log_service import log_service


STRICT_KEYWORDS = frozenset({
    "type", "description", "properties", "required", "additionalProperties", "items", "anyOf", "enum", "const",
    "$defs", "$ref", "minimum", "maximum",
})
DROPPED_KEYWORDS = frozenset({"title", "default"})


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    hints: list[str] = []

    for key, value in schema.items():
        if key == "properties":
            result[key] = {name: strict_schema(prop) for name, prop in value.items()}
        elif key == "$defs":
            result[key] = {name: strict_schema(definition) for name, definition in value.items()}
        elif key == "items" and isinstance(value, dict):
            result[key] = strict_schema(value)
        elif key == "anyOf":
            result[key] = [strict_schema(variant) for variant in value]
        elif key in STRICT_KEYWORDS:
            result[key] = value
        elif key == "default" and value is not None:
            hints.append(f"по умолчанию {json.dumps(value, ensure_ascii=False)}")
        elif key not in DROPPED_KEYWORDS:
            hints.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")

    if "properties" in result:
        result["required"] = list(result["properties"])
        result["additionalProperties"] = False
    if hints:
        description = result.get("description")
        result["description"] = f"{description} ({', '.join(hints)})" if description else ", ".join(hints)
    return result


class OpenAILLMClient:
    def __init__(
            self,
            api_key: str,
            model: str,
            max_tokens: int,
            timeout: float,
            max_retries: int,
            http_client: openai.DefaultAsyncHttpxClient | None = None):
        self.model = model
        self.max_tokens = max_tokens
        self.client = openai.AsyncOpenAI(
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
        )

    async def complete(
            self,
            system: str,
            messages: list[LLMMessage],
            tools: list[ToolSpec],
            response_schema: type[BaseModel]) -> LLMResult:
        try:
            response = await self.client.responses.create(
                model=self.model,
                instructions=system,
                input=cast(Any, [item for message in messages for item in self._to_input(message)]),
                tools=cast(Any, [
                    {
                        "type": "function",
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": strict_schema(tool.input_schema),
                        "strict": True,
                    }
                    for tool in tools
                ]),
                text=cast(Any, {
                    "format": {
                        "type": "json_schema",
                        "name": response_schema.__name__,
                        "schema": strict_schema(response_schema.model_json_schema()),
                        "strict": True,
                    },
                }),
                max_output_tokens=self.max_tokens,
                store=False,
                include=["reasoning.encrypted_content"],
            )
        except openai.APIConnectionError as exc:
            log_service.warning("llm_unavailable", provider="openai", reason=type(exc).__name__)
            raise LLMUnavailableError("ИИ-ассистент временно недоступен") from exc
        except openai.APIStatusError as exc:
            log_service.warning("llm_unavailable", provider="openai", status_code=exc.status_code,
                                request_id=exc.request_id)
            raise LLMUnavailableError("ИИ-ассистент временно недоступен") from exc

        tool_calls = [
            ToolCall(id=item.call_id, name=item.name, arguments=json.loads(item.arguments or "{}"))
            for item in response.output
            if item.type == "function_call"
        ]
        refused = any(
            content.type == "refusal"
            for item in response.output if item.type == "message"
            for content in item.content
        )

        stop_reason: StopReason
        if tool_calls:
            stop_reason = "tool_use"
        elif refused:
            stop_reason = "refusal"
        elif response.status == "incomplete":
            reason = response.incomplete_details.reason if response.incomplete_details else None
            stop_reason = "max_tokens" if reason == "max_output_tokens" else "other"
        else:
            stop_reason = "end_turn"

        return LLMResult(
            stop_reason=stop_reason,
            text=response.output_text,
            tool_calls=tool_calls,
            raw_content=[item.model_dump(exclude_none=True) for item in response.output],
        )

    async def close(self) -> None:
        await self.client.close()

    @staticmethod
    def _to_input(message: LLMMessage) -> list[dict[str, Any]]:
        if isinstance(message, UserMessage):
            return [{"role": "user", "content": message.text}]

        if isinstance(message, AssistantMessage):
            result = message.result
            if result.raw_content is not None:
                return list(result.raw_content)

            items: list[dict[str, Any]] = []
            if result.text:
                items.append({"role": "assistant", "content": result.text})
            items += [
                {"type": "function_call", "call_id": call.id, "name": call.name,
                 "arguments": json.dumps(call.arguments, ensure_ascii=False)}
                for call in result.tool_calls
            ]
            return items

        if isinstance(message, ToolResultsMessage):
            return [
                {"type": "function_call_output", "call_id": result.tool_call_id, "output": result.content}
                for result in message.results
            ]

        raise TypeError(f"Unsupported message type: {type(message).__name__}")
