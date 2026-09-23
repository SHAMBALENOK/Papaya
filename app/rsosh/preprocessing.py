"""RSOSH-импорт: поиск локальной копии документа в хранилище."""

import os

from app.core.config import DOCS_DIR


def resolve_doc_file(doc: dict) -> str | None:
    """Вернуть абсолютный путь к локальному файлу документа или None.

    Путь строится только от ``storage_key`` внутри DOCS_DIR (без name-файла
    клиента). ``os.path.commonpath`` исключает выход за пределы хранилища.
    """
    storage_key = doc.get('storage_key')
    if not storage_key:
        return None
    file_path = os.path.realpath(os.path.join(DOCS_DIR, storage_key))
    if os.path.commonpath((DOCS_DIR, file_path)) != DOCS_DIR:
        return None
    if not os.path.isfile(file_path):
        return None
    return file_path