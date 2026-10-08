"""Регистрация, вход и выход: жизненный цикл сессии."""

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