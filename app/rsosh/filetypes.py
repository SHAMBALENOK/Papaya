"""Определение типа файла импорта РСОШ.

Поддерживаемые форматы заданы концепцией: PDF, XLSX и изображения
PNG/JPG/JPEG. Тип определяется и по расширению, и по сигнатуре файла:
реальные документы часто приходят с неверным расширением, а сигнатура —
единственный надёжный признак.
"""

import os
import zipfile
from pathlib import Path

from app.rsosh.types import RsoshError

PDF = 'pdf'
XLSX = 'xlsx'
IMAGE = 'image'

SUPPORTED = (PDF, XLSX, IMAGE)
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg'}
EXTENSION_TYPES = {
    '.pdf': PDF,
    '.xlsx': XLSX,
    '.xls': XLSX,
    '.png': IMAGE,
    '.jpg': IMAGE,
    '.jpeg': IMAGE,
}
SUPPORTED_EXTENSIONS = frozenset(EXTENSION_TYPES)

# Tesseract понимает PNG/TIFF/BMP/JPEG — форматы без потерь и с альфой
# tesseract не справляется (альфа превращается в чёрный фон).
OCR_IMAGE_FORMATS = {'.png', '.tif', '.tiff', '.bmp'}


def detect_kind(path: str | Path) -> str:
    """Определить ``pdf`` / ``xlsx`` / ``image`` по содержимому файла."""
    file_path = Path(path)
    try:
        with open(file_path, 'rb') as handle:
            head = handle.read(8)
    except OSError as exc:
        raise RsoshError(f'Cannot read file: {exc}') from exc

    if head.startswith(b'%PDF'):
        return PDF
    if head.startswith(b'PK\x03\x04'):
        # xlsx — zip-контейнер с [Content_Types].xml и xl/workbook.xml.
        if zipfile.is_zipfile(file_path):
            with zipfile.ZipFile(file_path) as archive:
                names = set(archive.namelist())
            if 'xl/workbook.xml' in names:
                return XLSX
        return XLSX if _looks_like_legacy_xls(file_path) else 'unknown'
    if head.startswith(b'\x89PNG\r\n\x1a\n') or head.startswith(b'\xff\xd8\xff'):
        return IMAGE
    if head.startswith((b'GIF87a', b'GIF89a', b'BM')) or head[4:12] in (
        b'ftypheic',
        b'ftypavif',
        b'ftypqt  ',
    ):
        return IMAGE
    if head.startswith(b'\xd7\xcd\xc6\x9a'):
        return 'wmf'
    if head.startswith(b'\x01\x00\x00\x00') or head.startswith(b'\xd0\xcf\x11\xe0'):
        return 'legacy_office'
    return 'unknown'


def _looks_like_legacy_xls(file_path: Path) -> bool:
    """Старый бинарный .xls (OLE2) — тоже таблица, но не openpyxl."""
    try:
        with open(file_path, 'rb') as handle:
            return handle.read(8) == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
    except OSError:
        return False


def detect(path: str | Path) -> str:
    """Определить тип файла и проверить, что формат поддерживается.

    Расширение используется только как подсказка: если сигнатура файла
    указывает на поддерживаемый формат, импорт идёт, даже когда имя вводит
    в заблуждение.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise RsoshError('File not found')

    kind = detect_kind(file_path)
    extension = os.path.splitext(file_path.name)[1].lower()

    if kind in SUPPORTED:
        return kind
    if kind == 'legacy_office' and extension in EXTENSION_TYPES:
        # .xls без поддержки чтения: сообщаем честно, а не молча игнорируем.
        raise RsoshError(
            'Legacy .xls format is not supported: convert the file to .xlsx or PDF'
        )
    if kind in ('wmf', 'legacy_office'):
        raise RsoshError(
            f'Unsupported file format: {extension or kind}. '
            'Allowed: ' + ', '.join(sorted(SUPPORTED_EXTENSIONS))
        )
    if extension in EXTENSION_TYPES:
        # Расширение обещает поддерживаемый формат, содержимое не совпало.
        raise RsoshError(
            f'File content does not match its extension ({extension or "no extension"})'
        )
    raise RsoshError(
        'Unsupported file format. Allowed: ' + ', '.join(sorted(SUPPORTED_EXTENSIONS))
    )
