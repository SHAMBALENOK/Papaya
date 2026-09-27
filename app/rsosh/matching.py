"""Дедупликация олимпиад: сопоставление импортируемых записей с каталогом.

Один и тот же перечень РСОSH нельзя импортировать дважды: иначе каталог
разрастается копиями одной олимпиады. Но и сравнивать только строки нельзя —
в разных документах название пишут по-разному («ё»/«е», кавычки, двойные
пробелы, переносы строк, разный порядок слов).

Поэтому сопоставление трёхуровневое:

1. **Точное совпадение** по нормализованному названию (``name_norm``) —
   уверенное ``merge`` без вопросов;
2. **Близкое совпадение** (похожие длинные названия) — ``merge``;
3. **Сомнительное совпадение** — ``merge``, но с пометкой ``review``:
   администратор видит такое в preview и решает сам.

Явно разные олимпиады не объединяются: у слишком коротких или заметно
различающихся названий порог близости не достигается.
"""

from app.database import olympiads as db_olympiads
from app.database.search import normalize_name
from app.rsosh.types import Candidate, OlympiadRecord

# Порог для автоматического объединения.
MERGE_THRESHOLD = 0.92
# Порог, ниже которого совпадение не считается совпадением вовсе.
REVIEW_THRESHOLD = 0.74
# Слишком короткие названия не сравниваем нечётко: «Математика» и
# «Информатика» различаются на 0.85, но это разные олимпиады.
MIN_FUZZY_LENGTH = 24


def _similarity(first: str, second: str) -> float:
    from difflib import SequenceMatcher

    return SequenceMatcher(None, first, second).ratio()


def _token_overlap(first: str, second: str) -> float:
    first_tokens = set(first.split())
    second_tokens = set(second.split())
    if not first_tokens or not second_tokens:
        return 0.0
    return len(first_tokens & second_tokens) / len(first_tokens | second_tokens)


def match_record(
    record: OlympiadRecord,
    catalog: dict[str, dict],
) -> Candidate:
    """Сопоставить одну запись с каталогом и вернуть кандидата.

    ``catalog`` — словарь ``{name_norm: olympiad}`` текущего каталога.
    """
    candidate = Candidate(
        name=record.name,
        name_norm=record.name_norm or normalize_name(record.name),
        description=record.description,
        action='create',
        page=record.page,
        issues=list(record.issues),
    )

    exact = catalog.get(candidate.name_norm)
    if exact:
        candidate.action = 'merge'
        candidate.matched_olympiad_id = exact['id']
        candidate.match_score = 1.0
        candidate.confidence = 'ok'
        return candidate

    if len(candidate.name_norm) < MIN_FUZZY_LENGTH:
        return candidate

    best_score = 0.0
    best_olympiad = None
    for name_norm, olympiad in catalog.items():
        if abs(len(name_norm) - len(candidate.name_norm)) > max(
            12, int(len(candidate.name_norm) * 0.4)
        ):
            continue
        score = _similarity(candidate.name_norm, name_norm)
        overlap = _token_overlap(candidate.name_norm, name_norm)
        if overlap < 0.5:
            # Наборы слов не пересекаются — это заведомо разные олимпиады,
            # даже если строки случайно похожи по символам.
            continue
        score = score * 0.6 + overlap * 0.4
        if score > best_score:
            best_score = score
            best_olympiad = olympiad

    if best_olympiad is None or best_score < REVIEW_THRESHOLD:
        return candidate

    candidate.action = 'merge'
    candidate.matched_olympiad_id = best_olympiad['id']
    candidate.match_score = round(best_score, 3)
    if best_score >= MERGE_THRESHOLD:
        candidate.confidence = 'ok'
    else:
        candidate.confidence = 'review'
        candidate.issues.append(
            'Похоже на «' + (best_olympiad['name'] or '') + '» — проверьте вручную'
        )
    return candidate


async def build_candidates(records: list[OlympiadRecord]) -> list[Candidate]:
    """Сопоставить все записи импорта с текущим каталогом.

    Записи, повторяющиеся внутри одного документа, схлопываются: в каталог
    попадает одна запись на олимпиаду.
    """
    catalog_list = await db_olympiads.list_olympiads(status=None)
    catalog = {item['name_norm']: item for item in catalog_list}

    candidates: dict[str, Candidate] = {}
    for record in records:
        candidate = match_record(record, catalog)
        existing = candidates.get(candidate.name_norm)
        if existing is None:
            candidates[candidate.name_norm] = candidate
            continue
        # Одна и та же олимпиада из разных строк документа: оставляем
        # запись с лучшей уверенностью, предупреждения объединяем.
        if candidate.confidence == 'ok' and existing.confidence != 'ok':
            candidates[candidate.name_norm] = candidate
        else:
            existing.issues = list(dict.fromkeys([*existing.issues, *candidate.issues]))

    return list(candidates.values())
