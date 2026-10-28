import openai

from sfmshop.core.exceptions import EmbeddingUnavailableError
from sfmshop.core.metrics import EMBEDDING_COST, EMBEDDING_REQUESTS, EMBEDDING_TOKENS
from sfmshop.services.log_service import log_service


MAX_INPUTS_PER_REQUEST = 2048


class OpenAIEmbeddingClient:
    def __init__(
            self,
            api_key: str,
            model: str,
            dimensions: int,
            batch_size: int,
            usd_per_million_tokens: float,
            timeout: float,
            max_retries: int,
            http_client: openai.DefaultAsyncHttpxClient | None = None):
        self.model = model
        self.dimensions = dimensions
        self.batch_size = max(1, min(batch_size, MAX_INPUTS_PER_REQUEST))
        self.usd_per_million_tokens = usd_per_million_tokens
        self.client = openai.AsyncOpenAI(
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors += await self._embed_batch(texts[start:start + self.batch_size])
        return vectors

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=texts,
                dimensions=self.dimensions,
            )
        except openai.APIConnectionError as exc:
            EMBEDDING_REQUESTS.labels("unavailable").inc()
            log_service.warning("embeddings_unavailable", provider="openai", reason=type(exc).__name__)
            raise EmbeddingUnavailableError("Сервис эмбеддингов недоступен") from exc
        except openai.APIStatusError as exc:
            EMBEDDING_REQUESTS.labels("unavailable").inc()
            log_service.warning("embeddings_unavailable", provider="openai", status_code=exc.status_code,
                                request_id=exc.request_id)
            raise EmbeddingUnavailableError("Сервис эмбеддингов недоступен") from exc

        tokens = response.usage.total_tokens
        EMBEDDING_REQUESTS.labels("ok").inc()
        EMBEDDING_TOKENS.labels(self.model).inc(tokens)
        EMBEDDING_COST.labels(self.model).inc(tokens * self.usd_per_million_tokens / 1_000_000)

        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]

    async def close(self) -> None:
        await self.client.close()
