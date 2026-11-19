"""Проверка разбора одной страницы: имитируем предыдущую олимпиаду."""
import os
import sys

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

import numpy as np  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402

from app.rsosh import list_parser as lp, preprocessing  # noqa: E402

page_number = int(sys.argv[1]) if len(sys.argv) > 1 else 77
pdf = pdfium.PdfDocument(
    r'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\original\26-27.pdf'
)
image = pdf[page_number - 1].render(scale=300 / 72.0).to_pil().convert('RGB')
array = np.ascontiguousarray(np.array(image)[:, :, ::-1])
binary = preprocessing.prepare(array)['image']
angle, conf, binary, skew, vertical, horizontal = lp._orient_page(binary)
bands = lp._table_columns(binary, vertical=vertical, horizontal=horizontal)
columns = lp._ocr_columns(binary, bands)
height, width = binary.shape[:2]
horizontal_values = [center for center, _ in horizontal]
table_top = lp._table_top(horizontal, width, height)
boundaries = sorted(
    {table_top, *[value for value in horizontal_values if value > table_top], height}
)
boundaries = lp._dedupe_boundaries(boundaries, height)

state = lp._Stitcher()
state.current = {
    'number': '50',
    'name_parts': ['Открытая химическая олимпиада'],
    'organizer_parts': [],
    'rows': [
        {
            'profile': 'химия',
            'subjects': 'химия',
            'level': '1',
            'level_raw': 'I',
            'page': 76,
            'source_row': 1,
            'source_band': 1,
            'confidence': 0.5,
            'raw': {'organizer': ''},
            'issues': [],
        }
    ],
}
state.groups = [state.current]
state.consume_page(
    columns=columns,
    boundaries=boundaries,
    binary=binary,
    bands=bands,
    page_number=page_number,
)
for group in state.groups:
    print('GROUP', group['number'], repr(' '.join(group['name_parts'])))
    for row in group['rows']:
        print('   ', repr(row['profile']), row['level'], '|', repr(row['raw'].get('organizer', ''))[:70])
print('issues', state.page_issues)
