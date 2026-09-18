"""Регистрация, вход и выход: жизненный цикл сессии."""

from tests.conftest import register_user


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