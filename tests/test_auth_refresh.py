"""JWT refresh (Фаза 2): типы токенов, истечения и продление сессии.

Промоделирован полный сценарий «access протух → POST /auth/refresh → новый
access → повтор запроса», который раньше выполнялся неявным fallback на
refresh-claims (из-за чего выдавался «невидимый» логин).
"""

import jwt
import pytest
import redis as redis_sync
from datetime import datetime, timedelta, timezone
from sqlalchemy import update

from app.core.config import JWT_KEY, REDIS_URL
from app.database.database import AsyncSessionLocal
from app.middlewares.tokenz import main as tokenz
from app.models.users import Users
from tests.conftest import register_user


def _craft(type_, sub, exp_delta, key=JWT_KEY):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            'type': type_,
            'sub': sub,
            'iat': now - timedelta(seconds=100),
            'exp': now + exp_delta,
        },
        key,
        algorithm='HS256',
    )


def _expired_access(sub):
    return _craft('access', sub, timedelta(seconds=-100))


def _expired_refresh(sub):
    return _craft('refresh', sub, timedelta(seconds=-100))


def _flush_redis():
    redis_sync.Redis.from_url(REDIS_URL).flushdb()


def _cookie_header(**cookies):
    """Собрать Cookie-заголовок — точный контроль над отправляемыми токенами.

    Ручное `client.cookies.set(...)` в httpx создаёт domain-cookie, который
    сосуществует с host-only cookie от сервера, из-за чего запрос уходит с
    двумя одноимёнными cookie. Явный заголовок снимает эту неоднозначность.
    """
    return '; '.join(f'{name}={value}' for name, value in cookies.items())


async def _disable_user(user_id):
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Users).where(Users.id == user_id).values(isActive=False)
        )
        await session.commit()
    _flush_redis()


class TestTokenTypes:
    async def test_access_token_has_type_and_short_ttl(self):
        token = await tokenz.create_access_token({'sub': 'u-1'})
        claims = jwt.decode(token, JWT_KEY, algorithms=['HS256'])
        assert claims['type'] == 'access'
        assert claims['exp'] - claims['iat'] == tokenz.ACCESS_TTL_SECONDS

    async def test_refresh_token_has_type_and_long_ttl(self):
        token = await tokenz.create_refresh_token({'sub': 'u-1'})
        claims = jwt.decode(token, JWT_KEY, algorithms=['HS256'])
        assert claims['type'] == 'refresh'
        assert claims['exp'] - claims['iat'] == tokenz.REFRESH_TTL_SECONDS

    async def test_decode_returns_claims(self):
        token = await tokenz.create_access_token({'sub': 'u-1'})
        claims = await tokenz.decode_access_token(token)
        assert claims['sub'] == 'u-1'


class TestMixups:
    async def test_refresh_cannot_be_used_as_access(self):
        token = await tokenz.create_refresh_token({'sub': 'u-1'})
        with pytest.raises(Exception) as exc:
            await tokenz.decode_access_token(token)
        assert exc.value.status_code == 403
        assert exc.value.detail['code'] == tokenz.ACCESS_TOKEN_INVALID

    async def test_access_cannot_be_used_as_refresh(self):
        token = await tokenz.create_access_token({'sub': 'u-1'})
        with pytest.raises(Exception) as exc:
            await tokenz.decode_refresh_token(token)
        assert exc.value.status_code == 403
        assert exc.value.detail['code'] == tokenz.REFRESH_TOKEN_INVALID


class TestExpiration:
    async def test_expired_access(self):
        with pytest.raises(Exception) as exc:
            await tokenz.decode_access_token(_expired_access('u-1'))
        assert exc.value.status_code == 401
        assert exc.value.detail['code'] == tokenz.ACCESS_TOKEN_EXPIRED

    async def test_expired_refresh(self):
        with pytest.raises(Exception) as exc:
            await tokenz.decode_refresh_token(_expired_refresh('u-1'))
        assert exc.value.status_code == 401
        assert exc.value.detail['code'] == tokenz.REFRESH_TOKEN_EXPIRED

    async def test_missing_access(self):
        with pytest.raises(Exception) as exc:
            await tokenz.decode_access_token(None)
        assert exc.value.status_code == 401
        assert exc.value.detail['code'] == tokenz.ACCESS_TOKEN_MISSING

    async def test_missing_refresh(self):
        with pytest.raises(Exception) as exc:
            await tokenz.decode_refresh_token(None)
        assert exc.value.status_code == 401
        assert exc.value.detail['code'] == tokenz.REFRESH_TOKEN_MISSING

    async def test_invalid_signature(self):
        forged = _craft('access', 'u-1', timedelta(seconds=600), key='other_secret_key_over_32_bytes_long')
        with pytest.raises(Exception) as exc:
            await tokenz.decode_access_token(forged)
        assert exc.value.status_code == 403
        assert exc.value.detail['code'] == tokenz.ACCESS_TOKEN_INVALID


class TestRefreshFlow:
    async def test_expired_access_then_refresh_then_retry(self, client):
        """Полный цикл: 401 по access → refresh ставит новый access → 200."""
        user = await register_user(client, email='flow@example.com')
        sub = str(user['id'])
        valid_refresh = await tokenz.create_refresh_token({'sub': sub})

        client.cookies.clear()
        stale = await client.get(
            '/api/v1/',
            headers={'Cookie': _cookie_header(
                access_jwt=_expired_access(sub), refresh_jwt=valid_refresh,
            )},
        )
        assert stale.status_code == 401
        assert stale.json()['detail']['code'] == 'ACCESS_TOKEN_EXPIRED'

        refreshed = await client.post(
            '/api/v1/auth/refresh',
            headers={'Cookie': _cookie_header(refresh_jwt=valid_refresh)},
        )
        assert refreshed.status_code == 200
        new_access = refreshed.cookies.get('access_jwt')
        assert new_access

        retried = await client.get(
            '/api/v1/',
            headers={'Cookie': _cookie_header(
                access_jwt=new_access, refresh_jwt=valid_refresh,
            )},
        )
        assert retried.status_code == 200

    async def test_refresh_mints_access_with_valid_type(self, client):
        user = await register_user(client, email='type@example.com')
        valid_refresh = await tokenz.create_refresh_token({'sub': str(user['id'])})
        client.cookies.clear()
        response = await client.post(
            '/api/v1/auth/refresh',
            headers={'Cookie': _cookie_header(refresh_jwt=valid_refresh)},
        )
        assert response.status_code == 200
        new_access = response.cookies.get('access_jwt')
        claims = jwt.decode(new_access, JWT_KEY, algorithms=['HS256'])
        assert claims['type'] == 'access'
        # Новый access по-прежнему нельзя применить как refresh.
        with pytest.raises(Exception):
            await tokenz.decode_refresh_token(new_access)

    async def test_expired_refresh_is_401(self, client):
        user = await register_user(client, email='exp_r@example.com')
        client.cookies.clear()
        response = await client.post(
            '/api/v1/auth/refresh',
            headers={'Cookie': _cookie_header(
                refresh_jwt=_expired_refresh(str(user['id'])),
            )},
        )
        assert response.status_code == 401
        assert response.json()['detail']['code'] == 'REFRESH_TOKEN_EXPIRED'

    async def test_missing_refresh_is_401(self, client):
        await register_user(client, email='no_r@example.com')
        client.cookies.clear()
        response = await client.post('/api/v1/auth/refresh')
        assert response.status_code == 401
        assert response.json()['detail']['code'] == 'REFRESH_TOKEN_MISSING'

    async def test_invalid_refresh_signature_is_403(self, client):
        user = await register_user(client, email='bad_r@example.com')
        forged = _craft(
            'refresh', str(user['id']), timedelta(seconds=1209600), key='other_secret_key_over_32_bytes_long',
        )
        client.cookies.clear()
        response = await client.post(
            '/api/v1/auth/refresh',
            headers={'Cookie': _cookie_header(refresh_jwt=forged)},
        )
        assert response.status_code == 403
        assert response.json()['detail']['code'] == 'REFRESH_TOKEN_INVALID'

    async def test_disabled_user_is_rejected_on_refresh(self, client):
        """Забаненный пользователь не может продлить сессию (403)."""
        user = await register_user(client, email='banned@example.com')
        await _disable_user(user['id'])
        valid_refresh = await tokenz.create_refresh_token({'sub': str(user['id'])})
        client.cookies.clear()
        response = await client.post(
            '/api/v1/auth/refresh',
            headers={'Cookie': _cookie_header(refresh_jwt=valid_refresh)},
        )
        assert response.status_code == 403
        assert response.json()['detail']['code'] == 'ACCOUNT_DISABLED'

    async def test_disabled_user_blocked_on_me(self, client):
        """Деактивация отсекает даже свежий access на /api/v1/."""
        user = await register_user(client, email='banned_me@example.com')
        await _disable_user(user['id'])
        response = await client.get('/api/v1/')
        assert response.status_code == 403
        assert response.json()['detail']['code'] == 'ACCOUNT_DISABLED'

    async def test_logout_works_without_valid_tokens(self, client):
        """Выход не должен зависеть от валидности JWT."""
        await register_user(client, email='logout_any@example.com')
        client.cookies.clear()
        response = await client.post(
            '/api/v1/auth/logout',
            headers={'Cookie': _cookie_header(
                access_jwt='garbage', refresh_jwt='garbage',
            )},
        )
        assert response.status_code == 200
        set_cookie = response.headers.get('set-cookie', '').lower()
        assert 'access_jwt=' in set_cookie
        assert 'refresh_jwt=' in set_cookie
        # delete_cookie выставляет max-age=0 — браузер снимет обе куки.
        assert set_cookie.count('max-age=0') == 2


class TestAuthStatus:
    async def test_status_with_valid_session_is_403(self, client):
        await register_user(client, email='status_ok@example.com')
        response = await client.get('/api/v1/auth/')
        assert response.status_code == 403

    async def test_status_without_session_is_200(self, client):
        client.cookies.clear()
        response = await client.get('/api/v1/auth/')
        assert response.status_code == 200

    async def test_status_with_expired_access_but_live_refresh_is_403(self, client):
        user = await register_user(client, email='status_ref@example.com')
        valid_refresh = await tokenz.create_refresh_token({'sub': str(user['id'])})
        client.cookies.clear()
        response = await client.get(
            '/api/v1/auth/',
            headers={'Cookie': _cookie_header(
                access_jwt=_expired_access(str(user['id'])),
                refresh_jwt=valid_refresh,
            )},
        )
        assert response.status_code == 403