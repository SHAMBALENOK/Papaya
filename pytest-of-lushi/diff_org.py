import json
import os
import re
import sys

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

import openpyxl  # noqa: E402

from app.rsosh.list_parser import OfficialList  # noqa: E402

parsed = OfficialList.from_dict(
    json.load(open('pytest-of-lushi/parsed_26_27.json', encoding='utf-8'))
)
reference = openpyxl.load_workbook(
    r'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\table\26-27.xlsx'
).worksheets[0]


def norm(value):
    text = str(value or '')
    for source, target in (
        ('\u201c', '\u00ab'), ('\u201d', '\u00bb'), ('\u201e', '\u00ab'),
        ('\u2013', '-'), ('\u2014', '-'), ('\u2212', '-'),
    ):
        text = text.replace(source, target)
    text = re.sub('[\u00ab\u00bb"\'`]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip().casefold()


for row in (3, 4, 6):
    expected = norm(reference.cell(row=row, column=3).value)
    actual = norm(parsed.rows[row - 2].organizer)
    print('row', row, len(expected), len(actual), expected == actual)
    if expected != actual:
        index = 0
        while (
            index < min(len(expected), len(actual))
            and expected[index] == actual[index]
        ):
            index += 1
        print(' at', index)
        print(' ref', repr(expected[index:index + 120]))
        print(' got', repr(actual[index:index + 120]))
