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
)
ref_summary = reference.worksheets[1]
ref_rows = [
    [ref_summary.cell(row=index, column=column).value for column in range(1, 5)]
    for index in range(2, ref_summary.max_row + 1)
]

with tempfile.TemporaryDirectory() as tmp:
    generated = openpyxl.load_workbook(
        list_xlsx.save(parsed, os.path.join(tmp, 'list.xlsx'))
    ).worksheets[1]
gen_rows = [
    [generated.cell(row=index, column=column).value for column in range(1, 5)]
    for index in range(2, generated.max_row + 1)
]


def norm(value):
    text = str(value or '')
    for source, target in (
        ('\u201c', '\u00ab'), ('\u201d', '\u00bb'), ('\u201e', '\u00ab'),
        ('\u2013', '-'), ('\u2014', '-'), ('\u2212', '-'),
    ):
        text = text.replace(source, target)
    text = ''.join(ch for ch in text if ch not in '\u00ab\u00bb"\'`')
    return ' '.join(text.split()).strip().casefold()


exact = 0
for index, ref in enumerate(ref_rows):
    gen = gen_rows[index] if index < len(gen_rows) else [None] * 4
    if [norm(value) for value in ref] == [norm(value) for value in gen]:
        exact += 1
print('reference summary rows', len(ref_rows))
print('generated summary rows', len(gen_rows))
print('positional exact matches', exact)

ref_names = {norm(row[1]): row for row in ref_rows}
matched = 0
for row in gen_rows:
    ref = ref_names.get(norm(row[1]))
    if ref and [norm(value) for value in ref[2:]] == [
        norm(value) for value in row[2:]
    ]:
        matched += 1
print('generated rows whose name+counts+levels match reference', matched)
