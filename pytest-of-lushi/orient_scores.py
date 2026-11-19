import os
import sys

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

import numpy as np  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402

from app.rsosh import list_parser, ocr, preprocessing  # noqa: E402

path = r'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\original\26-27.pdf'
doc = pdfium.PdfDocument(path)
for page_number in (13, 70, 77):
    page = doc[page_number - 1]
    bitmap = page.render(scale=300 / 72.0)
    array = np.array(bitmap.to_pil().convert('RGB'))
    array = np.ascontiguousarray(array[:, :, ::-1])
    prepared = preprocessing.prepare(array)
    binary = prepared['image']
    print('page', page_number, 'shape', binary.shape)
    print('  direction candidates', preprocessing.text_direction_candidates(binary))
    print('  osd', ocr.osd_rotation(binary))
    for angle in (0, 90, 180, 270):
        rotated = preprocessing.rotate_cw(binary, angle) if angle else binary
        small = list_parser._to_pil(rotated)
        small.thumbnail((1500, 1500))
        text = ocr.pytesseract.image_to_string(
            small, lang=ocr.LANG, config='--psm 6'
        )
        score = list_parser._score_text(text)
        print('  angle', angle, 'score', score, 'sample', repr(text[:120]))
doc.close()
