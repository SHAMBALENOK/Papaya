"""Разбор таблиц РСОШ без сканера: геометрия колонок и строк.

Реальный перечень РСОШ — скан без горизонтальных линеек: колонки разделены
вертикальными линиями рамки, а строки — только вертикальным пробелом между
текстом. Ломается это молча: OCR читается отлично, а в каталог попадает ноль
записей, потому что таблица «маленькая» или названия слиплись в одну строку.

Поэтому геометрия проверяется на синтетическом изображении, а разбор — на
коротких таблицах, похожих на настоящие страницы. Здесь нет базы: чистая
функциональность разбора.
"""

import numpy as np

from app.rsosh import tables
from app.rsosh.extraction import PageTables
from app.rsosh.parsing import (
    _is_row_number,
    _merge_continuation_rows,
    _plausible_name,
    _table_records,
    _voted_name_index,
    normalize_olympiad_name,
    parse_pages,
    split_olympiad_names,
)


def _white(width: int = 1800, height: int = 1200):
    """Пустой «скан»: тёмный текст на светлом фоне, как у Tesseract."""
    return np.full((height, width), 255, dtype=np.uint8)


def _rule(image, x: int, top: int = 0, bottom: int | None = None, thickness: int = 1):
    bottom = image.shape[0] if bottom is None else bottom
    image[top:bottom, x:x + thickness] = 0


def _box(image, x0: int, y0: int, x1: int, y1: int):
    image[y0:y1, x0:x1] = 0


def test_cluster_positions_keeps_every_distinct_line():
    """Линии рамки не схлопываются и не переставляются.

    Раньше список групп склеивался с самим собой, из-за чего часть линий
    пропадала, а оставшиеся возвращались в порядке контуров — колонки
    таблицы разъезжались местами.
    """
    assert tables._cluster_positions([300, 100, 200], tolerance=6) == [100, 200, 300]


def test_cluster_positions_merges_neighbours():
    assert tables._cluster_positions([100, 104, 400], tolerance=6) == [102, 400]


def test_vertical_rules_ignore_dense_text_column():
    """Колонка плотного текста не считается линией рамки.

    Между строками такой колонки почти нет промежутка, поэтому она после
    морфологического «склеивания» выглядит как сплошная линия — и раньше
    становилась границей колонки, рвя таблицу посередине.
    """
    image = _white(width=1600, height=1200)
    expected = [200, 600, 1000, 1400]
    for x in expected:
        _rule(image, x)
    # Псевдотекст: узкие штрихи с большими промежутками между строками.
    for y in range(40, 1180, 24):
        _box(image, 795, y, 805, y + 8)

    words = [{'x0': 0, 'y0': 0, 'x1': 1600, 'y1': 1200}]
    found = tables.detect_vertical_rules(image, words)

    assert found == expected


def test_vertical_rules_drop_frame_border_of_the_scan():
    """Чёрная рамка самого скана по краю кадра не становится колонкой."""
    image = _white(width=1600, height=1200)
    _rule(image, 0, thickness=6)
    _rule(image, 1594, thickness=6)
    _rule(image, 800)

    words = [{'x0': 0, 'y0': 0, 'x1': 1600, 'y1': 1200}]
    assert tables.detect_vertical_rules(image, words) == [800]


def _two_line_words() -> list[dict]:
    """Слова таблицы: 6 колонок, 3 строки, часть ячеек многострочная.

    Без многострочных ячеек промежуток между строками равен шагу между
    строками, и границу не по чему определить — так и в настоящем перечне:
    разрыв виден только там, где ячейка занята двумя-четырьмя строками.
    """
    columns = [(100, 400), (400, 800), (800, 1200), (1200, 1600), (1600, 1900), (1900, 2300)]
    rows = [200, 700, 1200]
    multi_line = {0, 1, 3}
    words: list[dict] = []
    for row_index, top in enumerate(rows):
        for column, (x0, x1) in enumerate(columns):
            lines = 2 if column in multi_line else 1
            for line in range(lines):
                y0 = top + line * 40
                words.append({
                    'x0': x0 + 10,
                    'y0': y0,
                    'x1': x1 - 10,
                    'y1': y0 + 30,
                    'text': f'c{column}r{row_index}l{line}',
                })
    return words


def test_ink_continuity_tells_line_from_gapped_column():
    """Сплошная линия непрерывна, а колонка с разрывами — нет.

    Это главное отличие рамки таблицы от колонки текста: между строками
    букв всегда остаётся пустой ряд пикселей.
    """
    span = np.zeros((100, 40), dtype=bool)
    span[:, 5] = True
    span[::3, 20] = True

    assert tables._ink_continuity(span, 5) >= 0.9
    assert tables._ink_continuity(span, 20) < tables.MIN_RULE_CONTINUITY


def test_build_table_recovers_rows_by_multi_column_gaps():
    """Строки восстанавливаются голосованием по нескольким колонкам."""
    words = _two_line_words()
    image = _white(width=2400, height=1600)
    for x in (100, 400, 800, 1200, 1600, 1900, 2300):
        _rule(image, x, top=0, bottom=1500)

    table = tables.build_table(image, words)

    assert len(table.rows) == 3
    assert all(len(row) == 6 for row in table.rows)
    assert table.rows[0][0].text == 'c0r0l0 c0r0l1'
    assert table.rows[2][5].text == 'c5r2l0'


def test_empty_cell_is_kept_so_columns_stay_aligned():
    """Пустая ячейка не разъезжает: строка остаётся прямоугольной."""
    words = _two_line_words()
    words = [
        word for word in words
        if not (word['text'].startswith('c4r0'))
    ]
    image = _white(width=2400, height=1600)
    for x in (100, 400, 800, 1200, 1600, 1900, 2300):
        _rule(image, x, top=0, bottom=1500)

    table = tables.build_table(image, words)

    assert len(table.rows) == 3
    assert all(len(row) == 6 for row in table.rows)
    assert table.rows[0][4].text == ''


def test_split_keeps_single_olympiad_intact():
    for name in (
        'Всероссийская олимпиада школьников по математике',
        'Международная олимпиада школьников по информатике',
        'Открытая олимпиада ШКОЛЬНИКОВ по программированию',
    ):
        assert split_olympiad_names(name) == [name]


def test_split_separates_two_olympiads_in_one_cell():
    """Две олимпиады в одной ячейке становятся двумя записями.

    Иначе в каталог попадает слитная строка, которую невозможно сопоставить
    ни с одной реальной олимпиадой.
    """
    cell = (
        'Олимпиада МГИМО МИД России для школьников , '
        'Олимпиада по комплексу предметов «Культура и искусство»'
    )
    parts = split_olympiad_names(cell)

    assert len(parts) == 2
    assert parts[0].startswith('Олимпиада МГИМО')
    assert parts[1].startswith('Олимпиада по комплексу')
    assert parts[1].endswith('»')


def test_split_does_not_break_a_single_title_in_two():
    """Прилагательное и «олимпиада» — одна фраза, а не два названия."""
    cell = 'Всероссийская олимпиада школьников выполнима. Твое призвание — финансист!»'
    assert split_olympiad_names(cell) == [cell.rstrip('»')]


def test_voted_name_index_ignores_margin_noise_and_organizer():
    """Колонка названия выбирается по всему документу, а не по странице.

    На части страниц ячейка названия пустая, и по одной строке побеждает
    колонка организатора — длинная и тоже содержащая слово «олимпиада».
    """
    rows = [
        ['', '', 'Федеральное государственное образовательное учреждение'],
        ['| | |', '«Формула Единства» Всероссийская олимпиада', ''],
        ['', '', 'Бюджетное государственное автономное учреждение'],
        ['', 'Открытая олимпиада школьников по математике', 'Федеральное учреждение науки'],
    ]

    assert _voted_name_index(rows) == 1


def test_short_table_is_a_caption_until_width_is_proven():
    """Подпись документа не становится перечнем — а вот строка страницы — да.

    В реальном перечне РСОШ на страницу попадает одна-две строки, и раньше
    такие страницы пропускались целиком: каталог оставался пустым, хотя OCR
    читался отлично. Решение принимается по документу целиком — ширина
    таблицы считается перечнем, если на другой странице он уже подтверждён.
    """
    caption = [
        ['Раздел I. Общеобразовательные предметы'],
        ['Приложение к приказу'],
    ]
    records, issues, _ = _table_records(caption, 5, known_name_index=0)
    assert records == []
    assert any('Small table' in issue for issue in issues)

    body_only = [
        ['1', 'Всероссийская олимпиада школьников', 'Министерство просвещения'],
        ['2', 'Открытая олимпиада школьников', 'Государственный комитет'],
    ]
    records, issues, _ = _table_records(body_only, 5, known_name_index=1)
    assert records == []
    assert any('Small table' in issue for issue in issues)

    records, issues, _ = _table_records(
        body_only, 5, known_name_index=1, allow_short=True
    )
    assert [record.name for record in records] == [
        'Всероссийская олимпиада школьников',
        'Открытая олимпиада школьников',
    ]
    assert not any('Small table' in issue for issue in issues)


def test_header_row_is_found_below_requisites_of_the_order():
    """Шапка идёт после реквизитов приказа, а не в первой строке таблицы."""
    table = [
        ['УТВЕРЖДЕНЫ Министерством приказом', 'от 00.00.2025', '2025/26'],
        ['№', 'Полное наименование', 'Организатор'],
        ['1', 'Всероссийская олимпиада школьников', 'Министерство просвещения'],
    ]

    records, issues, header = _table_records(table, 1, known_name_index=1)

    assert header == ['№', 'Полное наименование', 'Организатор']
    assert len(records) == 1
    assert records[0].name == 'Всероссийская олимпиада школьников'
    assert not any('Small table' in issue for issue in issues)


def test_is_row_number_tolerates_ocr_junk():
    assert _is_row_number('14')
    assert _is_row_number('| 14')
    assert _is_row_number('21.')
    assert not _is_row_number('|')
    assert not _is_row_number('.')
    assert not _is_row_number('')


def test_merge_continuation_rows_joins_cells_with_ocr_noise():
    """Строка перечня, разорванная по странице, собирается в одну.

    В продолжения строки нет номера: колонка номера несёт мусор скана («|»,
    «.»), по которому раньше начиналась новая строка, и олимпиада терялась.
    """
    body = [
        ['| 14', 'Всесибирская |', 'Министерство образования'],
        ['|', '| открытая олимпиада', 'области'],
        ['', '| Школьников', ''],
        ['15', 'Вузовско- академическая олимпиада', ''],
    ]

    merged = _merge_continuation_rows(body, 3)

    assert len(merged) == 2
    assert merged[0][0] == '| 14'
    assert merged[0][1] == 'Всесибирская | | открытая олимпиада | Школьников'
    assert merged[0][2] == 'Министерство образования области'
    assert merged[1][1] == 'Вузовско- академическая олимпиада'


def test_merge_continuation_rows_needs_a_number_anywhere():
    """Без номеров строки не склеиваются: колонка может быть вообще не номерной."""
    body = [
        ['', 'Основания и порядок', ''],
        ['', 'подтверждаются свидетельством', ''],
    ]
    assert _merge_continuation_rows(body, 3) == body


def test_merge_continuation_rows_does_not_glue_two_olympiads():
    """Номер следующей строки начинает новую группу, а не продолжает."""
    body = [
        ['14', 'Всесибирская олимпиада', ''],
        ['15', 'Вузовско- академическая олимпиада', ''],
    ]
    merged = _merge_continuation_rows(body, 3)
    assert [row[1] for row in merged] == [
        'Всесибирская олимпиада',
        'Вузовско- академическая олимпиада',
    ]


def test_plausible_name_keeps_real_olympiads():
    assert _plausible_name('Всероссийская олимпиада школьников') is not None
    assert _plausible_name('Герценовская олимпиада школьников') is not None
    assert _plausible_name('Турнир имени') is not None


def test_plausible_name_rejects_fragments_and_junk():
    assert _plausible_name('олимпиада') is None
    assert _plausible_name('математика') is None
    assert _plausible_name('области') is None
    assert _plausible_name('| школьников имени И.Я. Верченко |') is None
    assert _plausible_name('ХИМИЯ') is None
    assert _plausible_name('УТВЕРЖДЕНЫ приказом Министерства') is None
    assert _plausible_name('Казанский. (Приволжский) федеральный ниверситет') is None
    assert _plausible_name('Челябинского университетского образовательного округа') is None


def test_plausible_name_trims_organizer_tail():
    """«…Северо-Кавказского федерального университета» — название, а не мусор."""
    name = 'Открытая олимпиада Северо-Кавказского федерального университета среди учащихся'
    assert _plausible_name(name) == 'Открытая олимпиада Северо-Кавказского'
    assert (
        _plausible_name('Университетская олимпиада')
        == 'Университетская олимпиада'
    )
    assert (
        _plausible_name('Межрегиональные предметные олимпиады федерального государственного')
        == 'Межрегиональные предметные олимпиады'
    )


def test_continuation_row_becomes_one_record_not_fragments():
    """Одна логическая строка на нескольких строках таблицы — одна запись."""
    table = [
        ['| 14', 'Всесибирская |', 'Министерство образования'],
        ['|', '| открытая олимпиада', 'области'],
        ['', '| Школьников', ''],
        ['15', 'Вузовско- академическая олимпиада', ''],
    ]

    records, issues, _ = _table_records(table, 35, known_name_index=1)

    assert len(records) == 2
    assert any(record.name.startswith('Всесибирская') for record in records)
    assert any('Вузовско-' in record.name for record in records)
    assert not any('plausible name' in issue for issue in issues)


def test_order_page_does_not_leak_into_catalog():
    """Реквизиты приказа на титуле перечня не становятся олимпиадой."""
    table = [
        ['Врио', 'Министра', ''],
        ['№ п/п', 'Полное наименование', 'Организатор'],
        ['1', 'Всероссийская олимпиада школьников', 'Министерство просвещения'],
    ]

    records, issues, _ = _table_records(table, 1, known_name_index=1)

    assert len(records) == 1
    assert records[0].name == 'Всероссийская олимпиада школьников'


def test_normalize_olympiad_name_removes_rule_line_pipes():
    """Палочки от вертикальных линеек рамки не остаются в названии."""
    assert normalize_olympiad_name('Всесибирская | открытая олимпиада') == (
        'Всесибирская открытая олимпиада'
    )
    assert normalize_olympiad_name('«Инженерная олимпиада | школьников»') == (
        'Инженерная олимпиада школьников'
    )


def test_parse_pages_aggregates_page_and_structure_warnings():
    """Постраничные предупреждения становятся несколькими итоговыми строками.

    Старые отчёты показывали администратору ленту из сотни одинаковых строк
    («страница была повёрнута», «шапка не распознана», «строки восстановлены по
    промежуткам») в начале окна результата. Теперь это счётчики по документу, а
    маркеры структуры (``Table header was not recognized``, ``Small table
    skipped``), от которых persist зависит при решении об архивировании,
    сохраняются дословно.
    """
    pages = [
        PageTables(page=1, method='ocr', orientation=90, tables=[
            [['№', 'Наименование олимпиады', 'Организатор'],
             ['1', 'Всероссийская олимпиада школьников', 'Министерство просвещения'],
             ['2', 'Открытая олимпиада школьников', 'Государственный комитет'],
             ['3', 'Олимпиада школьников «Ломоносов»', 'МГУ']],
        ], issues=[
            'Page was rotated by 90° before OCR',
            'Page skew of 0.35° was straightened',
        ]),
        PageTables(page=2, method='ocr', orientation=90, tables=[
            [['1', 'Олимпиада школьников «Физтех»', 'МФТИ'],
             ['2', 'Открытая олимпиада школьников по программированию', 'ИТМО']],
        ], issues=['Page was rotated by 90° before OCR']),
        # Подпись документа другой ширины: ни перечень, ни продолжение таблицы.
        PageTables(page=3, method='ocr', tables=[
            [['Подпись документа 1', 'Строка'],
             ['Подпись документа 2', '']],
        ], issues=[]),
    ]

    records, warnings = parse_pages(pages)

    assert len(records) == 5
    assert not any(w.startswith('p.') for w in warnings), warnings
    assert any(
        'Повёрнуто страниц перед распознаванием: 2' in w for w in warnings
    ), warnings
    assert any(
        w.startswith('Table header was not recognized') for w in warnings
    ), warnings
    assert any(w.startswith('Small table skipped') for w in warnings), warnings
    # Наклон скана — штатное условие чтения, в отчёте его нет вовсе.
    assert not any('skew' in w.lower() for w in warnings), warnings

