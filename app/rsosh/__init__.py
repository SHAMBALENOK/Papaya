"""Импорт официальных документов РСОШ — единственный автоматический способ
добавить олимпиаду в каталог Papaya.

Pipeline:

    Document
        ↓ file type detection        (filetypes)
    Preprocessing + orientation     (preprocessing)
    Native extraction / OCR         (extraction, ocr)
    Table detection/reconstruction  (tables)
    Cell normalization              (normalization)
    Olympiad extraction             (parsing)
    Validation                      (validation)
    Deduplication (matching)        (matching)
        ↓
    Import preview                  (states → docs.metadata)
        ↓ admin confirmation
    Create/update Olympiads + archiving (persist)

Ручное создание олимпиады администратором остаётся резервным способом
(``app/routers/olympiads.py``), старый массовый импорт таблиц в Papaya больше
не является доступным путём создания олимпиад.
"""

from app.rsosh.processor import (
    RSOSH_DOC_TYPE,
    confirm_import,
    document_path,
    run_import,
    start_import,
)
from app.rsosh.types import (
    Candidate,
    ExtractionResult,
    OlympiadRecord,
    RsoshConflictError,
    RsoshError,
)

__all__ = [
    'RSOSH_DOC_TYPE',
    'Candidate',
    'ExtractionResult',
    'OlympiadRecord',
    'RsoshConflictError',
    'RsoshError',
    'confirm_import',
    'document_path',
    'run_import',
    'start_import',
]
