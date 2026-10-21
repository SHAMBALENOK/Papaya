"""Сопоставление строк приказа с олимпиадами существующего каталога.

Ключевой инвариант: приказ вуза **не создаёт олимпиад**. Строка приказа либо
сопоставляется с уже существующей олимпиадой каталога (и даёт связь БВИ), либо
остаётся несопоставленной — тогда администратор выбирает олимпиаду вручную в
окне проверки, и без его выбора строка не применяется.

Сопоставление переиспользует ту же нечёткую логику, что и импорт РСОШ
(``app.rsosh.matching``): точное совпадение по ``name_norm``, затем близкие
длинные названия. Пороги те же — смысл сравнения названий не зависит от того,
из какого документа они взяты.
"""

from app.database import olympiads as db_olympiads
from app.rsosh.matching import MERGE_THRESHOLD, REVIEW_THRESHOLD, best_catalog_match
from app.university.types import UniversityCandidate, UniversityRecord

#: Порог близости, ниже которого название считается незнакомым каталогу.
UNMATCHED_REVIEW_THRESHOLD = REVIEW_THRESHOLD


def match_record(
    record: UniversityRecord,
    catalog: dict[str, dict],
) -> UniversityCandidate:
    """Сопоставить строку приказа с каталогом."""
    candidate = UniversityCandidate(
        olympiad_name=record.olympiad_name,
        name_norm=record.name_norm,
        meta=dict(record.meta),
        page=record.page,
        issues=list(record.issues),
    )

    olympiad, score = best_catalog_match(record.name_norm, catalog)
    if olympiad is None or score < UNMATCHED_REVIEW_THRESHOLD:
        # Каталог не знает такой олимпиады. Приказ её не создаёт: строку
        # показываем как несопоставленную и помечаем для администратора.
        candidate.confidence = 'review'
        candidate.issues.append(
            'Олимпиада не найдена в каталоге: выберите её вручную, '
            'иначе строка не будет применена'
        )
        return candidate

    candidate.olympiad_id = olympiad['id']
    candidate.matched_name = olympiad.get('name')
    candidate.match_score = score
    if score >= MERGE_THRESHOLD:
        candidate.confidence = 'ok'
    else:
        candidate.confidence = 'review'
        candidate.issues.append(
            'Похоже на «' + (olympiad.get('name') or '') + '» — проверьте'
        )
    return candidate


async def build_candidates(
    records: list[UniversityRecord],
) -> list[UniversityCandidate]:
    """Сопоставить все строки приказа с каталогом и схлопнуть повторы.

    Одна и та же олимпиада встречается в приказе для нескольких направлений:
    связь БВИ в модели одна на пару (университет, олимпиада), поэтому дубли
    внутри документа схлопываются, а характеристики строк объединяются в
    ``meta`` (список направлений/профилей).
    """
    catalog_list = await db_olympiads.list_olympiads(status=None)
    catalog = {item['name_norm']: item for item in catalog_list}

    candidates: dict[str, UniversityCandidate] = {}
    for record in records:
        candidate = match_record(record, catalog)
        existing = candidates.get(candidate.name_norm)
        if existing is None:
            candidates[candidate.name_norm] = candidate
            continue
        _merge_candidate(existing, candidate)
    return list(candidates.values())


def _merge_candidate(
    existing: UniversityCandidate,
    incoming: UniversityCandidate,
) -> None:
    """Схлопнуть дубль строки: оставляем лучшее сопоставление, объединяем meta."""
    if incoming.confidence == 'ok' and existing.confidence != 'ok':
        existing.olympiad_id = incoming.olympiad_id
        existing.matched_name = incoming.matched_name
        existing.match_score = incoming.match_score
        existing.confidence = 'ok'
        existing.issues = list(incoming.issues)
    _collect_directions(existing, incoming.meta)


def _collect_directions(candidate: UniversityCandidate, meta: dict) -> None:
    """Собрать направления/профили одной олимпиады в список в ``meta``.

    У олимпиады, идущей по нескольким направлениям, ``direction``/``profile``
    превращаются в ``directions``/``profiles`` — иначе от строки осталось бы
    только последнее значение, и связь потеряла бы остальные направления.
    """
    for key, plural in (('direction', 'directions'), ('profile', 'profiles')):
        value = meta.get(key)
        if not value:
            continue
        collected = candidate.meta.setdefault(plural, [])
        if value not in collected:
            collected.append(value)
        candidate.meta.pop(key, None)
