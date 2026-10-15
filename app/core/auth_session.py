"""Серверные сессии обновления токенов (refresh rotation).

Refresh-токен не «живёт сам по себе»: его действие привязано к записи в
Redis ``papaya:session:{sid}``, где хранится текущий (и предыдущий, в окне
grace) refresh-токен сессии. Каждое успешное обновление **ротирует** токен:
старый перестаёт быть актуальным. Это закрывает три сценария:

- кража refresh--cookie: после ротации украденный токен невалиден;
- повтор (reuse) уже ротированного токена вне grace-окна — признак кражи,
  вся сессия отзывается (``revoke_session``);
- конкурентное обновление из двух вкладок: первый запрос ротирует токен,
  второй успевает с прежним токеном в коротком grace-окне и получает
  актуальный (см. ``rotate_refresh_token``).

Access-токены сессией не проверяются (stateless, см. ``tokenz.jwt_check``):
сессия нужна только для обновления и ревокации при logout.
"""

import json
import time

import redis.asyncio as aioredis

from app.middlewares.tokenz.main import (
    REFRESH_TOKEN_TTL_SECONDS,
    TYP_REFRESH,
    create_jwt,
)

#: Ключ сессии в Redis.
SESSION_KEY_TPL = 'papaya:session:{sid}'

#: Окно, в течение которого предыдущий (ротированный) refresh-токен ещё
#: принимается. Нужно только для конкурентного обновления из двух вкладок:
#: первый запрос ротирует токен, второй отправляет уже старый и должен
#: получить актуальный, а не ошибку. Больше окна — тем дольше живёт украденный
#: токен после ротации, поэтому оно короткое.
REFRESH_GRACE_SECONDS = 30


def _session_key(sid: str) -> str:
    return SESSION_KEY_TPL.format(sid=sid)


async def create_session(
    r: aioredis.Redis,
    *,
    user_id: str,
    sid: str | None = None,
) -> dict:
    """Создать сессию обновления и вернуть её начальное состояние.

    Возвращает ``{'sid': ..., 'refresh_token': ...}``: refresh-токен подписан
    сразу, чтобы вызывающий код выставил куки и записал его в сессию одним
    шагом (см. ``store_session``).
    """
    import uuid

    sid = sid or str(uuid.uuid4())
    refresh_token = await create_jwt(
        ins={'sub': str(user_id), 'sid': sid},
        is_refresh=True,
    )
    return {'sid': sid, 'refresh_token': refresh_token}


async def store_session(
    r: aioredis.Redis,
    *,
    sid: str,
    user_id: str,
    refresh_token: str,
    prev_token: str | None = None,
    prev_expires_at: float | None = None,
) -> None:
    """Сохранить сессию; TTL ключа — полный срок жизни refresh-токена.

    Токены хранятся как есть: они — серверные секреты, доступные только
    серверу (Redis), а grace-окно должно уметь вернуть предыдущий токен
    клиенту без повторной подписи.
    """
    payload = {
        'user_id': str(user_id),
        'current': refresh_token,
        'prev': prev_token,
        'prev_expires_at': prev_expires_at,
    }
    await r.set(
        _session_key(sid),
        json.dumps(payload),
        ex=REFRESH_TOKEN_TTL_SECONDS,
    )


async def load_session(r: aioredis.Redis, sid: str) -> dict | None:
    """Прочитать сессию; ``None`` — отозвана, истекла или не создавалась."""
    raw = await r.get(_session_key(sid))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


async def revoke_session(r: aioredis.Redis, sid: str) -> None:
    """Отозвать сессию: её refresh-токены перестают действовать."""
    await r.delete(_session_key(sid))


async def rotate_refresh_token(
    r: aioredis.Redis,
    *,
    sid: str,
    presented_token: str,
) -> tuple[str, str] | None:
    """Ротировать refresh-токен сессии по предъявленному.

    Возвращает ``(новый_refresh_токен, sid)`` или ``None``, если ротация
    невозможна (нет сессии, не тот токен, reuse вне grace-окна). ``None`` —
    сигнал вызывающему отдать 401; при suspected reuse сессия уже отозвана
    внутри.

    Правила:

    - предъявленный токен совпадает с текущим — обычная ротация: старый
      уходит в ``prev`` с grace-окном, подписывается новый;
    - совпадает с ``prev`` внутри grace-окна — конкурентное обновление:
      возвращается **текущий** токен без новой ротации (вкладки не спорят);
    - всё остальное — reuse ротированного токена или чужой токен: сессия
      отзывается целиком (защита от повторной эксплуатации украденного
      токена).
    """
    session = await load_session(r, sid)
    if not session:
        return None

    user_id = session.get('user_id')
    current = session.get('current')
    if not user_id or not current:
        await revoke_session(r, sid)
        return None

    now = time.time()
    if presented_token == current:
        new_token = await create_jwt(
            ins={'sub': str(user_id), 'sid': sid},
            is_refresh=True,
        )
        await store_session(
            r,
            sid=sid,
            user_id=user_id,
            refresh_token=new_token,
            prev_token=presented_token,
            prev_expires_at=now + REFRESH_GRACE_SECONDS,
        )
        return new_token, sid

    prev = session.get('prev')
    prev_expires_at = session.get('prev_expires_at') or 0
    if presented_token == prev and now <= prev_expires_at:
        # Конкурентное обновление: второй запрос получил ротированный токен
        # первого. Отдаём текущий токен сессии без новой ротации.
        return current, sid

    # Reuse ротированного токена (или неизвестный): сессия скомпрометирована
    # или устарела — отзываем её целиком.
    await revoke_session(r, sid)
    return None


async def sid_from_refresh_cookie(refresh_jwt: str) -> str | None:
    """Извлечь ``sid`` из refresh-токена для ревокации (logout).

    Срок жизни намеренно не проверяется: истёкший refresh-токен всё ещё
    указывает на сессию, которую нужно отозвать. Подпись и тип проверяются.
    """
    try:
        claims = decode_jwt_no_exp(refresh_jwt)
    except Exception:  # noqa: BLE001 — любой разбор = токен не годится
        return None
    if claims.get('typ') != TYP_REFRESH:
        return None
    sid = claims.get('sid')
    return str(sid) if sid else None


def decode_jwt_no_exp(token: str) -> dict:
    """Раскодировать токен по подписи и типу, игнорируя срок (для revocation)."""
    import jwt as jwt_mod

    from app.core.config import JWT_KEY

    return jwt_mod.decode(
        token,
        JWT_KEY,
        algorithms=['HS256'],
        options={'verify_exp': False},
    )
