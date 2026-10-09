from typing import Any
import anthropic
from pydantic import BaseModel

from src.clients.llm.base import (AssistantMessage, LLMMessage, LLMResult, StopReason, ToolCall, ToolResultsMessage,
                                  ToolSpec, UserMessage)
from src.core.exceptions import LLMUnavailableError
from src.services.log_service import log_service


FALLBACK_BETA = "server-side-fallback-2026-07-01"

STOP_REASONS: dict[str, StopReason] = {
    "end_turn": "end_turn",
    "stop_sequence": "end_turn",
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
    "refusal": "refusal",
}


class AnthropicLLMClient:
    def __init__(
            self,
            api_key: str,
            model: str,
            max_tokens: int,
            timeout: float,
            max_retries: int,
            http_client: anthropic.DefaultAsyncHttpxClient | None = None):
        self.model = model
        self.max_tokens = max_tokens
        self.client = anthropic.AsyncAnthropic(
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
            response = await self.client.beta.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[self._to_param(message) for message in messages],
                tools=[
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": anthropic.transform_schema(tool.input_schema),
                        "strict": True,
                    }
                    for tool in tools
                ],
                output_config={
                    "format": {"type": "json_schema", "schema": anthropic.transform_schema(response_schema)},
                },
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.APIConnectionError as exc:
            log_service.warning("llm_unavailable", provider="anthropic", reason=type(exc).__name__)
            raise LLMUnavailableError("ИИ-ассистент временно недоступен") from exc
        except anthropic.APIStatusError as exc:
            log_service.warning("llm_unavailable", provider="anthropic", status_code=exc.status_code,
                                request_id=exc.request_id)
            raise LLMUnavailableError("ИИ-ассистент временно недоступен") from exc

        text = "".join(block.text for block in response.content if block.type == "text")
        tool_calls = [
            ToolCall(id=block.id, name=block.name, arguments=dict(block.input))
            for block in response.content
            if block.type == "tool_use"
        ]

        return LLMResult(
            stop_reason=STOP_REASONS.get(response.stop_reason or "", "other"),
            text=text,
            tool_calls=tool_calls,
            raw_content=response.content,
        )

    @staticmethod
    def _to_param(message: LLMMessage) -> Any:
        if isinstance(message, UserMessage):
            return {"role": "user", "content": message.text}

        if isinstance(message, AssistantMessage):
            result = message.result
            if result.raw_content is not None:
                return {"role": "assistant", "content": result.raw_content}

            content: list[dict[str, Any]] = [{"type": "text", "text": result.text}] if result.text else []
            content += [
                {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
                for call in result.tool_calls
            ]
            return {"role": "assistant", "content": content}

        if isinstance(message, ToolResultsMessage):
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": result.tool_call_id,
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                    for result in message.results
                ],
            }

        raise TypeError(f"Unsupported message type: {type(message).__name__}")

    async def close(self) -> None:
        await self.client.close()
