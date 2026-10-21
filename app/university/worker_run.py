"""Точка входа импорта приказа университета для отдельного процесса.

Запускается воркером (или вручную для отладки):

    python -m app.university.worker_run <doc_id>

Нужен собственный интерпретатор, потому что у воркера нет event loop, а
``run_import`` работает через async SQLAlchemy.
"""

import asyncio
import logging
import sys

from app.core.config import validate_config

validate_config()

from app.database.database import engine  # noqa: E402
from app.university.processor import run_import  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            'usage: python -m app.university.worker_run <doc_id>', file=sys.stderr
        )
        return 2

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )
    doc_id = argv[1]

    async def _run() -> int:
        try:
            doc = await run_import(doc_id)
        finally:
            await engine.dispose()
        section = ((doc or {}).get('metadata') or {}).get('university') or {}
        print(f"university import of {doc_id}: state={section.get('state')}")
        return 0 if section.get('state') == 'review' else 1

    return asyncio.run(_run())


if __name__ == '__main__':
    sys.exit(main(sys.argv))
