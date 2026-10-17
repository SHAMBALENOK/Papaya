"""Идентификатор запроса: сквозная корреляция логов и ответов.

Каждому HTTP-запросу присваивается ``request_id`` (из входящего заголовка
``X-Request-ID``, если он есть, иначе сгенерированный). Он возвращается клиенту
в ответе и подставляется в каждую строку лога через контекстную переменную, так
что по одному запросу можно собрать всю историю его обработки — включая записи
аудита административных действий.

Middleware — «чистый ASGI», а не ``BaseHTTPMiddleware``: последний исполняет
приложение в отдельной задаче, из-за чего контекстные переменные, выставленные
в middleware, не всегда видны обработчику. Здесь приложение вызывается в том же
контексте, поэтому ``request_id`` доступен и в маршруте, и в логгере.
"""

import logging
import uuid
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar('request_id', default='-')

#: Заголовок, которым идентификатор приходит и уходит.
REQUEST_ID_HEADER = 'x-request-id'


class RequestIdFilter(logging.Filter):
    """Добавить ``request_id`` в каждую запись лога."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def current_request_id() -> str:
    """Идентификатор текущего запроса (``-`` вне запроса)."""
    return request_id_ctx.get()


def _clean(value: str | None) -> str:
    """Заголовок не должен ломать логи: только короткие безопасные символы."""
    if not value:
        return uuid.uuid4().hex
    cleaned = ''.join(ch for ch in value if ch.isalnum() or ch in '-_.')[:128]
    return cleaned or uuid.uuid4().hex


class RequestIdMiddleware:
    """ASGI-middleware: назначить ``request_id`` и вернуть его в ответе."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        headers = {k.decode('latin-1').lower(): v for k, v in scope.get('headers', [])}
        incoming = headers.get(REQUEST_ID_HEADER)
        request_id = _clean(incoming.decode('latin-1') if incoming else None)

        token = request_id_ctx.set(request_id)
        scope.setdefault('state', {})['request_id'] = request_id

        async def send_with_header(message):
            if message['type'] == 'http.response.start':
                headers_list = list(message.get('headers', []))
                headers_list.append(
                    (REQUEST_ID_HEADER.encode('latin-1'), request_id.encode('latin-1'))
                )
                message = {**message, 'headers': headers_list}
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            request_id_ctx.reset(token)
