import os
import sys

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402

from app.rsosh import list_parser as lp  # noqa: E402
from app.rsosh import preprocessing  # noqa: E402

pdf = pdfium.PdfDocument(
    r'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\original\17-18.pdf'
)
image = pdf[2].render(scale=300 / 72.0).to_pil().convert('RGB')
array = np.ascontiguousarray(np.array(image)[:, :, ::-1])
binary = preprocessing.prepare(array)['image']
angle, conf, binary, skew, vertical, horizontal = lp._orient_page(binary)
bands = lp._table_columns(binary, vertical=vertical, horizontal=horizontal)
left, right = bands[5]
top, bottom = 942, 1139
for margin in (0, 4, 8, 12, 20):
    x0, x1 = int(left) + margin, int(right) - margin
    y0, y1 = top + 8, bottom - 8
    crop = binary[y0:y1, x0:x1]
    ink = cv2.bitwise_not(crop)
    count, _labels, stats, _c = cv2.connectedComponentsWithStats(ink, 8)
    print('margin', margin, 'components', count - 1)
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        print('   w', w, 'h', h, 'area', area, 'ratio', round(w / max(1, h), 2))
