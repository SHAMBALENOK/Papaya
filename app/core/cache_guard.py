"""Устойчивость кэш-записей после COMMIT в БД.

Запись в Redis выполняется уже после успешного COMMIT в PostgreSQL. Отказ кэша
не должен превращать успешную операцию в 500: иначе клиент повторит запрос и
получит дубликат (например, повторную регистрацию). Ошибка кэша логируется,
а ответ строится на подтверждённых данных из БД.
"""

import logging

logger = logging.getLogger('papaya.cache')


async def safe_cache_write(coro) -> None:
    """Исполнить кэш-запись, не дав ошибке Redis провалить HTTP-запрос."""
    try:
        await coro
    except Exception:
        logger.exception('Cache write failed; committed data is authoritative')