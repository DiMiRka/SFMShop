"""Пересчитать эмбеддинги всех товаров

Товары у которых текст и модель не менялись, пропускаются: их вектор уже актуален
--force пересчитывает все, например после смены EMBEDDING_MODEL

Запуск из корня проекта:
    python -m scripts.reindex_products
    python -m scripts.reindex_products --force --batch-size 200

В Docker:
    docker compose -f deploy/docker/docker-compose.yml --env-file .env exec app python -m scripts.reindex_products
"""
import argparse
import asyncio
import sys

from sfmshop.clients.embeddings import create_embedding_client
from sfmshop.core.config import app_settings
from sfmshop.database.connection import async_session, engine
from sfmshop.repositories.product_repository import ProductRepository
from sfmshop.services.product_index_service import ProductIndexer


async def reindex(force: bool, batch_size: int) -> int:
    client = create_embedding_client(app_settings)
    if client is None:
        print("Эмбеддинги выключены: не задан OPENAI_API_KEY", file=sys.stderr)
        return 1

    indexer = ProductIndexer(async_session, client)
    indexed = unchanged = missing = 0
    after_id = 0
    try:
        while True:
            async with async_session() as session:
                ids = await ProductRepository(session).get_ids_after(after_id, batch_size)
            if not ids:
                break

            result = await indexer.index(ids, force=force)
            indexed += result.indexed
            unchanged += result.unchanged
            missing += result.missing
            after_id = ids[-1]
            print(f"До id={after_id}: посчитано {indexed}, без изменений {unchanged}")
    finally:
        await client.close()
        await engine.dispose()

    print(f"Готово: посчитано {indexed}, без изменений {unchanged}, удалены во время работы {missing}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Переиндексация эмбеддингов товаров SFMShop")
    parser.add_argument("--force", action="store_true", help="пересчитать даже неизменившиеся товары")
    parser.add_argument("--batch-size", type=int, default=100, help="сколько товаров обрабатывать за раз")
    args = parser.parse_args()

    return asyncio.run(reindex(force=args.force, batch_size=args.batch_size))


if __name__ == "__main__":
    sys.exit(main())
