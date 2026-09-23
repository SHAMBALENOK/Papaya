"""RSOSH-импорт: сопоставление записей с существующими олимпиадами и организациями.

Сопоставление происходит по нормализованному названию (точное совпадение).
Размытого («fuzzy») сопоставления в v1 нет: ошибочная автосклейка двух разных
олимпиад опаснее ручной проверки, поэтому при малейших сомнениях кандидат
уходит в NEEDS_REVIEW, а не «подтягивается» к похожему названию.
"""

import re

from app import database
from app.rsosh import normalization as norm
from app.rsosh import states


_SEPARATOR_RE = re.compile(r'[;]|(?:\s*[,/]\s*)|\n')


def _split_tokens(values) -> list[str]:
    """Разбить набор ячеек на отдельные токены (предметы/профили/уровни)."""
    tokens = []
    for value in values or []:
        if not value:
            continue
        for piece in _SEPARATOR_RE.split(str(value)):
            piece = ' '.join(piece.split()).strip(' .')
            if piece:
                tokens.append(piece)
    return tokens


async def match_records(records: list[dict], doc: dict) -> list[dict]:
    """Преобразовать сырые записи в кандидатов с полями RSOSH-секции.

    Возможные action: create (новой), merge (объединить с существующей),
    skip (точный дубликат без новых данных). Организация-загрузчик
    (``doc.organization_id``) становится организатором новой олимпиады.
    """
    candidates = []
    for record in records:
        name = record['raw_name']
        subjects = norm.normalize_subjects(_split_tokens(record['subjects_raw']))
        levels = norm.normalize_levels(_split_tokens(record['levels_raw']))
        years = norm.extract_years(' '.join(record['years']))

        name_norm = norm.normalize_name(name)
        existing = await database.olympiads.find_olympiad_by_name_norm(name_norm)
        action = states.ACTION_MERGE if existing else states.ACTION_CREATE

        candidate = {
            'name': name,
            'name_norm': name_norm,
            'subjects': subjects,
            'levels': levels,
            'years': years,
            'description': record['description'],
            'action': action,
            'matched_olympiad_id': existing['id'] if existing else None,
            'confidence': 'ok',
            'reviews': [],
            'persisted': False,
        }
        candidates.append(candidate)
    return candidates