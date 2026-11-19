"""Примеры расхождений по колонке организатора: эталон против генерации."""
import json
import os
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

shown = 0
for index in range(2, reference.max_row + 1):
    expected = str(reference.cell(row=index, column=3).value or '').strip()
    actual = str(generated.cell(row=index, column=3).value or '').strip()
    if expected == actual:
        continue
    print('row', index, 'ref  ', repr(expected[:150]))
    print('row', index, 'gen  ', repr(actual[:150]))
    shown += 1
    if shown >= 5:
        break
