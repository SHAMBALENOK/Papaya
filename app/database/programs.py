import uuid as uuid_mod
from sqlalchemy import select

from app.database.database import AsyncSessionLocal
from app.database.search import normalize_name
from app.models.programs import UniversityProgram

def _as_uuid(value):
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))

def _iso(v):
    return v.isoformat() if v else None

def program_to_dict(p):
    return {
        'id': str(p.id),
        'university_id': str(p.university_id),
        'name': p.name,
        'name_norm': p.name_norm,
        'code': p.code,
        'description': p.description,
        'createdAt': _iso(p.createdAt),
        'updatedAt': _iso(p.updatedAt),
    }

async def list_programs(university_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UniversityProgram).where(UniversityProgram.university_id == _as_uuid(university_id)))
        return [program_to_dict(x) for x in result.scalars().all()]

async def get_program(program_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UniversityProgram).where(UniversityProgram.id == _as_uuid(program_id)))
        p = result.scalar_one_or_none()
        return program_to_dict(p) if p else None

async def create_program(data: dict):
    data = dict(data)
    if 'name' in data and 'name_norm' not in data:
        data['name_norm'] = normalize_name(data['name'])
    async with AsyncSessionLocal() as session:
        p = UniversityProgram(**data)
        session.add(p)
        await session.commit()
        await session.refresh(p)
        return program_to_dict(p)

async def update_program(program_id, data: dict):
    data = dict(data)
    if 'name' in data and 'name_norm' not in data:
        data['name_norm'] = normalize_name(data['name'])
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UniversityProgram).where(UniversityProgram.id == _as_uuid(program_id)))
        p = result.scalar_one_or_none()
        if not p:
            return None
        for k, v in data.items():
            setattr(p, k, v)
        p.version = (p.version or 1) + 1
        await session.commit()
        await session.refresh(p)
        return program_to_dict(p)