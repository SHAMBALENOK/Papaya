"""Ограничение частоты запросов к чувствительным маршрутам аутентификации.

Зачем отдельный модуль: подбор пароля и массовая регистрация — это не логика
маршрута, а общее правило безопасности. Оно собрано здесь в одном месте, чтобы
лимиты не расползались по обработчикам и чтобы поведение при недоступности
Redis было определено явно.

Механика — фиксированное окно в Redis:

- счётчик ``papaya:ratelimit:{scope}:{subject}`` заводится один раз командой
  ``SET key 0 EX window NX`` и далее инкрементируется; TTL, выставленный при
  создании, не продлевается на последующих запросах, поэтому окно не «едет»
  вперёд под нагрузкой;
- ``SET NX`` в связке с ``INCR`` работает на любой поддерживаемой версии Redis
  (не требует ``EXPIRE ... NX``) и не даёт гонке двух первых запросов создать
  счётчик без TTL.

Ключи ограничиваются независимо по IP и по идентификатору (email): точечный
подбор одного аккаунта и распределённый перебор с одного адреса должны упираться
в разные счётчики.

При недоступности Redis проверка **пропускает** запрос (fail-open): иначе
падение кэша превращало бы вход в полную недоступность, хотя Redis — не
единственный источник истины. Событие логируется, чтобы отказ не остался
незамеченным.
"""

import logging

import redis.asyncio as aioredis
from fastapi import HTTPException, Request

from app.core.config import (
    LOGIN_RATE_IDENTIFIER_LIMIT,
    LOGIN_RATE_IP_LIMIT,
    LOGIN_RATE_WINDOW_SECONDS,
    RATE_LIMIT_ENABLED,
    REFRESH_RATE_IP_LIMIT,
    REFRESH_RATE_WINDOW_SECONDS,
    REGISTER_RATE_IP_LIMIT,
    REGISTER_RATE_WINDOW_SECONDS,
)

logger = logging.getLogger('papaya.ratelimit')

#: Единый текст для всех лимитов: не подсказывает, какой именно счётчик исчерпан.
RATE_LIMITED_DETAIL = 'Слишком много попыток. Попробуйте ещё раз позже.'


def client_ip(request: Request) -> str:
    """IP клиента.

    ``request.client`` уже учитывает ``X-Forwarded-For``, когда uvicorn запущен
    за доверенным прокси (``--proxy-headers``); здесь домысливать заголовок
    нельзя — иначе клиент подделал бы IP и обнулил лимит.
    """
    client = request.client
    if client and client.host:
        return client.host
    return 'unknown'


async def _increment(r: aioredis.Redis, key: str, window_seconds: int) -> int:
    """Увеличить счётчик окна и вернуть новое значение."""
    pipe = r.pipeline(transaction=True)
    pipe.set(key, 0, ex=window_seconds, nx=True)
    pipe.incr(key)
    _, count = await pipe.execute()
    return int(count)


async def _enforce(
    r: aioredis.Redis,
    *,
    scope: str,
    subject: str,
    limit: int,
    window_seconds: int,
    detail: str,
) -> None:
    """Проверить один счётчик; при превышении — 429 с ``Retry-After``."""
    if not RATE_LIMIT_ENABLED or limit <= 0:
        return
    key = f'papaya:ratelimit:{scope}:{subject}'
    try:
        count = await _increment(r, key, window_seconds)
    except Exception:
        logger.exception('Rate limit check failed; allowing request')
        return
    if count <= limit:
        return

    retry_after = window_seconds
    try:
        ttl = await r.ttl(key)
        if isinstance(ttl, int) and ttl > 0:
            retry_after = ttl
    except Exception:  # pragma: no cover - TTL недоступен, окно и так известно
        pass
    raise HTTPException(
        status_code=429,
        detail=detail,
        headers={'Retry-After': str(retry_after)},
    )


async def enforce_login(
    r: aioredis.Redis,
    request: Request,
    email: str | None,
) -> None:
    """Лимиты входа: по IP и по email одновременно."""
    await _enforce(
        r,
        scope='login-ip',
        subject=client_ip(request),
        limit=LOGIN_RATE_IP_LIMIT,
        window_seconds=LOGIN_RATE_WINDOW_SECONDS,
        detail=RATE_LIMITED_DETAIL,
    )
    identifier = (email or '').strip().casefold()
    if identifier:
        await _enforce(
            r,
            scope='login-id',
            subject=identifier,
            limit=LOGIN_RATE_IDENTIFIER_LIMIT,
            window_seconds=LOGIN_RATE_WINDOW_SECONDS,
            detail=RATE_LIMITED_DETAIL,
        )


async def enforce_register(r: aioredis.Redis, request: Request) -> None:
    """Лимит регистрации по IP."""
    await _enforce(
        r,
        scope='register-ip',
        subject=client_ip(request),
        limit=REGISTER_RATE_IP_LIMIT,
        window_seconds=REGISTER_RATE_WINDOW_SECONDS,
        detail=RATE_LIMITED_DETAIL,
    )


async def enforce_refresh(r: aioredis.Redis, request: Request) -> None:
    """Лимит обновления сессии по IP (выше остальных: это частый запрос)."""
    await _enforce(
        r,
        scope='refresh-ip',
        subject=client_ip(request),
        limit=REFRESH_RATE_IP_LIMIT,
        window_seconds=REFRESH_RATE_WINDOW_SECONDS,
        detail=RATE_LIMITED_DETAIL,
    )
