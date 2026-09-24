"""Создание и проверка JWT для Papaya.

Контракт токенов (Фаза 2, «JWT refresh полностью»):

* access и refresh создаются с явным claim ``type`` («access» / «refresh»);
  refresh нельзя использовать как access, и наоборот;
* access TTL — 600 секунд, refresh TTL — 1209600 секунд (14 дней);
* токены передаются только в HttpOnly-куках (см. routers/auth.py), не в JSON;
* rotation refresh-токенов НЕ делается: выдаётся новый access, refresh
  остаётся прежним (сознательное решение этой итерации — блок blacklist
  и переотзыв пока вне объёма);
* после истечения access endpoint возвращает 401 с кодом ACCESS_TOKEN_EXPIRED
  в body — фронтенд по этому коду сам вызывает POST /auth/refresh и повторяет
  исходный запрос ровно один раз (см. frontend/js/api.js);
* ошибки возвращаются в виде detail = {"code", "message"} — фронтенд различает
  «access протух → refresh» и «refresh невалиден → logout».
"""

import jwt
from fastapi import HTTPException
from datetime import datetime, timezone, timedelta

from app.core.config import JWT_KEY as SECRET

ACCESS_TTL_SECONDS = 600
REFRESH_TTL_SECONDS = 1209600

# Коды ошибок в detail — контракт для фронтенда (docs/responses.md).
ACCESS_TOKEN_MISSING = 'ACCESS_TOKEN_MISSING'
ACCESS_TOKEN_INVALID = 'ACCESS_TOKEN_INVALID'
ACCESS_TOKEN_EXPIRED = 'ACCESS_TOKEN_EXPIRED'
REFRESH_TOKEN_MISSING = 'REFRESH_TOKEN_MISSING'
REFRESH_TOKEN_INVALID = 'REFRESH_TOKEN_INVALID'
REFRESH_TOKEN_EXPIRED = 'REFRESH_TOKEN_EXPIRED'
ACCOUNT_DISABLED = 'ACCOUNT_DISABLED'

_TYPE_ACCESS = 'access'
_TYPE_REFRESH = 'refresh'


def _auth_error(status_code: int, code: str, message: str) -> HTTPException:
    """HTTP-ошибка авторизации с машиночитаемым кодом в detail."""
    return HTTPException(
        status_code=status_code,
        detail={'code': code, 'message': message},
        headers={'location': '/auth'},
    )


def account_disabled_error() -> HTTPException:
    """403 для деактивированного (забаненного) пользователя."""
    return _auth_error(403, ACCOUNT_DISABLED, 'Account is disabled')


def _encode(claims: dict, ttl: int) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = dict(claims)
    payload['iat'] = now
    payload['exp'] = now + timedelta(seconds=ttl)
    return jwt.encode(payload, SECRET, algorithm='HS256')


async def create_access_token(ins: dict) -> str:
    """Создать короткоживущий access-токен (type=access, 600 сек)."""
    return _encode({'type': _TYPE_ACCESS, **ins}, ACCESS_TTL_SECONDS)


async def create_refresh_token(ins: dict) -> str:
    """Создать refresh-токен (type=refresh, 14 дней)."""
    return _encode({'type': _TYPE_REFRESH, **ins}, REFRESH_TTL_SECONDS)


def _decode_token(token: str | None, expected_type: str, missing_code: str,
                  invalid_code: str, expired_code: str) -> dict:
    """Распарсить и проверить JWT ожидаемого типа.

    Любая проблема → исключение HTTPException с detail={"code","message"}.
    """
    if not token:
        raise _auth_error(401, missing_code, f'{expected_type} token missing')
    try:
        claims = jwt.decode(token, SECRET, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        raise _auth_error(401, expired_code, f'{expected_type} token expired')
    except jwt.PyJWTError:
        raise _auth_error(403, invalid_code, f'Invalid {expected_type} token')
    if claims.get('type') != expected_type:
        # Токен другого типа не должен работать как запрошенный.
        raise _auth_error(403, invalid_code, f'Invalid {expected_type} token')
    return claims


async def decode_access_token(access_jwt: str | None) -> dict:
    """Проверить access-токен и вернуть claims.

    Истёкший access → 401 ACCESS_TOKEN_EXPIRED (фронт вызывает /auth/refresh).
    Отсутствующий/неподписанный/чужого типа → 401/403 с соответствующим кодом.
    """
    return _decode_token(
        access_jwt,
        expected_type=_TYPE_ACCESS,
        missing_code=ACCESS_TOKEN_MISSING,
        invalid_code=ACCESS_TOKEN_INVALID,
        expired_code=ACCESS_TOKEN_EXPIRED,
    )


async def decode_refresh_token(refresh_jwt: str | None) -> dict:
    """Проверить refresh-токен и вернуть claims (используется в /auth/refresh)."""
    return _decode_token(
        refresh_jwt,
        expected_type=_TYPE_REFRESH,
        missing_code=REFRESH_TOKEN_MISSING,
        invalid_code=REFRESH_TOKEN_INVALID,
        expired_code=REFRESH_TOKEN_EXPIRED,
    )


async def jwt_check(
    access_jwt: str | None = None,
    refresh_jwt: str | None = None,
) -> dict:
    """Совместимая обёртка: проверяется только access.

    ``refresh_jwt`` намеренно не используется как fallback: раньше истёкший
    access молча подменялся refresh-claims, из-за чего выдавался «невидимый»
    логин. Теперь refresh-сессия оживляется явно через POST /auth/refresh.
    """
    return await decode_access_token(access_jwt)
