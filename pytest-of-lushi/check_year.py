"""Быстрая проверка разбора разных лет: шапка, сезон, первые строки."""
import os
import sys

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

from app.rsosh import list_parser  # noqa: E402

year = sys.argv[1]
pages = int(sys.argv[2]) if len(sys.argv) > 2 else 6
path = rf'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\original\{year}.pdf'
doc = list_parser.parse_official_list(path, max_pages=pages)
print('=' * 70)
print(year, 'season', doc.season_label, 'header', doc.header_source)
print('headers:', doc.headers)
print('rows', len(doc.rows), 'warnings', doc.warnings[:2])
for row in doc.rows:
    print(
        row.number, '|', row.profile[:50], '|',
        row.subjects[:70], '|', row.level,
        '| p', row.page,
    )
