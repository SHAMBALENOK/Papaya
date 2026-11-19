import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

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
async def list_university_programs(
    university_id: uuid.UUID,
    include_archived: bool = Query(default=False),
):
    try:
        programs = await database.programs.list_programs(
            university_id, include_archived=include_archived
        )
        return {'programs': programs}
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@university_programs_page.post('/universities/{university_id}/programs')
async def create_university_program(university_id: uuid.UUID, body: ProgramCreate, current_user: dict = Depends(deps.require_manage_university)):
    try:
        university = await database.universities.get_university(university_id)
        if not university:
            raise HTTPException(status_code=404, detail='University not found')
        data = body.model_dump()
        data['university_id'] = str(university_id)
        program = await database.programs.create_program(data)
        await database.audit.log_action('university_program', program['id'], 'create', user_id=current_user['id'], after=program)
        return program
    except HTTPException:
        raise
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail='Program with this name already exists for the university',
        ) from exc
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
async def update_program(program_id: uuid.UUID, body: ProgramUpdate, current_user: dict = Depends(deps.require_university_rep)):
    try:
        existing = await database.programs.get_program(program_id)
        if not existing:
            raise HTTPException(status_code=404, detail='Program not found')
        if not deps.can_manage_university(current_user, existing['university_id']):
            raise HTTPException(
                status_code=403, detail='You can only manage your own university'
            )
        data = body.model_dump(exclude_unset=True)
        expected = data.pop('version', None)
        program = await database.programs.update_program(
            program_id, data, expected_version=expected
        )
        if not program:
            raise HTTPException(status_code=404, detail='Program not found')
        await database.audit.log_action('university_program', program_id, 'update', user_id=current_user['id'], after=program)
        return program
    except HTTPException:
        raise
    except database.programs.VersionConflict as exc:
        raise HTTPException(status_code=409, detail='Version conflict') from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail='Program with this name already exists for the university',
        ) from exc
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@university_programs_page.post('/universities/{university_id}/programs/{program_id}/archive')
async def archive_university_program(
    university_id: uuid.UUID,
    program_id: uuid.UUID,
    archived: bool = Query(default=True),
    current_user: dict = Depends(deps.require_manage_university),
):
    """Архивировать программу своего вуза.

    Архив не удаляет программу: правила и история ссылаются на неё, а
    публичный каталог просто перестаёт её предлагать.
    """
    try:
        existing = await database.programs.get_program(program_id)
        if not existing:
            raise HTTPException(status_code=404, detail='Program not found')
        if str(existing['university_id']) != str(university_id):
            raise HTTPException(status_code=404, detail='Program not found')
        program = await database.programs.update_program(
            program_id, {'is_archived': bool(archived)}
        )
        await database.audit.log_action(
            'university_program', program_id, 'archive',
            user_id=current_user['id'], after=program,
        )
        return program
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')