import pytest
import asyncio


@pytest.mark.integration
class TestAuth:
    """Тесты аутентификации"""

    async def test_register_success(self, client):
        """Успешная регистрация пользователя"""
        user_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "Password123!",
            "role": "student"
        }
        response = await client.post("/auth/register", data=user_data)
        assert response.status_code in [200, 302]

    async def test_register_duplicate_username(self, client, test_user):
        """Регистрация с существующим username"""
        user_data = {
            "username": test_user["data"]["username"],
            "email": "another@example.com",
            "password": "Password123!",
            "role": "student"
        }
        response = await client.post("/auth/register", data=user_data)
        assert response.status_code in [400, 200]

    async def test_login_success(self, client, test_user):
        """Успешный вход"""
        login_data = {
            "username": test_user["data"]["username"],
            "password": test_user["data"]["password"]
        }
        response = await client.post("/auth/login", data=login_data)
        assert response.status_code in [200, 302]

    async def test_login_wrong_password(self, client, test_user):
        """Вход с неверным паролем"""
        login_data = {
            "username": test_user["data"]["username"],
            "password": "WrongPassword123!"
        }
        response = await client.post("/auth/login", data=login_data)
        assert response.status_code in [401, 400]

    async def test_logout(self, client, authenticated_user):
        """Выход из системы"""
        response = await client.get(
            "/logout",
            cookies=authenticated_user["cookies"]
        )
        assert response.status_code in [200, 302]

    async def test_auth_page_loads(self, client):
        """Загрузка страницы авторизации"""
        response = await client.get("/auth")
        assert response.status_code == 200
        assert "html" in response.headers.get("content-type", "")