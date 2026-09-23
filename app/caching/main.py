"""Redis connection and versioned cache helpers.

Mutable objects and collections are cached under a generation number.  A
successful write increments the relevant generations atomically, therefore a
reader that was already filling an old cache entry can never overwrite the
new generation with stale data.
"""

import json
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Awaitable, Callable, TypeVar

import redis.asyncio as aioredis
from fastapi import FastAPI, Request

from app.core.config import CACHE_TTL, REDIS_URL


T = TypeVar('T')
_MISSING = object()


_USERS_VERSION_KEY = 'papaya:cache:users:version'
_EVENTS_VERSION_KEY = 'papaya:cache:events:version'
_OLYMPIADS_VERSION_KEY = 'papaya:cache:olympiads:version'
_ORGANIZATIONS_VERSION_KEY = 'papaya:cache:organizations:version'
_DOCS_VERSION_KEY = 'papaya:cache:docs:version'


def _user_version_key(user_id: str) -> str:
    return f'papaya:cache:user:{user_id}:version'


def _user_data_key(user_id: str, version: int) -> str:
    return f'papaya:cache:user:{user_id}:v:{version}'


def _event_version_key(event_id: str) -> str:
    return f'papaya:cache:event:{event_id}:version'


def _event_data_key(event_id: str, version: int) -> str:
    return f'papaya:cache:event:{event_id}:v:{version}'


def _olympiad_version_key(olympiad_id: str) -> str:
    return f'papaya:cache:olympiad:{olympiad_id}:version'


def _olympiad_data_key(olympiad_id: str, version: int) -> str:
    return f'papaya:cache:olympiad:{olympiad_id}:v:{version}'


def _doc_version_key(doc_id: str) -> str:
    return f'papaya:cache:doc:{doc_id}:version'


def _doc_data_key(doc_id: str, version: int) -> str:
    return f'papaya:cache:doc:{doc_id}:v:{version}'


def _organization_version_key(org_id: str) -> str:
    return f'papaya:cache:organization:{org_id}:version'


def _organization_data_key(org_id: str, version: int) -> str:
    return f'papaya:cache:organization:{org_id}:v:{version}'


def _users_data_key(include_inactive: bool, version: int) -> str:
    scope = 'all' if include_inactive else 'active'
    return f'papaya:cache:users:{scope}:v:{version}'


def _events_data_key(scope: str, version: int) -> str:
    return f'papaya:cache:events:{scope}:v:{version}'


def _olympiads_data_key(scope: str, version: int) -> str:
    return f'papaya:cache:olympiads:{scope}:v:{version}'


def _organizations_data_key(scope: str, version: int) -> str:
    return f'papaya:cache:organizations:{scope}:v:{version}'


def _docs_data_key(scope: str, version: int) -> str:
    return f'papaya:cache:docs:{scope}:v:{version}'


def _connection_pool() -> aioredis.ConnectionPool:
    """Пул соединений Redis: URL всегда вычислен в конфигурации."""
    return aioredis.ConnectionPool.from_url(
        REDIS_URL,
        decode_responses=True,
        max_connections=20,
    )


def get_standalone_redis() -> aioredis.Redis:
    """Redis-клиент вне FastAPI-запроса (Celery-воркер, пайплайн, subprocess).

    Пул создаётся на каждый вызов и не переживает цикл событий вызвавшего
    контекста: в тестах loop создаётся на каждый тест, в API — на запрос.
    Вызывающий обязан закрыть клиент (``aclose``).
    """
    return aioredis.Redis(connection_pool=_connection_pool())


async def cache_doc_outside_request(doc: dict) -> None:
    """Записать документ в кэш вне HTTP-запроса (после пайплайна/воркера)."""
    client = get_standalone_redis()
    try:
        await cache_doc_after_write(client, doc)
    finally:
        close = getattr(client, 'aclose', client.close)
        await close()


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


async def get_cached_olympiad(
    r: aioredis.Redis,
    olympiad_id: str,
    loader: Callable[[], Awaitable[dict | None]],
) -> dict | None:
    olympiad_id = str(olympiad_id)
    return await _get_versioned(
        r,
        _olympiad_version_key(olympiad_id),
        lambda version: _olympiad_data_key(olympiad_id, version),
        loader,
    )


async def get_cached_olympiads(
    r: aioredis.Redis,
    scope: str,
    loader: Callable[[], Awaitable[list[dict]]],
) -> list[dict]:
    return await _get_versioned(
        r,
        _OLYMPIADS_VERSION_KEY,
        lambda version: _olympiads_data_key(scope, version),
        loader,
    )


async def cache_olympiad_after_write(r: aioredis.Redis, olympiad: dict) -> None:
    """Publish an olympiad write and invalidate every olympiad-list scope."""
    olympiad_id = str(olympiad['id'])
    pipe = r.pipeline(transaction=True)
    pipe.incr(_olympiad_version_key(olympiad_id))
    pipe.incr(_OLYMPIADS_VERSION_KEY)
    olympiad_version, _ = await pipe.execute()
    await _write_json(
        r,
        _olympiad_data_key(olympiad_id, int(olympiad_version)),
        olympiad,
    )


async def cache_olympiads_after_write(
    r: aioredis.Redis,
    olympiads: list[dict],
) -> None:
    """Publish an olympiad bulk import with one generation change."""
    if not olympiads:
        return

    olympiad_ids = [str(olympiad['id']) for olympiad in olympiads]
    pipe = r.pipeline(transaction=True)
    pipe.incr(_OLYMPIADS_VERSION_KEY)
    for olympiad_id in olympiad_ids:
        pipe.incr(_olympiad_version_key(olympiad_id))
    versions = await pipe.execute()

    pipe = r.pipeline(transaction=True)
    for olympiad, olympiad_id, version in zip(olympiads, olympiad_ids, versions[1:]):
        payload = json.dumps(olympiad, ensure_ascii=False, separators=(',', ':'))
        pipe.set(
            _olympiad_data_key(olympiad_id, int(version)),
            payload,
            ex=CACHE_TTL,
        )
    await pipe.execute()


async def get_cached_organization(
    r: aioredis.Redis,
    org_id: str,
    loader: Callable[[], Awaitable[dict | None]],
) -> dict | None:
    org_id = str(org_id)
    return await _get_versioned(
        r,
        _organization_version_key(org_id),
        lambda version: _organization_data_key(org_id, version),
        loader,
    )


async def get_cached_organizations(
    r: aioredis.Redis,
    scope: str,
    loader: Callable[[], Awaitable[list[dict]]],
) -> list[dict]:
    return await _get_versioned(
        r,
        _ORGANIZATIONS_VERSION_KEY,
        lambda version: _organizations_data_key(scope, version),
        loader,
    )


async def cache_organization_after_write(
    r: aioredis.Redis,
    org: dict,
) -> None:
    """Publish an organization write and invalidate organization-list scopes."""
    org_id = str(org['id'])
    pipe = r.pipeline(transaction=True)
    pipe.incr(_organization_version_key(org_id))
    pipe.incr(_ORGANIZATIONS_VERSION_KEY)
    org_version, _ = await pipe.execute()
    await _write_json(
        r,
        _organization_data_key(org_id, int(org_version)),
        org,
    )


async def invalidate_organization(r: aioredis.Redis, org_id: str) -> None:
    """Пометить карточку и списки организаций устаревшими после удаления."""
    org_id = str(org_id)
    pipe = r.pipeline(transaction=True)
    pipe.incr(_organization_version_key(org_id))
    pipe.incr(_ORGANIZATIONS_VERSION_KEY)
    await pipe.execute()


async def invalidate_olympiad(r: aioredis.Redis, olympiad_id: str) -> None:
    """Пометить карточку и списки олимпиад устаревшими после удаления."""
    olympiad_id = str(olympiad_id)
    pipe = r.pipeline(transaction=True)
    pipe.incr(_olympiad_version_key(olympiad_id))
    pipe.incr(_OLYMPIADS_VERSION_KEY)
    await pipe.execute()


async def invalidate_doc(r: aioredis.Redis, doc_id: str) -> None:
    """Пометить карточку и списки документов устаревшими после удаления."""
    doc_id = str(doc_id)
    pipe = r.pipeline(transaction=True)
    pipe.incr(_doc_version_key(doc_id))
    pipe.incr(_DOCS_VERSION_KEY)
    await pipe.execute()


async def get_cached_doc(
    r: aioredis.Redis,
    doc_id: str,
    loader: Callable[[], Awaitable[dict | None]],
) -> dict | None:
    doc_id = str(doc_id)
    return await _get_versioned(
        r,
        _doc_version_key(doc_id),
        lambda version: _doc_data_key(doc_id, version),
        loader,
    )


async def get_cached_docs(
    r: aioredis.Redis,
    scope: str,
    loader: Callable[[], Awaitable[list[dict]]],
) -> list[dict]:
    return await _get_versioned(
        r,
        _DOCS_VERSION_KEY,
        lambda version: _docs_data_key(scope, version),
        loader,
    )


async def cache_doc_after_write(r: aioredis.Redis, doc: dict) -> None:
    """Publish a doc write and invalidate doc-list scopes."""
    doc_id = str(doc['id'])
    pipe = r.pipeline(transaction=True)
    pipe.incr(_doc_version_key(doc_id))
    pipe.incr(_DOCS_VERSION_KEY)
    doc_version, _ = await pipe.execute()
    await _write_json(
        r,
        _doc_data_key(doc_id, int(doc_version)),
        doc,
    )