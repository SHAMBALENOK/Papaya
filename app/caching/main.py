"""Redis connection and versioned cache helpers.

Mutable objects and collections are cached under a generation number.  A
successful write increments the relevant generations atomically, therefore a
reader that was already filling an old cache entry can never overwrite the
new generation with stale data.
"""

import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Awaitable, Callable, TypeVar

import redis.asyncio as aioredis
from fastapi import FastAPI, Request


T = TypeVar('T')
_MISSING = object()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


CACHE_TTL = _env_int('CACHE_TTL', 600)
REDIS_URL = os.getenv('REDIS_URL')
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = _env_int('REDIS_PORT', 6379)

_USERS_VERSION_KEY = 'papaya:cache:users:version'
_EVENTS_VERSION_KEY = 'papaya:cache:events:version'


def _user_version_key(user_id: str) -> str:
    return f'papaya:cache:user:{user_id}:version'


def _user_data_key(user_id: str, version: int) -> str:
    return f'papaya:cache:user:{user_id}:v:{version}'


def _event_version_key(event_id: str) -> str:
    return f'papaya:cache:event:{event_id}:version'


def _event_data_key(event_id: str, version: int) -> str:
    return f'papaya:cache:event:{event_id}:v:{version}'


def _users_data_key(include_inactive: bool, version: int) -> str:
    scope = 'all' if include_inactive else 'active'
    return f'papaya:cache:users:{scope}:v:{version}'


def _events_data_key(scope: str, version: int) -> str:
    return f'papaya:cache:events:{scope}:v:{version}'


def _connection_pool() -> aioredis.ConnectionPool:
    options = {
        'decode_responses': True,
        'max_connections': 20,
    }
    if REDIS_URL:
        return aioredis.ConnectionPool.from_url(REDIS_URL, **options)
    return aioredis.ConnectionPool(
        host=REDIS_HOST,
        port=REDIS_PORT,
        **options,
    )


@asynccontextmanager
async def redis_lifespan(app: FastAPI):
    app.state.redis_pool = _connection_pool()
    try:
        yield
    finally:
        await app.state.redis_pool.disconnect()


async def get_redis(request: Request) -> AsyncGenerator[aioredis.Redis, None]:
    client = aioredis.Redis(connection_pool=request.app.state.redis_pool)
    try:
        yield client
    finally:
        close = getattr(client, 'aclose', client.close)
        await close()


async def _version(r: aioredis.Redis, key: str) -> int:
    value = await r.get(key)
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        # A damaged generation must not make the whole API unusable or revive
        # an old generation-zero entry.
        version = time.time_ns()
        await r.set(key, version)
        return version


async def _read_json(r: aioredis.Redis, key: str) -> Any:
    cached = await r.get(key)
    if cached is None:
        return _MISSING
    try:
        return json.loads(cached)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        await r.delete(key)
        return _MISSING


async def _write_json(r: aioredis.Redis, key: str, value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    await r.set(key, payload, ex=CACHE_TTL)


async def _get_versioned(
    r: aioredis.Redis,
    version_key: str,
    data_key: Callable[[int], str],
    loader: Callable[[], Awaitable[T]],
) -> T:
    version = await _version(r, version_key)
    key = data_key(version)
    cached = await _read_json(r, key)
    if cached is not _MISSING:
        return cached

    value = await loader()
    if value is not None:
        # If a concurrent writer increments the version while loader() runs,
        # this value is written only to the old generation and is never read
        # as current data.
        await _write_json(r, key, value)
    return value


async def get_cached_user(
    r: aioredis.Redis,
    user_id: str,
    loader: Callable[[], Awaitable[dict | None]],
) -> dict | None:
    user_id = str(user_id)
    return await _get_versioned(
        r,
        _user_version_key(user_id),
        lambda version: _user_data_key(user_id, version),
        loader,
    )


async def get_cached_event(
    r: aioredis.Redis,
    event_id: str,
    loader: Callable[[], Awaitable[dict | None]],
) -> dict | None:
    event_id = str(event_id)
    return await _get_versioned(
        r,
        _event_version_key(event_id),
        lambda version: _event_data_key(event_id, version),
        loader,
    )


async def get_cached_users(
    r: aioredis.Redis,
    include_inactive: bool,
    loader: Callable[[], Awaitable[list[dict]]],
) -> list[dict]:
    return await _get_versioned(
        r,
        _USERS_VERSION_KEY,
        lambda version: _users_data_key(include_inactive, version),
        loader,
    )


async def get_cached_events(
    r: aioredis.Redis,
    scope: str,
    loader: Callable[[], Awaitable[list[dict]]],
) -> list[dict]:
    return await _get_versioned(
        r,
        _EVENTS_VERSION_KEY,
        lambda version: _events_data_key(scope, version),
        loader,
    )


async def cache_user_after_write(r: aioredis.Redis, user: dict) -> None:
    """Publish a user write and invalidate both active and admin lists."""
    user_id = str(user['id'])
    pipe = r.pipeline(transaction=True)
    pipe.incr(_user_version_key(user_id))
    pipe.incr(_USERS_VERSION_KEY)
    user_version, _ = await pipe.execute()
    await _write_json(r, _user_data_key(user_id, int(user_version)), user)


async def cache_event_after_write(r: aioredis.Redis, event: dict) -> None:
    """Publish an event write and invalidate every event-list scope."""
    event_id = str(event['id'])
    pipe = r.pipeline(transaction=True)
    pipe.incr(_event_version_key(event_id))
    pipe.incr(_EVENTS_VERSION_KEY)
    event_version, _ = await pipe.execute()
    await _write_json(r, _event_data_key(event_id, int(event_version)), event)


async def cache_events_after_write(
    r: aioredis.Redis,
    events: list[dict],
) -> None:
    """Publish a table import with one collection-generation change."""
    if not events:
        return

    event_ids = [str(event['id']) for event in events]
    pipe = r.pipeline(transaction=True)
    pipe.incr(_EVENTS_VERSION_KEY)
    for event_id in event_ids:
        pipe.incr(_event_version_key(event_id))
    versions = await pipe.execute()

    pipe = r.pipeline(transaction=True)
    for event, event_id, version in zip(events, event_ids, versions[1:]):
        payload = json.dumps(event, ensure_ascii=False, separators=(',', ':'))
        pipe.set(
            _event_data_key(event_id, int(version)),
            payload,
            ex=CACHE_TTL,
        )
    await pipe.execute()