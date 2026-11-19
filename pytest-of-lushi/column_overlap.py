"""Сверка содержимого по колонкам: множества значений, а не позиции строк.

Построчное сравнение сбивается от одного сдвига: строка потеряна в начале —
и все последующие считаются расхождением. Здесь сравниваются составы
колонок: сколько значений эталона встретилось в сгенерированной таблице.
"""
import json
import os
import sys
import tempfile
from collections import Counter

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


def column(sheet, index, rows):
    return [norm(sheet.cell(row=row, column=index).value) for row in rows]


rows = range(2, reference.max_row + 1)
columns = {1: 'A номер', 2: 'B олимпиада', 3: 'C организатор',
           4: 'D профиль', 5: 'E предметы', 6: 'F уровень'}
for index, label in columns.items():
    expected = Counter(value for value in column(reference, index, rows) if value)
    actual = Counter(value for value in column(generated, index, rows) if value)
    shared = sum((expected & actual).values())
    total = sum(expected.values())
    print(f'{label:14} {shared:3} / {total:3} значений эталона найдено')
