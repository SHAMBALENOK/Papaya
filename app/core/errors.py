"""Глобальные обработчики ошибок и конфигурация логирования.

Клиенту не должны утекать внутренние детали исключений (стектрейсы, пути,
значения переменных): ошибка логируется на сервере, а клиент получает
стандартный JSON ``{"detail": "Internal server error"}``.
"""

import logging

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from app.middlewares.request_id import RequestIdFilter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s',
)

# Фильтр добавляет request_id в каждую запись. Он ставится на обработчики
# корневого логгера, через которые проходят записи всех модулей приложения.
for _handler in logging.getLogger().handlers:
    _handler.addFilter(RequestIdFilter())

logger = logging.getLogger('papaya')


def install_exception_handlers(app: FastAPI) -> None:
    """Зарегистрировать обработчик необработанных исключений.

    FastAPI/Starlette продолжают обрабатывать HTTPException и ошибки валидации
    Pydantic собственными (более специфичными) обработчиками; этот обработчик
    срабатывает только для непредвиденных исключений.
    """

    @app.exception_handler(Exception)
    async def _unhandled_exception(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception(
            'Unhandled exception on %s %s',
            request.method,
            request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={'detail': 'Internal server error'},
        )