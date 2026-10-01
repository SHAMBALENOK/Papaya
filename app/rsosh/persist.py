"""Запись подтверждённого импорта в каталог олимпиад.

Правила, которые держит этот модуль:

- одна строка кандидата = одна запись каталога: дубли не создаются, а
  существующая олимпиада обновляется (merge);
- олимпиада, присутствующая в новом перечне РСОШ, снова становится актуальной
  (``PUBLISHED``, причина архива сбрасывается) — так возвращается из архива;
- олимпиада, **исчезнувшая** из перечня РСОШ, не удаляется, а переводится в
  ``ARCHIVED`` с причиной ``RSOSH_ABSENT`` (см. ``_archive_missing``);
- записи, которые администратор снял в preview (``skip``), не считаются
  отсутствующими: ошибочная строка распознавания не должна архивировать
  существующую олимпиаду;
- **неполный импорт не архивирует ничего** (см. ``_archive_decision``).

Последний пункт — самый важный для целостности каталога. «Отсутствует в новом
перечне» — это утверждение о полноте: чтобы его сделать, нужно знать, что
перечень прочитан целиком. Если часть строк не распозналась или не
применилась, «отсутствует» означает совсем другое, и массовая архивация
уничтожила бы действующие записи каталога.
"""

import logging

from sqlalchemy import select

from app.database.database import AsyncSessionLocal
from app.database.search import normalize_name
from app.middlewares.serializers import olympiad_to_dict
from app.models.docs import Docs
from app.models.olympiads import Olympiads
from app.rsosh.types import Candidate

logger = logging.getLogger('papaya.rsosh.persist')

# Причины архивирования (совпадают с комментарием в app/models/olympiads.py).
ARCHIVE_BY_RSOSH = 'RSOSH_ABSENT'
ARCHIVE_MANUAL = 'MANUAL'

#: Предупреждения, после которых перечень нельзя считать прочитанным целиком.
#:
#: Это не «что-то подозрительно», а прямой ответ разбора на вопрос «насколько
#: мне удалось разобрать структуру»: если шапка или границы таблицы не
#: распознаны или таблица выглядела не списком, то «этой олимпиады в
#: перечне нет» означает «я её не увидел», а не «её больше нет».
#:
#: Остальные предупреждения (поворот страницы, OCR как запасной путь,
#: повтор олимпиады в разных разделах, служебные строки) структурой не
#: противоречат и архивированию не мешают: это нормальные условия чтения
#: перечня.
STRUCTURE_WARNING_MARKERS = (
    'Table header was not recognized',
    'Table borders were not detected',
    'Small table skipped',
    'Sheet is empty',
)


def _as_uuid(value):
    import uuid as uuid_mod

    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


def _as_iso(value):
    """Время в ISO-8601; на вход может прийти уже строкой."""
    if value is None or isinstance(value, str):
        return value
    return value.isoformat()


def _archive_decision(
    *,
    requested: bool,
    errors: list[str],
    warnings: list[str],
) -> tuple[bool, str | None]:
    """Можно ли считать, что отсутствующие олимпиады исчезли из перечня.

    Возвращает ``(архивировать, причина_отказа)``. Отказ — это не ошибка
    импорта: подтверждённые кандидаты всё равно создаются и обновляются,
    просто каталог не трогают, а причина отказа возвращается администратору в
    отчёте.
    """
    if not requested:
        return False, None
    if errors:
        # Часть строк документа не применилась: для них «нет в перечне» — это
        # не факт, а последствие ошибки записи.
        return False, (
            'Архивирование отключено: часть строк перечня не удалось применить '
            f'({len(errors)} шт.). Неприменённые строки не считаются '
            'отсутствующими.'
        )
    unreadable = [
        warning
        for warning in warnings
        if any(marker in warning for marker in STRUCTURE_WARNING_MARKERS)
    ]
    if unreadable:
        return False, (
            'Архивирование отключено: перечень прочитан не полностью '
            f'({unreadable[0]}). По такому перечню нельзя судить, какие '
            'олимпиады из него исчезли.'
        )
    return True, None


async def apply_candidates(
    *,
    candidates: list[Candidate],
    doc: dict,
    archive_missing: bool = True,
    protected_ids: set[str] | None = None,
    warnings: list[str] | None = None,
) -> dict:
    """Применить подтверждённый импорт.

    ``protected_ids`` — id олимпиад, которые нельзя архивировать, даже если их
    не было в текущем документе (например, кандидаты, которые администратор
    снял в preview из-за ошибки распознавания).

    ``warnings`` — предупреждения разбора документа: часть из них означает, что
    структуру перечня прочитать не удалось, и тогда архивирование отключается
    (см. ``_archive_decision``).

    Возвращает итог: сколько олимпиад создано, сколько обновлено, какие
    отправлены в архив и какие записи пропущены.
    """
    doc_id = _as_uuid(doc['id'])
    created: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    touched_ids: list[str] = []
    # Олимпиады, о которых администратор сказал «не трогать»: снятые с
    # подтверждения кандидаты. Они не считаются отсутствующими в перечне.
    protected_ids: set[str] = {str(value) for value in (protected_ids or set())}

    async with AsyncSessionLocal() as session:
        for candidate in candidates:
            try:
                olympiad = await _upsert(session, candidate, doc_id)
            except Exception as exc:  # noqa: BLE001 - одна плохая строка не
                # должна откатывать весь импорт
                logger.exception('rsosh: cannot apply candidate %s', candidate.name)
                errors.append(f'{candidate.name}: {exc}')
                continue
            if olympiad is None:
                skipped.append(candidate.name)
                continue
            touched_ids.append(str(olympiad['id']))
            if candidate.action == 'create':
                created.append(olympiad['name'])
            else:
                updated.append(olympiad['name'])

        archived: list[str] = []
        archive_reason = None
        should_archive, archive_reason = _archive_decision(
            requested=archive_missing,
            errors=errors,
            warnings=list(warnings or []),
        )
        if should_archive:
            archived = await _archive_missing(
                session,
                doc_id,
                set(touched_ids) | protected_ids,
            )

        await session.commit()

    logger.info(
        'rsosh: applied %s candidates (created=%s, merged=%s, archived=%s%s)',
        len(candidates), len(created), len(updated), len(archived),
        ', archive skipped' if archive_reason else '',
    )
    return {
        'created': created,
        'updated': updated,
        'archived': archived,
        'skipped': skipped,
        'errors': errors,
        # Почему каталог не тронут, когда это важно администратору: пустое
        # значение означает, что архивирование либо не запрашивали, либо
        # отработало штатно.
        'archive_skipped_reason': archive_reason,
    }


async def _upsert(session, candidate: Candidate, doc_id):
    """Создать или обновить олимпиаду по кандидату."""
    from datetime import datetime, timezone

    olympiad = None
    if candidate.action == 'merge' and candidate.matched_olympiad_id:
        result = await session.execute(
            select(Olympiads).where(
                Olympiads.id == _as_uuid(candidate.matched_olympiad_id)
            )
        )
        olympiad = result.scalar_one_or_none()

    if olympiad is None:
        name_norm = candidate.name_norm or normalize_name(candidate.name)
        result = await session.execute(
            select(Olympiads).where(Olympiads.name_norm == name_norm)
        )
        olympiad = result.scalar_one_or_none()

    if olympiad is None:
        now = datetime.now(timezone.utc)
        olympiad = Olympiads(
            name=candidate.name,
            name_norm=candidate.name_norm or normalize_name(candidate.name),
            description=candidate.description,
            source_doc_id=doc_id,
            status='PUBLISHED',
            archive_reason=None,
            createdAt=now,
            updatedAt=now,
        )
        session.add(olympiad)
        await session.flush()
        return olympiad_to_dict(olympiad)

    changed = False
    if olympiad.status != 'PUBLISHED' or olympiad.archive_reason is not None:
        # Олимпиада снова встретилась в актуальном перечне: возвращаем её в
        # актуальные и сбрасываем причину архива.
        olympiad.status = 'PUBLISHED'
        olympiad.archive_reason = None
        changed = True
    if candidate.description and not olympiad.description:
        olympiad.description = candidate.description
        changed = True
    if olympiad.source_doc_id != doc_id:
        olympiad.source_doc_id = doc_id
        changed = True
    if changed:
        olympiad.updatedAt = datetime.now(timezone.utc)
    await session.flush()
    return olympiad_to_dict(olympiad)


async def _archive_missing(session, doc_id, keep_ids: set[str]) -> list[str]:
    """Перевести в архив олимпиады, исчезнувшие из перечня РСОШ.

    Архивируются только те записи, которые ранее пришли из документа РСОШ
    (``source_doc_id`` задан и это не текущий документ) и не встретились в
    новом перечне. Олимпиады, созданные вручную, архивированию не подлежат.

    ``keep_ids`` — олимпиады, которых нельзя архивировать: применённые
    кандидаты и кандидаты, снятые администратором в preview. Снятые с
    подтверждения записи не считаются отсутствующими в перечне: иначе ошибка
    распознавания одной строки архивировала бы существующую олимпиаду.
    """
    from datetime import datetime, timezone

    result = await session.execute(
        select(Olympiads).where(
            Olympiads.status == 'PUBLISHED',
            Olympiads.source_doc_id.is_not(None),
            Olympiads.source_doc_id != doc_id,
        )
    )
    archived: list[str] = []
    now = datetime.now(timezone.utc)
    for olympiad in result.scalars().all():
        if str(olympiad.id) in keep_ids:
            continue
        olympiad.status = 'ARCHIVED'
        olympiad.archive_reason = ARCHIVE_BY_RSOSH
        olympiad.updatedAt = now
        archived.append(olympiad.name)
    return archived


async def newest_confirmed_rsosh_doc_id(exclude_doc_id=None) -> tuple | None:
    """Самый «свежий» уже подтверждённый документ РСОШ.

    Порядок снимков определяется временем загрузки документа: год олимпиады
    Papaya не моделирует (одна каноническая олимпиада независимо от года), и
    разбирать документ ради даты — значит трогать распознавание. Практически
    это и есть нужный порядок: перечень РСОШ загружают по мере выхода новой
    редакции.

    Возвращает ``(id, createdAt)`` последнего подтверждённого перечня.

    Время возвращается в том же виде, что и у словаря документа (ISO-8601),
    чтобы сравнение не зависело от типа: документ приходит в процессор
    сериализованным, и сравнивать его ``createdAt`` с ``datetime`` означало бы
    упасть на ``TypeError`` вместо отказа по смыслу.
    """
    newest = None
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(Docs.id, Docs.createdAt, Docs.meta)
            .where(Docs.type == 'RSOSH_LIST')
            .order_by(Docs.createdAt.desc(), Docs.id)
        )).all()
        for doc_id, created_at, meta in rows:
            if exclude_doc_id is not None and str(doc_id) == str(exclude_doc_id):
                continue
            section = ((meta or {}).get('rsosh') or {})
            if section.get('state') == 'approved':
                newest = (doc_id, _as_iso(created_at))
                break
    return newest


def is_outdated_snapshot(doc: dict, newest_confirmed) -> bool:
    """Является ли документ устаревшим снимком перечня.

    Устаревшим считается документ, загруженный **раньше** уже подтверждённого:
    подтверждение такого документа вернуло бы каталог к старой редакции —
    опубликовало бы олимпиаду, которой в свежем перечне уже нет, и заархивировало
    новую.

    Тот же документ устаревшим не считается: повторное подтверждение уже
    применённого перечня ничего не откатывает.
    """
    if not newest_confirmed:
        return False
    newest_id, newest_created_at = newest_confirmed
    if str(newest_id) == str(doc.get('id')):
        return False
    created_at = doc.get('createdAt')
    if created_at is None or newest_created_at is None:
        return False
    # ISO-8601 в UTC сравнивается лексикографически в том же порядке, что и по
    # времени, — поэтому достаточно строкового сравнения.
    return str(created_at) < str(newest_created_at)


async def mark_processed(doc_id) -> None:
    """Отметить время завершения обработки документа."""
    from datetime import datetime, timezone

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Docs).where(Docs.id == _as_uuid(doc_id))
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return
        doc.processedAt = datetime.now(timezone.utc)
        await session.commit()
