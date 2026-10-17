"""Создать (или повысить) первого администратора Papaya.

Зачем отдельный скрипт: роль администратора назначается только из панели
действующим администратором (``POST /admin/role/{user_id}``). На чистой
установке администратора ещё нет, поэтому зайти в панель и назначить первого
некому — «курица и яйцо». Этот скрипт заводит первого администратора напрямую
в БД, минуя API, и предназначен для разового запуска при развёртывании.

Идемпотентность: если пользователь с таким email уже есть — пароль не трогаем,
только повышаем роль до ``ADMIN`` (или сообщаем, что он уже администратор).
Повторный запуск безопасен.

Использование:

    python scripts/create_admin.py --email admin@example.com --password 'StrongPass123!'
    # либо через переменные окружения:
    ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD='StrongPass123!' python scripts/create_admin.py

Требуется заданный ``DATABASE_URL`` (как и у остального приложения).
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database.database import AsyncSessionLocal  # noqa: E402
from app.database.users import ROLE_ADMIN  # noqa: E402
from app.middlewares import re_check  # noqa: E402
from app.models.users import Users  # noqa: E402


async def _create_or_promote(
    *,
    email: str,
    password: str | None,
    name: str,
    surname: str,
) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Users).where(Users.email == email))
        user = result.scalars().first()

        if user is None:
            if not password:
                print(
                    'ERROR: пользователя с таким email нет — нужен --password '
                    '(или ADMIN_PASSWORD), чтобы его создать.',
                    file=sys.stderr,
                )
                return 2
            valid, message = re_check.is_valid_password(password)
            if not valid:
                print(f'ERROR: пароль не прошёл проверку: {message}', file=sys.stderr)
                return 2
            user = Users(
                name=name,
                surname=surname,
                email=email,
                password=bcrypt.hashpw(
                    password.encode('utf-8'), bcrypt.gensalt(rounds=12)
                ).decode('utf-8'),
            )
            session.add(user)
            await session.flush()
            print(f'INFO: создан пользователь {email}')

        if user.role == ROLE_ADMIN:
            print(f'INFO: {email} уже администратор — изменений не требуется')
            return 0

        user.role = ROLE_ADMIN
        user.isActive = True
        await session.commit()
        print(f'INFO: {email} повышен до администратора')
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Создать первого администратора Papaya')
    parser.add_argument('--email', default=os.getenv('ADMIN_EMAIL'))
    parser.add_argument('--password', default=os.getenv('ADMIN_PASSWORD'))
    parser.add_argument('--name', default=os.getenv('ADMIN_NAME', 'Admin'))
    parser.add_argument('--surname', default=os.getenv('ADMIN_SURNAME', 'Papaya'))
    args = parser.parse_args()

    if not os.environ.get('DATABASE_URL'):
        print('ERROR: DATABASE_URL is not set', file=sys.stderr)
        return 2
    if not args.email:
        print(
            'ERROR: укажите --email (или ADMIN_EMAIL)',
            file=sys.stderr,
        )
        return 2

    return asyncio.run(
        _create_or_promote(
            email=args.email.strip(),
            password=args.password,
            name=args.name,
            surname=args.surname,
        )
    )


if __name__ == '__main__':
    sys.exit(main())
