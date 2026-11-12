"""История прогонов импорта.

Текущий импортёр хранит состояние в ``docs.metadata['rsosh']``. Здесь —
журнал прогонов, который переживает перезапись этого раздела: кто запустил,
когда, чем закончилось. Он нужен панели администратора и аудиту.
"""

import uuid as uuid_mod
from datetime import datetime, timezone

from sqlalchemy import select

from app.database.database import AsyncSessionLocal
from app.models.imports import ImportJob, ImportRecord


def _as_uuid(value):
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


def _iso(value):
    return value.isoformat() if value else None


def job_to_dict(job: ImportJob) -> dict:
    return {
        'id': str(job.id),
        'doc_id': str(job.doc_id),
        'kind': job.kind,
        'status': job.status,
        'started_by': str(job.started_by) if job.started_by else None,
        'started_at': _iso(job.started_at),
        'finished_at': _iso(job.finished_at),
        'summary': job.summary,
        'error': job.error,
    }


async def get_job(job_id) -> dict | None:
    """Прогон импорта вместе с построчными результатами подтверждения."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ImportJob).where(ImportJob.id == _as_uuid(job_id))
        )
        job = result.scalar_one_or_none()
        if not job:
            return None
        data = job_to_dict(job)
        records = await session.execute(
            select(ImportRecord)
            .where(ImportRecord.job_id == job.id)
            .order_by(ImportRecord.createdAt, ImportRecord.id)
        )
        data['records'] = [
            record_to_dict(item) for item in records.scalars().all()
        ]
        return data


def record_to_dict(record: ImportRecord) -> dict:
    return {
        'id': str(record.id),
        'job_id': str(record.job_id),
        'name': record.name,
        'action': record.action,
        'status': record.status,
        'payload': record.payload,
        'createdAt': _iso(record.createdAt),
    }


async def start_job(doc_id, *, kind='RSOSH', user_id=None) -> dict:
    async with AsyncSessionLocal() as session:
        job = ImportJob(
            doc_id=_as_uuid(doc_id),
            kind=kind,
            status='PROCESSING',
            started_by=_as_uuid(user_id) if user_id else None,
            started_at=datetime.now(timezone.utc),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job_to_dict(job)


async def finish_job(
    job_id, *, status, summary=None, error=None, records=None,
) -> dict | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ImportJob).where(ImportJob.id == _as_uuid(job_id))
        )
        job = result.scalar_one_or_none()
        if not job:
            return None
        job.status = status
        job.summary = summary
        job.error = error
        job.finished_at = datetime.now(timezone.utc)
        for item in records or []:
            session.add(
                ImportRecord(
                    job_id=job.id,
                    name=item.get('name'),
                    action=item.get('action'),
                    status=item.get('status'),
                    payload=item,
                )
            )
        await session.commit()
        await session.refresh(job)
        return job_to_dict(job)


async def list_jobs(*, doc_id=None, limit=50, offset=0) -> list[dict]:
    async with AsyncSessionLocal() as session:
        stmt = select(ImportJob).order_by(ImportJob.started_at.desc(), ImportJob.id)
        if doc_id:
            stmt = stmt.where(ImportJob.doc_id == _as_uuid(doc_id))
        stmt = stmt.limit(limit).offset(max(0, int(offset or 0)))
        result = await session.execute(stmt)
        return [job_to_dict(job) for job in result.scalars().all()]


async def finish_open_job(doc_id, *, status, summary=None, error=None, records=None):
    """Закрыть текущий незавершённый прогон документа, если он есть."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ImportJob)
            .where(
                ImportJob.doc_id == _as_uuid(doc_id),
                ImportJob.status == 'PROCESSING',
            )
            .order_by(ImportJob.started_at.desc())
        )
        job = result.scalars().first()
        if not job:
            return None
        job.status = status
        job.summary = summary
        job.error = error
        job.finished_at = datetime.now(timezone.utc)
        for item in records or []:
            session.add(
                ImportRecord(
                    job_id=job.id,
                    name=item.get('name'),
                    action=item.get('action'),
                    status=item.get('status'),
                    payload=item,
                )
            )
        await session.commit()
        await session.refresh(job)
        return job_to_dict(job)
