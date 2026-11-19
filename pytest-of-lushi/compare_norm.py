"""Сверка распознанных строк с эталонным XLSX без различий оформления.

Сравнивается содержание, а не типографика: кавычки, тире, переносы строк
организатора и лишние пробелы не считаются расхождением. Всё остальное —
потерянный или искажённый текст — показывается построчно.
"""
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
dump = f'pytest-of-lushi/full_{year}.json'
if not os.path.exists(dump):
    dump = f'pytest-of-lushi/parsed_{year.replace("-", "_")}.json'
with open(dump, encoding='utf-8') as handle:
    parsed = OfficialList.from_dict(json.load(handle))


def norm(value) -> str:
    text = str(value or '')
    text = text.replace('“', '«').replace('”', '»').replace('„', '«')
    text = text.replace('–', '-').replace('—', '-').replace('−', '-')
    text = re.sub(r'[«»"\'`]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip().casefold()


reference = openpyxl.load_workbook(
    rf'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\table\{year}.xlsx'
).worksheets[0]

with tempfile.TemporaryDirectory() as tmp:
    path = list_xlsx.save(parsed, os.path.join(tmp, 'list.xlsx'))
    generated = openpyxl.load_workbook(path).worksheets[0]

mismatch = 0
for index, row in enumerate(parsed.rows, start=2):
    expected = [reference.cell(row=index, column=c).value for c in range(1, 7)]
    actual = [generated.cell(row=index, column=c).value for c in range(1, 7)]
    diffs = [
        (column, expected_value, actual_value)
        for column, (expected_value, actual_value) in enumerate(
            zip(expected, actual), start=1
        )
        if norm(expected_value) != norm(actual_value)
    ]
    if diffs:
        mismatch += 1
        print('DIFF row', index, 'p', row.page)
        for column, expected_value, actual_value in diffs:
            print('   col', column)
            print('    ref :', str(expected_value)[:200])
            print('    got :', str(actual_value)[:200])

print(
    'rows compared', len(parsed.rows),
    'rows with content differences', mismatch,
    'rows in reference', reference.max_row - 1,
)
