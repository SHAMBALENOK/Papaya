"""Обработка документов университетов: извлечение таблиц без автоматического создания льгот.

Использует существующий стек извлечения (extraction.extract_document) и
возвращает черновики строк для ручной модерации. Не создаёт и не изменяет
правила льгот автоматически: результат сохраняется в разделе
``metadata['university']`` документа и доступен администратору.
"""

import logging
from datetime import datetime, timezone

from app.core.config import DOCS_DIR
from app.database import docs as db_docs
from app.rsosh import extraction
from app.rsosh.types import RsoshError

logger = logging.getLogger('papaya.rsosh.university')


def document_path(doc):
    from pathlib import Path

    storage_key = doc.get('storage_key')
    if not storage_key:
        raise RsoshError('Document has no local file copy')
    path = (Path(DOCS_DIR) / storage_key).resolve()
    root = Path(DOCS_DIR).resolve()
    if root not in path.parents and path != root:
        raise RsoshError('Document storage key points outside the storage directory')
    if not path.is_file():
        raise RsoshError(f'Document file not found: {storage_key}')
    return path


def _now():
    return datetime.now(timezone.utc).isoformat()


def parse_pages(pages):
    drafts = []
    warnings = []
    for page in pages:
        for ti, table in enumerate(page.tables or [], start=1):
            if not table:
                continue
            header = table[0] if table else []
            for ri, row in enumerate(table[1:], start=2):
                if not any((cell or '').strip() for cell in row):
                    continue
                drafts.append({
                    'page': page.page,
                    'table': ti,
                    'row': ri,
                    'header': header,
                    'cells': row,
                    'method': page.method,
                    'confidence': page.confidence,
                })
            if not header:
                warnings.append(f'Страница {page.page}: заголовок таблицы не распознан')
    if not drafts:
        warnings.append('В документе не найдено строк таблиц')
    return drafts, warnings


async def run_university_import(doc_id):
    doc = await db_docs.get_doc(doc_id)
    if not doc:
        raise RsoshError(f'Document {doc_id} not found')
    if doc.get('type') not in ('UNIVERSITY_ORDER', 'OTHER'):
        raise RsoshError('Only university documents can be processed here')
    try:
        path = document_path(doc)
        pages = await __import__('asyncio').to_thread(extraction.extract_document, str(path))
        drafts, warnings = parse_pages(pages)
        section = {
            'state': 'review',
            'started_at': _now(),
            'finished_at': _now(),
            'error': None,
            'drafts': drafts,
            'warnings': warnings,
            'pages': len(pages),
        }
        metadata = dict(doc.get('metadata') or {})
        metadata['university'] = section
        await db_docs.edit_doc(doc_id, {'metadata': metadata, 'status': 'NEEDS_REVIEW'})
        updated = await db_docs.get_doc(doc_id)
        return updated
    except Exception as exc:
        logger.exception('university import failed')
        metadata = dict(doc.get('metadata') or {})
        metadata['university'] = {
            'state': 'failed',
            'error': str(exc),
            'finished_at': _now(),
        }
        await db_docs.edit_doc(doc_id, {'metadata': metadata, 'status': 'FAILED'})
        raise