import jwt
import os
from functools import wraps
from flask import request
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, ParamSpec, TypeVar, Coroutine

SECRET = os.getenv('JWT_KEY')

D_Spec = ParamSpec('D_Spec')
D_Return = TypeVar('D_Return')

async def create_jwt(
        ins: dict,
        is_refresh: bool,
) -> str:
    '''
    Асинхронный создатель jwt токенов
    '''
    ins['iat'] = datetime.now(tz=timezone.utc)
    if is_refresh:
        ins['exp'] = datetime.now(tz=timezone.utc) + timedelta(seconds=86400)
    else:
        ins['exp'] = datetime.now(tz=timezone.utc) + timedelta(seconds=3600)

    return jwt.encode(ins, SECRET, algorithm="HS256")


def jwt_check(
        func: Callable[
            D_Spec,
            Coroutine[Any, Any, D_Return]
        ]
) -> Callable[
    D_Spec,
    Coroutine[Any, Any, D_Return]
]:
    '''
    Асинхронный декоратор для обработки входящих jwt токенов
    '''
    @wraps(func)
    async def wrapper(
            *args: D_Spec.args,
            **kwargs: D_Spec.kwargs
    ) -> D_Return:
        # try:
        #     jwt.decode(token, "secret", algorithms=["HS256"])
        # except jwt.ExpiredSignatureError:
        #     print("expired")
        return await func(*args, **kwargs)
    return wrapper