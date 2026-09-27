"""Запись подтверждённого импорта в каталог олимпиад.

Правила, которые держит этот модуслей:

- одна строка кандидата = одна запись каталога: дубли не создаются, а
  существующая олимпиада обновляется (merge);
- олимпиада, присутствующая в новом перечне РСОШ, снова становится актуальной
  (``PUBLISHED``) — так возвращается из архива;
- олимпиада, **исчезнувшая** из перечня РСОШ, не удаляется, а переводится в
  ``ARCHIVED`` (см. ``archive_missing``): историческая запись сохраняется, а
  пользователь видит, что олимпиады больше нет в актуальном перечне;
- записи, которые администратор снял в preview (``skip``), не пишутся.
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


def _as_uuid(value):
    import uuid as uuid_mod

    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


async def apply_candidates(
    *,
    candidates: list[Candidate],
    doc: dict,
    archive_missing: bool = True,
) -> dict:
    """Применить подтверждённый импорт.

    Возвращает итог: сколько олимпиад создано, сколько обновлено, какие
    отправлены в архив и какие записи пропущены.
    """
    doc_id = _as_uuid(doc['id'])
    created: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    touched_ids: list[str] = []

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
            archived = await _archive_missing(session, doc_id, set(touched_ids))

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
    now = None
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
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        olympiad = Olympiads(
            name=candidate.name,
            name_norm=candidate.name_norm or normalize_name(candidate.name),
            description=candidate.description,
            source_doc_id=doc_id,
            status='PUBLISHED',
            createdAt=now,
            updatedAt=now,
        )
        session.add(olympiad)
        await session.flush()
        return olympiad_to_dict(olympiad)

    from datetime import datetime, timezone

    changed = False
    if olympiad.status != 'PUBLISHED':
        olympiad.status = 'PUBLISHED'
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


async def _archive_missing(session, doc_id, touched_ids: set[str]) -> list[str]:
    """Перевести в архив олимпиады, исчезнувшие из перечня РСОШ.

    Архивируются только те записи, которые ранее пришли из документа РСОШ
    (``source_doc_id`` задан и это не текущий документ) и не встретились в
    новом перечне. Олимпиады, созданные вручную, архивированию не подлежат.
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
    for olympiad in result.scalars().all():
        if str(olympiad.id) in touched_ids:
            continue
        olympiad.status = 'ARCHIVED'
        olympiad.updatedAt = datetime.now(timezone.utc)
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
