"""Регистрация, вход и выход: жизненный цикл сессии."""

from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from app.core.config import JWT_KEY
from tests.conftest import admin_client, login_user, register_user


async def test_register_success(client):
    payload = await register_user(client)
    assert payload['id']
    assert payload['name'] == 'Test'
    # Пароль сервер никогда не возвращает.
    assert 'password' not in payload
    assert 'access_jwt' in client.cookies


async def test_register_duplicate_email(client):
    email = 'duplicate@example.com'
    await register_user(client, email=email)
    response = await client.post(
        '/api/v1/auth/register',
        json={
            'name': 'Test',
            'surname': 'User',
            'email': email,
            'password': 'StrongPass123!',
        },
    )
    assert response.status_code == 409
    assert response.json()['detail'] == 'You already have account'


async def test_register_weak_password(client):
    response = await client.post(
        '/api/v1/auth/register',
        json={
            'name': 'Test',
            'surname': 'User',
            'email': 'weak@example.com',
            'password': '123',
        },
    )
    assert response.status_code == 400


async def test_register_oversized_password_is_400(client):
    """Пароль длиннее 72 байт (лимит bcrypt) — валидационная 400, не 500."""
    long_password = 'Ab1!' + 'x' * 90
    response = await client.post(
        '/api/v1/auth/register',
        json={
            'name': 'Test',
            'surname': 'User',
            'email': 'oversized@example.com',
            'password': long_password,
        },
    )
    assert response.status_code == 400
    assert response.json()['detail'].startswith('Пароль слишком длинный')


async def test_login_with_oversized_password_is_401(client):
    """Проверка bcrypt на пароле >72 байт возвращает 401, а не 500."""
    email = 'oversized_login@example.com'
    await register_user(client, email=email)
    client.cookies.clear()

    long_password = 'Ab1!' + 'y' * 90
    response = await client.post(
        '/api/v1/auth/login',
        json={'email': email, 'password': long_password},
    )
    assert response.status_code == 401
    assert 'access_jwt' not in client.cookies


async def test_login_unknown_email_is_401_not_500(client):
    """Несуществующий email — 401 с постоянным временем, а не 500.

    Заглушка сравнивает пароль с dummy-хэшем, чтобы время ответа не выдавало
    отсутствие аккаунта. Раньше заглушка падала (``AttributeError`` на
    байтовом хэше), наружу уходил 500 — и разница «есть email / нет email»
    снова становилась видимой для перебора.
    """
    response = await client.post(
        '/api/v1/auth/login',
        json={'email': 'ghost@example.com', 'password': 'StrongPass123!'},
    )
    assert response.status_code == 401, response.text
    assert response.json()['detail'] == 'Invalid email or password'
    assert 'access_jwt' not in client.cookies


async def test_login_wrong_password(client):
    email = 'login@example.com'
    await register_user(client, email=email)
    # Сбрасываем cookie-сессию регистрации, чтобы проверить только вход.
    client.cookies.clear()
    response = await client.post(
        '/api/v1/auth/login',
        json={'email': email, 'password': 'WrongPass123!'},
    )
    assert response.status_code == 401
    assert 'access_jwt' not in client.cookies


async def test_login_success_sets_cookies(client):
    email = 'login_ok@example.com'
    await register_user(client, email=email)
    client.cookies.clear()

    response = await client.post(
        '/api/v1/auth/login',
        json={'email': email, 'password': 'StrongPass123!'},
    )
    assert response.status_code == 200
    assert 'access_jwt' in client.cookies
    assert 'refresh_jwt' in client.cookies


async def test_auth_cookies_are_httponly_samesite(client):
    """JWT-куки: HttpOnly + SameSite=Lax (защита от XSS-стелла и CSRF)."""
    email = 'cookie_flags@example.com'
    response = await client.post(
        '/api/v1/auth/register',
        json={
            'name': 'Cookie',
            'surname': 'Check',
            'email': email,
            'password': 'StrongPass123!',
        },
    )
    assert response.status_code == 201
    header = response.headers.get('set-cookie')
    assert header is not None

    access, refresh = header.split(',')
    for part in (access, refresh):
        assert 'HttpOnly' in part
        assert 'SameSite=lax' in part
    # В тестовом окружении COOKIE_SECURE=false, Secure не должен присутствовать.
    assert 'Secure' not in header


async def test_logout_clears_cookies(client):
    await register_user(client)
    response = await client.post('/api/v1/auth/logout')
    assert response.status_code == 200
    assert 'access_jwt' not in client.cookies
    assert 'refresh_jwt' not in client.cookies


async def test_auth_status(client):
    # Без токена — «не залогинен».
    response = await client.get('/api/v1/auth/')
    assert response.status_code == 200

    # С активной сессией — «уже залогинен».
    await register_user(client)
    response = await client.get('/api/v1/auth/')
    assert response.status_code == 403


async def _banned_user(client) -> dict:
    """Зарегистрировать пользователя и заблокировать его администратором."""
    target = await register_user(client)
    await admin_client(client)
    resp = await client.post(f"/api/v1/admin/ban/{target['id']}")
    assert resp.status_code == 200, resp.text
    return target


async def test_banned_login_is_403(client):
    """Заблокированный пользователь не может войти даже с верным паролем."""
    target = await _banned_user(client)
    client.cookies.clear()
    response = await client.post(
        '/api/v1/auth/login',
        json={'email': target['email'], 'password': 'StrongPass123!'},
    )
    assert response.status_code == 403
    assert response.json()['detail'] == 'Account is blocked'
    assert 'access_jwt' not in client.cookies


async def test_banned_wrong_password_still_401(client):
    """Неверный пароль заблокированного — 401, а не 403: не раскрываем аккаунт."""
    target = await _banned_user(client)
    client.cookies.clear()
    response = await client.post(
        '/api/v1/auth/login',
        json={'email': target['email'], 'password': 'WrongPass123!'},
    )
    assert response.status_code == 401


async def test_banned_existing_session_stops_working(client):
    """Валидная JWT-сессия не переживает блокировку: дальше — 403 на всё."""
    target = await register_user(client)
    target_cookies = dict(client.cookies)
    await admin_client(client)
    resp = await client.post(f"/api/v1/admin/ban/{target['id']}")
    assert resp.status_code == 200, resp.text

    client.cookies.clear()
    for key, value in target_cookies.items():
        client.cookies.set(key, value)

    for path in ('/api/v1/', f"/api/v1/user/{target['id']}"):
        response = await client.get(path)
        assert response.status_code == 403, (path, response.text)
        assert response.json()['detail'] == 'Account is blocked', path

    # Проверка «есть ли сессия» не врёт: заблокированный — «не вошёшь».
    response = await client.get('/api/v1/auth/')
    assert response.status_code == 200


async def test_unban_restores_access(client):
    """После разблокировки вход и профиль снова работают."""
    target = await _banned_user(client)
    resp = await client.post(f"/api/v1/admin/unban/{target['id']}")
    assert resp.status_code == 200, resp.text

    client.cookies.clear()
    await login_user(client, target['email'])
    profile = await client.get('/api/v1/')
    assert profile.status_code == 200
    assert profile.json()['id'] == target['id']
    assert profile.json()['isActive'] is True


async def test_profile_read_restricted_to_self_and_admin(client):
    """Чужой профиль не читается: UserResponse раскрывает email и телефон.

    Раньше ``GET /user/{id}`` отдавал полный профиль любому вошедшему — при
    публичном доступе это утечка персональных данных по одному id. Интерфейсу
    чужие профили не нужны: страница профиля работает со своим id, админка —
    с маршрутом списка пользователей.
    """
    target = await register_user(client)

    # Сессия другого пользователя: чужой профиль не читается.
    other = await register_user(client)
    response = await client.get(f"/api/v1/user/{target['id']}")
    assert response.status_code == 403, response.text
    assert response.json()['detail'] == 'You can only view your own profile'

    # Свой профиль по id читается, как и раньше.
    response = await client.get(f"/api/v1/user/{other['id']}")
    assert response.status_code == 200, response.text
    assert response.json()['id'] == other['id']

    # Администратор читает любой профиль (админка, модерация).
    await admin_client(client)
    response = await client.get(f"/api/v1/user/{target['id']}")
    assert response.status_code == 200, response.text
    assert response.json()['id'] == target['id']


# ------------------------- Истечение access и ротация refresh -------------------------


def _decode(token: str) -> dict:
    return pyjwt.decode(token, JWT_KEY, algorithms=['HS256'])


def _craft_token(sub: str, sid: str, *, typ: str, expired: bool) -> str:
    """Свой токен той же формы, что выдаёт сервер (для сценариев истечения)."""
    delta = timedelta(seconds=-10 if expired else 600)
    return pyjwt.encode(
        {
            'sub': sub,
            'sid': sid,
            'typ': typ,
            'iat': datetime.now(timezone.utc),
            'exp': datetime.now(timezone.utc) + delta,
        },
        JWT_KEY,
        algorithm='HS256',
    )


def _sync_cookies(client, response) -> None:
    """Пересобрать cookie-джар клиента ровно по Set-Cookie ответа.

    httpx хранит cookie, выставленные вручную (``.set``), и пришедшие из
    ответа как разные записи одного имени: при отправке в заголовок Cookie
    могут попасть обе. Нормализация избавляет тесты от этой неопределённости.
    """
    client.cookies.clear()
    for name, value in response.cookies.items():
        client.cookies.set(name, value)


async def test_expired_access_is_401_not_silent_refresh_fallback(client):
    """Истёкший access — явный 401 «Access token expired», не decode refresh.

    Раньше jwt_check молча декодировал refresh-куку как access: сессия
    «работала» без ротации и без ревокации. Теперь клиент обязан прийти в
    POST /auth/refresh.
    """
    user = await register_user(client)
    refresh_claims = _decode(client.cookies['refresh_jwt'])
    expired = _craft_token(
        user['id'], refresh_claims['sid'], typ='access', expired=True,
    )
    client.cookies.clear()
    client.cookies.set('access_jwt', expired)

    response = await client.get('/api/v1/')
    assert response.status_code == 401
    assert response.json()['detail'] == 'Access token expired'


async def test_refresh_rotates_tokens_and_extends_session(client):
    """POST /auth/refresh ротирует пару токенов; старый refresh становится prev."""
    user = await register_user(client)
    old_refresh = client.cookies['refresh_jwt']
    old_access = client.cookies['access_jwt']

    response = await client.post('/api/v1/auth/refresh')
    assert response.status_code == 200, response.text
    _sync_cookies(client, response)

    new_refresh = client.cookies['refresh_jwt']
    new_access = client.cookies['access_jwt']
    assert new_refresh != old_refresh
    assert new_access != old_access
    assert _decode(new_refresh)['sid'] == _decode(old_refresh)['sid']
    assert _decode(new_access)['sub'] == user['id']

    profile = await client.get('/api/v1/')
    assert profile.status_code == 200
    assert profile.json()['id'] == user['id']


async def test_refresh_with_expired_access_cookie_still_works(client):
    """Refresh не требует валидного access: именно ради его истечения клиент и приходит."""
    user = await register_user(client)
    refresh_token = client.cookies['refresh_jwt']
    refresh_claims = _decode(refresh_token)
    expired = _craft_token(
        user['id'], refresh_claims['sid'], typ='access', expired=True,
    )
    client.cookies.clear()
    client.cookies.set('access_jwt', expired)
    client.cookies.set('refresh_jwt', refresh_token)

    response = await client.post('/api/v1/auth/refresh')
    assert response.status_code == 200, response.text
    _sync_cookies(client, response)

    profile = await client.get('/api/v1/')
    assert profile.status_code == 200


async def test_refresh_requires_cookie(client):
    response = await client.post('/api/v1/auth/refresh')
    assert response.status_code == 401
    assert response.json()['detail'] == 'Refresh token missing'


async def test_access_token_is_not_accepted_as_refresh(client):
    """Claim typ не даёт подменить тип токена при том же секрете."""
    await register_user(client)
    access_token = client.cookies['access_jwt']
    client.cookies.clear()
    client.cookies.set('refresh_jwt', access_token)

    response = await client.post('/api/v1/auth/refresh')
    assert response.status_code == 403
    assert response.json()['detail'] == 'Invalid refresh token'


async def test_expired_refresh_token_is_401(client):
    user = await register_user(client)
    claims = _decode(client.cookies['refresh_jwt'])
    expired = _craft_token(
        user['id'], claims['sid'], typ='refresh', expired=True,
    )
    client.cookies.clear()
    client.cookies.set('refresh_jwt', expired)

    response = await client.post('/api/v1/auth/refresh')
    assert response.status_code == 401
    assert response.json()['detail'] == 'Refresh token expired'


async def test_reused_rotated_refresh_token_revokes_session(client):
    """Повтор украденного ротированного токена отзывает сессию целиком.

    Первый ротированный токен ещё живёт в grace-окне (конкурентные вкладки),
    поэтому для сценария reuse нужны две ротации: тогда украденный токен не
    совпадает ни с текущим, ни с предыдущим — и сессия отзывается.
    """
    await register_user(client)
    stolen = client.cookies['refresh_jwt']

    response = await client.post('/api/v1/auth/refresh')
    assert response.status_code == 200
    response = await client.post('/api/v1/auth/refresh')
    assert response.status_code == 200
    current = client.cookies['refresh_jwt']

    client.cookies.clear()
    client.cookies.set('refresh_jwt', stolen)
    response = await client.post('/api/v1/auth/refresh')
    assert response.status_code == 401

    # Сессия отозвана: и «хороший» ротированный токен теперь бесполезен.
    client.cookies.clear()
    client.cookies.set('refresh_jwt', current)
    response = await client.post('/api/v1/auth/refresh')
    assert response.status_code == 401


async def test_concurrent_refresh_within_grace_returns_current_token(client):
    """Вторая вкладка в grace-окне получает текущий токен без новой ротации."""
    await register_user(client)
    first = client.cookies['refresh_jwt']

    response = await client.post('/api/v1/auth/refresh')
    assert response.status_code == 200
    _sync_cookies(client, response)
    current = client.cookies['refresh_jwt']
    assert current != first

    # Вкладка, успевшая отправить уже ротированный токен, не должна получить
    # 401 и разлогинить пользователя — она получает актуальный токен.
    client.cookies.clear()
    client.cookies.set('refresh_jwt', first)
    response = await client.post('/api/v1/auth/refresh')
    assert response.status_code == 200, response.text
    _sync_cookies(client, response)
    assert client.cookies['refresh_jwt'] == current

    # Сессия жива: текущий токен ротируется дальше как обычно.
    response = await client.post('/api/v1/auth/refresh')
    assert response.status_code == 200
    _sync_cookies(client, response)
    assert client.cookies['refresh_jwt'] != current


async def test_logout_revokes_refresh_session(client):
    """После logout старый refresh-токен не может воскресить сессию."""
    await register_user(client)
    refresh_token = client.cookies['refresh_jwt']

    response = await client.post('/api/v1/auth/logout')
    assert response.status_code == 200
    assert 'access_jwt' not in client.cookies
    assert 'refresh_jwt' not in client.cookies

    client.cookies.set('refresh_jwt', refresh_token)
    response = await client.post('/api/v1/auth/refresh')
    assert response.status_code == 401


async def test_logout_without_tokens_is_401(client):
    response = await client.post('/api/v1/auth/logout')
    assert response.status_code == 401
    assert response.json()['detail'] == 'Access token missing'