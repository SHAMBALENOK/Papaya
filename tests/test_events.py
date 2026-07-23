import pytest
import asyncio


@pytest.mark.integration
class TestEvents:
    """Тесты событий/олимпиад"""

    async def test_view_events_list(self, client, authenticated_user):
        """Просмотр списка событий"""
        response = await client.get("/", cookies=authenticated_user["cookies"])
        assert response.status_code == 200

    async def test_view_single_event(self, client, authenticated_user):
        """Просмотр отдельного события"""
        response = await client.get(
            "/event/1",
            cookies=authenticated_user["cookies"]
        )
        assert response.status_code in [200, 404]

    async def test_add_event(self, client, authenticated_user):
        """Создание нового события"""
        event_data = {
            "title": f"Test Olympiad {asyncio.get_event_loop().time()}",
            "description": "Test description",
            "date": "2026-12-01",
            "location": "Moscow"
        }
        user_id = authenticated_user["user"]["data"]["username"]
        response = await client.post(
            f"/user/{user_id}/add_event",
            data=event_data,
            cookies=authenticated_user["cookies"]
        )
        assert response.status_code in [200, 302]

    async def test_edit_event(self, client, authenticated_user):
        """Редактирование события"""
        user_id = authenticated_user["user"]["data"]["username"]
        edit_data = {
            "title": "Updated Olympiad Title",
            "description": "Updated description"
        }
        response = await client.post(
            f"/user/{user_id}/1/edit_event",
            data=edit_data,
            cookies=authenticated_user["cookies"]
        )
        assert response.status_code in [200, 302, 404]

    async def test_view_events_unauthorized(self, client):
        """Просмотр событий без авторизации"""
        response = await client.get("/")
        assert response.status_code in [401, 302]