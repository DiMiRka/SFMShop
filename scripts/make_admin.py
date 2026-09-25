"""Выдать или отозвать права администратора у существующего пользователя.

Запуск из корня проекта:
    python -m scripts.make_admin user@example.com
    python -m scripts.make_admin user@example.com --revoke

В Docker:
    docker compose -f docker/docker-compose.yml --env-file .env exec app python -m scripts.make_admin user@example.com
"""
import argparse
import asyncio
import sys

import redis.asyncio as aioredis
from redis.exceptions import RedisError
from sqlalchemy import select

from src.core.config import app_settings
from src.database.connection import async_session, engine
from src.database.models import User
from src.services.cache_service import CacheService


async def set_admin(email: str, is_admin: bool) -> int:
    async with async_session() as session:
        async with session.begin():
            result = await session.execute(select(User).where(User.email == email).with_for_update())
            user = result.scalar_one_or_none()

            if user is None:
                print(f"Пользователь с email {email} не найден", file=sys.stderr)
                return 1

            user.is_admin = is_admin
            user_id = user.id

    await engine.dispose()

    # Права проверяются по БД, но профиль пользователя лежит в кэше: сбрасываем, чтобы is_admin в ответах был актуален
    redis_client = aioredis.Redis.from_url(app_settings.redis_url)
    try:
        await CacheService(redis_client).delete_users(user_id)
    except RedisError as exc:
        print(f"Не удалось сбросить кэш пользователя: {exc}", file=sys.stderr)
    finally:
        await redis_client.aclose()

    action = "назначен администратором" if is_admin else "лишён прав администратора"
    print(f"Пользователь {email} (id={user_id}) {action}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Управление правами администратора SFMShop")
    parser.add_argument("email", help="email существующего пользователя")
    parser.add_argument("--revoke", action="store_true", help="отозвать права вместо выдачи")
    args = parser.parse_args()

    return asyncio.run(set_admin(args.email, is_admin=not args.revoke))


if __name__ == "__main__":
    sys.exit(main())
