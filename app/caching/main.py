from contextlib import asynccontextmanager
from typing import AsyncGenerator
import redis.asyncio as aioredis
from fastapi import FastAPI, Request
import os

REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = int(os.getenv('REDIS_PORT'))

# Версия каталога событий. Ключи каталогов строятся как
# user:{id}:events:v{version}, поэтому после любого изменения событий
# достаточно увеличить счётчик: все клиенты при следующем запросе
# промахнутся мимо кэша и получат свежие данные, а старые ключи
# спокойно истекут по TTL (600с).
EVENTS_CATALOG_VERSION_KEY = "events:catalog:version"


@asynccontextmanager
async def redis_lifespan(app: FastAPI):
    app.state.redis_pool = aioredis.ConnectionPool(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        max_connections=20
    )
    yield
    await app.state.redis_pool.disconnect()


async def get_redis(request: Request) -> AsyncGenerator[aioredis.Redis, None]:
    pool = request.app.state.redis_pool
    client = aioredis.Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.close()


async def get_events_catalog_version(r: aioredis.Redis) -> int:
    """
    Текущая версия каталога событий (0, если кэш ещё не использовался).
    """
    version = await r.get(EVENTS_CATALOG_VERSION_KEY)
    try:
        return int(version) if version is not None else 0
    except (TypeError, ValueError):
        return 0


async def bump_events_catalog_version(r: aioredis.Redis) -> int:
    """
    Инвалидирует кэш каталога событий у ВСЕХ пользователей.

    Вызывать после любого изменения событий (создание, редактирование,
    импорт, архивация). Версия подмешивается в ключ каталога, поэтому
    ничего сканировать и удалять не нужно.
    """
    return int(await r.incr(EVENTS_CATALOG_VERSION_KEY))


async def bump_events_catalog_version_from_worker() -> int:
    """
    То же, что bump_events_catalog_version, но для процессов без
    FastAPI-приложения (Celery-воркер): создаёт короткоживущее
    подключение к Redis напрямую.
    """
    client = aioredis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
    )
    try:
        return int(await client.incr(EVENTS_CATALOG_VERSION_KEY))
    finally:
        await client.aclose()
