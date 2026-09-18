"""Маршруты проверки здоровья приложения.

- ``/api/v1/health`` — liveness: процесс жив и отвечает на HTTP.
- ``/api/v1/ready`` — readiness: доступны PostgreSQL и Redis, приложение
  готово принимать трафик.
"""

import logging

import redis.asyncio as aioredis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import REDIS_URL
from app.database.database import engine

logger = logging.getLogger('papaya.health')

health_page = APIRouter(prefix='/api/v1', tags=['health'])


@health_page.get('/health')
async def health():
    """Liveness-проба (используется docker healthcheck)."""
    return JSONResponse(status_code=200, content={'status': 'ok'})


@health_page.get('/ready')
async def ready():
    """Readiness-проба: PostgreSQL и Redis доступны."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text('SELECT 1'))
    except Exception:
        logger.exception('Readiness check failed: database is unreachable')
        return JSONResponse(
            status_code=503,
            content={'status': 'degraded', 'component': 'database'},
        )

    try:
        client = aioredis.from_url(REDIS_URL)
        try:
            await client.ping()
        finally:
            await client.aclose()
    except Exception:
        logger.exception('Readiness check failed: redis is unreachable')
        return JSONResponse(
            status_code=503,
            content={'status': 'degraded', 'component': 'redis'},
        )

    return JSONResponse(status_code=200, content={'status': 'ready'})