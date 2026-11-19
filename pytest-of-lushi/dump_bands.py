"""Постраничный дамп полос: что видит сборщик строк на странице."""
import os
import sys

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

import numpy as np  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402

from app.rsosh import list_parser as lp  # noqa: E402
from app.rsosh import ocr, preprocessing  # noqa: E402

year = sys.argv[1]
page_index = int(sys.argv[2])
pdf = pdfium.PdfDocument(
    rf'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\original\{year}.pdf'
)
scale = 300 / 72.0
image = pdf[page_index].render(scale=scale).to_pil().convert('RGB')
array = np.ascontiguousarray(np.array(image)[:, :, ::-1])
binary = preprocessing.prepare(array)['image']
angle, conf, binary, skew, vertical, horizontal = lp._orient_page(binary)
bands = lp._table_columns(binary, vertical=vertical, horizontal=horizontal)
print('page', page_index + 1, 'angle', angle, 'bands', bands)
columns = lp._ocr_columns(binary, bands)
height, width = binary.shape[:2]
horizontal_values = [c for c, _ in horizontal]
table_top = lp._table_top(horizontal, width, height)
if len(horizontal_values) < 2:
    horizontal_values = lp._rows_from_words(
        [w for col in columns for w in col], height
    )
    table_top = horizontal_values[0] if horizontal_values else 0
boundaries = sorted(
    {table_top, *[v for v in horizontal_values if v > table_top], height}
)
boundaries = lp._dedupe_boundaries(boundaries, height)
for i, (top, bottom) in enumerate(zip(boundaries, boundaries[1:])):
    row = lp._columns_of_band(columns, top, bottom)
    texts = [lp._cell_text(col) for col in row]
    number = lp._read_number(binary, bands[0], top, bottom, fallback=texts[0])
    print(f'--- band {i} y {top}-{bottom} number={number!r}')
    print('  A', repr(texts[0]))
    print('  B', repr(texts[1][:160]))
    print('  C', repr(lp._cell_text(row[2], newline=True)[:160]))
    print('  D', repr(lp._tidy_profile(texts[3])[:160]))
    print('  E', repr(lp._tidy_subjects(texts[4])[:160]))
    print('  F', repr(texts[5]))
    print(
        '  header?', lp._header_band(' '.join(texts)),
        'name_header?', lp._header_band(lp._soften_caps(texts[1], min_length=4)),
    )
    level, level_text, level_issues = lp._read_level(
        binary, bands[5], top, bottom, fallback=texts[5]
    )
    print(
        '  level', level, repr(level_text), level_issues,
        'bars', lp._vertical_bars(binary, bands[5], top, bottom),
        'colF', repr(lp._ocr_cell(binary, bands[5], top, bottom,
                                  whitelist='IVX123')),
    )
