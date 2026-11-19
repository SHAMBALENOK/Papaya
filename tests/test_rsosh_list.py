"""Официальный перечень: таблица, сводка, план и правки плана.

Здесь нет OCR: строки перечня заданы явно. Это проверки того, что конвейер
делает с уже распознанными данными — XLSX, сводка, сопоставление с каталогом,
правки плана и защита от повторного применения. Сам разбор скана проверяется
отдельно на реальных PDF (см. ``tests/test_rsosh_list_scan.py``).
"""

import openpyxl
import pytest

from app.rsosh import list_plan, list_xlsx
from app.rsosh.list_parser import ListRow, OfficialList


def _row(
    number='1',
    olympiad='Олимпиада имени Теста',
    organizer='Организатор',
    profile='профиль',
    subjects='математика',
    level='1',
    page=2,
    source_row=1,
):
    return ListRow(
        number=number,
        olympiad=olympiad,
        organizer=organizer,
        profile=profile,
        subjects=subjects,
        level=level,
        level_raw=level or '',
        page=page,
        source_row=source_row,
        source_band=1,
    )


def _parsed(rows=None, season='2026/2027', complete=True):
    return OfficialList(
        season_label=season,
        title='Перечень олимпиад школьников на 2026/27 учебный год',
        headers=list_plan_headers('укрупненные группы'),
        header_source='document',
        rows=rows or [_row()],
        complete=complete,
        source_pages=86,
        detected_tables=80,
    )


def list_plan_headers(e_variant):
    from app.rsosh import list_parser

    headers = [
        list_parser._HEADER_A,
        list_parser._HEADER_B,
        list_parser._HEADER_C,
        list_parser._HEADER_D,
        None,
        list_parser._HEADER_F,
    ]
    if 'укрупнен' in e_variant:
        headers[4] = list_parser._HEADER_E_VARIANTS[2]
    else:
        headers[4] = list_parser._HEADER_E_VARIANTS[0]
    return headers


# ------------------------------------------------------------------ XLSX


def test_workbook_has_official_sheets_and_styles(tmp_path):
    parsed = _parsed()
    path = list_xlsx.save(parsed, tmp_path / 'list.xlsx')
    workbook = openpyxl.load_workbook(path)

    assert workbook.sheetnames == ['Перечень 2026-27', 'Сводка']
    sheet = workbook['Перечень 2026-27']

    # Шапка: официальная формулировка, тёмная заливка, белый жирный текст.
    assert sheet['A1'].value == '№ п/п'
    assert sheet['E1'].value.startswith('Общеобразовательные предметы')
    assert 'укрупненные группы' in sheet['E1'].value
    assert sheet['A1'].fill.fgColor.rgb == '001F4E78'
    assert sheet['A1'].font.bold is True
    assert sheet['A1'].font.color.rgb == '00FFFFFF'
    assert sheet['A1'].alignment.wrap_text is True
    assert sheet['A1'].border.left.style == 'thin'

    # Ширины, закрепление шапки и автофильтр.
    widths = {column: sheet.column_dimensions[column].width for column in 'ABCDEF'}
    assert widths == {'A': 7, 'B': 48, 'C': 75, 'D': 34, 'E': 60, 'F': 11}
    assert sheet.freeze_panes == 'A2'
    assert sheet.auto_filter.ref == 'A1:F2'

    # Данные: уровень римскими, номер числом, высота строки по содержимому.
    assert sheet['A2'].value == 1
    assert sheet['F2'].value == 'I'
    assert sheet.row_dimensions[2].height > 0


def test_summary_aggregates_profiles_and_levels():
    rows = [
        _row(number='1', olympiad='Первая', profile='профиль А', level='2'),
        _row(number='1', olympiad='Первая', profile='профиль Б', level='3'),
        _row(number='2', olympiad='Вторая', profile='профиль В', level='1'),
    ]
    summary = list_xlsx.summary(rows)

    assert [item.olympiad for item in summary] == ['Первая', 'Вторая']
    assert summary[0].profiles == 2
    assert summary[0].levels == 'II×1, III×1'
    assert summary[1].profiles == 1
    assert summary[1].levels == 'I×1'


def test_summary_sheet_matches_list_sheet(tmp_path):
    rows = [
        _row(number='7', olympiad='Одна', profile='А', level='3'),
        _row(number='7', olympiad='Одна', profile='Б', level='3'),
    ]
    parsed = _parsed(rows)
    path = list_xlsx.save(parsed, tmp_path / 'list.xlsx')
    workbook = openpyxl.load_workbook(path)
    summary = workbook['Сводка']

    assert [summary.cell(row=1, column=c).value for c in range(1, 5)] == [
        '№', 'Олимпиада', 'Профилей', 'Уровни'
    ]
    assert summary['A2'].value == 7
    assert summary['B2'].value == 'Одна'
    assert summary['C2'].value == 2
    assert summary['D2'].value == 'III×2'
    assert summary.freeze_panes == 'A2'


def test_html_table_contains_all_rows(tmp_path):
    rows = [_row(profile='рисунок, живопись'), _row(profile='экономика')]
    parsed = _parsed(rows)
    text = list_xlsx.render_html(parsed)

    assert '<table>' in text
    assert '№ п/п' in text
    assert 'рисунок, живопись' in text
    assert 'Сводка' in text
    assert '2026/2027' in text
    # Разметка не ломается значениями из документа.
    parsed.rows[0].profile = '<script>alert(1)</script>'
    assert '<script>alert(1)</script>' not in list_xlsx.render_html(parsed)


def test_sheet_title_uses_hyphenated_season():
    assert list_xlsx.sheet_title('2026/2027') == 'Перечень 2026-27'
    assert list_xlsx.sheet_title(None) == 'Перечень'


# ------------------------------------------------------------------ план


class _Catalog(list_plan.Catalog):
    """Снимок каталога для тестов: тот же тип, что строит ``load_catalog``."""


def _catalog(olympiads=None, seasons=None):
    items = olympiads or []
    by_norm = {item['name_norm']: item for item in items}
    return list_plan.Catalog(
        olympiads=items,
        by_norm=by_norm,
        seasons=seasons or {},
    )


def _catalog_item(name, name_norm=None, status='PUBLISHED', olympiad_id='11111111-1111-1111-1111-111111111111'):
    return {
        'id': olympiad_id,
        'name': name,
        'name_norm': name_norm or list_plan.normalize_name(name),
        'status': status,
        'archive_reason': None,
        'organizer': None,
    }


def test_plan_creates_new_olympiad_and_profiles():
    parsed = _parsed()
    plan = list_plan.build_plan(parsed, doc_id='doc', catalog=_catalog())

    assert plan['season_label'] == '2026/2027'
    assert len(plan['olympiads']) == 1
    item = plan['olympiads'][0]
    assert item['match']['action'] == 'create'
    assert item['profiles'][0]['match']['action'] == 'create'
    assert plan['summary']['create'] == 1
    assert plan['summary']['profiles_create'] == 1
    assert plan['errors'] == []


def test_plan_uses_existing_olympiad_and_updates_level():
    name = 'Олимпиада имени Теста'
    norm = list_plan.normalize_name(name)
    catalog = _catalog(
        [_catalog_item(name)],
        seasons={
            '11111111-1111-1111-1111-111111111111': [
                {
                    'id': '22222222-2222-2222-2222-222222222222',
                    'season_label': '2026/2027',
                    'is_archived': False,
                    'profiles': [
                        {
                            'id': '33333333-3333-3333-3333-333333333333',
                            'name': 'профиль',
                            'name_norm': 'профиль',
                            'rsosh_level': '2',
                        }
                    ],
                }
            ]
        },
    )
    plan = list_plan.build_plan(_parsed(), doc_id='doc', catalog=catalog)
    item = plan['olympiads'][0]
    profile = item['profiles'][0]

    assert item['name_norm'] == norm
    assert item['match']['action'] == 'use'
    assert item['season']['action'] == 'use'
    assert profile['match']['action'] == 'update'
    assert profile['level_change'] == {'from': '2', 'to': '1'}
    assert plan['summary']['profiles_update'] == 1


def test_plan_marks_similar_names_for_review_not_merge():
    parsed = _parsed(rows=[_row(olympiad='Олимпиада имени Теста 2026')])
    catalog = _catalog([_catalog_item('Олимпиада имени Теста')])
    plan = list_plan.build_plan(parsed, doc_id='doc', catalog=catalog)

    item = plan['olympiads'][0]
    assert item['match']['action'] == 'review'
    assert item['match']['olympiad_id'] is None
    assert item['match']['candidates']
    assert plan['summary']['review'] == 1
    assert any('похожие записи' in warning for warning in plan['warnings'])


def test_missing_only_when_list_is_complete():
    catalog = _catalog(
        [_catalog_item('Исчезнувшая', olympiad_id='44444444-4444-4444-4444-444444444444')],
        seasons={
            '44444444-4444-4444-4444-444444444444': [
                {
                    'id': '55555555-5555-5555-5555-555555555555',
                    'season_label': '2026/2027',
                    'is_archived': False,
                    'profiles': [],
                }
            ]
        },
    )
    complete = list_plan.build_plan(_parsed(), doc_id='doc', catalog=catalog)
    assert complete['missing_allowed'] is True
    assert [item['name'] for item in complete['missing']] == ['Исчезнувшая']

    partial = list_plan.build_plan(
        _parsed(complete=False), doc_id='doc', catalog=catalog
    )
    assert partial['missing_allowed'] is False
    assert partial['missing'] == []
    assert any('не фиксируется' in warning for warning in partial['warnings'])


def test_unrecognized_profile_blocks_apply():
    parsed = _parsed(rows=[_row(profile='', level=None)])
    plan = list_plan.build_plan(parsed, doc_id='doc', catalog=_catalog())

    assert plan['errors']
    assert plan['missing_allowed'] is False


def test_apply_changes_selects_existing_olympiad():
    parsed = _parsed(rows=[_row(olympiad='Олимпиада имени Теста 2026')])
    catalog = _catalog([_catalog_item('Олимпиада имени Теста')])
    plan = list_plan.build_plan(parsed, doc_id='doc', catalog=catalog)
    norm = plan['olympiads'][0]['name_norm']

    updated = list_plan.apply_changes(
        plan,
        {
            'olympiads': [
                {
                    'name_norm': norm,
                    'action': 'use',
                    'olympiad_id': '11111111-1111-1111-1111-111111111111',
                }
            ]
        },
    )
    item = updated['olympiads'][0]
    assert item['match']['action'] == 'use'
    assert item['match']['confidence'] == 'manual'
    assert updated['errors'] == []
    assert updated['summary']['use'] == 1


def test_apply_changes_rejects_unknown_olympiad():
    plan = list_plan.build_plan(_parsed(), doc_id='doc', catalog=_catalog())
    with pytest.raises(ValueError):
        list_plan.apply_changes(
            plan, {'olympiads': [{'name_norm': 'нет такой', 'action': 'skip'}]}
        )


def test_apply_changes_allows_explicit_skip_of_unreadable_row():
    """Нераспознанную строку нельзя пропустить молча, но можно — вручную."""
    parsed = _parsed(rows=[_row(profile='', level=None)])
    plan = list_plan.build_plan(parsed, doc_id='doc', catalog=_catalog())
    assert plan['errors']

    updated = list_plan.apply_changes(
        plan,
        {
            'profiles': [
                {
                    'olympiad': plan['olympiads'][0]['name_norm'],
                    'source_row': 1,
                    'action': 'skip',
                }
            ]
        },
    )
    assert updated['errors'] == []
    assert updated['missing_allowed'] is True
    assert updated['summary']['profiles_skip'] == 1


def test_apply_changes_fixes_profile_name_and_level():
    parsed = _parsed(rows=[_row(profile='', level=None)])
    plan = list_plan.build_plan(parsed, doc_id='doc', catalog=_catalog())
    assert plan['errors']

    updated = list_plan.apply_changes(
        plan,
        {
            'profiles': [
                {
                    'olympiad': plan['olympiads'][0]['name_norm'],
                    'source_row': 1,
                    'name': 'инфохимия',
                    'level': '3',
                }
            ]
        },
    )
    profile = updated['olympiads'][0]['profiles'][0]
    assert profile['name'] == 'инфохимия'
    assert profile['level'] == '3'
    assert updated['errors'] == []
    assert updated['missing_allowed'] is True


def test_apply_changes_rejects_bad_level():
    plan = list_plan.build_plan(_parsed(), doc_id='doc', catalog=_catalog())
    with pytest.raises(ValueError):
        list_plan.apply_changes(
            plan,
            {
                'profiles': [
                    {
                        'olympiad': plan['olympiads'][0]['name_norm'],
                        'source_row': 1,
                        'level': 'IV',
                    }
                ]
            },
        )


def test_apply_changes_recomputes_missing():
    catalog = _catalog(
        [_catalog_item('Исчезнувшая', olympiad_id='44444444-4444-4444-4444-444444444444')],
        seasons={
            '44444444-4444-4444-4444-444444444444': [
                {
                    'id': '55555555-5555-5555-5555-555555555555',
                    'season_label': '2026/2027',
                    'is_archived': False,
                    'profiles': [],
                }
            ]
        },
    )
    plan = list_plan.build_plan(_parsed(), doc_id='doc', catalog=catalog)
    assert plan['summary']['missing'] == 1

    # Администратор решил, что строка документа — это та самая олимпиада.
    updated = list_plan.apply_changes(
        plan,
        {
            'olympiads': [
                {
                    'name_norm': plan['olympiads'][0]['name_norm'],
                    'action': 'use',
                    'olympiad_id': '44444444-4444-4444-4444-444444444444',
                }
            ]
        },
    )
    assert updated['summary']['missing'] == 0
    assert updated['missing'] == []


def test_plan_error_blocks_unresolved_rows():
    from app.rsosh.list_apply import _plan_error

    plan = list_plan.build_plan(
        _parsed(rows=[_row(olympiad='Олимпиада имени Теста 2026')]),
        doc_id='doc',
        catalog=_catalog([_catalog_item('Олимпиада имени Теста')]),
    )
    assert 'не выбрано существующее совпадение' in _plan_error(plan)

    plan['olympiads'][0]['match'] = {'action': 'create', 'olympiad_id': None}
    assert _plan_error(plan) is None


def test_detection_ignores_non_pdf(tmp_path):
    from app.rsosh import list_processor

    path = tmp_path / 'list.xlsx'
    path.write_bytes(b'PK\x03\x04')
    result = list_processor.detect_official_list(path)
    assert result['official'] is False
    assert 'PDF' in result['reason']


def test_name_starter_recognizes_new_olympiad_without_number():
    """Заглавное начало названия — признак новой записи, а не продолжения.

    Номер строки на границе страницы иногда не распознаётся. Тогда строку
    начинает заголовок («Отраслевая…»), а продолжение названия начинается со
    строчного слова («интеллекту…»). Это решение по тексту, без OCR.
    """
    from app.rsosh.list_parser import _starts_new_olympiad

    assert _starts_new_olympiad('Отраслевая олимпиада школьников «Газпром»')
    assert _starts_new_olympiad('XIX Южно-Российская олимпиада')
    assert not _starts_new_olympiad(
        'интеллекту (с возможностью участия иностранных обучающихся)'
    )
    assert not _starts_new_olympiad('школьников «Газпром»')
    # Продолжение, начинающееся со строчного слова, не путается с заголовком.
    assert not _starts_new_olympiad('межрегиональная олимпиада школьников')


def test_out_of_order_number_is_flagged_not_guessed():
    """Повтор или шаг назад по номерам — повод предупредить, а не исправить."""
    from app.rsosh.list_parser import _number_is_out_of_order

    assert _number_is_out_of_order('19', 18) is False
    assert _number_is_out_of_order('19', 19) is True
    assert _number_is_out_of_order('12', 19) is True
    assert _number_is_out_of_order('1', None) is False
