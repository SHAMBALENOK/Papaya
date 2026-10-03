"""Запись подтверждённого импорта в каталог олимпиад.

Правила, которые держит этот модуль:

- одна строка кандидата = одна запись каталога: дубли не создаются, а
  существующая олимпиада обновляется (merge);
- олимпиада, присутствующая в новом перечне РСОШ, снова становится актуальной
  (``PUBLISHED``, причина архива сбрасывается) — так возвращается из архива.
  **Исключение — ручной архив** (``archive_reason = MANUAL``): это решение
  администратора, и перечень РСОШ его не отменяет (см. ``_upsert``);
- олимпиада, **исчезнувшая** из перечня РСОШ, не удаляется, а переводится в
  ``ARCHIVED`` с причиной ``RSOSH_ABSENT`` (см. ``_archive_missing``);
- записи, которые администратор снял в preview (``skip``), не считаются
  отсутствующими: ошибочная строка распознавания не должна архивировать
  существующую олимпиаду;
- **неполный импорт не архивирует ничего** (см. ``_archive_decision``).

Последний пункт — самый важный для целостности каталога. «Отсутствует в новом
перечне» — это утверждение о полноте: чтобы его сделать, нужно знать, что
перечень прочитан целиком. Если часть строк не распозналась или не
применилась, «отсутствует» означает совсем другое, и массовая архивация
уничтожила бы действующие записи каталога.

Всё применение перечня происходит в одной транзакции (см.
``apply_confirmed_import``). Это не оптимизация, а требование целостности:

- подтверждение двух перечней не должно пересекаться, иначе старый перечень,
  подтверждённый вторым, откатил бы каталог назад (проверка актуальности и
  запись должны быть под одним замком);
- один перечень нельзя применить дважды, поэтому состояние документа
  проверяется под блокировкой его строки;
- ошибка одной строки не должна ломать остальные, поэтому каждый кандидат
  записывается в SAVEPOINT (см. ``_apply_candidates``).
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.database.database import AsyncSessionLocal
from app.database.search import normalize_name
from app.middlewares.serializers import doc_to_dict, olympiad_to_dict
from app.models.docs import Docs
from app.models.olympiads import Olympiads
from app.rsosh import states
from app.rsosh.types import Candidate, RsoshConflictError, RsoshError

logger = logging.getLogger('papaya.rsosh.persist')

# Причины архивирования (совпадают с комментарием в app/models/olympiads.py).
ARCHIVE_BY_RSOSH = 'RSOSH_ABSENT'
ARCHIVE_MANUAL = 'MANUAL'

#: Единственный тип документа, который может создавать и обновлять олимпиады.
#:
#: Другие типы (``UNIVERSITY_ORDER``, ``OTHER``) существуют как хранилище
#: источников: приказ университета полезно хранить рядом с каталогом, но он не
#: является перечнем олимпиад и не должен ни создавать, ни обновлять записи
#: каталога. Значение совпадает с ``processor.RSOSH_DOC_TYPE``, но продублировано
#: намеренно: persist не должен импортировать процессор (тот импортирует persist).
RSOSH_DOC_TYPE = 'RSOSH_LIST'

#: Статусы документа, из которых импорт запустить можно.
#:
#: ``PROCESSING`` исключён осознанно: документ в обработке уже занят, и повторный
#: запуск должен отказать (см. ``claim_import_start``). Воркер при этом
#: проходит проверку типа и продолжает работу: он запускается после того, как
#: переход в ``PROCESSING`` уже занял документ.
STARTABLE_DOC_STATUSES = ('UPLOADED', 'NEEDS_REVIEW', 'FAILED', 'PROCESSED')

#: Ключ advisory-блокировки, сериализующей применение перечней РСОШ.
#:
#: Произвольное, но постоянное число: важно лишь, чтобы применение любого
#: перечня РСОШ в пределах одной базы шло через один и тот же ключ. Блокировка
#: транзакционная (``pg_advisory_xact_lock``), поэтому снимается сама при
#: commit или rollback — «забыть» её нельзя, в том числе при падении процесса.
RSOSH_SNAPSHOT_LOCK_KEY = 0x7061_7061  # 'papa'

#: Предупреждения, после которых перечень нельзя считать прочитанным целиком.
#:
#: Это не «что-то подозрительно», а прямой ответ разбора на вопрос «насколько
#: мне удалось разобрать структуру»: если шапка или границы таблицы не
#: распознаны или таблица выглядела не списком, то «этой олимпиады в
#: перечне нет» означает «я её не увидел», а не «её больше нет».
#:
#: Остальные предупреждения (поворот страницы, OCR как запасной путь,
#: повтор олимпиады в разных разделах, служебные строки) структурой не
#: противоречат и архивированию не мешают: это нормальные условия чтения
#: перечня.
STRUCTURE_WARNING_MARKERS = (
    'Table header was not recognized',
    'Table borders were not detected',
    'Small table skipped',
    'Sheet is empty',
)


def _as_uuid(value):
    import uuid as uuid_mod

    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


def _as_iso(value):
    """Время в ISO-8601; на вход может прийти уже строкой."""
    if value is None or isinstance(value, str):
        return value
    return value.isoformat()


def _candidate_error_text(exc: Exception) -> str:
    """Понятная причина неудачной строки без внутренностей реализации.

    Текст попадает в отчёт импорта, который возвращается в API и хранится в
    метаданных документа, поэтому тексты ошибок БД (имена таблиц, колонок,
    значения параметров) туда не выводятся.
    """
    if isinstance(exc, IntegrityError):
        return 'строка нарушает ограничения целостности (дубликат или '\
            'недопустимое значение)'
    if isinstance(exc, DBAPIError):
        return 'строку не удалось записать: ошибка соединения с базой данных'
    if isinstance(exc, (TypeError, ValueError, AttributeError, KeyError)):
        # Ошибка уровня Python: текст безопасен и полезен (какое поле сломано).
        return f'некорректные данные строки: {exc}'
    return 'строку не удалось записать'



def _archive_decision(
    *,
    requested: bool,
    errors: list[str],
    warnings: list[str],
) -> tuple[bool, str | None]:
    """Можно ли считать, что отсутствующие олимпиады исчезли из перечня.

    Возвращает ``(архивировать, причина_отказа)``. Отказ — это не ошибка
    импорта: подтверждённые кандидаты всё равно создаются и обновляются,
    просто каталог не трогают, а причина отказа возвращается администратору в
    отчёте.
    """
    if not requested:
        return False, None
    if errors:
        # Часть строк документа не применилась: для них «нет в перечне» — это
        # не факт, а последствие ошибки записи.
        return False, (
            'Архивирование отключено: часть строк перечня не удалось применить '
            f'({len(errors)} шт.). Неприменённые строки не считаются '
            'отсутствующими.'
        )
    unreadable = [
        warning
        for warning in warnings
        if any(marker in warning for marker in STRUCTURE_WARNING_MARKERS)
    ]
    if unreadable:
        return False, (
            'Архивирование отключено: перечень прочитан не полностью '
            f'({unreadable[0]}). По такому перечню нельзя судить, какие '
            'олимпиады из него исчезли.'
        )
    return True, None


async def apply_confirmed_import(
    *,
    doc_id,
    skip: list[str] | None = None,
    archive_missing: bool = True,
) -> dict:
    """Применить подтверждённый перечень целиком, в одной транзакции.

    Порядок именно такой, и он обеспечен блокировками, а не проверками:

    1. advisory-блокировка (transaction-scoped) — с этого момента никакое
       другое применение перечня РСОШ не идёт ни в этой базе, ни в этой
       транзакции. Это и есть защита от отката: проверка актуальности и
       запись каталога не могут разойтись по времени;
    2. блокировка строки документа (``SELECT ... FOR UPDATE``) — второй
       администратор, подтверждающий тот же перечень, дождётся конца первой
       транзакции и увидит состояние ``approved``, а не ``review``;
    3. перечитывание состояния документа и поиск свежего подтверждённого
       перечня — уже под обеими блокировками, то есть по актуальным данным;
    4. запись кандидатов (каждый в SAVEPOINT) и архивирование пропавших;
    5. запись состояния ``approved`` и ``processedAt`` **той же**
       транзакцией, что и каталог.

    Благодаря пункту 5 подтверждённый перечень становится актуальным ровно в
    момент коммита вместе с записями каталога. Расхождение «каталог записан, а
    документ ещё не approved» невозможно, а значит невозможен и откат каталога
    старым перечнем, который сочтётся самым свежим по состоянию документов.

    Возвращает ``{'document': dict, 'result': dict, 'skipped': [name_norm]}``.
    """
    skip_list = [str(item) for item in (skip or [])]
    doc_uuid = _as_uuid(doc_id)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _lock_snapshot_scope(session)

            doc_row = (
                await session.execute(
                    select(Docs).where(Docs.id == doc_uuid).with_for_update()
                )
            ).scalar_one_or_none()
            if doc_row is None:
                raise RsoshError(f'Document {doc_id} not found')

            document = doc_to_dict(doc_row)
            section = states.rsosh_section(document)
            if section.get('state') not in states.CONFIRMABLE_STATES:
                # Сюда попадает и повторное подтверждение уже применённого
                # перечня: состояние approved не confirmable.
                raise RsoshConflictError(
                    f'Импорт в состоянии {section.get("state")} уже применён '
                    'или не может быть применён повторно'
                )
            if document.get('type') != RSOSH_DOC_TYPE:
                # Единственный документ, который может обновлять каталог.
                # Приказ университета и любой другой источник остаются
                # хранилищем документов и олимпиад из них не создают.
                raise RsoshError(
                    'Only RSOSH_LIST documents can update the catalog'
                )

            newest = await _newest_confirmed(session, exclude_doc_id=doc_uuid)
            if is_outdated_snapshot(document, newest):
                newest_id, newest_created_at = newest
                raise RsoshConflictError(
                    'Этот перечень устарел: он загружен раньше уже '
                    f'подтверждённого документа (от {str(newest_created_at)[:10]}). '
                    'Подтверждение вернуло бы каталог к старой редакции, '
                    'поэтому невозможно. Загрузите актуальный перечень РСОШ.'
                )

            candidates = [
                Candidate.from_dict(item)
                for item in (section.get('candidates') or [])
            ]
            skip_set = set(skip_list)
            unknown = skip_set - {item.name_norm for item in candidates}
            if unknown:
                raise RsoshError(
                    'Unknown candidates in skip: ' + ', '.join(sorted(unknown))
                )

            selected = [
                item for item in candidates if item.name_norm not in skip_set
            ]
            # Кандидаты, снятые администратором в preview, защищаются от
            # автоматического архивирования: «не подтвердил» не значит «нет в
            # перечне РСОШ» (чаще всего снятие — это реакция на ошибку
            # распознавания).
            protected_ids = {
                item.matched_olympiad_id
                for item in candidates
                if item.name_norm in skip_set and item.matched_olympiad_id
            }

            result = await _apply_candidates(
                session,
                candidates=selected,
                doc_id=doc_uuid,
                archive_missing=archive_missing,
                protected_ids=protected_ids,
                # Предупреждения разбора решают, можно ли доверять перечню в
                # вопросе «кого в нём больше нет».
                warnings=section.get('warnings') or [],
            )

            now = datetime.now(timezone.utc)
            doc_row.processedAt = now
            doc_row.updatedAt = now
            doc_row.status = states.DOCS_STATUS['approved']
            doc_row.meta = states.docs_metadata_with_section(
                document, states.confirmed_section(document, result)
            )
            document = doc_to_dict(doc_row)

    return {
        'document': document,
        'result': result,
        'skipped': sorted(skip_set),
    }


async def reject_confirmed_import(doc_id) -> dict:
    """Отклонить результаты импорта под теми же блокировками, что и confirm.

    Отклонение меняет только состояние документа, каталог не трогает, и
    именно поэтому раньше оно выглядело безобидным. Но состояние прогона — это
    и есть факт «этот перечень применён», поэтому менять его в обход
    блокировок нельзя:

    - ``confirm`` фиксирует применение перечня и состояние ``approved`` в одной
      транзакции под advisory-блокировкой;
    - ``reject`` раньше читал состояние, затем менял его отдельной операцией, и
      мог сработать уже после коммита ``confirm``.

    Итогом был документ, для которого каталог применён, а прогон помечен
    ``rejected``: по интерфейсу выглядит так, будто перечень отклонили, а
    олимпиады в каталоге уже изменены.

    Здесь порядок тот же, что в ``apply_confirmed_import``: advisory-блокировка
    → ``SELECT ... FOR UPDATE`` по документу → проверка состояния → запись →
    commit. Поэтому возможен ровно один исход: либо отклонение, либо
    подтверждение, и второе после первого получает 409.

    Возвращает обновлённый документ.
    """
    doc_uuid = _as_uuid(doc_id)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _lock_snapshot_scope(session)

            doc_row = (
                await session.execute(
                    select(Docs).where(Docs.id == doc_uuid).with_for_update()
                )
            ).scalar_one_or_none()
            if doc_row is None:
                raise RsoshError(f'Document {doc_id} not found')

            document = doc_to_dict(doc_row)
            section = states.rsosh_section(document)
            if section.get('state') not in states.REJECTABLE_STATES:
                # Сюда попадает и «уже применён» (approved): подтвердить и
                # отклонить один и тот же прогон нельзя.
                raise RsoshConflictError(
                    f'Импорт в состоянии {section.get("state")} уже применён '
                    'или не может быть отклонён'
                )

            now = datetime.now(timezone.utc)
            doc_row.updatedAt = now
            doc_row.status = states.DOCS_STATUS['rejected']
            doc_row.meta = states.docs_metadata_with_section(
                document, states.rejected_section(document)
            )
            return doc_to_dict(doc_row)


async def claim_import_start(doc_id) -> dict:
    """Атомарно занять документ под обработку: перевести его в ``PROCESSING``.

    Запуск импорта раньше состоял из двух независимых операций — чтение
    документа и запись состояния. Два одновременных запроса успевали оба
    прочитать документ до перехода и оба запустить обработку: две задачи на
    один документ писали в один и тот же ``docs.metadata['rsosh']``, и итог
    зависел от того, кто финишировал последним.

    Теперь переход выполняется под advisory-блокировкой и блокировкой строки
    документа, поэтому он атомарен. Второй concurrent-запрос дожидается первого,
    видит ``PROCESSING`` и получает 409: обработка уже идёт, запускать вторую
    нельзя.

    Повторный запуск после завершения (и после ошибки) остаётся возможным:
    ``PROCESSING`` — единственное состояние, которое занято.

    Возвращает документ в состоянии ``processing``.
    """
    doc_uuid = _as_uuid(doc_id)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _lock_snapshot_scope(session)

            doc_row = (
                await session.execute(
                    select(Docs).where(Docs.id == doc_uuid).with_for_update()
                )
            ).scalar_one_or_none()
            if doc_row is None:
                raise RsoshError(f'Document {doc_id} not found')

            document = doc_to_dict(doc_row)
            if document.get('type') != RSOSH_DOC_TYPE:
                raise RsoshError('Only RSOSH_LIST documents can be imported')

            section = states.rsosh_section(document)
            already_running = (
                document.get('status') == states.DOCS_STATUS['processing']
                or section.get('state') == 'processing'
            )
            if already_running:
                raise RsoshConflictError(
                    'Импорт этого документа уже запущен: дождитесь окончания '
                    'или отклоните текущий прогон'
                )
            if document.get('status') not in STARTABLE_DOC_STATUSES:
                raise RsoshError(
                    'Import is not startable from status '
                    + str(document.get('status'))
                    + '; startable: ' + ', '.join(STARTABLE_DOC_STATUSES)
                )

            now = datetime.now(timezone.utc)
            doc_row.updatedAt = now
            doc_row.status = states.DOCS_STATUS['processing']
            doc_row.meta = states.docs_metadata_with_section(
                document, states.start_section(document)
            )
            return doc_to_dict(doc_row)


async def _lock_snapshot_scope(session) -> None:
    """Заблокировать применение перечней РСОШ до конца транзакции.

    ``pg_advisory_xact_lock`` — блокировка уровня базы, привязанная к
    транзакции: PostgreSQL отдаёт её при commit и rollback, а также при
    разрыве соединения. Отдельного «забытого» замка не остаётся, в том числе
    если процесс упал посреди импорта.
    """
    await session.execute(
        text('SELECT pg_advisory_xact_lock(:key)'),
        {'key': RSOSH_SNAPSHOT_LOCK_KEY},
    )


async def _newest_confirmed(session, *, exclude_doc_id=None) -> tuple | None:
    """Самый «свежий» уже подтверждённый перечень — в текущей транзакции.

    Порядок снимков определяется временем загрузки документа: год олимпиады
    Papaya не моделирует (одна каноническая олимпиада независимо от года), и
    разбирать документ ради даты — значит трогать распознавание. Практически
    это и есть нужный порядок: перечень РСОШ загружают по мере выхода новой
    редакции.

    Чтение выполняется в сессии вызывающего намеренно: под advisory-блокировкой
    так видны изменения, зафиксированные другим применением, — именно это и
    нужно, чтобы отвергнуть старый перечень.

    Время возвращается в том же виде, что и у словаря документа (ISO-8601),
    чтобы сравнение не зависело от типа.
    """
    rows = (
        await session.execute(
            select(Docs.id, Docs.createdAt, Docs.meta)
            .where(Docs.type == 'RSOSH_LIST')
            .order_by(Docs.createdAt.desc(), Docs.id)
        )
    ).all()
    for row_id, created_at, meta in rows:
        if exclude_doc_id is not None and str(row_id) == str(exclude_doc_id):
            continue
        row_section = ((meta or {}).get('rsosh') or {})
        if row_section.get('state') == 'approved':
            return row_id, _as_iso(created_at)
    return None


async def _apply_candidates(
    session,
    *,
    candidates: list[Candidate],
    doc_id,
    archive_missing: bool,
    protected_ids: set[str],
    warnings: list[str],
) -> dict:
    """Записать кандидатов в каталог в рамках уже открытой транзакции.

    Каждый кандидат сохраняется в отдельном SAVEPOINT. Это не «хороший тон»,
    а требование: ошибка ``flush()`` переводит сессию SQLAlchemy в
    failed-состояние, и простой ``continue`` после такой ошибки не оставляет
    сессию пригодной для следующих строк — вместо «одна строка не записалась»
    получается «весь импорт развалился». SAVEPOINT откатывает только
    неудачную строку, оставляя транзакцию и уже записанное на месте.

    ``protected_ids`` — id олимпиад, которые нельзя архивировать, даже если их
    не было в текущем документе (кандидаты, снятые администратором в preview).

    ``warnings`` — предупреждения разбора документа: часть из них означает, что
    структуру перечня прочитать не удалось, и тогда архивирование отключается
    (см. ``_archive_decision``).
    """
    created: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    touched_ids: list[str] = []

    for candidate in candidates:
        try:
            async with session.begin_nested():
                olympiad = await _upsert(session, candidate, doc_id)
        except Exception as exc:  # noqa: BLE001 - одна плохая строка не
            # должна откатывать весь импорт
            logger.exception('rsosh: cannot apply candidate %s', candidate.name)
            errors.append(f'{candidate.name}: {_candidate_error_text(exc)}')
            continue
        if olympiad is None:
            skipped.append(candidate.name)
            continue
        touched_ids.append(str(olympiad['id']))
        if candidate.action == 'create':
            created.append(olympiad['name'])
        else:
            updated.append(olympiad['name'])

    archived: list[str] = []
    archive_reason = None
    should_archive, archive_reason = _archive_decision(
        requested=archive_missing,
        errors=errors,
        warnings=list(warnings or []),
    )
    if should_archive:
        archived = await _archive_missing(
            session,
            doc_id,
            set(touched_ids) | {str(value) for value in protected_ids},
        )

    logger.info(
        'rsosh: applied %s candidates (created=%s, merged=%s, archived=%s%s)',
        len(candidates), len(created), len(updated), len(archived),
        ', archive skipped' if archive_reason else '',
    )
    return {
        'created': created,
        'updated': updated,
        'archived': archived,
        'skipped': skipped,
        'errors': errors,
        # Почему каталог не тронут, когда это важно администратору: пустое
        # значение означает, что архивирование либо не запрашивали, либо
        # отработало штатно.
        'archive_skipped_reason': archive_reason,
    }



async def _upsert(session, candidate: Candidate, doc_id):
    """Создать или обновить олимпиаду по кандидату."""
    from datetime import datetime, timezone

    olympiad = None
    if candidate.action == 'merge' and candidate.matched_olympiad_id:
        result = await session.execute(
            select(Olympiads).where(
                Olympiads.id == _as_uuid(candidate.matched_olympiad_id)
            )
        )
        olympiad = result.scalar_one_or_none()

    if olympiad is None:
        name_norm = candidate.name_norm or normalize_name(candidate.name)
        result = await session.execute(
            select(Olympiads).where(Olympiads.name_norm == name_norm)
        )
        olympiad = result.scalar_one_or_none()

    if olympiad is None:
        now = datetime.now(timezone.utc)
        olympiad = Olympiads(
            name=candidate.name,
            name_norm=candidate.name_norm or normalize_name(candidate.name),
            description=candidate.description,
            source_doc_id=doc_id,
            status='PUBLISHED',
            archive_reason=None,
            createdAt=now,
            updatedAt=now,
        )
        session.add(olympiad)
        await session.flush()
        return olympiad_to_dict(olympiad)

    changed = False
    if olympiad.archive_reason == ARCHIVE_MANUAL:
        # Ручной архив — это решение администратора, а не вывод разбора РСОШ.
        # Перечень РСОШ не отменяет его: иначе олимпиада, которую исключили
        # руками (например, из-за ошибки в данных), возвращалась бы в актуальные
        # при первом же импорте, где она встретится. Вернуть такую запись может
        # только администратор через POST /admin/archive_olympiad.
        #
        # Остальные поля (описание, источник) при этом обновляются как обычно:
        # перечень подтверждает, что олимпиада существует, и это не повод
        # отказывать ей в актуальных данных.
        pass
    elif olympiad.status != 'PUBLISHED' or olympiad.archive_reason is not None:
        # Олимпиада снова встретилась в актуальном перечне: возвращаем её в
        # актуальные и сбрасываем причину архива. Это относится только к
        # архиву «нет в перечне РСОШ» (RSOSH_ABSENT) и к неконсистентным
        # записям без причины.
        olympiad.status = 'PUBLISHED'
        olympiad.archive_reason = None
        changed = True
    if candidate.description and not olympiad.description:
        olympiad.description = candidate.description
        changed = True
    if olympiad.source_doc_id != doc_id:
        olympiad.source_doc_id = doc_id
        changed = True
    if changed:
        olympiad.updatedAt = datetime.now(timezone.utc)
    await session.flush()
    return olympiad_to_dict(olympiad)


async def _archive_missing(session, doc_id, keep_ids: set[str]) -> list[str]:
    """Перевести в архив олимпиады, исчезнувшие из перечня РСОШ.

    Архивируются только те записи, которые ранее пришли из документа РСОШ
    (``source_doc_id`` задан и это не текущий документ) и не встретились в
    новом перечне. Олимпиады, созданные вручную, архивированию не подлежат.

    ``keep_ids`` — олимпиады, которых нельзя архивировать: применённые
    кандидаты и кандидаты, снятые администратором в preview. Снятые с
    подтверждения записи не считаются отсутствующими в перечне: иначе ошибка
    распознавания одной строки архивировала бы существующую олимпиаду.
    """
    from datetime import datetime, timezone

    result = await session.execute(
        select(Olympiads).where(
            Olympiads.status == 'PUBLISHED',
            Olympiads.source_doc_id.is_not(None),
            Olympiads.source_doc_id != doc_id,
        )
    )
    archived: list[str] = []
    now = datetime.now(timezone.utc)
    for olympiad in result.scalars().all():
        if str(olympiad.id) in keep_ids:
            continue
        olympiad.status = 'ARCHIVED'
        olympiad.archive_reason = ARCHIVE_BY_RSOSH
        olympiad.updatedAt = now
        archived.append(olympiad.name)
    return archived


def is_outdated_snapshot(doc: dict, newest_confirmed) -> bool:
    """Является ли документ устаревшим снимком перечня.

    Устаревшим считается документ, загруженный **раньше** уже подтверждённого:
    подтверждение такого документа вернуло бы каталог к старой редакции —
    опубликовало бы олимпиаду, которой в свежем перечне уже нет, и заархивировало
    новую.

    Тот же документ устаревшим не считается: повторное подтверждение уже
    применённого перечня ничего не откатывает. Проверка состояния перечня
    (можно ли его применять вообще) живёт отдельно, в
    ``apply_confirmed_import``, под блокировкой.
    """
    if not newest_confirmed:
        return False
    newest_id, newest_created_at = newest_confirmed
    if str(newest_id) == str(doc.get('id')):
        return False
    created_at = doc.get('createdAt')
    if created_at is None or newest_created_at is None:
        return False
    # ISO-8601 в UTC сравнивается лексикографически в том же порядке, что и по
    # времени, — поэтому достаточно строкового сравнения.
    return str(created_at) < str(newest_created_at)

