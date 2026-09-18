"""Проверка жизнеспособности приложения и его зависимостей."""

async def test_liveness(client):
    response = await client.get('/api/v1/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


async def test_readiness(client):
    response = await client.get('/api/v1/ready')
    assert response.status_code == 200
    assert response.json() == {'status': 'ready'}


async def test_unknown_api_route_is_json_404(client):
    """Опечатка в API-пути даёт JSON 404, а не SPA-заглушку index.html."""
    response = await client.get('/api/v1/does_not_exist')
    assert response.status_code == 404
    assert response.headers['content-type'].startswith('application/json')
    assert response.json() == {'detail': 'Not found'}