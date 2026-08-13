from contextlib import asynccontextmanager
from typing import AsyncGenerator
import redis.asyncio as aioredis
from fastapi import FastAPI, Request
import os

REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = int(os.getenv('REDIS_PORT'))

@asynccontextmanager
async def redis_lifespan(app: FastAPI):
    app.state.redis_pool = aioredis.ConnectionPool(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        max_connections=20
    )
    yield
    await app.state.redis_pool.disconnect()

async def get_redis(request: Request) -> AsyncGenerator[aioredis.Redis, None]:
    pool = request.app.state.redis_pool
    client = aioredis.Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.close()