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

args = sys.argv[1:]
year, page = args[0], int(args[1])
pdf = pdfium.PdfDocument(
    rf'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\original\{year}.pdf'
)
image = pdf[page].render(scale=300 / 72.0).to_pil().convert('RGB')
array = np.ascontiguousarray(np.array(image)[:, :, ::-1])
binary = preprocessing.prepare(array)['image']
angle, conf, binary, skew, vertical, horizontal = lp._orient_page(binary)
ink = cv2.bitwise_not(binary)
height, width = ink.shape[:2]
for fraction in (0.18, 0.12, 0.08, 0.05):
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(20, int(width * fraction)), 1)
    )
    opened = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(
        opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    found = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w >= width * lp.MIN_HORIZONTAL_SPAN and h <= lp.MAX_LINE_THICKNESS:
            found.append((y + h // 2, int(w)))
    print(fraction, [int(center) for center, _ in lp._cluster(found)])
