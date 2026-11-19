import json
import os
import sys

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

import openpyxl  # noqa: E402

from app.rsosh.list_parser import OfficialList  # noqa: E402

for year in ('26-27', '17-18'):
    with open(f'pytest-of-lushi/full_{year}.json', encoding='utf-8') as handle:
        parsed = OfficialList.from_dict(json.load(handle))
    reference = openpyxl.load_workbook(
        rf'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\table\{year}.xlsx'
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

    ref_pairs = []
    for index in range(2, reference.max_row + 1):
        name = norm(reference.cell(row=index, column=2).value)
        profile = norm(reference.cell(row=index, column=4).value)
        ref_pairs.append((name, profile))
    got_pairs = [(norm(row.olympiad), norm(row.profile)) for row in parsed.rows]

    # Мультимножества: сколько строк с такой парой «олимпиада+профиль».
    from collections import Counter

    ref_counter = Counter(ref_pairs)
    got_counter = Counter(got_pairs)
    common = sum((ref_counter & got_counter).values())

    ref_names = {name for name, _ in ref_pairs}
    got_names = {name for name, _ in got_pairs}
    print(
        year,
        'rows', len(got_pairs), '/', len(ref_pairs),
        '| profile rows matched', common, f'({common / len(ref_pairs):.0%})',
        '| olympiad names matched', len(ref_names & got_names), '/',
        len(ref_names),
    )
