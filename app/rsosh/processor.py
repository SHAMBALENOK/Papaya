"""Оркестратор импорта РСОШ.

    Document
        ↓ file type detection
    extraction (XLSX / PDF text layer / PDF scan / image)
        ↓ orientation + OCR
    table reconstruction
        ↓ cell normalization
    olympiad extraction
        ↓ validation
    matching (deduplication)
        ↓
    import preview
        ↓ admin confirmation
    create/update Olympiads + archiving

``run_import`` выполняет цепочку до состояния «готов к подтверждению» и
никогда не пишет олимпиады: запись в каталог происходит только в
``confirm_import``. Благодаря этому результат импорта можно посмотреть и
отклонить, а повторный импорт того же документа не создаёт дубликаты.

Запуск: ``celery`` (по умолчанию) либо ``inline`` — в процессе API. Режим
``auto`` выбирает celery, если брокер доступен, иначе inline: так импорт
работает и в окружениях без воркера (тесты, одиночный запуск).
"""

import asyncio
import logging
from pathlib import Path

from app.core.config import DOCS_DIR, RSOSH_EXECUTION
from app.database import docs as db_docs
from app.rsosh import extraction, matching, parsing, states, validation
from app.rsosh.types import RsoshError

logger = logging.getLogger('papaya.rsosh.processor')

RSOSH_DOC_TYPE = 'RSOSH_LIST'

#: Статусы, из которых ``run_import`` может продолжить обработку.
#:
#: Отличается от ``persist.STARTABLE_DOC_STATUSES``, который проверяет старт для
#: пользователя: сюда входит и ``PROCESSING``, потому что воркер получает
#: документ уже занятым под обработку (переход в PROCESSING делает
#: ``persist.claim_import_start`` перед постановкой задачи).
RESUMABLE_DOC_STATUSES = ('UPLOADED', 'PROCESSING', 'NEEDS_REVIEW', 'FAILED', 'PROCESSED')


def document_path(doc: dict) -> Path:
    """Путь к файлу документа-источника."""
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


def _validate_document(doc: dict) -> None:
    if doc.get('type') != RSOSH_DOC_TYPE:
        raise RsoshError('Only RSOSH_LIST documents can be imported')
    if doc.get('status') not in RESUMABLE_DOC_STATUSES:
        raise RsoshError(
            'Import is not startable from status ' + str(doc.get('status'))
            + '; startable: ' + ', '.join(RESUMABLE_DOC_STATUSES)
        )


async def _set_state(doc: dict, section: dict) -> dict:
    """Сохранить раздел состояния и статус документа одной операцией."""
    metadata = states.docs_metadata_with_section(doc, section)
    updated = await db_docs.edit_doc(
        doc['id'],
        {
            'metadata': metadata,
            'status': states.DOCS_STATUS.get(section.get('state'), doc['status']),
        },
    )
    return updated or doc


async def run_import(doc_id) -> dict:
    """Обработать документ РСОШ и подготовить preview.

    Возвращает документ с разделом ``rsosh`` в состоянии ``review`` (или
    ``failed`` с причиной). Олимпиады в каталог на этом шаге не пишутся.
    """
    doc = await db_docs.get_doc(doc_id)
    if not doc:
        raise RsoshError(f'Document {doc_id} not found')
    _validate_document(doc)

    path = document_path(doc)
    doc = await _set_state(doc, states.start_section(doc))

    try:
        pages = await asyncio.to_thread(extraction.extract_document, str(path))
        records, warnings = parsing.parse_pages(pages)
        page_confidence = _page_confidence(pages)
        for record in records:
            record.confidence = page_confidence.get(record.page, 1.0)
            validation.validate_record(record)

        candidates = await matching.build_candidates(records)
        summary = {
            'total': len(records),
            'new': sum(1 for item in candidates if item.action == 'create'),
            'merge': sum(1 for item in candidates if item.action == 'merge'),
            'review': sum(1 for item in candidates if item.confidence == 'review'),
        }
        page_reports = [
            report.to_dict()
            for report in validation.build_page_reports(
                pages,
                method=pages[0].method if pages else 'ocr',
            )
        ]

        if not candidates:
            section = states.failed_section(
                doc,
                error='В документе не найдено ни одной олимпиады: проверьте, '
                      'что это перечень РСОШ (с таблицей и шапкой)',
            )
            doc = await _set_state(doc, section)
            return doc

        section = states.review_section(
            doc,
            candidates=[item.to_dict() for item in candidates],
            pages=page_reports,
            warnings=warnings,
            summary=summary,
        )
        return await _set_state(doc, section)
    except RsoshError as exc:
        # Тексты RsoshError написаны вручную и предназначены для показа, но
        # даже они могут содержать путь к файлу (см. _document_path).
        logger.warning('rsosh: import of %s failed: %s', doc_id, exc)
        return await _set_state(
            doc, states.failed_section(doc, error=_public_error(exc))
        )
    except Exception:  # noqa: BLE001 - любая ошибка не должна ронять импорт
        # Неизвестная ошибка в отчёте импорта не показывается: `str(exc)`
        # у ошибок БД и файловой системы содержит имена таблиц, пути и строки
        # подключения, а этот текст отдаётся в API и рисуется в панели.
        # Подробности остаются в логе.
        logger.exception('rsosh: unexpected failure while importing %s', doc_id)
        return await _set_state(
            doc,
            states.failed_section(
                doc,
                error='Не удалось обработать документ. Подробности — в логе сервера.',
            ),
        )


#: Что показывать вместо внутреннего текста ошибки импорта.
_PUBLIC_ERROR = (
    'Не удалось обработать документ: {reason}. Подробности — в логе сервера.'
)


def _public_error(exc: Exception) -> str:
    """Понятный текст ошибки без внутренних деталей.

    Сообщения ``RsoshError`` в основном пригодны для показа, но могут
    содержать путь к файлу документа. Такие места заменяются нейтральной
    формулировкой, а не просто обрезаются: администратору нужно понимать,
    что именно сломалось, не получая при этом внутренности.
    """
    text = str(exc)
    # Внутренние детали: пути к файлам, имена каталогов хранилища.
    if 'storage' in text.lower() or '\\' in text or '/' in text:
        return _PUBLIC_ERROR.format(reason='файл документа недоступен')
    return text


def _page_confidence(pages) -> dict:
    """Уверенность распознавания по страницам (для XLSX/text — 1.0).

    Ключ ``None`` — значение для записей, у которых страница неизвестна
    (например, склеенная многостраничная ячейка).
    """
    confidence = {page.page: page.confidence for page in pages}
    mean = (
        sum(page.confidence for page in pages) / len(pages) if pages else 1.0
    )
    confidence[None] = round(mean, 3)
    return confidence


async def confirm_import(
    doc_id,
    *,
    skip: list[str] | None = None,
    rename: dict | None = None,
    descriptions: dict | None = None,
    merge: dict | None = None,
    archive_missing: bool = True,
) -> dict:
    """Применить импорт: создать/обновить олимпиады и архивировать пропавшие.

    Само применение живёт в ``persist.apply_confirmed_import`` и выполняется в
    одной транзакции под advisory-блокировкой применения перечней и блокировкой
    строки документа. Здесь нет ничего, что стоило бы делать до или после неё:
    и проверка актуальности снимка, и проверка состояния, и запись каталога, и
    отметка документа обработанным должны быть под одними блокировками, иначе
    два параллельных подтверждения снова смогут разойтись по времени.

    Перечень — снимок, отвечающий на вопрос «какие олимпиады актуальны сейчас».
    Поэтому перечень, загруженный раньше уже подтверждённого, применить нельзя
    (409): подтверждение вернуло бы каталог к старой редакции. Обхода этого
    правила нет — «подтвердить всё равно» здесь означало бы вернуть каталог
    назад, а каталог должен отвечать на вопрос о текущей редакции перечня.
    """
    from app.rsosh import persist

    applied = await persist.apply_confirmed_import(
        doc_id=doc_id,
        skip=list(skip or []),
        rename=dict(rename or {}),
        descriptions=dict(descriptions or {}),
        merge=dict(merge or {}),
        archive_missing=archive_missing,
    )
    return {
        'document': applied['document'],
        'result': applied['result'],
        'skipped': applied['skipped'],
    }


def _celery_available() -> bool:
    try:
        from app.middlewares.task_queue import task_queue

        connection = task_queue.connection_for_read()
        connection.ensure_connection(max_retries=0, timeout=1)
        connection.release()
        return True
    except Exception:  # noqa: BLE001 - брокер недоступен
        return False


async def start_import(doc_id) -> tuple[dict, str]:
    """Запустить импорт в фоне (celery) или в текущем процессе (inline).

    Документ переводится в ``PROCESSING`` до постановки задачи, чтобы интерфейс
    не показывал устаревший результат предыдущего прогона, пока задача стоит в
    очереди.

    Переход выполняется через ``persist.claim_import_start``, то есть атомарно
    под блокировкой. Раньше чтение документа и запись состояния были отдельными
    операциями, и два одновременных запроса запускали две обработки одного
    документа — они писали в один и тот же ``docs.metadata['rsosh']``, и
    результат зависел от того, кто закончил последним. Теперь второй запрос
    получает 409 и лишней задачи не создаётся.

    Возвращает ``(документ, способ запуска)``.
    """
    from app.rsosh import persist

    doc = await persist.claim_import_start(doc_id)

    mode = RSOSH_EXECUTION or 'auto'
    if mode == 'celery' or (mode == 'auto' and _celery_available()):
        try:
            from app.rsosh.worker import rsosh_import_task

            await asyncio.to_thread(
                lambda: rsosh_import_task.apply_async(args=[str(doc_id)])
            )
            return await db_docs.get_doc(doc_id), 'celery'
        except Exception as exc:  # noqa: BLE001 - нет брокера, делаем импорт здесь
            if mode == 'celery':
                # Документ уже переведён в ``PROCESSING``, а задача не
                # поставлена: без возврата в ``FAILED`` он завис бы в
                # PROCESSING навсегда, и импорт невозможно было бы ни
                # перезапустить, ни прочитать. Возвращаем документ в стартовое
                # состояние с безопасным текстом (без деталей брокера).
                safe = (
                    'Не удалось отправить импорт в очередь: брокер задач '
                    'недоступен. Повторите запуск.'
                )
                logger.exception('rsosh: failed to enqueue import %s', doc_id)
                await _set_state(
                    doc, states.failed_section(doc, error=safe)
                )
                raise RsoshError(safe) from exc
            logger.warning('rsosh: celery unavailable, running import inline')
    return await run_import(doc_id), 'inline'


__all__ = [
    'RSOSH_DOC_TYPE',
    'confirm_import',
    'document_path',
    'run_import',
    'start_import',
]
