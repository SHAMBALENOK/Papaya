"""Оркестратор импорта приказа университета.

    Document (UNIVERSITY_ORDER)
        ↓ file type detection
    extraction (XLSX / PDF text layer / PDF scan / image)
        ↓ orientation + OCR
    table reconstruction
        ↓ cell normalization
    university + order-line extraction
        ↓ matching against existing olympiad catalog
    import preview
        ↓ admin review (choose university / link unmatched / skip)
    create draft BenefitRule rows        ← приказ НЕ создаёт олимпиад

``run_import`` выполняет цепочку до состояния «готов к подтверждению» и
никогда не создаёт правил: запись происходит только в ``confirm_import``, и
даже там правила заводятся как черновики (``draft``) — публикует и проверяет их человек
отдельным действием. Поэтому результат импорта можно посмотреть и отклонить,
а повторный импорт того же документа не создаёт дубликатов.

Запуск: ``celery`` (по умолчанию) либо ``inline`` — в процессе API. Режим
``auto`` выбирает celery, если брокер доступен, иначе inline: так импорт
работает и в окружениях без воркера (тесты, одиночный запуск).
"""

import asyncio
import logging
from pathlib import Path

from app.core.config import DOCS_DIR, RSOSH_EXECUTION
from app.database import docs as db_docs
from app.rsosh import extraction
from app.university import matching, parsing, persist, states
from app.university.types import (
    UniversityError,
    UniversityRecord,
)

logger = logging.getLogger('papaya.university.processor')

UNIVERSITY_DOC_TYPE = 'UNIVERSITY_ORDER'

#: Статусы, из которых ``run_import`` может продолжить обработку.
#:
#: Шире, чем ``persist.STARTABLE_DOC_STATUSES``, который проверяет старт для
#: пользователя: сюда входят ``PROCESSING`` (воркер получает документ уже
#: занятым) и ``PAUSED`` (возобновление возвращает его в ``PROCESSING`` до
#: вызова ``run_import``).
RESUMABLE_DOC_STATUSES = (
    'UPLOADED', 'PROCESSING', 'PAUSED', 'NEEDS_REVIEW', 'FAILED', 'PROCESSED',
)


def document_path(doc: dict) -> Path:
    """Путь к файлу документа-источника."""
    storage_key = doc.get('storage_key')
    if not storage_key:
        raise UniversityError('Document has no local file copy')
    path = (Path(DOCS_DIR) / storage_key).resolve()
    root = Path(DOCS_DIR).resolve()
    if root not in path.parents and path != root:
        raise UniversityError(
            'Document storage key points outside the storage directory'
        )
    if not path.is_file():
        raise UniversityError(f'Document file not found: {storage_key}')
    return path


def _validate_document(doc: dict) -> None:
    if doc.get('type') != UNIVERSITY_DOC_TYPE:
        raise UniversityError('Only UNIVERSITY_ORDER documents can be imported')
    if doc.get('status') not in RESUMABLE_DOC_STATUSES:
        raise UniversityError(
            'Import is not startable from status ' + str(doc.get('status'))
            + '; startable: ' + ', '.join(RESUMABLE_DOC_STATUSES)
        )


async def _set_state(doc: dict, section: dict) -> dict:
    """Сохранить раздел состояния и статус документа одной операцией.

    Запись идёт через ``persist.write_import_state``: под блокировками и со
    свежими правками администратора (выбор, запрос паузы). Снимок документа в
    памяти воркера устаревает за время долгих этапов обработки, и прямая
    запись снимка стёрла бы эти правки.
    """
    updated = await persist.write_import_state(doc['id'], section)
    return updated or doc


async def _mark_failed(doc: dict, section: dict) -> dict:
    """Перевести документ в ``failed``, только пока он ещё ``PROCESSING``.

    Проверка статуса нужна для ошибок «до конвейера»: иначе ``failed`` перетёр
    бы чужой результат, записанный, пока прогон уже ушёл из ``PROCESSING``.
    """
    fresh = await db_docs.get_doc(doc['id'])
    if not fresh:
        return doc
    if fresh.get('status') != 'PROCESSING':
        logger.warning(
            'university: not marking %s failed — status is %s',
            doc['id'],
            fresh.get('status'),
        )
        return fresh
    return await _set_state(fresh, section)


async def _pause_here(
    doc: dict,
    *,
    stage: str,
    records=None,
    pages=None,
    warnings=None,
    university=None,
) -> dict | None:
    """Приостановить обработку, если администратор запросил паузу.

    Проверка идёт по свежему состоянию: запрос паузы приходит отдельным
    HTTP-вызовом и пишется в тот же раздел. Смена состояния возможна только
    из ``processing``.
    """
    fresh = await db_docs.get_doc(doc['id'])
    if not fresh:
        return None
    section = states.university_section(fresh)
    if section.get('state') != 'processing' or not section.get('pause_requested'):
        return None
    record_dicts = (
        [record.to_dict() for record in records] if records is not None else None
    )
    paused = states.paused_section(
        fresh,
        stage=stage,
        records=record_dicts,
        pages=pages,
        warnings=warnings,
        university=university,
    )
    return await _set_state(fresh, paused)


async def run_import(doc_id) -> dict:
    """Обработать документ приказа и подготовить preview.

    Возвращает документ с разделом ``university`` в состоянии ``review`` (либо
    ``failed``, либо ``paused``). Связи БВИ на этом шаге не создаются.

    Если в разделе уже есть контрольная точка (``records``), обработка
    продолжается с неё — документ повторно не распознаётся.
    """
    doc = await db_docs.get_doc(doc_id)
    if not doc:
        raise UniversityError(f'Document {doc_id} not found')

    try:
        _validate_document(doc)

        section = states.university_section(doc)
        resume_records = section.get('records')
        if resume_records:
            records = [
                UniversityRecord.from_dict(item) for item in resume_records
            ]
            warnings = list(section.get('warnings') or [])
            page_reports = list(section.get('pages') or [])
            university = dict(section.get('university') or {})
        else:
            path = document_path(doc)
            # Пауза могла быть запрошена сразу после старта: проверка идёт до
            # ``start_section``, который сбрасывает флаг паузы.
            paused = await _pause_here(doc, stage='starting')
            if paused is not None:
                return paused
            doc = await _set_state(doc, states.start_section(doc))
            doc = await _set_state(
                doc, states.progress_section(doc, stage='extracting')
            )
            pages = await asyncio.to_thread(
                extraction.extract_document, str(path)
            )
            records, warnings, university = parsing.parse_pages(pages)
            page_reports = [
                report.to_dict()
                for report in parsing.build_page_reports(pages)
            ]
            paused = await _pause_here(
                doc,
                stage='parsed',
                records=records,
                pages=page_reports,
                warnings=warnings,
                university=university,
            )
            if paused is not None:
                return paused

        doc = await _set_state(
            doc, states.progress_section(doc, stage='matching')
        )
        candidates = await matching.build_candidates(records)
        university = await _resolve_recognized_university(university)
        summary = {
            'total': len(records),
            'linked': sum(1 for item in candidates if item.olympiad_id),
            'review': sum(
                1 for item in candidates if item.confidence == 'review'
            ),
            'unmatched': sum(1 for item in candidates if not item.olympiad_id),
        }

        if not candidates:
            section = states.failed_section(
                doc,
                error='В документе не найдено ни одной строки приказа: проверьте, '
                      'что это приказ университета (с таблицей и шапкой)',
            )
            doc = await _set_state(doc, section)
            return doc

        # Граница этапа «сопоставление»: запрос паузы, поданный во время
        # сопоставления, иначе погиб бы вместе с переходом в review.
        paused = await _pause_here(
            doc,
            stage='matching',
            records=records,
            pages=page_reports,
            warnings=warnings,
            university=university,
        )
        if paused is not None:
            return paused

        section = states.review_section(
            doc,
            candidates=[item.to_dict() for item in candidates],
            pages=page_reports,
            warnings=warnings,
            summary=summary,
            university=university,
        )
        return await _set_state(doc, section)
    except UniversityError as exc:
        logger.warning('university: import of %s failed: %s', doc_id, exc)
        return await _mark_failed(
            doc, states.failed_section(doc, error=_public_error(exc))
        )
    except Exception:  # noqa: BLE001 - любая ошибка не должна ронять импорт
        # Текст неизвестной ошибки в отчёте не показывается: `str(exc)` у
        # ошибок БД и файловой системы содержит пути и строки подключения.
        logger.exception('university: unexpected failure while importing %s', doc_id)
        return await _mark_failed(
            doc,
            states.failed_section(
                doc,
                error='Не удалось обработать документ. Подробности — в логе сервера.',
            ),
        )


async def _resolve_recognized_university(university: dict) -> dict:
    """Сопоставить распознанный вуз со строкой каталога (или пометить, что нет).

    Результат сохраняется в раздел, чтобы админ видел, каким вузом приказ будет
    применён, и мог переопределить его в окне проверки. Матчинг ленивый: если
    вуз уже сопоставлен (при возобновлении), каталог повторно не читается.
    """
    from app.database.universities import list_universities

    result = dict(university or {})
    if result.get('matched_id'):
        return result
    name_norm = result.get('name_norm')
    if not name_norm:
        result.setdefault('matched_id', None)
        return result

    catalog = await list_universities()
    best = None
    best_score = 0.0
    for item in catalog:
        if item['name_norm'] == name_norm:
            best = item
            best_score = 1.0
            break
    result['matched_id'] = best['id'] if best else None
    result['matched_name'] = best['name'] if best else None
    result['match_score'] = round(best_score, 3)
    return result


#: Что показывать вместо внутреннего текста ошибки импорта.
_PUBLIC_ERROR = (
    'Не удалось обработать документ: {reason}. Подробности — в логе сервера.'
)


def _public_error(exc: Exception) -> str:
    """Понятный текст ошибки без внутренних деталей."""
    text = str(exc)
    if 'storage' in text.lower() or '\\' in text or '/' in text:
        return _PUBLIC_ERROR.format(reason='файл документа недоступен')
    return text


async def confirm_import(
    doc_id,
    *,
    selection: dict | None = None,
    university_id=None,
) -> dict:
    """Применить импорт: создать черновики правил льгот по сопоставлениям.

    Олимпиады каталога не создаются и не изменяются; правила заводятся как
    черновики, которые публикует и проверяет человек. Всё применение живёт в
    ``persist.apply_confirmed_import`` и идёт в одной транзакции под
    advisory-блокировкой применения приказов и блокировкой строки документа.
    """
    applied = await persist.apply_confirmed_import(
        doc_id=doc_id,
        selection=selection,
        university_id=university_id,
    )
    return {
        'document': applied['document'],
        'result': applied['result'],
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
    не показывал устаревший результат предыдущего прогона. Переход атомарен
    (``persist.claim_import_start``), поэтому второй запрос получает 409.

    Возвращает ``(документ, способ запуска)``.
    """
    doc = await persist.claim_import_start(doc_id)

    mode = RSOSH_EXECUTION or 'auto'
    if mode == 'celery' or (mode == 'auto' and _celery_available()):
        try:
            from app.university.worker import university_import_task

            await asyncio.to_thread(
                lambda: university_import_task.apply_async(args=[str(doc_id)])
            )
            return await db_docs.get_doc(doc_id), 'celery'
        except Exception as exc:  # noqa: BLE001 - нет брокера, делаем здесь
            if mode == 'celery':
                safe = (
                    'Не удалось отправить импорт в очередь: брокер задач '
                    'недоступен. Повторите запуск.'
                )
                logger.exception('university: failed to enqueue import %s', doc_id)
                await _set_state(doc, states.failed_section(doc, error=safe))
                raise UniversityError(safe) from exc
            logger.warning('university: celery unavailable, running inline')
    return await run_import(doc_id), 'inline'


async def resume_import(doc_id) -> tuple[dict, str]:
    """Возобновить приостановленный импорт.

    ``persist.claim_resume`` атомарно возвращает документ в ``PROCESSING``,
    сохраняя контрольную точку; ``run_import`` продолжает с сопоставления.

    Сбой постановки задачи в celery-режиме возвращает прогон в ``paused``, а
    не в ``failed``: контрольная точка — уже сделанная работа.

    Возвращает ``(документ, способ запуска)``.
    """
    doc = await persist.claim_resume(doc_id)

    mode = RSOSH_EXECUTION or 'auto'
    if mode == 'celery' or (mode == 'auto' and _celery_available()):
        try:
            from app.university.worker import university_import_task

            await asyncio.to_thread(
                lambda: university_import_task.apply_async(args=[str(doc_id)])
            )
            return await db_docs.get_doc(doc_id), 'celery'
        except Exception as exc:  # noqa: BLE001 - нет брокера, продолжаем здесь
            if mode == 'celery':
                safe = (
                    'Не удалось отправить импорт в очередь: брокер задач '
                    'недоступен. Повторите возобновление.'
                )
                logger.exception('university: failed to enqueue resume %s', doc_id)
                restored = {
                    **states.university_section(doc),
                    'state': 'paused',
                    'progress': {'stage': 'resuming'},
                }
                await _set_state(doc, restored)
                raise UniversityError(safe) from exc
            logger.warning('university: celery unavailable, resuming inline')
    return await run_import(doc_id), 'inline'


__all__ = [
    'UNIVERSITY_DOC_TYPE',
    'confirm_import',
    'document_path',
    'resume_import',
    'run_import',
    'start_import',
]
