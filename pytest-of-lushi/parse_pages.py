import os
import sys

import openpyxl

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

from app.rsosh import list_parser  # noqa: E402

doc = list_parser.parse_official_list(
    r'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\original\26-27.pdf',
    max_pages=9,
)
print('rows', len(doc.rows), 'warnings', doc.warnings)
for row in doc.rows:
    print('P', row.page, '#', row.number, '|', str(row.profile)[:42], '|',
          str(row.subjects)[:70], '|', row.level, row.issues)

print('=== REFERENCE ===')
wb = openpyxl.load_workbook(
    r'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\table\26-27.xlsx'
)
ws = wb.worksheets[0]
for r in range(2, 22):
    values = [ws.cell(row=r, column=c).value for c in range(1, 7)]
    print(values[0], '|', str(values[3])[:42], '|', str(values[4])[:70], '|', values[5])
