import jwt
import os
import inspect
from functools import wraps
from flask import request
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, ParamSpec, TypeVar, Coroutine

SECRET = os.getenv('JWT_KEY')

D_Spec = ParamSpec('D_Spec')
D_Return = TypeVar('D_Return')

async def create_jwt(
        ins: dict,
        is_refresh: bool = False,
) -> str:
    '''
    Асинхронный создатель jwt токенов
    '''
    ins['iat'] = datetime.now(tz=timezone.utc)
    if is_refresh:
        ins['exp'] = datetime.now(tz=timezone.utc) + timedelta(seconds=1209600)
    else:
        ins['exp'] = datetime.now(tz=timezone.utc) + timedelta(seconds=600)

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
    Асинхронный декоратор для обработки входящих jwt токенов. Работает только, если есть True последний параметр и параметр-схема с jwt в первом
    '''
    @wraps(func)
    async def wrapper(
            *args: D_Spec.args,
            **kwargs: D_Spec.kwargs
    ) -> D_Return:
        args_list = list(args)
        try:
            jwt.decode(args_list[0].jwt.token, "secret", algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            args_list[-1] = False
        return await func(*args, **kwargs)
    return wrapper