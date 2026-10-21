"""Запись подтверждённого импорта приказа университета.

Главное отличие от ``app.rsosh.persist``: приказ вуза **не пишет в каталог
олимпиад**. Он создаёт только связи БВИ «этот университет даёт БВИ за эту
олимпиаду» — и то лишь как **заявки** (``PENDING``). Подтверждает их человек
штатной модерацией (``app.database.bvi.moderate_bvi_link``), а не импорт:
автоподтверждение запрещено, потому что распознавание приказа может ошибиться
и в олимпиаде, и в самом факте БВИ.

Из этого следуют правила модуля:

- **никаких олимпиад**: строка приказа либо ссылается на существующую
  олимпиаду каталога, либо не применяется вовсе (несопоставленные строки
  администратор связывает вручную в окне проверки);
- **никаких подтверждений**: записанная связь всегда ``PENDING``, даже если
  такая же связь уже была подтверждена ранее — повторный импорт не должен
  «разжаловать» подтверждённую связь и не должен выдавать её за новую заявку;
- **никаких дублей**: запись идемпотентна по уникальной паре
  ``(university_id, olympiad_id)``; уже существующая связь пропускается;
- всё применение идёт в одной транзакции под advisory-блокировкой применения
  приказов и блокировкой строки документа — так два подтверждения одного
  документа не пересекаются, а состояние прогона и записи связей согласованы.

Происхождение связи сохраняется рядом: ``source_doc_id`` (документ-источник) и
``source_meta`` (распознанные характеристики строки — направление, профиль,
предмет, уровень, диплом). Сущностей «сезон/профиль/правило» в модели Papaya
нет, поэтому распознанные поля хранятся как есть и не создают новых записей.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.database.database import AsyncSessionLocal
from app.middlewares.serializers import doc_to_dict
from app.models.bvi import UniversityBvi
from app.models.docs import Docs
from app.models.olympiads import Olympiads
from app.models.universities import Universities
from app.university import states
from app.university.types import (
    UniversityCandidate,
    UniversityConflictError,
    UniversityError,
)

logger = logging.getLogger('papaya.university.persist')

#: Единственный тип документа, который может создавать связи БВИ.
UNIVERSITY_DOC_TYPE = 'UNIVERSITY_ORDER'

#: Статусы документа, из которых импорт приказа запустить можно.
#:
#: Совпадают с РСОШ: ``PROCESSING`` исключён (документ занят обработкой),
#: повторный запуск после завершения и после ошибки — разрешён.
STARTABLE_DOC_STATUSES = ('UPLOADED', 'NEEDS_REVIEW', 'FAILED', 'PROCESSED')

#: Ключ advisory-блокировки, сериализующей применение приказов вузов.
#:
#: Отдельный от РСОШ (``0x70617061``): импорт РСОШ и импорт приказов пишут в
#: разные сущности, и их не нужно сериализовать друг относительно друга.
UNIVERSITY_SNAPSHOT_LOCK_KEY = 0x756E6976  # 'univ'


def _as_uuid(value):
    import uuid as uuid_mod

    if value is None:
        return None
    return value if isinstance(value, uuid_mod.UUID) else uuid_mod.UUID(str(value))


async def _lock_apply_scope(session) -> None:
    """Заблокировать применение приказов вузов до конца транзакции."""
    await session.execute(
        text('SELECT pg_advisory_xact_lock(:key)'),
        {'key': UNIVERSITY_SNAPSHOT_LOCK_KEY},
    )


async def _locked_doc(session, doc_id):
    """Строка документа под ``SELECT ... FOR UPDATE`` (или ``None``)."""
    return (
        await session.execute(
            select(Docs).where(Docs.id == _as_uuid(doc_id)).with_for_update()
        )
    ).scalar_one_or_none()


async def write_import_state(doc_id, section: dict) -> dict | None:
    """Записать раздел состояния прогона, не затирая правки администратора.

    Воркер держит документ в памяти через долгие этапы (чтение и OCR скана
    идут минуты), поэтому его снимок устаревает: администратор тем временем
    может сохранить выбор или подать запрос паузы — оба изменения пишут в ту
    же строку под блокировкой. Прямая запись устаревшего снимка стёрла бы эти
    правки, поэтому строка берётся под блокировками, а актуальные значения
    переносятся в новый раздел:

    - ``selection`` — всегда: воркер его не порождает;
    - ``pause_requested`` — только пока раздел остаётся в ``processing``:
      в ``paused`` флаг уже погашен записью паузы, и возрождать его нельзя.

    Статус документа выводится из состояния раздела.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _lock_apply_scope(session)

            doc_row = await _locked_doc(session, doc_id)
            if doc_row is None:
                return None

            document = doc_to_dict(doc_row)
            fresh = states.university_section(document)
            merged = dict(section)
            if 'selection' in fresh:
                merged['selection'] = fresh['selection']
            if merged.get('state') == 'processing' and 'pause_requested' in fresh:
                merged['pause_requested'] = fresh['pause_requested']

            now = datetime.now(timezone.utc)
            doc_row.updatedAt = now
            doc_row.status = states.DOCS_STATUS.get(
                merged.get('state'), doc_row.status
            )
            doc_row.meta = states.docs_metadata_with_section(document, merged)
            return doc_to_dict(doc_row)


async def claim_import_start(doc_id) -> dict:
    """Атомарно занять документ под обработку (переход в ``PROCESSING``).

    Запуск под advisory-блокировкой и блокировкой строки: два одновременных
    запроса не запускают две обработки одного документа. Второй видит
    ``processing`` и получает 409. Повторный запуск после завершения разрешён.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _lock_apply_scope(session)

            doc_row = await _locked_doc(session, doc_id)
            if doc_row is None:
                raise UniversityError(f'Document {doc_id} not found')

            document = doc_to_dict(doc_row)
            if document.get('type') != UNIVERSITY_DOC_TYPE:
                raise UniversityError(
                    'Only UNIVERSITY_ORDER documents can be imported'
                )

            section = states.university_section(document)
            if (
                document.get('status') == states.DOCS_STATUS['processing']
                or section.get('state') == 'processing'
            ):
                raise UniversityConflictError(
                    'Импорт этого документа уже запущен: дождитесь окончания '
                    'обработки'
                )
            if document.get('status') not in STARTABLE_DOC_STATUSES:
                raise UniversityError(
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


async def request_pause(doc_id) -> dict:
    """Запросить приостановку идущего импорта (ставит флаг паузы).

    Флаг не меняет состояние сам: обработка может идти в другом процессе, и
    pipeline проверяет флаг на границах этапов, тогда и переводит прогон в
    ``paused``.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _lock_apply_scope(session)

            doc_row = await _locked_doc(session, doc_id)
            if doc_row is None:
                raise UniversityError(f'Document {doc_id} not found')

            document = doc_to_dict(doc_row)
            section = states.university_section(document)
            if (
                document.get('status') != states.DOCS_STATUS['processing']
                or section.get('state') != 'processing'
            ):
                raise UniversityConflictError(
                    'Импорт не обрабатывается: приостановить можно только '
                    'идущую обработку'
                )

            section = {**section, 'pause_requested': True}
            doc_row.updatedAt = datetime.now(timezone.utc)
            doc_row.meta = states.docs_metadata_with_section(document, section)
            return doc_to_dict(doc_row)


async def claim_resume(doc_id) -> dict:
    """Атомарно возобновить приостановленный импорт (переход в ``PROCESSING``).

    Контрольная точка сохраняется: ``run_import`` видит сохранённые строки и
    продолжает с сопоставления, не читая документ заново.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _lock_apply_scope(session)

            doc_row = await _locked_doc(session, doc_id)
            if doc_row is None:
                raise UniversityError(f'Document {doc_id} not found')

            document = doc_to_dict(doc_row)
            if document.get('type') != UNIVERSITY_DOC_TYPE:
                raise UniversityError(
                    'Only UNIVERSITY_ORDER documents can be imported'
                )

            section = states.university_section(document)
            if section.get('state') != 'paused':
                raise UniversityConflictError(
                    'Импорт не приостановлен: возобновить можно только '
                    'приостановленный импорт'
                )

            now = datetime.now(timezone.utc)
            doc_row.updatedAt = now
            doc_row.status = states.DOCS_STATUS['processing']
            doc_row.meta = states.docs_metadata_with_section(
                document, states.resumed_section(document)
            )
            return doc_to_dict(doc_row)


def _clean_selection(selection: dict | None) -> dict:
    """Нормализовать выбор администратора к известным полям."""
    selection = selection or {}
    skip = [
        str(item).strip()
        for item in (selection.get('skip') or [])
        if str(item).strip()
    ]
    links = {
        str(key).strip(): str(value).strip()
        for key, value in (selection.get('links') or {}).items()
        if str(key).strip() and str(value).strip()
    }
    university_id = selection.get('university_id')
    return {
        'skip': sorted(set(skip)),
        'links': links,
        'university_id': str(university_id).strip() if university_id else None,
    }


async def save_import_selection(doc_id, *, selection: dict) -> dict:
    """Сохранить выбор администратора для прогона, готового к подтверждению.

    Выбор хранится вместе с прогоном, поэтому переживает перезагрузку
    страницы. Применяется он только при подтверждении: сам по себе раздел
    связи не создаёт. Чужой выбор (для незнакомых строк) отвергается как
    ошибка запроса.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _lock_apply_scope(session)

            doc_row = await _locked_doc(session, doc_id)
            if doc_row is None:
                raise UniversityError(f'Document {doc_id} not found')

            document = doc_to_dict(doc_row)
            section = states.university_section(document)
            if section.get('state') != 'review':
                raise UniversityConflictError(
                    'Выбор можно сохранить только для прогона, готового к '
                    'подтверждению'
                )

            clean = _clean_selection(selection)
            known = {
                item.get('name_norm')
                for item in (section.get('candidates') or [])
            }
            unknown = (
                set(clean['skip']) | set(clean['links'])
            ) - known
            if unknown:
                raise UniversityError(
                    'Unknown candidates in selection: '
                    + ', '.join(sorted(unknown))
                )

            doc_row.updatedAt = datetime.now(timezone.utc)
            doc_row.meta = states.docs_metadata_with_section(
                document, states.selection_section(document, clean)
            )
            return doc_to_dict(doc_row)


async def reject_import(doc_id) -> dict:
    """Отклонить результаты импорта (каталог и связи не трогаются).

    Смена состояния идёт под теми же блокировками, что и подтверждение, чтобы
    отклонение не сработало после коммита подтверждения.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _lock_apply_scope(session)

            doc_row = await _locked_doc(session, doc_id)
            if doc_row is None:
                raise UniversityError(f'Document {doc_id} not found')

            document = doc_to_dict(doc_row)
            section = states.university_section(document)
            if section.get('state') not in states.REJECTABLE_STATES:
                state = section.get('state')
                if state == 'processing':
                    raise UniversityConflictError(
                        'Импорт ещё обрабатывается: дождитесь окончания обработки'
                    )
                raise UniversityConflictError(
                    f'Импорт в состоянии {state} уже применён '
                    'или не может быть отклонён'
                )

            doc_row.updatedAt = datetime.now(timezone.utc)
            doc_row.status = states.DOCS_STATUS['rejected']
            doc_row.meta = states.docs_metadata_with_section(
                document, states.rejected_section(document)
            )
            return doc_to_dict(doc_row)


async def mark_import_failed_if_stuck(doc_id, *, error: str) -> bool:
    """Перевести зависший (``PROCESSING``) импорт в ``failed``.

    Нужна воркеру: если подпроцесс упал до записи результата, документ без
    отметки завис бы в ``PROCESSING`` навсегда. Чужой результат не трогается:
    отметка ставится, только если документ всё ещё ``PROCESSING``.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _lock_apply_scope(session)

            doc_row = await _locked_doc(session, doc_id)
            if doc_row is None:
                return False

            document = doc_to_dict(doc_row)
            section = states.university_section(document)
            if (
                document.get('status') != states.DOCS_STATUS['processing']
                or section.get('state') != 'processing'
            ):
                return False

            doc_row.updatedAt = datetime.now(timezone.utc)
            doc_row.status = states.DOCS_STATUS['failed']
            doc_row.meta = states.docs_metadata_with_section(
                document, states.failed_section(document, error)
            )
            return True


#: Действия кандидата, которые что-то записывают при подтверждении.
_APPLYING_ACTION = 'link'


async def apply_confirmed_import(
    doc_id,
    *,
    selection: dict | None = None,
    university_id=None,
) -> dict:
    """Создать связи БВИ (``PENDING``) по подтверждённым сопоставлениям.

    Возвращает ``{'document', 'result'}: сам документ и итоги записи
    (``linked``/``skipped``/``unmatched``/``errors``).

    Строка приказа применяется, только если:

    - она не снята администратором (``skip``);
    - у неё есть целевая олимпиада — автоматически сопоставленная либо
      выбранная вручную в ``selection.links`` (приказ сам олимпиад не
      создаёт);
    - определён целевой университет (из шапки документа либо переопределён
      администратором).

    Одна олимпиада в строке = одна связь: дубли внутри документа схлопнуты
    ещё при сопоставлении, а повторный импорт не создаёт второй связи
    (идемпотентность по уникальной паре).
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _lock_apply_scope(session)

            doc_row = await _locked_doc(session, doc_id)
            if doc_row is None:
                raise UniversityError(f'Document {doc_id} not found')

            document = doc_to_dict(doc_row)
            section = states.university_section(document)
            if section.get('state') not in states.CONFIRMABLE_STATES:
                raise UniversityConflictError(
                    f'Импорт в состоянии {section.get("state")} нельзя '
                    'подтвердить: подтверждение возможно только для прогона, '
                    'готового к проверке'
                )

            stored_selection = _clean_selection(section.get('selection'))
            incoming = _clean_selection(selection) if selection else None
            if incoming:
                overrides = incoming
            else:
                overrides = stored_selection

            target_university = await _resolve_university(
                session, document, section, overrides, university_id
            )
            if target_university is None:
                raise UniversityError(
                    'Не удалось определить университет приказа: выберите '
                    'университет в окне проверки'
                )

            candidates = [
                UniversityCandidate.from_dict(item)
                for item in (section.get('candidates') or [])
            ]
            result = await _apply_candidates(
                session,
                doc_id=_as_uuid(doc_id),
                university_uuid=target_university,
                candidates=candidates,
                overrides=overrides,
            )

            doc_row.updatedAt = datetime.now(timezone.utc)
            doc_row.status = states.DOCS_STATUS['approved']
            doc_row.meta = states.docs_metadata_with_section(
                document, states.confirmed_section(document, result)
            )
            return {'document': doc_to_dict(doc_row), 'result': result}


async def _resolve_university(session, document, section, overrides, explicit):
    """Определить целевой университет приказа (или ``None``).

    Приоритет: явный аргумент подтверждения → выбор администратора в
    ``selection`` → распознанный из шапки документа университет каталога с
    наилучшим совпадением. Возвращает UUID строки каталога.
    """
    chosen = explicit or overrides.get('university_id')
    if chosen:
        found = (
            await session.execute(
                select(Universities.id).where(
                    Universities.id == _as_uuid(chosen)
                )
            )
        ).scalar_one_or_none()
        if found is None:
            raise UniversityError('Выбранный университет не найден в каталоге')
        return found

    recognized = (section.get('university') or {}).get('matched_id')
    if not recognized:
        return None
    found = (
        await session.execute(
            select(Universities.id).where(Universities.id == _as_uuid(recognized))
        )
    ).scalar_one_or_none()
    if found is None:
        # Каталог изменился после прогона: распознанный вуз мог быть удалён.
        return None
    return found


async def _apply_candidates(
    session,
    *,
    doc_id,
    university_uuid,
    candidates: list[UniversityCandidate],
    overrides: dict,
) -> dict:
    """Записать связи по кандидатам, вернуть итоги.

    Каждый кандидат пишется в отдельном ``SAVEPOINT``: ошибка одной строки
    (например, гонка на уникальной паре) не должна откатывать остальные.
    """
    skips = set(overrides.get('skip') or [])
    links = dict(overrides.get('links') or {})
    linked = 0
    skipped = 0
    unmatched = 0
    errors: list[str] = []

    for candidate in candidates:
        if candidate.name_norm in skips:
            skipped += 1
            continue

        olympiad_id = candidate.olympiad_id or links.get(candidate.name_norm)
        if not olympiad_id:
            unmatched += 1
            continue

        try:
            async with session.begin_nested():
                await _upsert_link(
                    session,
                    university_uuid=university_uuid,
                    olympiad_id=olympiad_id,
                    doc_id=doc_id,
                    source_meta=candidate.meta,
                    candidate=candidate,
                )
            linked += 1
        except UniversityError:
            unmatched += 1
        except IntegrityError:
            # Гонка на уникальной паре: связь уже есть. Для импорта это
            # идемпотентный результат, а не ошибка строки.
            linked += 1
        except Exception as exc:  # noqa: BLE001 - одна строка не роняет импорт
            logger.exception(
                'university: failed to link candidate %s', candidate.name_norm
            )
            errors.append(f'{candidate.olympiad_name}: {_error_text(exc)}')

    return {
        'linked': linked,
        'skipped': skipped,
        'unmatched': unmatched,
        'errors': errors,
    }


async def _upsert_link(
    session,
    *,
    university_uuid,
    olympiad_id,
    doc_id,
    source_meta: dict,
    candidate: UniversityCandidate,
) -> None:
    """Создать связь ``PENDING`` либо обновить ``source_meta`` у существующей.

    Подтверждённая связь не трогается: повторный импорт не «разжаловывает»
    её и не переписывает историю модерации. У существующей заявки дополняется
    только происхождение (распознанные характеристики могли уточниться).
    """
    olympiad_uuid = _as_uuid(olympiad_id)
    exists = (
        await session.execute(
            select(Olympiads.id).where(Olympiads.id == olympiad_uuid)
        )
    ).scalar_one_or_none()
    if exists is None:
        # Олимпиада из выбора администратора не найдена в каталоге.
        raise UniversityError('Олимпиада не найдена в каталоге')

    link = (
        await session.execute(
            select(UniversityBvi).where(
                UniversityBvi.university_id == university_uuid,
                UniversityBvi.olympiad_id == olympiad_uuid,
            )
        )
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if link is None:
        payload_meta = dict(source_meta or {})
        payload_meta.setdefault('olympiad_name', candidate.olympiad_name)
        session.add(
            UniversityBvi(
                university_id=university_uuid,
                olympiad_id=olympiad_uuid,
                status='PENDING',
                source_doc_id=doc_id,
                source_meta=payload_meta,
                createdAt=now,
                updatedAt=now,
            )
        )
        return

    if link.status != 'PENDING':
        # Уже подтверждённая/иная связь: статус и автора не трогаем.
        return
    if link.source_doc_id is None:
        link.source_doc_id = doc_id
    merged_meta = dict(link.source_meta or {})
    merged_meta.update(source_meta or {})
    merged_meta.setdefault('olympiad_name', candidate.olympiad_name)
    link.source_meta = merged_meta
    link.updatedAt = now


def _error_text(exc: Exception) -> str:
    """Безопасный для показа текст ошибки строки (без внутренностей БД)."""
    text = str(exc)
    if '\\' in text or '/' in text or 'storage' in text.lower():
        return 'не удалось записать связь'
    return text


__all__ = [
    'STARTABLE_DOC_STATUSES',
    'UNIVERSITY_DOC_TYPE',
    'apply_confirmed_import',
    'claim_import_start',
    'claim_resume',
    'mark_import_failed_if_stuck',
    'reject_import',
    'request_pause',
    'save_import_selection',
    'write_import_state',
]
