"""Полный разбор года и сверка количества строк/олимпиад с эталоном."""
import json
import os
import sys
import time

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

import openpyxl  # noqa: E402

from app.rsosh import list_parser  # noqa: E402

year = sys.argv[1] if len(sys.argv) > 1 else '26-27'
started = time.time()
doc = list_parser.parse_official_list(
    rf'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\original\{year}.pdf'
)
path = f'pytest-of-lushi/full_{year}.json'
with open(path, 'w', encoding='utf-8') as handle:
    json.dump(doc.to_dict(), handle, ensure_ascii=False, indent=1)

numbers = [row.number for row in doc.rows if row.number]
olympiads = len(set(numbers))
reference = openpyxl.load_workbook(
    rf'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\table\{year}.xlsx'
).worksheets[0]
reference_numbers = {
    str(reference.cell(row=index, column=1).value).strip()
    for index in range(2, reference.max_row + 1)
    if reference.cell(row=index, column=1).value not in (None, '')
}
print(
    year,
    f'{time.time() - started:.0f}s',
    'rows', len(doc.rows), 'reference', reference.max_row - 1,
    'olympiads', olympiads, 'reference', len(reference_numbers),
    'season', doc.season_label, 'complete', doc.complete,
    'level_missing', sum(1 for row in doc.rows if not row.level),
    'profile_missing', sum(1 for row in doc.rows if not row.profile),
)
print('warnings', doc.warnings)
missing = sorted(reference_numbers - set(numbers), key=lambda v: int(v))
extra = sorted(set(numbers) - reference_numbers, key=lambda v: int(v))
print('numbers missing', missing[:20], 'extra', extra[:20])
