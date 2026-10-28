from collections.abc import Callable

from sfmshop.clients.embeddings.base import EmbeddingClient
from sfmshop.clients.embeddings.openai import OpenAIEmbeddingClient
from sfmshop.core.config import AppSettings
from sfmshop.database.models import EMBEDDING_DIMENSIONS


def build_openai_embedding_client(settings: AppSettings) -> EmbeddingClient | None:
    if not settings.openai_api_key:
        return None

    return OpenAIEmbeddingClient(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
        usd_per_million_tokens=settings.embedding_usd_per_million_tokens,
        timeout=settings.embedding_timeout,
        max_retries=settings.embedding_max_retries,
    )


EMBEDDING_PROVIDERS: dict[str, Callable[[AppSettings], EmbeddingClient | None]] = {
    "openai": build_openai_embedding_client,
}


def create_embedding_client(settings: AppSettings) -> EmbeddingClient | None:
    factory = EMBEDDING_PROVIDERS.get(settings.embedding_provider)
    if factory is None:
        raise ValueError(f"Unknown embedding provider: {settings.embedding_provider}")
    if settings.embedding_dimensions != EMBEDDING_DIMENSIONS:
        raise ValueError(f"EMBEDDING_DIMENSIONS={settings.embedding_dimensions}, "
                         f"а колонка product_embeddings.embedding рассчитана на {EMBEDDING_DIMENSIONS}")

    return factory(settings)


__all__ = [
    'EmbeddingClient',
    'OpenAIEmbeddingClient',
    'EMBEDDING_PROVIDERS',
    'create_embedding_client',
]
