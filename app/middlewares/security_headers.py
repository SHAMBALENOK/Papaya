"""Заголовки безопасности для всех HTTP-ответов.

Заголовки не зависят от конкретного маршрута, поэтому ставятся один раз
middleware-слоем — включая ответы об ошибках и статику. CSP намеренно
ограничена директивами, которые не ломают текущий фронтенд (Tailwind Play
CDN и Google Fonts грузятся как внешние ресурсы): запрещаем встраивание в
iframe, смену ``base`` и плагины, но не сужаем ``script-src``.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: CSP без ограничения источников скриптов: SPA использует inline-обработчики
#: (``onerror`` у изображений) и Tailwind Play CDN. Остальные директивы
#: закрывают кликджекинг, подмену base-URL и legacy-плагины.
CONTENT_SECURITY_POLICY = (
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "form-action 'self'"
)

BASE_HEADERS = {
    'x-content-type-options': 'nosniff',
    'x-frame-options': 'DENY',
    'referrer-policy': 'strict-origin-when-cross-origin',
    'permissions-policy': 'geolocation=(), microphone=(), camera=(), payment=(), usb=()',
    'content-security-policy': CONTENT_SECURITY_POLICY,
}

#: HSTS имеет смысл только на HTTPS-домене; заголовок отправляется лишь в
#: production, чтобы не «залипать» на локальном HTTP.
HSTS_HEADER = 'max-age=31536000; includeSubDomains'


class SecurityHeadersMiddleware:
    """ASGI-middleware: добавить защитные заголовки к каждому ответу."""

    def __init__(self, app: ASGIApp, *, hsts: bool = False):
        self.app = app
        self.hsts = hsts

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message['type'] == 'http.response.start':
                headers = MutableHeaders(scope=message)
                for name, value in BASE_HEADERS.items():
                    headers[name] = value
                if self.hsts:
                    headers['strict-transport-security'] = HSTS_HEADER
            await send(message)

        await self.app(scope, receive, send_with_headers)
