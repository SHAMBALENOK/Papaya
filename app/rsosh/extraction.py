"""RSOSH-импорт: извлечение табличных данных из исходного файла.

Синхронные CPU-тяжёлые операции (img2table+Tesseract OCR по PDF) выполняются
в Celery-воркере (``processor.rsosh_import_task``), а не в HTTP-запросе:
для XLSX сразу возвращается исходный путь.
"""

import os

from img2table.document import PDF
from img2table.ocr import TesseractOCR

from app.core.config import RSOSH_WORK_DIR

_ocr = None


def _get_ocr():
    global _ocr
    if _ocr is None:
        _ocr = TesseractOCR(lang='rus')
    return _ocr


def extract_xlsx(source_path: str) -> str:
    """PDF -> объединённый XLSX (OCR по таблицам), XLSX -> as-is.

    Промежуточный файл создаётся в ``RSOSH_WORK_DIR/<base>_extracted.xlsx`` —
    каталог смонтирован и в web, и в celery, поэтому воркер пишет туда, где
    его увидит API-процесс при чтении результата.
    """
    extension = os.path.splitext(source_path)[1].lower()
    os.makedirs(RSOSH_WORK_DIR, exist_ok=True)

    if extension == '.xlsx':
        return source_path
    if extension != '.pdf':
        raise ValueError(f'Unsupported import file extension: {extension}')

    base_name = os.path.splitext(os.path.basename(source_path))[0]
    output_path = os.path.join(RSOSH_WORK_DIR, f'{base_name}_extracted.xlsx')

    pdf = PDF(src=source_path)
    pdf.to_xlsx(
        output_path,
        ocr=_get_ocr(),
        implicit_columns=True,
        borderless_tables=False,
        min_confidence=70,
    )
    return output_path