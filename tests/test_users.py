import pytest
import asyncio


@pytest.mark.integration
class TestUsers:
    """Тесты пользователей"""

    async def test_view_user_profile(self, client, authenticated_user):
        """Просмотр профиля пользователя"""
        user_id = authenticated_user["user"]["data"]["username"]
        response = await client.get(
            f"/user/{user_id}",
            cookies=authenticated_user["cookies"]
        )
        assert response.status_code == 200

    async def test_edit_user_profile(self, client, authenticated_user):
        """Редактирование профиля"""
        user_id = authenticated_user["user"]["data"]["username"]
        edit_data = {
            "bio": "Updated bio for testing"
        }
        response = await client.post(
            f"/user/{user_id}/edit_info",
            data=edit_data,
            cookies=authenticated_user["cookies"]
        )
        assert response.status_code in [200, 302]

    async def test_view_profile_unauthorized(self, client):
        """Просмотр профиля без авторизации"""
        response = await client.get("/user/someuser")
        assert response.status_code in [401, 302]

    async def test_edit_profile_unauthorized(self, client):
        """Редактирование профиля без авторизации"""
        edit_data = {"bio": "Unauthorized edit"}
        response = await client.post("/user/someuser/edit_info", data=edit_data)
        assert response.status_code in [401, 302]