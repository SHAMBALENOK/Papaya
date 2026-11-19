import os
import sys

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

import numpy as np  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402
from PIL import Image  # noqa: E402

from app.rsosh import list_parser as lp  # noqa: E402
from app.rsosh import preprocessing  # noqa: E402

year, page, top, bottom = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
pdf = pdfium.PdfDocument(
    rf'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\original\{year}.pdf'
)
image = pdf[page].render(scale=300 / 72.0).to_pil().convert('RGB')
array = np.ascontiguousarray(np.array(image)[:, :, ::-1])
binary = preprocessing.prepare(array)['image']
angle, conf, binary, skew, vertical, horizontal = lp._orient_page(binary)
crop = binary[top:bottom, :]
Image.fromarray(crop).save(f'pytest-of-lushi/strip_{year}_{page}_{top}.png')
print(crop.shape)
