import asyncio
import os
from celery import Celery, Task

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    host = os.getenv("REDIS_HOST", "localhost")
    port = os.getenv("REDIS_PORT", "6379")
    REDIS_URL = f"redis://{host}:{port}/0"

task_queue = Celery(
    "main",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

task_queue.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    imports=(
        "app.database.users",
        "app.database.events",
        "app.middlewares.parse_tables.pdf_processing",
        "app.middlewares.parse_tables.sql_processing",
    ),
)


class AsyncCeleryTask(Task):
    """
    Base task class that executes ``async def`` tasks.

    Celery's default prefork worker has no event loop, so a task defined
    with ``async def`` would return an unawaited coroutine instead of running.
    This base class detects coroutine tasks and drives them to completion with
    ``asyncio.run()`` inside the worker process.
    """

    def __call__(self, *args, **kwargs):
        if asyncio.iscoroutinefunction(self.run):
            return asyncio.run(self.run(*args, **kwargs))
        return super().__call__(*args, **kwargs)


async def run_task(task, *args, timeout=None, **kwargs):
    """
    Dispatch a Celery task to the broker and await its result.

    Celery rules: tasks must be invoked via ``.delay()`` / ``.apply_async()``
    so they are executed by a worker (calling the task object directly would
    run it in-process and bypass the broker). Arguments must be
    JSON-serializable. The blocking ``AsyncResult.get()`` is moved to a thread
    so it doesn't stall the event loop.
    """
    result = task.delay(*args, **kwargs)
    return await asyncio.to_thread(result.get, timeout=timeout)
