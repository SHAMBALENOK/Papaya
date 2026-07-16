from fastapi import FastAPI, Depends, HTTPException, Cookie
from fastapi.responses import JSONResponse
from app.database.database import get_db
import app.middlewares.tokenz.main as tokenz
from sqlalchemy.ext.asyncio import AsyncSession
from app import models, schemas, database
from typing import Annotated
from app.routers import user, events, auth

app = FastAPI(root_path="/api/v1")

app.include_router(user.user_page)
app.include_router(events.events_page)
app.include_router(auth.auth_page)

@app.get(
    '/',
    response_model=JSONResponse,
    responses={
        200: {'model': JSONResponse, 'hint': 'OK'},
        401: {'model': HTTPException, 'hint': 'Access or refresh token missing'},
        403: {'model': HTTPException, 'hint': 'Invalid refresh or access token'},
        500: {'model': HTTPException, 'hint': 'Something has broken ¯\_(ツ)_/¯'},
    }
)
async def main(
    db: AsyncSession = Depends(get_db),
    access_jwt: Annotated[str | None, Cookie()] = None,
    refresh_jwt: Annotated[str | None, Cookie()] = None,
):
    try:
        jwt_data = await tokenz.jwt_check(access_jwt, refresh_jwt)
        user = database.users.find_user_by_id(jwt_data.get('sub'), db, models.users)
        random_events = database.events.show_random_events(
            quantity=database.events.get_amount_of_events(
                session=db,
                model=models.events,
            ),
            session=db,
            model=models.events,
        )

        return JSONResponse(
            status_code=200,
            content={
                'user_id': user.id,
                'user_name': user.name,
                'user_surname': user.surname,
                'user_email': user.email,
                'events': random_events,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'App has broken caused by error\n{e}\n ¯\_(ツ)_/¯' )