from typing import Protocol


class EmbeddingClient(Protocol):
    model: str

    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    async def close(self) -> None:
        ...
