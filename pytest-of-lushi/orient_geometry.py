import os
import sys

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

import numpy as np  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402

from app.rsosh import list_parser as lp, ocr, preprocessing  # noqa: E402

path = r'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\original\26-27.pdf'
doc = pdfium.PdfDocument(path)
for page_number in (13, 70, 77):
    image = doc[page_number - 1].render(scale=300 / 72.0).to_pil().convert('RGB')
    array = np.ascontiguousarray(np.array(image)[:, :, ::-1])
    binary = preprocessing.prepare(array)['image']
    print('=== page', page_number, binary.shape, 'osd', ocr.osd_rotation(binary))
    for angle in (0, 90, 180, 270):
        rotated = preprocessing.rotate_cw(binary, angle) if angle else binary
        rotated, skew = preprocessing.straighten(rotated)
        vertical, horizontal = lp._table_geometry(rotated)
        print(
            ' angle', angle, 'skew', skew,
            'vertical', len(vertical), 'horizontal', len(horizontal),
        )
doc.close()
