"""Запись подтверждённого импорта в каталог олимпиад.

Правила, которые держит этот модуль:

- одна строка кандидата = одна запись каталога: дубли не создаются, а
  существующая олимпиада обновляется (merge);
- олимпиада, присутствующая в новом перечне РСОШ, снова становится актуальной
  (``PUBLISHED``, причина архива сбрасывается) — так возвращается из архива;
- олимпиада, **исчезнувшая** из перечня РСОШ, не удаляется, а переводится в
  ``ARCHIVED`` с причиной ``RSOSH_ABSENT`` (см. ``archive_missing``);
- записи, которые администратор снял в preview (``skip``), не считаются
  отсутствующими: ошибочная строка распознавания не должна архивировать
  существующую олимпиаду.
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


def _as_uuid(value):
    import uuid as uuid_mod

    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


async def apply_candidates(
    *,
    candidates: list[Candidate],
    doc: dict,
    archive_missing: bool = True,
    protected_ids: set[str] | None = None,
) -> dict:
    """Применить подтверждённый импорт.

    ``protected_ids`` — id олимпиад, которые нельзя архивировать, даже если их
    не было в текущем документе (например, кандидаты, которые администратор
    снял в preview из-за ошибки распознавания).

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
        if archive_missing:
            archived = await _archive_missing(
                session,
                doc_id,
                set(touched_ids) | protected_ids,
            )

        await session.commit()

    logger.info(
        'rsosh: applied %s candidates (created=%s, merged=%s, archived=%s)',
        len(candidates), len(created), len(updated), len(archived),
    )
    return {
        'created': created,
        'updated': updated,
        'archived': archived,
        'skipped': skipped,
        'errors': errors,
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


async def document_rsosh_list_ids(doc_id) -> set[str]:
    """id олимпиад, пришедших из конкретного документа РСОШ."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Olympiads.id).where(Olympiads.source_doc_id == _as_uuid(doc_id))
        )
        return {str(value) for value in result.scalars().all()}


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
