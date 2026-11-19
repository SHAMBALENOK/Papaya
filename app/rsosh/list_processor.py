"""Конвейер импорта официального перечня РСОШ.

Этот конвейер запускается только для скана официального перечня и идёт по
шагам, каждый из которых оставляет проверяемый артефакт:

    PDF            — исходный скан, уже сохранённый в Docs;
    разбор         — строки таблицы с номерами страниц и предупреждениями;
    XLSX + HTML    — промежуточная таблица, доступная администратору;
    сопоставление  — план: что создать, что использовать, чего не хватает;
    проверка       — администратор правит план;
    применение     — одна транзакция (``list_apply``).

XLSX собирается до сопоставления намеренно: пока таблицы нет, проверять
нечего, а «тихое» сопоставление по нераспознанным строкам создало бы
олимпиады с мусорными названиями.

Если документ не похож на официальный перечень, конвейер возвращает
``None`` и вызывающий код продолжает прежнюю обработку: старый импортёр
отвечает за другие документы и не должен терять функциональность.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid as uuid_mod
from pathlib import Path

from app.core.config import DOCS_DIR
from app.database import docs as db_docs
from app.rsosh import list_apply, list_plan, list_xlsx, states
from app.rsosh.types import RsoshError

logger = logging.getLogger('papaya.rsosh.list_processor')

#: Сколько первых страниц достаточно, чтобы отличить перечень от другого
#: документа. Перечень узнаётся по шапке (она на первой табличной странице)
#: и по учебному году в заголовке приказа.
DETECT_PAGES = 5
#: Минимум символов текстового слоя, при котором PDF считается текстовым.
#: Официальные перечни — сканы, и текстовый слой у них пустой или содержит
#: только водяные знаки; текстовый PDF обрабатывает прежний конвейер.
TEXT_LAYER_LIMIT = 400

TABLE_MIME = (
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)
HTML_MIME = 'text/html'


def _storage_path(doc_id: str, extension: str) -> Path:
    """Путь производного файла: имя строится от id документа.

    Такая же схема, как у загрузки (``<doc_id><ext>``): файл нельзя вынести
    за пределы ``DOCS_DIR`` подстановкой имени, потому что имя не приходит
    извне.
    """
    return Path(DOCS_DIR) / f'{doc_id}{extension}'


def text_layer_chars(path: str | Path, pages: int = 5) -> int:
    """Сколько символов текста есть в PDF без OCR.

    Проверка дешёвая и решает, нужен ли вообще этот конвейер: официальные
    перечни — сканы, а текстовый PDF (приказ, выгрузка) обрабатывается
    прежним импортёром.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:  # pragma: no cover - зависимость обязательна
        return 0
    try:
        document = pdfium.PdfDocument(str(path))
    except Exception:  # noqa: BLE001 - битый PDF отсеет прежний конвейер
        return 0
    total = 0
    for index in range(min(len(document), pages)):
        try:
            textpage = document[index].get_textpage()
            total += len(textpage.get_text_range() or '')
        except Exception:  # noqa: BLE001 - страница без текстового слоя
            continue
    return total


def detect_official_list(path: str | Path) -> dict:
    """Похож ли документ на официальный перечень РСОШ.

    Разбор нескольких страниц даёт не только ответ «да/нет»: вместе с ним
    возвращается учебный год и число найденных таблиц, которые попадают в
    отчёт импорта. Это важно, потому что администратор должен видеть, почему
    документ пошёл по тому или иному пути, а не гадать по статусу.
    """
    suffix = Path(path).suffix.lower()
    if suffix != '.pdf':
        return {
            'official': False,
            'reason': 'Официальный перечень приходит только PDF-сканом',
            'season_label': None,
            'tables': 0,
            'rows': 0,
        }
    if text_layer_chars(path) >= TEXT_LAYER_LIMIT:
        return {
            'official': False,
            'reason': 'В документе есть текстовый слой: это не скан перечня',
            'season_label': None,
            'tables': 0,
            'rows': 0,
        }

    # Импорт внутри функции: list_parser тянет OCR-зависимости, а модуль
    # импортируется и там, где OCR не нужен (API-слой).
    from app.rsosh import list_parser

    probe = list_parser.parse_official_list(path, max_pages=DETECT_PAGES)
    official = bool(probe.detected_tables) and bool(probe.season_label)
    if official:
        reason = (
            f'Найдена таблица перечня за {probe.season_label}; '
            f'шапка: {probe.header_source}'
        )
    elif not probe.detected_tables:
        reason = 'В первых страницах не найдена таблица перечня'
    else:
        reason = 'Таблица найдена, но учебный год перечня не определён'
    return {
        'official': official,
        'reason': reason,
        'season_label': probe.season_label,
        'tables': probe.detected_tables,
        'rows': len(probe.rows),
    }


def _checksum(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def _season_short(season_label: str | None) -> str:
    if not season_label:
        return 'перечень'
    return season_label.replace('/', '-')


async def _store_companion(
    doc: dict,
    *,
    existing_id: str | None,
    name: str,
    doc_type: str,
    extension: str,
    mime_type: str,
    writer,
    parsed,
    companion: str,
) -> str:
    """Записать производный документ и вернуть его id.

    Повторный разбор того же PDF не должен плодить копии таблицы: id берётся
    из состояния прошлого прогона, файл перезаписывается, запись обновляется.
    Поэтому в списке документов у перечня ровно один XLSX и один HTML.
    """
    target_id = existing_id or str(uuid_mod.uuid4())
    target = _storage_path(target_id, extension)
    target.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(writer, parsed, target)

    metadata = {
        'rsosh': {
            'source_doc_id': str(doc['id']),
            'companion': companion,
            'season_label': parsed.season_label,
            'rows': len(parsed.rows),
            'author': doc.get('uploaded_by'),
        }
    }
    values = {
        'name': name,
        'type': doc_type,
        'storage_key': target.name,
        'mime_type': mime_type,
        'status': states.DOCS_STATUS['approved'],
        'metadata': metadata,
    }
    existing = await db_docs.get_doc(target_id) if existing_id else None
    if existing:
        await db_docs.edit_doc(target_id, values)
        return target_id

    record = await db_docs.add_doc({
        'id': target_id,
        **values,
        'checksum': await asyncio.to_thread(_checksum, target),
        'university_id': doc.get('university_id'),
        'uploaded_by': doc.get('uploaded_by'),
    })
    if record is None:  # pragma: no cover - insert без конфликта
        raise RsoshError('Не удалось сохранить таблицу перечня как документ')
    return target_id


def _summary(parsed, plan: dict) -> dict:
    return {
        'mode': 'official_list',
        'rows': len(parsed.rows),
        'olympiads': plan['summary']['olympiads'],
        'create': plan['summary']['create'],
        'use': plan['summary']['use'],
        'review': plan['summary']['review'],
        'profiles': plan['summary']['profiles'],
        'profiles_create': plan['summary']['profiles_create'],
        'profiles_update': plan['summary']['profiles_update'],
        'missing': plan['summary']['missing'],
        'errors': plan['summary']['errors'],
        'pages': parsed.source_pages,
        'tables': parsed.detected_tables,
        'complete': bool(parsed.complete),
    }


def _page_reports(parsed) -> list[dict]:
    return [report.to_dict() for report in parsed.pages]


async def run_list_import(doc_id) -> dict | None:
    """Разобрать официальный перечень и построить план импорта.

    ``None`` означает «документ не перечень»: вызывающий код продолжает
    прежнюю обработку. Ошибки разбора перечня — это уже ошибки импорта, они
    поднимаются как :class:`RsoshError`, и документ получает ``FAILED``.
    """
    from app.rsosh import list_parser

    doc = await db_docs.get_doc(doc_id)
    if not doc:
        raise RsoshError(f'Document {doc_id} not found')

    from app.rsosh.processor import document_path

    path = document_path(doc)
    detection = await asyncio.to_thread(detect_official_list, path)
    if not detection['official']:
        logger.info(
            'rsosh: %s is not an official list (%s); legacy pipeline',
            doc_id,
            detection['reason'],
        )
        return None

    section = states.rsosh_section(doc)
    doc = await _write_state(
        doc, states.progress_section(doc, stage='parsing-list')
    )

    parsed = await asyncio.to_thread(
        list_parser.parse_official_list, path
    )
    if not parsed.rows:
        raise RsoshError(
            'Перечень распознан как официальный, но строки не прочитаны: '
            'проверьте качество скана'
        )
    paused = await _pause_if_requested(doc, stage='parsed-list')
    if paused is not None:
        return paused

    doc = await _write_state(
        doc, states.progress_section(doc, stage='building-table')
    )
    season = _season_short(parsed.season_label)
    previous = section.get('table') or {}
    html_previous = section.get('html') or {}
    table_doc_id = await _store_companion(
        doc,
        existing_id=previous.get('doc_id'),
        name=f'Перечень {season} — таблица',
        doc_type='RSOSH_TABLE',
        extension='.xlsx',
        mime_type=TABLE_MIME,
        writer=list_xlsx.save,
        parsed=parsed,
        companion='table',
    )
    html_doc_id = await _store_companion(
        doc,
        existing_id=html_previous.get('doc_id'),
        name=f'Перечень {season} — таблица (HTML)',
        doc_type='RSOSH_HTML',
        extension='.html',
        mime_type=HTML_MIME,
        writer=list_xlsx.save_html,
        parsed=parsed,
        companion='html',
    )

    doc = await _write_state(
        doc, states.progress_section(doc, stage='matching')
    )
    catalog = await list_plan.load_catalog()
    plan = await asyncio.to_thread(
        list_plan.build_plan, parsed, doc_id=str(doc['id']), catalog=catalog
    )

    summary = _summary(parsed, plan)
    section = states.list_review_section(
        doc,
        plan=plan,
        pages=_page_reports(parsed),
        warnings=list(plan.get('warnings') or []),
        summary=summary,
        table_doc_id=table_doc_id,
        html_doc_id=html_doc_id,
        title=parsed.title,
    )
    return await _write_state(doc, section)


async def _write_state(doc: dict, section: dict) -> dict:
    """Записать раздел состояния вместе со статусом документа."""
    from app.rsosh import persist

    updated = await persist.write_import_state(doc['id'], section)
    return updated or doc


async def _pause_if_requested(doc: dict, *, stage: str) -> dict | None:
    """Остановиться, если администратор попросил паузу.

    Долгий OCR нельзя прервать на середине страницы, но между этапами это
    обязательно: иначе кнопка «пауза» на большом перечне не работала бы
    вовсе. Признак читается из базы, а не из снимка в памяти: запрос паузы
    приходит от другого процесса.
    """
    fresh = await db_docs.get_doc(doc['id'])
    if not fresh:
        return None
    section = states.rsosh_section(fresh)
    if not section.get('pause_requested'):
        return None
    return await _write_state(
        fresh,
        states.paused_section(fresh, stage=stage, warnings=section.get('warnings')),
    )


async def apply(doc_id, *, user_id=None, mark_missing: bool = False) -> dict:
    """Применить утверждённый план официального перечня."""
    return await list_apply.apply_plan(
        doc_id, user_id=user_id, mark_missing=mark_missing
    )


async def update_plan(doc_id, changes: dict) -> dict:
    """Применить правки плана и вернуть обновлённый документ."""
    doc = await db_docs.get_doc(doc_id)
    if not doc:
        raise RsoshError(f'Document {doc_id} not found')
    section = states.rsosh_section(doc)
    current = section.get('plan')
    plan = list_plan.apply_changes(current, changes)
    return await _write_state(doc, states.plan_section(doc, plan))


async def table_page(
    doc_id,
    *,
    sheet: str = 'list',
    offset: int = 0,
    limit: int = 50,
    search: str | None = None,
) -> dict:
    """Страница таблицы перечня для показа в панели.

    Читается сохранённый XLSX, а не метаданные: администратор должен видеть
    ровно тот файл, который скачивается. Пагинация серверная — в перечне
    бывает 300+ строк, и отдавать их все в одном ответе незачем.
    """
    doc = await db_docs.get_doc(doc_id)
    if not doc:
        raise RsoshError(f'Document {doc_id} not found')
    section = states.rsosh_section(doc)
    table = section.get('table') or {}
    table_doc_id = table.get('doc_id')
    if not table_doc_id:
        raise RsoshError('У документа ещё нет таблицы перечня')
    path = _storage_path(str(table_doc_id), '.xlsx')
    if not path.is_file():
        raise RsoshError('Файл таблицы не найден')

    return await asyncio.to_thread(
        _read_sheet, path, sheet, offset, limit, search
    )


def _read_sheet(
    path: Path,
    sheet: str,
    offset: int,
    limit: int,
    search: str | None,
) -> dict:
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    index = 1 if sheet == 'summary' else 0
    if index >= len(workbook.worksheets):
        raise RsoshError('Лист таблицы не найден')
    worksheet = workbook.worksheets[index]
    rows = list(worksheet.iter_rows(values_only=True))
    headers = [str(value or '') for value in (rows[0] if rows else [])]
    body = rows[1:]
    if search:
        needle = search.casefold()
        body = [
            row for row in body
            if any(needle in str(value or '').casefold() for value in row)
        ]
    total = len(body)
    window = body[offset:offset + limit]
    return {
        'sheet': 'summary' if sheet == 'summary' else 'list',
        'title': worksheet.title,
        'headers': headers,
        'rows': [
            ['' if value is None else value for value in row] for row in window
        ],
        'total': total,
        'offset': offset,
        'limit': limit,
    }
