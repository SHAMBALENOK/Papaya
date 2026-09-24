"""Вычисление временного состояния олимпиады по её ``schedule`` (JSONB).

Фаза 2 «Этапы и даты». Источник истины расписания — даты этапов, хранящиеся
в ``Olympiads.schedule``. Статусы (этапа и олимпиады в целом) и ближайший
дедлайн НИКОГДА не сохраняются в БД/кэше: они считаются динамически при выдаче
из ``datetime.now`` и поэтому не устаревают за время жизни кэша.

Правила приоритета при пересечении этапов детерминированы:

- среди активных этапов выбирается тот, чей тип «более продвинут» по шкале
  ``_STATUS_PRIORITY`` (FINAL > QUALIFICATION > RESULTS > REGISTRATION);
  при равенстве — первый в исходном порядке массива ``stages``;
- олимпиадный ``current_status`` маппится из типа выбранного этапа
  (REGISTRATION → REGISTRATION_OPEN и т.д.); активных этапов нет:
  - все этапы ещё впереди → ``UPCOMING`` (олимпиада/регистрация ещё не началась);
  - все этапы завершены → ``FINISHED``;
  - «между этапами» (регистрация закрылась, следующий этап ещё впереди) →
    ``REGISTRATION_CLOSED``;
- этап RESULTS без ``end_at`` трактуется как событие публикации результатов:
  длится до конца суток ``start_at`` (активен — статус RESULTS), после чего
  олимпиада завершается (FINISHED).
"""

from datetime import datetime, timezone
from typing import Any, Optional

# Базовые типы этапов. Структура расширяемая: новые типы достаточно добавить
# в этот кортеж и в ``_STATUS_PRIORITY`` (валидация в schemas использует тот же
# источник перечислимых значений).
STAGE_TYPES = ('REGISTRATION', 'QUALIFICATION', 'FINAL', 'RESULTS')

STAGE_STATUS_UPCOMING = 'UPCOMING'
STAGE_STATUS_ACTIVE = 'ACTIVE'
STAGE_STATUS_FINISHED = 'FINISHED'

# Олимпиадные статусы (см. docs/TODO.md, Фаза 2).
STATUS_UPCOMING = 'UPCOMING'
STATUS_REGISTRATION_OPEN = 'REGISTRATION_OPEN'
STATUS_REGISTRATION_CLOSED = 'REGISTRATION_CLOSED'
STATUS_QUALIFICATION = 'QUALIFICATION'
STATUS_FINAL = 'FINAL'
STATUS_RESULTS = 'RESULTS'
STATUS_FINISHED = 'FINISHED'

# Приоритет типа этапа для статуса олимпиады при пересекающихся этапах.
_STATUS_PRIORITY = {
    'FINAL': 4,
    'QUALIFICATION': 3,
    'RESULTS': 2,
    'REGISTRATION': 1,
}

_STATUS_FROM_TYPE = {
    'REGISTRATION': STATUS_REGISTRATION_OPEN,
    'QUALIFICATION': STATUS_QUALIFICATION,
    'FINAL': STATUS_FINAL,
    'RESULTS': STATUS_RESULTS,
}


def parse_iso(value: Any) -> Optional[datetime]:
    """Распарсить ISO-8601 строку в timezone-aware datetime.

    Naive значения и неразбираемые строки считаются невалидными (None): такие
    даты не должны появляться после валидации Pydantic-схем.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else None
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo is not None else None


def _end_of_day(dt: datetime) -> datetime:
    """Последняя секунда того же календарного дня (в tz исходной даты)."""
    return datetime(dt.year, dt.month, dt.day, 23, 59, 59, tzinfo=dt.tzinfo)


def _effective_end(stage: dict) -> Optional[datetime]:
    """Фактический конец этапа.

    Явный ``end_at`` — источник истины. Без ``end_at``:

    - RESULTS трактуется как событие «публикация результатов»: длится до конца
      суток ``start_at`` (в этот день пользователь видит статус RESULTS), после
      чего олимпиада завершается FINISHED;
    - прочие типы без конца считаются длящимися (ACTIVE до конца).
    """
    end = parse_iso(stage.get('end_at'))
    if end is not None:
        return end
    start = parse_iso(stage.get('start_at'))
    if start is not None and (stage.get('type') or '').upper() == 'RESULTS':
        return _end_of_day(start)
    return None


def stage_status(stage: dict, now: datetime) -> Optional[str]:
    """Вычислить статус одного этапа из его дат.

    - start_at в будущем → UPCOMING;
    - иначе, когда фактический конец (end_at или конец суток публикации
      результатов) в прошлом → FINISHED;
    - в остальных случаях этап идёт сейчас → ACTIVE.
    """
    start = parse_iso(stage.get('start_at'))
    if start is None:
        return None
    if start > now:
        return STAGE_STATUS_UPCOMING

    end = _effective_end(stage)
    if end is not None and end < now:
        return STAGE_STATUS_FINISHED
    return STAGE_STATUS_ACTIVE


def _choose_current_stage(stages: list[dict], now: datetime) -> Optional[dict]:
    """Активный этап по детерминированному правилу приоритета типов."""
    active = []
    for stage in stages:
        if stage_status(stage, now) == STAGE_STATUS_ACTIVE:
            priority = _STATUS_PRIORITY.get((stage.get('type') or '').upper(), 0)
            active.append((priority, stage))
    if not active:
        return None
    # max по (priority, index): при равном приоритете побеждает первый в массиве.
    return max(enumerate(active), key=lambda pair: (pair[1][0], -pair[0]))[1][1]


def _next_deadline(stages: list[dict], now: datetime) -> Optional[str]:
    """Ближайшая будущая дата: конец активного/предстоящего этапа или
    начало следующего этапа. Возвращает ISO-строку или None."""
    candidates = []
    for stage in stages:
        status = stage_status(stage, now)
        if status == STAGE_STATUS_UPCOMING:
            start = parse_iso(stage.get('start_at'))
            if start is not None and start > now:
                candidates.append(start)
        elif status == STAGE_STATUS_ACTIVE:
            end = parse_iso(stage.get('end_at'))
            if end is not None and end > now:
                candidates.append(end)
    if not candidates:
        return None
    return min(candidates).isoformat()


def compute_schedule_state(schedule: dict, now: Optional[datetime] = None) -> dict:
    """Вернуть обогащённое состояние расписания.

    Вход — сохранённый ``schedule`` (источник данных), а ``stages`` на выходе
    дополнены вычисленным ``status`` каждого этапа. Это представление
    используется в API-ответах.
    """
    now = now or datetime.now(timezone.utc)
    raw_stages = schedule.get('stages')
    stages = raw_stages if isinstance(raw_stages, list) else []

    enriched = []
    for stage in stages:
        item = dict(stage or {})
        item['status'] = stage_status(item, now)
        enriched.append(item)

    current_stage = _choose_current_stage(enriched, now)

    if current_stage is not None:
        current_status = _STATUS_FROM_TYPE.get(
            (current_stage.get('type') or '').upper()
        )
    elif enriched:
        statuses = {item.get('status') for item in enriched}
        if statuses == {STAGE_STATUS_FINISHED}:
            # Всё завершено — олимпиада закончена.
            current_status = STATUS_FINISHED
        elif statuses == {STAGE_STATUS_UPCOMING}:
            # Ни один этап ещё не начался: «регистрация ещё не открыта».
            current_status = STATUS_UPCOMING
        else:
            # Активного этапа нет, но что-то уже прошло, а что-то ещё впереди:
            # регистрация закрылась, следующий этап стартует позже (next_deadline).
            current_status = STATUS_REGISTRATION_CLOSED
    else:
        current_status = None

    return {
        'season': schedule.get('season'),
        'stages': enriched,
        'current_stage': current_stage,
        'current_status': current_status,
        'next_deadline': _next_deadline(enriched, now),
    }


def enrich_olympiad(olympiad: dict, now: Optional[datetime] = None) -> dict:
    """Добавить в словарь олимпиады вычисляемые поля Фазы 2.

    Меняет и возвращает тот же словарь. Для олимпиад без расписания поля
    устанавливаются в None (обратная совместимость со старыми записями).
    """
    schedule = olympiad.get('schedule')
    if not isinstance(schedule, dict) or not isinstance(schedule.get('stages'), list):
        olympiad['schedule'] = None
        olympiad['current_status'] = None
        olympiad['current_stage'] = None
        olympiad['next_deadline'] = None
        return olympiad

    state = compute_schedule_state(schedule, now)
    olympiad['schedule'] = {
        'season': state['season'],
        'stages': state['stages'],
    }
    olympiad['current_status'] = state['current_status']
    olympiad['current_stage'] = state['current_stage']
    olympiad['next_deadline'] = state['next_deadline']
    return olympiad