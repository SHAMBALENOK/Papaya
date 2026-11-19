"""Разбор настоящих сканов перечня (необязательный тест).

Официальные PDF — это сканы по 86–200 страниц, и полный разбор идёт минуты.
Поэтому тест включается переменной окружения ``RSOSH_DATASET_DIR`` (каталог с
``original/17-18.pdf`` и ``table/17-18.xlsx``) и читает только первые страницы:
он проверяет сезон, шапку и несколько первых строк, а не весь документ.
"""

import os
from pathlib import Path

import pytest

from app.rsosh import list_parser

DATASET = os.environ.get('RSOSH_DATASET_DIR')
pytestmark = pytest.mark.skipif(
    not DATASET or not Path(DATASET).is_dir(),
    reason='RSOSH_DATASET_DIR не задан: сканы РСОШ не проверяются',
)


def _parse(year: str, pages: int):
    path = Path(DATASET) / 'original' / f'{year}.pdf'
    assert path.is_file(), path
    return list_parser.parse_official_list(str(path), max_pages=pages)


def test_old_edition_header_and_first_profiles():
    """Перечень 2017/18: старая формулировка колонки E и первые профили."""
    parsed = _parse('17-18', 6)

    assert parsed.season_label == '2017/2018'
    assert parsed.headers[0] == '№ п/п'
    assert 'специальность' in parsed.headers[4]
    assert parsed.header_source in ('document', 'inferred')

    first = [(row.profile, row.level) for row in parsed.rows[:6]]
    assert first[:3] == [
        ('литература', '3'),
        ('обществознание', '3'),
        ('литература', '3'),
    ]
    assert all(row.olympiad for row in parsed.rows)
    assert all(row.page for row in parsed.rows)


def test_new_edition_header_and_first_profiles():
    """Перечень 2026/27: укрупнённые группы и римские уровни."""
    parsed = _parse('26-27', 9)

    assert parsed.season_label == '2026/2027'
    assert 'укрупненные группы' in parsed.headers[4]

    first = [(row.profile, row.level) for row in parsed.rows[:4]]
    assert first[0] == ('рисунок, живопись, композиция, черчение', '1')
    assert first[1] == ('гуманитарные и социальные науки', '1')
    assert first[2] == ('экономика', '1')
    assert first[3][0] == 'автоматизация бизнес-процессов'
    assert first[3][1] == '2'


def _norm(value) -> str:
    text = str(value or '')
    for source, target in (
        ('\u201c', '\u00ab'), ('\u201d', '\u00bb'), ('\u201e', '\u00ab'),
        ('\u2013', '-'), ('\u2014', '-'), ('\u2212', '-'),
    ):
        text = text.replace(source, target)
    text = ''.join(ch for ch in text if ch not in '\u00ab\u00bb"\'`')
    return ' '.join(text.split()).strip().casefold()


def test_landscape_spread_page_is_read_upright(tmp_path):
    """Альбомная таблица внутри книжного скана не переворачивается.

    Страница 13 перечня 2026/27 — разворот альбомной таблицы: линии рамки
    дают больше вертикалей, чем горизонталей, и прежняя эвристика
    переворачивала её на 180°. Строка № 4 при этом терялась.
    """
    parsed = _parse('26-27', 13)
    rows = [
        row for row in parsed.rows
        if row.number == '4'
        and row.olympiad.startswith('Всероссийская олимпиада по агрогенетике')
    ]
    assert rows, 'строка № 4 альбомного разворота не прочитана'
    assert rows[0].profile
    assert rows[0].level == '1'

    # Сверка с эталоном по содержанию: шапка, листы и первые строки
    # (номер, название, профиль, уровень). Организатор и предметы в скане
    # теряют буквы, поэтому сверяются в отчёте отдельно.
    import openpyxl

    from app.rsosh import list_xlsx

    generated_path = list_xlsx.save(parsed, tmp_path / 'list.xlsx')
    generated = openpyxl.load_workbook(generated_path)
    reference = openpyxl.load_workbook(
        Path(DATASET) / 'table' / '26-27.xlsx'
    )
    assert generated.sheetnames == reference.sheetnames

    for column in range(1, 7):
        assert _norm(generated.worksheets[0].cell(row=1, column=column).value) == (
            _norm(reference.worksheets[0].cell(row=1, column=column).value)
        )

    reference_rows = reference.worksheets[0]
    for index, row in enumerate(parsed.rows, start=2):
        # Название № 5 обрывается на границе страницы («искусственном» без
        # «у»), поэтому сверяем строки № 1–4: они прочитаны полностью.
        if row.number == '5':
            break
        actual = [
            row.number, row.olympiad, row.profile,
            {'1': 'I', '2': 'II', '3': 'III'}.get(row.level, row.level),
        ]
        expected = [
            reference_rows.cell(row=index, column=1).value,
            reference_rows.cell(row=index, column=2).value,
            reference_rows.cell(row=index, column=4).value,
            reference_rows.cell(row=index, column=6).value,
        ]
        assert [_norm(value) for value in actual] == [
            _norm(value) for value in expected
        ], f'row {index}'
