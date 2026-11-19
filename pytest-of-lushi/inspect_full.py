import json
import os
import sys

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

import openpyxl

from app.rsosh import list_xlsx
from app.rsosh.list_parser import OfficialList

year = sys.argv[1] if len(sys.argv) > 1 else '26-27'
with open(f'pytest-of-lushi/full_{year}.json', encoding='utf-8') as handle:
    parsed = OfficialList.from_dict(json.load(handle))

reference = openpyxl.load_workbook(
    rf'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\table\{year}.xlsx'
)

ref_list = reference.worksheets[0]
ref_summary = reference.worksheets[1]

print('parsed rows', len(parsed.rows), 'ref rows', ref_list.max_row - 1)
print('parsed summary', len(list_xlsx.summary(parsed.rows)), 'ref summary',
      ref_summary.max_row - 1)
print('season', parsed.season_label, 'complete', parsed.complete)

# Olympiads in reference summary not found in parsed groups
parsed_names = {}
for row in parsed.rows:
    parsed_names.setdefault(row.olympiad.strip(), 0)
    parsed_names[row.olympiad.strip()] += 1

ref_names = []
for index in range(2, ref_summary.max_row + 1):
    name = ref_summary.cell(row=index, column=2).value
    if name:
        ref_names.append(str(name).strip())

def norm(value):
    text = str(value or '')
    for source, target in (
        ('\u201c', '\u00ab'), ('\u201d', '\u00bb'), ('\u201e', '\u00ab'),
        ('\u2013', '-'), ('\u2014', '-'), ('\u2212', '-'),
    ):
        text = text.replace(source, target)
    text = ''.join(ch for ch in text if ch not in '\u00ab\u00bb"\'`')
    return ' '.join(text.split()).strip().casefold()

parsed_norms = {norm(name) for name in parsed_names}
print('\n-- in reference summary, absent in parse:')
for name in ref_names:
    if norm(name) not in parsed_norms:
        print('   ', name)

print('\n-- in parse, absent in reference summary:')
ref_norms = {norm(name) for name in ref_names}
for name in parsed_names:
    if norm(name) not in ref_norms:
        print('   ', name)

print('\n-- rows with missing level:')
for row in parsed.rows:
    if not row.level:
        print(f'   p{row.page} #{row.number} {row.olympiad[:50]!r} '
              f'profile={row.profile[:50]!r} raw={row.level_raw!r}')

print('\n-- rows with empty profile:')
for row in parsed.rows:
    if not row.profile:
        print(f'   p{row.page} #{row.number} {row.olympiad[:60]!r}')

print('\n-- odd numbers:')
for row in parsed.rows:
    if row.number in ('0', None):
        print(f'   p{row.page} #{row.number} {row.olympiad[:60]!r} '
              f'profile={row.profile[:40]!r} level={row.level!r}')
