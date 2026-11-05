import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app import database
from app.core import deps

programs_page = APIRouter(prefix='/programs', tags=['programs'])
university_programs_page = APIRouter(tags=['programs'])

logger = logging.getLogger('papaya.programs')


class ProgramCreate(BaseModel):
    name: str
    code: str | None = None
    description: str | None = None


class ProgramUpdate(BaseModel):
    version: int | None = None
    name: str | None = None
    code: str | None = None
    description: str | None = None


@university_programs_page.get('/universities/{university_id}/programs')
async def list_university_programs(university_id: uuid.UUID):
    try:
        programs = await database.programs.list_programs(university_id)
        return {'programs': programs}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@university_programs_page.post('/universities/{university_id}/programs')
async def create_university_program(university_id: uuid.UUID, body: ProgramCreate, current_user: dict = Depends(deps.require_admin)):
    try:
        data = body.model_dump()
        data['university_id'] = str(university_id)
        program = await database.programs.create_program(data)
        await database.audit.log_action('university_program', program['id'], 'create', user_id=current_user['id'], after=program)
        return program
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@programs_page.get('/{program_id}')
async def get_program(program_id: uuid.UUID):
    try:
        program = await database.programs.get_program(program_id)
        if not program:
            raise HTTPException(status_code=404, detail='Program not found')
        return program
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@programs_page.put('/{program_id}')
async def update_program(program_id: uuid.UUID, body: ProgramUpdate, current_user: dict = Depends(deps.require_admin)):
    try:
        existing = await database.programs.get_program(program_id)
        if not existing:
            raise HTTPException(status_code=404, detail='Program not found')
        if body.version is not None and int(body.version) != int(existing.get('version', 0)):
            raise HTTPException(status_code=409, detail='Version conflict')
        data = body.model_dump(exclude_unset=True)
        data.pop('version', None)
        program = await database.programs.update_program(program_id, data)
        if not program:
            raise HTTPException(status_code=404, detail='Program not found')
        await database.audit.log_action('university_program', program_id, 'update', user_id=current_user['id'], after=program)
        return program
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')