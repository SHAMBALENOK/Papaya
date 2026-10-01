"""Общие помощники поиска и нормализации имён каталога Papaya.

Одно и то же правило нормализации используется в двух местах:

- поиск по каталогам (``app.database.search``) — чтобы запрос пользователя
  находил запись независимо от регистра, лишних пробелов, переносов строк
  внутри ячейки и написания буквы «ё»;
- импорт РСОШ (``app.rsosh``) — чтобы одинаковые олимпиады из разных
  документов сопоставлялись друг с другом.

Поэтому правило живёт здесь, а не дублируется в слоях доступа к данным.
"""

import re
import unicodedata

from sqlalchemy import func

_SPACES = re.compile(r'\s+')
_WHITESPACE = re.compile(r'[\s\u00a0]+')
_EDGE_PUNCT = re.compile(r'^[\s\W_]+|[\s\W_]+$', re.UNICODE)
_INNER_PUNCT = re.compile(r'[\s\W_]+', re.UNICODE)


def collapse_whitespace(value: str | None) -> str:
    """Схлопнуть любые пробельные символы (в т.ч. переводы строк) в один."""
    if not value:
        return ''
    return _WHITESPACE.sub(' ', value).strip()


def comparable_text(value: str | None) -> str:
    """Привести значение к виду, сопоставимому с пользовательским запросом.

    Импорт РСОШ берёт название из многострочной ячейки, поэтому в каталоге
    встречаются названия вида «Всероссийская\\nолимпиада\\nшкольников».
    Пользователь печатает обычную фразу с пробелами и ничего не находит:
    пробел в запросе не совпадает с переводом строки в базе. Здесь любые
    пробельные символы приводятся к одному пробелу — правятся только условия
    поиска, данные не меняются.
    """
    return collapse_whitespace(value)


def comparable_text_sql(column):
    """SQL-версия :func:`comparable_text` для поиска по колонке.

    То же правило, но на стороне PostgreSQL: ``regexp_replace`` схлопывает
    пробелы, табы и переводы строк прямо в условии ``LIKE``.
    """
    return func.coalesce(
        func.regexp_replace(func.coalesce(column, ''), r'\s+', ' ', 'g'),
        '',
    )


def normalize_name(value: str | None) -> str:
    """Нормализовать название для точного поиска дубликатов.

    Регистр, буква «ё», повторные пробелы, типографские кавычки и крайняя
    пунктуация не различаются: «Всероссийская олимпиада»,
    «всероссийская  олимпиада» и «“Всероссийская олимпиада“» — одна и та же
    олимпиада. Значимые символы названия сохраняются.
    """
    text = collapse_whitespace(value).casefold().replace('ё', 'е')
    text = unicodedata.normalize('NFKC', text)
    text = _EDGE_PUNCT.sub('', text)
    return _INNER_PUNCT.sub(' ', text).strip()


def like_pattern(search: str) -> str:
    """Построить LIKE-шаблон из пользовательского запроса.

    - лишние пробелы схлопываются;
    - ``%`` и ``_`` экранируются, иначе ввод пользователя превращался бы в
      шаблон LIKE и «100%» совпало бы с любой строкой.

    Регистр сравнения задаёт вызывающий код через ``ILIKE ... escape='\\'``.
    """
    collapsed = collapse_whitespace(search)
    escaped = (
        collapsed.replace('\\', '\\\\')
        .replace('%', '\\%')
        .replace('_', '\\_')
    )
    return f'%{escaped}%'
