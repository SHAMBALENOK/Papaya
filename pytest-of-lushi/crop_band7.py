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

pdf = pdfium.PdfDocument(
    r'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\original\17-18.pdf'
)
image = pdf[2].render(scale=300 / 72.0).to_pil().convert('RGB')
array = np.ascontiguousarray(np.array(image)[:, :, ::-1])
binary = preprocessing.prepare(array)['image']
angle, conf, binary, skew, vertical, horizontal = lp._orient_page(binary)
bands = lp._table_columns(binary, vertical=vertical, horizontal=horizontal)
top, bottom = 1676, 1832
left = bands[3][0]
right = bands[5][1]
crop = binary[top:bottom, int(left):int(right)]
Image.fromarray(crop).save('pytest-of-lushi/band7.png')
print(crop.shape)
