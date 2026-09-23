"""RSOSH-импорт: валидация кандидатов и определение потребности в ревью.

Правило «OCR/AI — только предложение»: кандидат помечается NEEDS_REVIEW
(confidence='review'), если данных недостаточно, они противоречивы или есть
сомнение в корректности. Подтверждённые админом данные властны над ревью,
а НЕподтверждённые ничего не создают в БД.
"""

from app.rsosh import states


def _normalize_action(action: str) -> str:
    return action if action in states.ACTION_VALUES else states.ACTION_CREATE


def validate_candidates(candidates: list[dict]) -> list[dict]:
    """Дополнить кандидатов confidence/reviews исходя из полноты данных."""
    for candidate in candidates:
        reviews = []

        if not candidate.get('name') or not candidate.get('name_norm'):
            reviews.append('не удалось распознать название олимпиады')

        if not candidate.get('subjects') and not candidate.get('levels'):
            if not candidate.get('description'):
                reviews.append('не выделены предметы/профили и уровень')
            else:
                reviews.append('предметы/уровень не выделены из описания')

        action = _normalize_action(candidate.get('action'))

        if action == states.ACTION_MERGE and not candidate.get('matched_olympiad_id'):
            reviews.append('найдено частичное совпадение — точный ID не определён')
            action = states.ACTION_CREATE

        if action == states.ACTION_MERGE:
            # Слияние с уже существующей без новых данных = дубликат.
            if not (candidate.get('subjects') or candidate.get('levels')
                    or candidate.get('description')):
                action = states.ACTION_SKIP

        candidate['action'] = action
        candidate['confidence'] = 'review' if reviews else 'ok'
        candidate['reviews'] = reviews
    return candidates


def summarize(candidates: list[dict]) -> dict:
    """Сводка для preview/ответов: сколько кандидатов и в каком состоянии."""
    total = len(candidates)
    review = sum(
        1 for candidate in candidates if candidate.get('confidence') == 'review'
    )
    by_action = {action: 0 for action in states.ACTION_VALUES}
    for candidate in candidates:
        action = _normalize_action(candidate.get('action'))
        by_action[action] += 1
    return {
        'total': total,
        'new': by_action[states.ACTION_CREATE],
        'merge': by_action[states.ACTION_MERGE],
        'duplicate': by_action[states.ACTION_SKIP],
        'review': review,
    }