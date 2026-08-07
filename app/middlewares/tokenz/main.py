import jwt
import os
from fastapi import HTTPException
from datetime import datetime, timezone, timedelta

SECRET = os.getenv('JWT_KEY')

async def create_jwt(
        ins: dict,
        is_refresh: bool = False,
) -> str:
    '''
    JWT creator
    '''
    ins['iat'] = datetime.now(tz=timezone.utc)
    if is_refresh:
        ins['exp'] = datetime.now(tz=timezone.utc) + timedelta(seconds=1209600)
    else:
        ins['exp'] = datetime.now(tz=timezone.utc) + timedelta(seconds=600)

    return jwt.encode(ins, SECRET, algorithm="HS256")

async def jwt_check(
    access_jwt: str | None = None,
    refresh_jwt: str | None = None,
) -> dict: #TODO: добавление access token в response
    """
    Validating incoming JWT token
    """
    if not access_jwt:
        raise HTTPException(status_code=401, detail="Access token missing", headers={"location": "/auth"})
    try:
        return jwt.decode(access_jwt, SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        if not refresh_jwt:
            raise HTTPException(status_code=401, detail="Refresh token missing", headers={"location": "/auth"})
        try:
            return jwt.decode(refresh_jwt, SECRET, algorithms=["HS256"])
        except jwt.PyJWTError:
            raise HTTPException(status_code=403, detail="Invalid refresh token", headers={"location": "/auth"})
    except jwt.PyJWTError:
        raise HTTPException(status_code=403, detail="Invalid access token", headers={"location": "/auth"})


# def jwt_check(
#         func: Callable[
#             D_Spec,
#             Coroutine[Any, Any, D_Return]
#         ]
# ) -> Callable[
#     D_Spec,
#     Coroutine[Any, Any, D_Return]
# ]:
#     '''
#     Асинхронный декоратор для обработки входящих jwt токенов.
#     '''
#     @wraps(func)
#     async def wrapper(
#             *args: D_Spec.args,
#             **kwargs: D_Spec.kwargs
#     ) -> D_Return:
#         sig = inspect.signature(func)
#         bound_args = sig.bind(*args, **kwargs)
#         bound_args.apply_defaults()
#         access_jwt = bound_args.arguments.get('access_jwt')
#         refresh_jwt = bound_args.arguments.get('refresh_jwt')
#         try:
#             jwt.decode(access_jwt, "secret", algorithms=["HS256"])
#         except jwt.ExpiredSignatureError:
#             try:
#                 jwt.decode(refresh_jwt, "secret", algorithms=["HS256"])
#             except jwt.ExpiredSignatureError:
#                 return JSONResponse(status_code=403, content=None, headers={"location": "/auth"})
#         return await func(*args, **kwargs)
#     return wrapper