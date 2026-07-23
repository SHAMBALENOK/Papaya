import pytest
import asyncio
import asyncpg
from httpx import AsyncClient
import time
import os

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:5000")
DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")


@pytest.fixture(scope="session")
def event_loop():
    """Event loop для всех тестов"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_pool():
    """Пул соединений с БД для тестов"""
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    yield pool
    await pool.close()


@pytest.fixture
async def client():
    """HTTP клиент для API тестов"""
    async with AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        yield c


@pytest.fixture
async def test_user(client):
    """Создание тестового пользователя"""
    user_data = {
        "username": f"testuser_{int(time.time())}",
        "email": f"test_{int(time.time())}@example.com",
        "password": "TestPassword123!",
        "role": "student"
    }
    response = await client.post("/auth/register", data=user_data)
    return {"data": user_data, "response": response}


@pytest.fixture
async def authenticated_user(client, test_user):
    """Аутентифицированный пользователь"""
    login_data = {
        "username": test_user["data"]["username"],
        "password": test_user["data"]["password"]
    }
    response = await client.post("/auth/login", data=login_data)
    cookies = response.cookies
    return {
        "user": test_user,
        "cookies": cookies,
        "login_response": response
    }