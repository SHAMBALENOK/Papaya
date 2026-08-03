from fastapi import FastAPI, Depends, HTTPException, Cookie
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from app.database.database import get_db
import app.middlewares.tokenz.main as tokenz
from sqlalchemy.ext.asyncio import AsyncSession
from app import models, schemas, database
from typing import Annotated
from app.routers import user, events, auth
import os
from contextlib import asynccontextmanager
from app.database.database import init_models
import debugpy

debugpy.listen(("0.0.0.0", 5678))
# Опционально, если нужно остановить код до нажатия F5:
# debugpy.wait_for_client()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Только один воркер создаёт таблицы
    if os.environ.get("GUNICORN_WORKER_ID", "0") == "0":
        try:
            await init_models()
        except Exception:
            pass  # таблицы уже существуют
    yield

app = FastAPI(lifespan=lifespan)

app.include_router(user.user_page, prefix="/api/v1")
app.include_router(events.events_page, prefix="/api/v1")
app.include_router(auth.auth_page, prefix="/api/v1")


@app.get('/api/v1/')
async def main(
    db: AsyncSession = Depends(get_db),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        user_obj = await database.users.find_user_by_id(jwt_data.get('sub'), db, models.users.Users)
        random_events = await database.events.show_random_events(
            quantity=await database.events.get_amount_of_events(session=db, model=models.events.Events),
            session=db,
            model=models.events.Events,
        )

        # Сериализуем events в словари
        events_list = [
            {
                'id': str(ev.id),
                'owner': str(ev.owner) if ev.owner else None,
                'name': ev.name,
                'disc': ev.disc,
                'preview_picture': ev.preview_picture,
                'picture': ev.picture,
                'isActive': ev.isActive,
                'createdAt': ev.createdAt.isoformat() if ev.createdAt else None,
                'updatedAt': ev.updatedAt.isoformat() if ev.updatedAt else None,
            }
            for ev in random_events
        ]

        return JSONResponse(status_code=200, content={
            'user_id': str(user_obj.id),       # UUID → str
            'user_name': user_obj.name,
            'user_surname': user_obj.surname,
            'user_email': user_obj.email,
            'events': events_list,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}')


# --- Frontend ---
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), 'frontend')

app.mount('/frontend', StaticFiles(directory=FRONTEND_DIR), name='frontend')


@app.get('/')
@app.get('/{path:path}')
async def spa_fallback(path: str = ''):
    # Если запрашивается файл из /frontend — отдаём его
    file_path = os.path.join(FRONTEND_DIR, path)
    if path and os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse(os.path.join(FRONTEND_DIR, 'index.html'))