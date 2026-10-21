"""Диагностический прогон конвейера РСОШ на реальных документах.

Скрипт не трогает базу: он только извлекает страницы и разбирает их, чтобы
сравнить «до/после» по метрикам (записи, предупреждения, уверенность OCR).

    python scripts/rsosh_baseline.py 0001202510020015.pdf --json out.json

Переменные окружения: ``DATABASE_URL`` и ``JWT_KEY`` нужны лишь потому, что
пакет ``app.rsosh`` тянет за собой модели через оркестратор.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault('DATABASE_URL', 'postgresql+asyncpg://u:p@localhost:5432/papaya')
os.environ.setdefault('JWT_KEY', 'baseline-secret-key-for-local-measurements')

from app.rsosh.extraction import extract_document  # noqa: E402
from app.rsosh.parsing import parse_pages  # noqa: E402


def _summarize(path: str) -> dict:
    started = time.monotonic()
    pages = extract_document(path)
    extract_seconds = time.monotonic() - started

    started = time.monotonic()
    records, warnings = parse_pages(pages)
    parse_seconds = time.monotonic() - started

    page_rows = [len(page.tables[0]) if page.tables else 0 for page in pages]
    confidences = [
        page.confidence for page in pages if page.confidence is not None
    ]
    return {
        'path': path,
        'pages': len(pages),
        'extract_seconds': round(extract_seconds, 1),
        'parse_seconds': round(parse_seconds, 1),
        'records': len(records),
        'records_with_olympiad': sum(
            1 for record in records if 'олимпиад' in record.name.lower()
        ),
        'records_missing_olympiad': sum(
            1 for record in records if 'олимпиад' not in record.name.lower()
        ),
        'max_records_per_page': max(
            (sum(1 for record in records if record.page == page.page) for page in pages),
            default=0,
        ),
        'pages_with_records': len({record.page for record in records}),
        'header_unrecognized': sum(
            1 for warning in warnings if warning.startswith('Table header was not recognized')
        ),
        'skip_no_plausible_name': sum(
            1 for warning in warnings if 'название не похоже на олимпиаду' in warning
        ),
        'mean_confidence': round(
            sum(confidences) / len(confidences), 3
        ) if confidences else None,
        'page_rows': page_rows,
        'records': [
            {'page': record.page, 'row': record.row, 'name': record.name}
            for record in records
        ],
        'warnings': warnings,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='+')
    parser.add_argument('--json', dest='out', default=None)
    args = parser.parse_args(argv[1:])

    summaries = [_summarize(path) for path in args.paths]
    report = {'documents': summaries}
    print(json.dumps(report, ensure_ascii=False, indent=1))
    if args.out:
        Path(args.out).write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8'
        )
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
