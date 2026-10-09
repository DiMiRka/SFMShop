from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from pydantic import BaseModel


StopReason = Literal["end_turn", "tool_use", "max_tokens", "refusal", "other"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class LLMResult:
    stop_reason: StopReason
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_content: Any = None


@dataclass(frozen=True)
class UserMessage:
    text: str


@dataclass(frozen=True)
class AssistantMessage:
    result: LLMResult


@dataclass(frozen=True)
class ToolResultsMessage:
    results: list[ToolResult]


LLMMessage = UserMessage | AssistantMessage | ToolResultsMessage


class LLMClient(Protocol):
    async def complete(
            self,
            system: str,
            messages: list[LLMMessage],
            tools: list[ToolSpec],
            response_schema: type[BaseModel]) -> LLMResult:
        ...

    async def close(self) -> None:
        ...
