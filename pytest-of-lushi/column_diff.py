import json
import os
import re
import sys
import tempfile

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

import openpyxl  # noqa: E402

from app.rsosh import list_xlsx  # noqa: E402
from app.rsosh.list_parser import OfficialList  # noqa: E402

year = sys.argv[1] if len(sys.argv) > 1 else '26-27'
with open(f'pytest-of-lushi/full_{year}.json', encoding='utf-8') as handle:
    parsed = OfficialList.from_dict(json.load(handle))

reference = openpyxl.load_workbook(
    rf'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\table\{year}.xlsx'
).worksheets[0]

with tempfile.TemporaryDirectory() as tmp:
    generated = openpyxl.load_workbook(
        list_xlsx.save(parsed, os.path.join(tmp, 'list.xlsx'))
    ).worksheets[0]


def norm(value):
    text = str(value or '')
    for source, target in (
        ('\u201c', '\u00ab'), ('\u201d', '\u00bb'), ('\u201e', '\u00ab'),
        ('\u2013', '-'), ('\u2014', '-'), ('\u2212', '-'),
    ):
        text = text.replace(source, target)
    text = ''.join(ch for ch in text if ch not in '\u00ab\u00bb"\'`')
    return ' '.join(text.split()).strip().casefold()


columns = {1: 'A номер', 2: 'B олимпиада', 3: 'C организатор',
           4: 'D профиль', 5: 'E предметы', 6: 'F уровень'}
diffs = {column: 0 for column in columns}
for index, row in enumerate(parsed.rows, start=2):
    for column in columns:
        expected = norm(reference.cell(row=index, column=column).value)
        actual = norm(generated.cell(row=index, column=column).value)
        if expected != actual:
            diffs[column] += 1

print('rows', len(parsed.rows))
for column, label in columns.items():
    print(f'{label:14} differs in {diffs[column]:3} / {len(parsed.rows)} rows')

# Олимпиад в сводке: сколько строк листа «Сводка» совпало по составу.
summary = openpyxl.load_workbook(
    rf'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\table\{year}.xlsx'
).worksheets[1]
print('reference summary rows', summary.max_row - 1)
print('generated summary rows', len(list_xlsx.summary(parsed.rows)))
