"""Нормализация строк импорта: названия, предметы, уровни, годы."""

import re

# Изделие из database/olympiads.normalize_name — избегаем дублирования.
from app.database.olympiads import normalize_name as _normalize_name

normalize_name = _normalize_name

_LEVEL_ALIASES = {
    '1': {'1', 'первый', 'первого', '1-й', '1ый', 'i', 'ⅰ', 'первый уровень'},
    '2': {'2', 'второй', 'второго', '2-й', '2ой', 'ii', 'ⅱ', 'второй уровень'},
    '3': {'3', 'третий', 'третьего', '3-й', '3ий', 'iii', 'ⅲ', 'третий уровень'},
}
_LEVEL_NUM_RE = re.compile(
    r'(\d+)\s*(?:-й|ый| ой)?\s*уровн', re.IGNORECASE
)
_LEVEL_WORD_RE = re.compile(r'\b(первый|второй|третий)\b', re.IGNORECASE)
_YEAR_RE = re.compile(r'\b(20\d{2})\b')


def normalize_subjects(subjects) -> list[str]:
    """Привести список предметов/профилей к единому виду: lower, ё->е, dedupe."""
    seen = set()
    result = []
    for item in subjects or []:
        if not item:
            continue
        norm = ' '.join(str(item).casefold().replace('ё', 'е').split())
        if not norm or norm in seen:
            continue
        seen.add(norm)
        result.append(norm)
    return result


def normalize_level(value) -> str | None:
    """Распознать уровень олимпиады из произвольного текста.

    Возвращает '1'/'2'/'3' или None (не распознано -> требует проверки).
    """
    if not value:
        return None
    text = ' '.join(str(value).casefold().replace('ё', 'е').split())

    match = _LEVEL_NUM_RE.search(text)
    if match:
        level = match.group(1)
        if level in _LEVEL_ALIASES:
            return level
        return None
    match = _LEVEL_WORD_RE.search(text)
    if match:
        for level, aliases in _LEVEL_ALIASES.items():
            if match.group(1) in aliases:
                return level
    if text.strip() in {'1', '2', '3'}:
        return text.strip()
    return None


def normalize_levels(values) -> list[str]:
    """Множественные уровни: дедуп и сортировка."""
    result = []
    for value in values or []:
        level = normalize_level(value)
        if level and level not in result:
            result.append(level)
    return sorted(result)


def extract_years(text) -> list[str]:
    """Найти годы (20xx) в произвольном тексте."""
    return sorted(set(_YEAR_RE.findall(' '.join(str(text).split())) if text else []))