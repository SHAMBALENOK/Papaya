"""Применение плана официального перечня: каталог, откат, отсутствие, права.

Разбор скана здесь не участвует: план строится по уже распознанным строкам,
поэтому тесты проверяют именно то, что нельзя проверить на «чистых» модулях —
одну транзакцию на весь перечень, запрет повторного применения, фиксацию
отсутствия и разграничение доступа.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.database import AsyncSessionLocal
from app.database.search import normalize_name
from app.models.olympiads import Olympiads
from app.models.seasons import OlympiadSeason
from app.rsosh import list_plan, persist, states
from app.rsosh.list_parser import ListRow, OfficialList
from tests.conftest import admin_client, register_user, upload_document
from tests.rsosh_fixtures import broken_pdf_bytes


def _row(
    number='1',
    olympiad='Олимпиада имени Теста',
    profile='профиль',
    level='1',
    page=2,
):
    return ListRow(
        number=number,
        olympiad=olympiad,
        organizer='Организатор',
        profile=profile,
        subjects='математика',
        level=level,
        level_raw=level,
        page=page,
        source_row=1,
        source_band=1,
    )


def _parsed(rows, season='2026/2027', complete=True):
    return OfficialList(
        season_label=season,
        title=f'Перечень олимпиад школьников на {season} учебный год',
        headers=['№ п/п', 'Полное наименование олимпиады', 'Организатор',
                 'Профиль олимпиады', 'Предметы', 'Уровень олимпиады'],
        header_source='document',
        rows=rows,
        complete=complete,
        source_pages=86,
        detected_tables=80,
    )


async def _review_doc(test_client, rows, *, season='2026/2027', complete=True):
    """Загрузить документ и сохранить план так, как это делает конвейер."""
    await admin_client(test_client)
    uploaded = await upload_document(
        test_client, 'perechen.pdf', broken_pdf_bytes()
    )
    from app import database

    doc = await database.docs.get_doc(uploaded['id'])
    catalog = await list_plan.load_catalog()
    plan = list_plan.build_plan(
        _parsed(rows, season=season, complete=complete),
        doc_id=doc['id'],
        catalog=catalog,
    )
    section = states.list_review_section(
        doc,
        plan=plan,
        pages=[],
        warnings=[],
        summary=plan['summary'],
        table_doc_id=None,
        html_doc_id=None,
        title=plan['title'],
    )
    assert await persist.write_import_state(doc['id'], section) is not None
    return doc


async def _olympiads():
    """Все олимпиады каталога как простые словари (для проверок после apply)."""
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(Olympiads).order_by(Olympiads.name)
        )).scalars().all()
        return [
            {
                'id': str(row.id),
                'name': row.name,
                'status': row.status,
                'archive_reason': row.archive_reason,
            }
            for row in rows
        ]


async def _levels(name, season_label='2026/2027'):
    """Профили сезона: ``{нормализованное имя: уровень или None}``."""
    async with AsyncSessionLocal() as session:
        olympiad = (
            await session.execute(
                select(Olympiads).where(
                    Olympiads.name_norm == normalize_name(name)
                )
            )
        ).scalar_one_or_none()
        if olympiad is None:
            return None
        season = (
            await session.execute(
                select(OlympiadSeason)
                .where(
                    OlympiadSeason.olympiad_id == olympiad.id,
                    OlympiadSeason.season_label == season_label,
                )
                .options(selectinload(OlympiadSeason.profiles))
            )
        ).scalar_one_or_none()
        if season is None:
            return None
        return {profile.name_norm: profile.rsosh_level for profile in season.profiles}


async def test_apply_creates_catalog_and_forbids_second_apply(client):
    """Один перечень — одна запись в каталоге и один сезон."""
    doc = await _review_doc(client, [
        _row(number='1', olympiad='Олимпиада имени Теста', profile='профиль А',
             level='1'),
        _row(number='1', olympiad='Олимпиада имени Теста', profile='профиль Б',
             level='3'),
    ])

    response = await client.post(f"/api/v1/imports/{doc['id']}/apply")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['result']['created'] == 1
    assert body['result']['profiles_created'] == 2
    assert body['import']['state'] == 'approved'

    olympiads = await _olympiads()
    assert [item['name'] for item in olympiads] == ['Олимпиада имени Теста']
    assert olympiads[0]['status'] == 'PUBLISHED'
    assert await _levels('Олимпиада имени Теста') == {
        normalize_name('профиль А'): '1',
        normalize_name('профиль Б'): '3',
    }
    assert any(
        item['action'] == 'olympiad_created' for item in body['history']
    )

    # Повторное применение — конфликт, а не дубликат.
    again = await client.post(f"/api/v1/imports/{doc['id']}/apply")
    assert again.status_code == 409
    assert len(await _olympiads()) == 1

    # Прежний «confirm» на официальном перечне не работает.
    legacy = await client.post(f"/api/v1/imports/{doc['id']}/confirm")
    assert legacy.status_code == 409


async def test_apply_rolls_back_on_later_failure(client):
    """Ошибка в конце плана не оставляет половину перечня в каталоге."""
    doc = await _review_doc(client, [
        _row(number='1', olympiad='Первая олимпиада', profile='профиль А'),
        _row(number='2', olympiad='Вторая олимпиада', profile='профиль Б'),
    ])

    # Второй пункт ссылается на несуществующую запись каталога: первая уже
    # создана и сброшена в БД, поэтому без транзакции она бы осталась.
    patched = await client.patch(
        f"/api/v1/imports/{doc['id']}/plan",
        json={
            'olympiads': [{
                'name_norm': normalize_name('Вторая олимпиада'),
                'action': 'use',
                'olympiad_id': str(uuid.uuid4()),
            }],
        },
    )
    assert patched.status_code == 200, patched.text

    response = await client.post(f"/api/v1/imports/{doc['id']}/apply")
    assert response.status_code == 400, response.text

    assert await _olympiads() == []
    # План не «сгорел»: после исправления его можно применить.
    fixed = (await client.get(f"/api/v1/imports/{doc['id']}/plan")).json()['plan']
    assert fixed['olympiads'][0]['match']['action'] == 'create'


async def test_mark_missing_records_absence_without_deleting(client):
    """Отсутствие фиксируется уровнями и архивом, но записи не удаляются."""
    first = await _review_doc(client, [
        _row(number='1', olympiad='Первая олимпиада', profile='профиль А',
             level='2'),
        _row(number='2', olympiad='Пропавшая олимпиада', profile='профиль Б',
             level='3'),
    ])
    assert (await client.post(
        f"/api/v1/imports/{first['id']}/apply"
    )).status_code == 200

    second = await _review_doc(client, [
        _row(number='1', olympiad='Первая олимпиада', profile='профиль В',
             level='1'),
    ])
    plan = (await client.get(f"/api/v1/imports/{second['id']}/plan")).json()['plan']
    # Перечень полный, поэтому отсутствие доказуемо и разрешено к фиксации.
    assert plan['missing_allowed'] is True
    assert [item['name'] for item in plan['missing']] == ['Пропавшая олимпиада']

    response = await client.post(
        f"/api/v1/imports/{second['id']}/apply",
        json={'mark_missing': True},
    )
    assert response.status_code == 200, response.text

    olympiads = {item['name']: item for item in await _olympiads()}
    assert set(olympiads) == {'Первая олимпиада', 'Пропавшая олимпиада'}
    assert olympiads['Пропавшая олимпиада']['status'] == 'ARCHIVED'
    assert olympiads['Пропавшая олимпиада']['archive_reason'] == 'RSOSH_ABSENT'

    # Уровень профиля, которого нет в перечне, снят, но профиль остался.
    levels = await _levels('Первая олимпиада')
    assert levels[normalize_name('профиль А')] is None
    assert levels[normalize_name('профиль В')] == '1'

    history = response.json()['history']
    actions = {item['action'] for item in history}
    assert 'profile_absent' in actions
    assert 'olympiad_absent' in actions


async def test_only_admin_can_review_and_apply_plan(client):
    """План и применение — административные операции."""
    doc = await _review_doc(client, [_row()])
    await register_user(client)

    assert (await client.get(f"/api/v1/imports/{doc['id']}/plan")).status_code == 403
    assert (await client.patch(
        f"/api/v1/imports/{doc['id']}/plan", json={'olympiads': []}
    )).status_code == 403
    assert (await client.post(
        f"/api/v1/imports/{doc['id']}/apply"
    )).status_code == 403
    assert await _olympiads() == []


@pytest.mark.parametrize('season', ['2025/2026', '2026/2027'])
async def test_season_comes_from_document(client, season):
    """Сезон берётся из перечня, а не из года запуска импорта."""
    doc = await _review_doc(client, [_row()], season=season)
    response = await client.post(f"/api/v1/imports/{doc['id']}/apply")
    assert response.status_code == 200, response.text

    async with AsyncSessionLocal() as session:
        seasons = (await session.execute(
            select(OlympiadSeason)
        )).scalars().all()
        assert [item.season_label for item in seasons] == [season]


async def test_reimport_reuses_table_and_html_documents(client, monkeypatch):
    """Повторный разбор того же документа не плодит копии XLSX/HTML и плана."""
    from app import database
    from app.rsosh import list_processor

    await admin_client(client)
    uploaded = await upload_document(
        client, 'perechen.pdf', broken_pdf_bytes()
    )
    parsed = _parsed([_row()])
    monkeypatch.setattr(
        list_processor,
        'detect_official_list',
        lambda path: {
            'official': True,
            'reason': 'тест',
            'season_label': parsed.season_label,
            'tables': parsed.detected_tables,
            'rows': len(parsed.rows),
        },
    )
    monkeypatch.setattr(
        'app.rsosh.list_parser.parse_official_list',
        lambda path: parsed,
    )

    first = await list_processor.run_list_import(uploaded['id'])
    second = await list_processor.run_list_import(uploaded['id'])
    assert first is not None and second is not None
    first_section = states.rsosh_section(first)
    second_section = states.rsosh_section(second)
    assert first_section['table']['doc_id'] == second_section['table']['doc_id']
    assert first_section['html']['doc_id'] == second_section['html']['doc_id']
    assert second_section['plan']['season_label'] == '2026/2027'

    docs = await database.docs.list_docs(limit=None)
    by_type: dict[str, list[dict]] = {}
    for doc in docs:
        by_type.setdefault(doc['type'], []).append(doc)
    assert len(by_type.get('RSOSH_LIST', [])) == 1
    assert len(by_type.get('RSOSH_TABLE', [])) == 1
    assert len(by_type.get('RSOSH_HTML', [])) == 1
