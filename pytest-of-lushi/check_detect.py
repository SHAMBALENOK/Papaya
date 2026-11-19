"""Проверка: детекция официального перечня на синтетических сканах 90/180/270."""
import os
import sys
import time

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

from tests.rsosh_fixtures import scanned_pdf_bytes  # noqa: E402
from app.rsosh import list_processor  # noqa: E402

for degrees in (90, 180, 270):
    path = f'pytest-of-lushi/scan_{degrees}.pdf'
    with open(path, 'wb') as handle:
        handle.write(scanned_pdf_bytes(degrees=degrees))
    started = time.time()
    result = list_processor.detect_official_list(path)
    print(degrees, round(time.time() - started, 1), 's', result)
