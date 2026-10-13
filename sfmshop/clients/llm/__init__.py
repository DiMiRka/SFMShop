from collections.abc import Callable

from sfmshop.clients.llm.anthropic import AnthropicLLMClient
from sfmshop.clients.llm.openai import OpenAILLMClient
from sfmshop.clients.llm.base import (AssistantMessage, LLMClient, LLMMessage, LLMResult, ToolCall, ToolResult,
                                  ToolResultsMessage, ToolSpec, UserMessage)
from sfmshop.core.config import AppSettings


DEFAULT_MODELS = {
    "anthropic": "claude-opus-5-5",
    "openai": "gpt-5.5",
}


def build_anthropic_client(settings: AppSettings) -> LLMClient | None:
    if not settings.anthropic_api_key:
        return None

    return AnthropicLLMClient(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model or DEFAULT_MODELS["anthropic"],
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
    )


def build_openai_client(settings: AppSettings) -> LLMClient | None:
    if not settings.openai_api_key:
        return None

    return OpenAILLMClient(
        api_key=settings.openai_api_key,
        model=settings.llm_model or DEFAULT_MODELS["openai"],
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
    )


LLM_PROVIDERS: dict[str, Callable[[AppSettings], LLMClient | None]] = {
    "anthropic": build_anthropic_client,
    "openai": build_openai_client,
}


def create_llm_client(settings: AppSettings) -> LLMClient | None:
    factory = LLM_PROVIDERS.get(settings.llm_provider)
    if factory is None:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")

    return factory(settings)


__all__ = [
    'AnthropicLLMClient',
    'OpenAILLMClient',
    'AssistantMessage',
    'LLMClient',
    'LLMMessage',
    'LLMResult',
    'ToolCall',
    'ToolResult',
    'ToolResultsMessage',
    'ToolSpec',
    'UserMessage',
    'LLM_PROVIDERS',
    'create_llm_client',
]
