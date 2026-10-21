"""Диагностический прогон вузовского адаптера на реальном приказе.

Скрипт не трогает базу: он только извлекает страницы, разбирает приказ и
сообщает метрики разбора (записи, распознанный вуз, предупреждения, доля
строк без направления). Нужен, чтобы измерить «до/после» и зафиксировать
методику в отчёте этапа.

    python scripts/university_baseline.py app/tables/rsosh_bvi/rsosh_bvi.pdf --json out.json

Переменные окружения: ``DATABASE_URL`` и ``JWT_KEY`` нужны лишь потому, что
пакет ``app.university`` тянет за собой модели через оркестратор.
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

from app.university.parsing import build_page_reports, parse_pages  # noqa: E402
from app.rsosh.extraction import extract_document  # noqa: E402


def _summarize(path: str) -> dict:
    started = time.monotonic()
    pages = extract_document(path)
    extract_seconds = time.monotonic() - started

    # Разбор возвращает и строки приказа, и распознанный вуз (из шапки письма),
    # и предупреждения: ровно то, что боевой ``processor.run_import`` кладёт в
    # раздел ``metadata['university']``.
    started = time.monotonic()
    records, warnings, university = parse_pages(pages)
    parse_seconds = time.monotonic() - started

    reports = build_page_reports(pages)
    names = [record.olympiad_name for record in records]
    unique_names = sorted({record.name_norm for record in records})
    missing_direction = sum(
        1 for record in records if not record.meta.get('direction')
    )
    missing_olympiad_word = sum(
        1 for record in records if 'олимпиад' not in record.olympiad_name.lower()
    )
    confidences = [
        page.confidence for page in pages if page.confidence is not None
    ]
    return {
        'path': path,
        'pages': len(pages),
        'extract_seconds': round(extract_seconds, 1),
        'parse_seconds': round(parse_seconds, 1),
        'university': {
            'name': (university or {}).get('name') if university else None,
            'name_norm': (university or {}).get('name_norm') if university else None,
        },
        'records': len(records),
        'unique_olympiads': len(unique_names),
        'missing_direction': missing_direction,
        'missing_olympiad_word': missing_olympiad_word,
        'pages_with_records': len({record.page for record in records}),
        'warnings': len(warnings),
        'mean_confidence': (
            round(sum(confidences) / len(confidences), 3) if confidences else None
        ),
        'records_detail': [
            {
                'page': record.page,
                'row': record.row,
                'name': record.olympiad_name,
                'direction': record.meta.get('direction'),
                'profile': record.meta.get('profile'),
                'subject': record.meta.get('subject'),
                'level': record.meta.get('level'),
                'diploma': record.meta.get('diploma'),
            }
            for record in records
        ],
        'unique_olympiad_names': unique_names,
        'page_reports': [report.to_dict() for report in reports],
        'warnings_detail': warnings,
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
