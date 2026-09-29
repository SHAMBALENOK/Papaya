"""Проверка внешних ссылок каталога.

В каталоге есть поля, которые интерфейс вставляет в ``href``/``src``
(``website``, ``official_url``, ``preview_image``, ``image``, ``source_url``).
Поэтому значение приходит из данных: ручной ввод администратора или разбор
документа РСОШ. Без проверки схемы туда можно положить ``javascript:`` — и
страница каталога выполнит это как ссылку.

Правило одно и общее для всех ссылок: внешняя ссылка — это ``http`` или
``https`` с хостом. Всё остальное (``javascript:``, ``data:``, ``file:``,
``vbscript:``, строки без схемы или с пробелами) отклоняется. Пустая строка
трактуется как «ссылки нет»: формы отправляют пустое поле вместо отсутствующего,
и ``''`` превращается в ``None`` вместо ошибки.

Тип ``ExternalUrl`` — обёртка над ``Optional[str]`` с after-валидатором,
поэтому объявление поля остаётся таким же, как было, а проверка живёт в одном
месте для всех схем.
"""

from typing import Annotated, Optional
from urllib.parse import urlsplit

from pydantic import AfterValidator

# Схемы, которые имеют смысл для ссылки в каталоге. Всё, что не входит в
# список, отклоняется: белый список безопаснее, чем чёрный.
ALLOWED_URL_SCHEMES = ('http', 'https')


def _validate_external_url(value: str | None) -> str | None:
    if value is None:
        return None
    url = value.strip()
    if not url:
        # «Ссылка не заполнена» — это отсутствие значения, а не ошибка ввода.
        return None

    # Пробелы внутри ссылки ломают разбор и позволяют обойти проверку схемы
    # («java script:» и подобное), поэтому запрещаем их явно.
    if any(char.isspace() for char in url):
        raise ValueError('URL не должен содержать пробелов')

    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise ValueError(f'Некорректный URL: {exc}') from exc

    if parts.scheme.lower() not in ALLOWED_URL_SCHEMES:
        raise ValueError(
            'URL должен начинаться с http:// или https:// '
            f'(получена схема: {parts.scheme or "нет"})'
        )
    if not parts.netloc:
        raise ValueError('URL должен содержать домен')
    return url


#: Внешняя ссылка каталога. Пустая строка превращается в ``None``.
ExternalUrl = Annotated[Optional[str], AfterValidator(_validate_external_url)]
