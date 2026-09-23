"""Точка входа RSOSH-импорта в отдельном процессе (модульная команда).

Запускается Celery-воркером (``processor.rsosh_import_task``) и вручную::

    python -m app.rsosh.worker_run <doc_id>
"""

import asyncio
import sys

from app.rsosh import states
from app.rsosh.processor import run_import


def main() -> int:
    if len(sys.argv) < 2:
        print('usage: python -m app.rsosh.worker_run <doc_id>', file=sys.stderr)
        return 2
    doc_id = sys.argv[1]
    section = asyncio.run(run_import(doc_id))
    print(
        f'rsosh import {doc_id} -> {section.get("state", "?")} '
        f'summary={section.get("summary")}',
        file=sys.stderr,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())