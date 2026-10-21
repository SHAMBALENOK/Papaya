"""Разбор приказа университета: строки, характеристики строки, вуз.

Проверяется то, что молча ломается на реальном приказе ИТМО: шапка бумаги
принималась за олимпиаду, а сам приказ — за мусор; перенос шапки таблицы на
вторую страницу терял всю страницу; объединённая колонка направления пропадала;
«Предмет (подтверждающий)» путал предмет с дипломом. Здесь нет базы и нет OCR —
чистый разбор коротких таблиц, повторяющих раскладку приказа.
"""

from pathlib import Path

from app.rsosh.extraction import PageTables
from app.university import parsing
from app.university.parsing import parse_pages
from tests.university_fixtures import (
    LETTERHEAD,
    ORDER_HEADER,
    letterhead_page,
    order_row,
    page,
    reverse,
)


#: Строка-наполнитель: реальный приказ состоит из множества строк, а таблица
#: признаётся приказом только при достаточном числе строк (``MIN_TABLE_ROWS``).
#: Она не мешает проверкам, потому что в них ищется нужная строка, а не их число.
FILLER = order_row(direction='01.03.02', name='Олимпиада-наполнитель')


def _single_page(rows, *, header=None):
    """Страница приказа: шапка письма + таблица с шапкой и строками."""
    body = [*rows, FILLER]
    tables = [list(LETTERHEAD), [header or list(ORDER_HEADER), *body]]
    return [page(1, tables)]


def test_letterhead_is_not_taken_for_an_order_row():
    """Шапка письма (министерство + вуз) не становится строкой приказа."""
    records, warnings, university = parse_pages(
        _single_page([order_row(direction='01.03.02', name='Олимпиада «Ломоносов»')])
    )
    assert 'Олимпиада «Ломоносов»' in {r.olympiad_name for r in records}
    assert university['name'] == 'Университет ИТМО'


def test_header_memory_carries_layout_to_next_page():
    """Шапка печатается один раз: без памяти о ней вторая страница пуста.

    На реальном приказе шапка есть только на первой странице. Если её не
    запомнить по ширине таблицы, таблица второй страницы выглядела бы «без
    шапки» и пропускалась целиком — терялась бы половина приказа.
    """
    pages = [
        letterhead_page(
            1,
            [[list(ORDER_HEADER), order_row(direction='01.03.02', name='Первая олимпиада'), FILLER]],
        ),
        # Вторая страница: таблица той же ширины, но без шапки.
        page(2, [[order_row(direction='01.03.02', name='Вторая олимпиада'), FILLER]]),
    ]
    records, _warnings, _uni = parse_pages(pages)
    names = {r.olympiad_name for r in records}
    assert names == {'Первая олимпиада', 'Вторая олимпиада'}


def test_repeated_header_row_on_next_page_is_skipped():
    """Повтор шапки на второй странице не превращается в строку приказа."""
    pages = [
        letterhead_page(1, [[list(ORDER_HEADER), order_row(direction='01.03.02', name='Олимпиада A'), FILLER]]),
        page(2, [[list(ORDER_HEADER), order_row(direction='01.03.02', name='Олимпиада B'), FILLER]]),
    ]
    records, _warnings, _uni = parse_pages(pages)
    assert {r.olympiad_name for r in records} == {'Олимпиада A', 'Олимпиада B'}


def test_merged_direction_column_is_propagated_down():
    """Объединённая колонка направления раздаётся вниз по группе строк.

    В приказе направление стоит только в первой строке группы, а олимпиад под
    ним несколько. Без раздачи вниз характеристика была бы только у первой
    строки, и остальные связи потеряли бы направление.
    """
    rows = [
        order_row(direction='01.03.02 Прикладная математика', name='Олимпиада A'),
        order_row(direction='', name='Олимпиада B'),
        order_row(direction='', name='Олимпиада C'),
    ]
    records, _warnings, _uni = parse_pages(_single_page(rows))
    group = [r for r in records if r.olympiad_name.startswith('Олимпиада ')]
    assert len(group) == 3
    assert all(
        r.meta.get('direction') == '01.03.02 Прикладная математика'
        for r in group
    )


def test_subject_column_is_not_taken_for_diploma():
    """«Предмет (подтверждающий)» — предмет, а рядом «Диплом» — диплом.

    Заголовок предмета содержит слово «подтверждающий», а диплома — «победител»
    в значениях; нечёткое совпадение маркеров раньше отдавало обе роли одной
    колонке. Разные роли должны достаться разным колонкам.
    """
    records, _warnings, _uni = parse_pages(
        _single_page([
            order_row(
                direction='01.03.02',
                name='Олимпиада A',
                profile='Информатика',
                subject='Информатика',
                level='1',
                diploma='Победитель или призер',
            )
        ])
    )
    meta = records[0].meta
    assert meta['subject'] == 'Информатика'
    assert meta['diploma'] == 'Победитель или призер'
    assert meta['profile'] == 'Информатика'
    assert meta['level'] == '1'


def test_mirrored_header_is_read():
    """Зеркальная шапка приказа распознаётся.

    Часть приказов печатает шапку зеркально («еинелварпаН иквотогдоп»). Ячейка
    разворачивается по маркерам шапки, но университетские заголовки в словарь
    реверса не входят, поэтому колонки ищутся сразу в двух прочтениях.
    """
    mirrored = [reverse(cell) for cell in ORDER_HEADER]
    records, _warnings, _uni = parse_pages(_single_page(
        [order_row(direction='01.03.02', name='Олимпиада A')],
        header=mirrored,
    ))
    target = next(r for r in records if r.olympiad_name == 'Олимпиада A')
    assert target.meta.get('profile') == 'Информатика'


def test_rows_without_olympiad_word_are_flagged():
    """Строка без слова «олимпиада» сохраняется, но помечается для проверки."""
    records, _warnings, _uni = parse_pages(
        _single_page([
            order_row(direction='01.03.02', name='Турнир имени М.В. Ломоносова'),
        ])
    )
    target = next(
        r for r in records if r.olympiad_name == 'Турнир имени М.В. Ломоносова'
    )
    assert any('олимпиад' in issue for issue in target.issues)


def test_university_not_taken_from_olympiad_name():
    """Вузом не становится название олимпиады с «университета» в тексте.

    В таблице приказа «университет» встречается в названиях олимпиад
    («… Уральского федерального университета»). Реквизиты вуза берутся только
    из короткой шапки письма, иначе вузом становилась бы олимпиада.
    """
    rows = [
        order_row(
            direction='01.03.02',
            name='Олимпиада Уральского федерального университета «Изумруд»',
        )
    ]
    _records, _warnings, university = parse_pages(_single_page(rows))
    assert university['name'] == 'Университет ИТМО'


def test_duplicate_olympiad_across_directions_is_reported_once():
    """Повтор олимпиады под разными направлениями сообщается предупреждением."""
    rows = [
        order_row(direction='01.03.02', name='Олимпиада «Ломоносов»'),
        order_row(direction='', name='Олимпиада «Ломоносов»'),
    ]
    records, warnings, _uni = parse_pages(_single_page(rows))
    duplicates = [r for r in records if r.olympiad_name == 'Олимпиада «Ломоносов»']
    assert len(duplicates) == 2
    assert any('несколько раз' in w for w in warnings)


def test_plausible_name_rejects_boilerplate():
    """Министерство/шапка письма не проходят как имя олимпиады."""
    assert parsing._plausible_name('Министерство науки') is None
    assert parsing._plausible_name('') is None
    assert parsing._plausible_name('Олимпиада «Высшая проба»') is not None


REAL_ORDER_PDF = (
    Path(__file__).resolve().parents[1]
    / 'app'
    / 'tables'
    / 'rsosh_bvi'
    / 'rsosh_bvi.pdf'
)


def test_real_itmo_order_pdf():
    """Реальный приказ ИТМО: строки, вуз и характеристики распознаются.

    Проверка идёт по text layer PDF (без OCR), поэтому стабильна. Приказ
    содержит несколько десятков строк и повторов олимпиад под разными
    направлениями; проверяем ключевые факты, а не точное число.
    """
    from app.rsosh.extraction import extract_document

    pages = extract_document(str(REAL_ORDER_PDF))
    records, _warnings, university = parse_pages(pages)

    assert len(records) >= 30
    assert university['name'] == 'Университет ИТМО'

    names = {r.olympiad_name for r in records}
    assert 'Всероссийская олимпиада школьников «Высшая проба»' in names
    assert 'Московская олимпиада школьников' in names

    # Характеристики строки распознаны (на реальном приказе ИТМО шапка полная):
    # на первой странице направление объединено и раздаётся вниз по группе.
    page_one = [r for r in records if r.page == 1 and r.meta.get('profile')]
    assert page_one, 'profile must be recognized on the real order'
    assert all(r.meta.get('direction') for r in page_one)
    assert all(r.meta.get('level') for r in page_one)
