"""Создание и проверка JWT-токенов Papaya.

Два типа токенов, и они не взаимозаменяемы:

- **access** (``typ='access'``, TTL 600 с) — состояниеless: проверяется только
  подпись и срок. Поэтому блокировка Redis или падение сессии не разрывают
  активные запросы, а ``logout`` не ждёт истечения токена (см. ротацию
  refresh-сессии в ``app.core.auth_session``);
- **refresh** (``typ='refresh'``, TTL 14 дней) — действует только при живой
  серверной сессии в Redis (ключ ``papaya:session:{sid}``) и только в паре
  с ``POST /auth/refresh``. Как access-токен не используется никогда:
  ``jwt_check`` при истёкшем access возвращает 401 «Access token expired»,
  а не молча декодирует refresh.

Оба токена несут ``sid`` (id серверной сессии): access — для ревокации при
logout, refresh — для ротации. Claim ``typ`` не даёт подделать один тип
токена другим при одинаковом секрете.
"""

import jwt
from fastapi import HTTPException
from datetime import datetime, timezone, timedelta

from app.core.config import JWT_KEY as SECRET

#: Время жизни access-токена. Короткое окно ограничивает ущерб от утечки
#: cookie; продление — через ``POST /auth/refresh`` (ротация refresh-сессии).
ACCESS_TOKEN_TTL_SECONDS = 600

#: Время жизни refresh-токена и серверной сессии обновления.
REFRESH_TOKEN_TTL_SECONDS = 1209600  # 14 дней

TYP_ACCESS = 'access'
TYP_REFRESH = 'refresh'


async def create_jwt(
        ins: dict,
        is_refresh: bool = False,
) -> str:
    '''
    JWT creator
    '''
    import uuid

    # jti делает каждый токен уникальным: без него два токена, выданные в
    # одну секунду для одного пользователя, байт-в-байт совпали бы (те же
    # sub/sid/iat/exp) — ротация refresh-токена выдала бы тот же самый токен,
    # и «старый» был бы неотличим от нового.
    ins['jti'] = str(uuid.uuid4())
    ins['typ'] = TYP_REFRESH if is_refresh else TYP_ACCESS
    ins['iat'] = datetime.now(tz=timezone.utc)
    if is_refresh:
        ins['exp'] = datetime.now(tz=timezone.utc) + timedelta(
            seconds=REFRESH_TOKEN_TTL_SECONDS,
        )
    else:
        ins['exp'] = datetime.now(tz=timezone.utc) + timedelta(
            seconds=ACCESS_TOKEN_TTL_SECONDS,
        )

    return jwt.encode(ins, SECRET, algorithm="HS256")


def decode_jwt(token: str, *, expected_typ: str) -> dict:
    """Раскодировать токен, проверив подпись, срок и тип.

    ``expected_typ`` — обязательный claim: refresh-токен не может пройти
    проверку как access (и наоборот), даже подписанный тем же ключом.
    """
    try:
        claims = jwt.decode(token, SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail=f'{expected_typ.capitalize()} token expired',
            headers={"location": "/auth"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=403,
            detail=f'Invalid {expected_typ} token',
            headers={"location": "/auth"},
        )
    if claims.get('typ') != expected_typ:
        raise HTTPException(
            status_code=403,
            detail=f'Invalid {expected_typ} token',
            headers={"location": "/auth"},
        )
    return claims


async def jwt_check(
    access_jwt: str | None = None,
) -> dict:
    """
    Validating incoming JWT token

    Только access-токен. Истёкший access — 401 «Access token expired»:
    продление сессии — отдельный шаг ``POST /auth/refresh``, который клиент
    делает явно. Молчаливая подмена access-токеном refresh из этого метода
    убрана: она позволяла работать с «протухшей» сессией без ротации и без
    ревокации при logout.
    """
    if not access_jwt:
        raise HTTPException(
            status_code=401,
            detail="Access token missing",
            headers={"location": "/auth"},
        )
    return decode_jwt(access_jwt, expected_typ=TYP_ACCESS)
