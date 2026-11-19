"""Сравнение двух вариантов колонки организатора с эталоном.

A — то, что сейчас в XLSX: клетка полосы строки (organizer_row).
B — организатор всей олимпиады (union), один и тот же во всех её строках.
Заодно проверяем, одинаков ли организатор у строк одной олимпиады в эталоне:
если да, вариант B ближе к оригиналу.
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

import openpyxl  # noqa: E402

from app.rsosh.list_parser import OfficialList  # noqa: E402

year = sys.argv[1] if len(sys.argv) > 1 else '26-27'
with open(f'pytest-of-lushi/full_{year}.json', encoding='utf-8') as handle:
    parsed = OfficialList.from_dict(json.load(handle))
reference = openpyxl.load_workbook(
    rf'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\table\{year}.xlsx'
).worksheets[0]


def norm(value):
    text = str(value or '')
    for source, target in (('\u201c', '"'), ('\u201d', '"'), ('\u201e', '"')):
        text = text.replace(source, target)
    text = text.replace('\u00ab', '"').replace('\u00bb', '"')
    text = ''.join(ch for ch in text if ch not in '"\'`')
    return ' '.join(text.split()).strip().casefold()


rows = range(2, reference.max_row + 1)
expected = Counter(norm(reference.cell(row=row, column=3).value) for row in rows)
expected.pop('', None)

option_a = Counter(norm(row.organizer_row or '') for row in parsed.rows)
option_b = Counter(norm(row.organizer or '') for row in parsed.rows)
for label, actual in (('A organizer_row', option_a), ('B organizer', option_b)):
    shared = sum((expected & actual).values())
    print(f'{label:16} {shared:3} / {sum(expected.values()):3}')

# Одинаков ли организатор у строк одной олимпиады в эталоне?
per_olympiad: dict[str, set[str]] = {}
for row in parsed.rows:
    per_olympiad.setdefault(norm(row.olympiad), set())
index_by_name: dict[str, list[str]] = {}
for row in parsed.rows:
    index_by_name.setdefault(norm(row.olympiad), []).append(
        norm(reference.cell(row=parsed.rows.index(row) + 2, column=3).value)
    )
same = sum(1 for values in index_by_name.values() if len(set(values)) == 1)
print(f'олимпиад с одинаковым организатором во всех строках эталона: '
      f'{same} / {len(index_by_name)}')
