from fastapi import APIRouter, Depends, HTTPException, Cookie
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

import app.middlewares.tokenz.main as tokenz
from app.database.database import get_db
from app import models, schemas, database
from typing import Annotated

admin_page = APIRouter(
    prefix='/admin',
    tags=['administration']
)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

async def _require_admin(db: AsyncSession, access_jwt, refresh_jwt):
    """Проверяет JWT и роль ADMIN. Возвращает объект администратора
    либо бросает 401/403."""
    token = await tokenz.jwt_check(access_jwt, refresh_jwt)
    admin_obj = await database.users.find_user_by_id(
        token['sub'], db, models.users.Users
    )
    if not admin_obj or admin_obj.role != 'ADMIN':
        raise HTTPException(status_code=403, detail='permission denied')
    return admin_obj


def _serialize_user(u) -> dict:
    """Пользователь для админ-панели: роль и активность обязательны."""
    return {
        'id': str(u.id),
        'name': u.name,
        'surname': u.surname,
        'email': u.email,
        'role': u.role,
        'isActive': u.isActive,
        'createdAt': u.createdAt.isoformat() if u.createdAt else None,
    }


def _serialize_event(e) -> dict:
    return {
        'id': str(e.id),
        'owner': str(e.owner) if e.owner else None,
        'name': e.name,
        'disc': e.disc,
        'preview_picture': e.preview_picture,
        'picture': e.picture,
        'isActive': e.isActive,
        'createdAt': e.createdAt.isoformat() if e.createdAt else None,
        'updatedAt': e.updatedAt.isoformat() if e.updatedAt else None,
    }


# ---------------------------------------------------------------------------
# Списки (данные для страницы #/admin)
# ---------------------------------------------------------------------------

@admin_page.get('/users')
async def list_users(
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Все пользователи с ролями и статусом активности."""
    try:
        await _require_admin(db, access_jwt, refresh_jwt)
        users = await database.users.show_random_users(
            quantity=await database.users.get_amount_of_users(
                session=db, model=models.users.Users
            ),
            session=db,
            model=models.users.Users,
        )
        return JSONResponse(status_code=200, content={
            'users': [_serialize_user(u) for u in users],
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')


@admin_page.get('/events')
async def list_events(
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Все события со статусом активности (для архивирования)."""
    try:
        await _require_admin(db, access_jwt, refresh_jwt)
        events = await database.events.show_random_events(
            quantity=await database.events.get_amount_of_events(
                session=db, model=models.events.Events
            ),
            session=db,
            model=models.events.Events,
        )
        return JSONResponse(status_code=200, content={
            'events': [_serialize_event(e) for e in events],
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')


# ---------------------------------------------------------------------------
# Действия
# ---------------------------------------------------------------------------

@admin_page.get(
    '/ban/{user_id}',
    response_model=schemas.users.UserResponse,
)
async def ban(
        user_id: str,
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Блокировка пользователя (isActive = False)."""
    try:
        await _require_admin(db, access_jwt, refresh_jwt)
        return await database.users.edit_user(
            user_id, {'isActive': False}, db, models.users.Users
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')


@admin_page.get(
    '/unban/{user_id}',
    response_model=schemas.users.UserResponse,
)
async def unban(
        user_id: str,
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Разблокировка пользователя (isActive = True)."""
    try:
        await _require_admin(db, access_jwt, refresh_jwt)
        return await database.users.edit_user(
            user_id, {'isActive': True}, db, models.users.Users
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')


@admin_page.get(
    '/archive_event/{event_id}',
    response_model=schemas.events.EventResponse,
)
async def archive_event(
        event_id: str,
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Перенос события в архив (isActive = False)."""
    try:
        await _require_admin(db, access_jwt, refresh_jwt)
        # Исправлено: ранее сюда ошибочно передавалась модель Users
        return await database.events.edit_event(
            event_id, {'isActive': False}, db, models.events.Events
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')


@admin_page.get(
    '/grant_admin/{user_id}',
    response_model=schemas.users.UserResponse,
)
async def grant_admin(
        user_id: str,
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Назначение роли ADMIN."""
    try:
        await _require_admin(db, access_jwt, refresh_jwt)
        to_user = await database.users.find_user_by_id(user_id, db, models.users.Users)
        if not to_user:
            raise HTTPException(status_code=404, detail='User not found')
        if to_user.role == 'ADMIN':
            raise HTTPException(status_code=403, detail='permission denied: user is already ADMIN')
        return await database.users.edit_user(
            user_id, {'role': 'ADMIN'}, db, models.users.Users
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')


@admin_page.get(
    '/demote_admin/{user_id}',
    response_model=schemas.users.UserResponse,
)
async def demote_admin(
        user_id: str,
        db: AsyncSession = Depends(get_db),
        access_jwt: Annotated[str | None, Cookie()] = None,
        refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    """Снятие роли ADMIN (до USER)."""
    try:
        await _require_admin(db, access_jwt, refresh_jwt)
        to_user = await database.users.find_user_by_id(user_id, db, models.users.Users)
        if not to_user:
            raise HTTPException(status_code=404, detail='User not found')
        if to_user.role == 'USER':
            raise HTTPException(status_code=403, detail='permission denied: user is already USER')
        return await database.users.edit_user(
            user_id, {'role': 'USER'}, db, models.users.Users
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')