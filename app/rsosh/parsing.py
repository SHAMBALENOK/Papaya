"""RSOSH-импорт: преобразование таблицы (XLSX) в «сырые» записи олимпиад.

Обработка только локальная и детерминированная: никаких внешних API.
Извлечение имен колонок повторяет эвристики parse_tables, но сохраняется в
REST-слое импорта отдельно, чтобы RSOSH-пайплайн не зависел от legacy-кода
событий (который в конце миграции удаляется).
"""

import re

import pandas as pd

_NAME_MARKERS = ('назван', 'наименован', 'заголов', 'name', 'title')
_OLYMPIAD_MARKERS = ('олимпиад', 'мероприят', 'перечн', 'contest', 'olympiad')
_SUBJECT_MARKERS = ('предмет', 'профил', 'subject', 'profile')
_LEVEL_MARKERS = ('уров', 'level')
_NEGATIVE_MARKERS = ('возраст', 'класс', 'участник', 'регион', 'субъект',
                     'телефон', 'email', 'дата', 'сумма', 'приз')
_YEAR_RE = re.compile(r'\b(20\d{2})\b')


def _column_score(header: str) -> int:
    norm = ' '.join(str(header).casefold().replace('ё', 'е').split())
    score = 0
    if any(marker in norm for marker in _NAME_MARKERS):
        score += 200
    if any(marker in norm for marker in _OLYMPIAD_MARKERS):
        score += 40
    if any(marker in norm for marker in _SUBJECT_MARKERS):
        score -= 60
    if any(marker in norm for marker in _LEVEL_MARKERS):
        score -= 80
    if any(marker in norm for marker in _NEGATIVE_MARKERS):
        score -= 150
    return score


def _classify(headers: list[str]) -> tuple[int, int | None, int | None]:
    """Вернуть индексы колонок: [название, предметы|профили, уровень]."""
    name_index = max(range(len(headers)), key=lambda i: _column_score(headers[i]))
    level_index = None
    subject_index = None
    for index, header in enumerate(headers):
        norm = ' '.join(str(header).casefold().replace('ё', 'е').split())
        if index == name_index:
            continue
        if subject_index is None and any(
            marker in norm for marker in _SUBJECT_MARKERS
        ):
            subject_index = index
        elif level_index is None and any(
            marker in norm for marker in _LEVEL_MARKERS
        ):
            level_index = index
    return name_index, subject_index, level_index


def parse_xlsx(xlsx_path: str) -> list[dict]:
    """Извлечь сырые записи об олимпиадах из таблицы.

    Пропускаются пустые строки и «служебные» строки (примечания к приказу).
    Для каждой записи собираются годы (20xx), встречающиеся в любых ячейках.
    """
    table = pd.ExcelFile(xlsx_path).parse().ffill()
    if table.empty:
        return []

    headers = [str(column).replace('\n', ' ').strip() for column in table.columns]
    name_index, subject_index, level_index = _classify(headers)

    raw_records = []
    for row_index, row in table.iterrows():
        name_value = row.iloc[name_index]
        if pd.isna(name_value):
            continue
        name = str(name_value).replace('\n', ' ').strip()
        if not name or name.casefold() in {'null', 'nan', 'итого'}:
            continue

        subjects_raw = []
        levels_raw = []
        description_parts = []
        years = set()
        for column_index, header in enumerate(headers):
            value = row.iloc[column_index]
            if pd.isna(value):
                continue
            text = str(value).replace('\n', ' ').strip()
            if not text or text.casefold() in {'null', 'nan'}:
                continue
            years.update(_YEAR_RE.findall(text))
            if column_index == name_index:
                continue
            if column_index == subject_index:
                subjects_raw.append(text)
            elif column_index == level_index:
                levels_raw.append(text)
            else:
                description_parts.append(f'{header}: {text}')

        raw_records.append(
            {
                'raw_name': name,
                'subjects_raw': subjects_raw,
                'levels_raw': levels_raw,
                'years': sorted(years),
                'description': '\n'.join(description_parts),
                'source_row': int(row_index) + 2,
            }
        )
    return raw_records