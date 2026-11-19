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

with open('pytest-of-lushi/parsed_26_27.json', encoding='utf-8') as handle:
    parsed = OfficialList.from_dict(json.load(handle))

print('rows', len(parsed.rows), 'warnings', parsed.warnings)
for row in parsed.rows:
    print(row.number, '|', row.profile[:45], '|', row.subjects[:95], '|', row.level)

reference = openpyxl.load_workbook(
    r'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\table\26-27.xlsx'
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
        if str(expected_value or '').strip() != str(actual_value or '').strip()
    ]
    if diffs:
        mismatch += 1
        print('DIFF row', index)
        for column, expected_value, actual_value in diffs:
            print('   col', column)
            print('    ref :', str(expected_value)[:160])
            print('    got :', str(actual_value)[:160])

print('rows compared', len(parsed.rows), 'rows with differences', mismatch)
