"""Превращение таблиц документа в записи об олимпиадах.

Задача модуля — отделить «название олимпиады» от остальных колонок
перечня РСОШ, где рядом лежат предмет, профиль, уровень, код и вид диплома.

Как это решается:

1. **Шапка.** Строка-шапка задаёт, где именно находится название, и
   отбрасывается; на следующих страницах она повторяется, поэтому шапки
   распознаются и внутри тела таблицы.
2. **Колонка названия.** Если в шапке есть колонка «наименование/название
   олимпиады», берётся она. Иначе выбирается самая текстовая колонка: в
   перечнях РСОШ название — это длинный текст, а соседние колонки — короткие
   коды и классы.
3. **Многострочные ячейки.** Переносы строк внутри названия схлопываются в
   один текст, поэтому «Всероссийская\\nолимпиада\\nшкольников» не
   распадается на три фрагмента.
4. **Многостраничные таблицы.** Таблицы одинаковой ширины на соседних
   страницах считаются продолжением одной таблицы, а не новой.
5. **Служебный текст.** Шапка письма, реквизиты приказа и подписи не являются
   олимпиадами и в каталог не попадают.
"""

import logging

from app.rsosh.extraction import PageTables
from app.rsosh.normalization import (
    clean_cell,
    clean_description,
    is_boilerplate,
    is_noise,
    looks_like_header,
    maybe_reverse,
    mentions_olympiad,
    name_key,
    normalize_olympiad_name,
)
from app.rsosh.types import OlympiadRecord

logger = logging.getLogger('papaya.rsosh.parsing')

# Доля непустых ячеек, при которой строка может быть шапкой.
HEADER_FILL_RATIO = 0.5
# Таблица с меньшим числом строк — это шапка письма или подпись, а не перечень.
MIN_TABLE_ROWS = 3


def _fill_ratio(row: list[str]) -> float:
    if not row:
        return 0.0
    return len([cell for cell in row if clean_cell(cell)]) / len(row)


def _is_header_row(row: list[str], next_row: list[str] | None = None) -> bool:
    """Похожа ли строка на шапку таблицы.

    Важен баланс: в перечнях РСОШ сама олимпиада часто называется
    «Всероссийская олимпиада школьников …», поэтому одного слова «олимпиада»
    недостаточно, чтобы объявить строку заголовком — иначе реальные записи
    молча выпадали бы из каталога. Шапкой считается строка, где заголовками
    выглядят хотя бы две ячейки, либо (для первой строки таблицы)
    единственная короткая ячейка-заголовок, когда следующая строка длиннее.
    """
    if _fill_ratio(row) < HEADER_FILL_RATIO:
        return False
    filled = [
        clean_cell(maybe_reverse(cell)) for cell in row if clean_cell(cell)
    ]
    matches = sum(1 for cell in filled if looks_like_header(cell))
    if matches >= 2:
        return True
    if matches == 1 and next_row is not None and all(len(cell) <= 25 for cell in filled):
        longer = [clean_cell(maybe_reverse(cell)) for cell in next_row]
        return any(len(cell) > 25 for cell in longer)
    return False


def _name_column_index(header: list[str], rows: list[list[str]]) -> int:
    """Индекс колонки с названием олимпиады."""
    normalized = [
        clean_cell(maybe_reverse(cell)).casefold().replace('ё', 'е') for cell in header
    ]
    for index, cell in enumerate(normalized):
        if 'наименован' in cell or 'название' in cell:
            return index
    for index, cell in enumerate(normalized):
        if 'олимпиад' in cell and 'уровень' not in cell and 'статус' not in cell:
            return index

    # Шапка бесполезна: выбираем самую «текстовую» колонку.
    best_index = 0
    best_score = -1.0
    width = max((len(row) for row in rows), default=0)
    for index in range(width):
        values = [clean_cell(row[index]) for row in rows if index < len(row)]
        values = [value for value in values if value]
        if not values:
            continue
        mean_length = sum(len(value) for value in values) / len(values)
        share = len(values) / max(1, len(rows))
        score = mean_length * share
        if score > best_score:
            best_score = score
            best_index = index
    return best_index


def _description_column_index(header: list[str], name_index: int) -> int | None:
    normalized = [
        clean_cell(maybe_reverse(cell)).casefold().replace('ё', 'е') for cell in header
    ]
    for index, cell in enumerate(normalized):
        if index == name_index:
            continue
        if 'описан' in cell or 'примечан' in cell or 'коммент' in cell:
            return index
    return None


def _table_records(
    table: list[list[str]],
    page: int,
    *,
    known_header: list[str] | None = None,
) -> tuple[list[OlympiadRecord], list[str], list[str] | None]:
    """Записи одной таблицы, предупреждения и найденная шапка.

    ``known_header`` — шапка, найденная ранее в документе для таблиц такой же
    ширины. В перечнях РСОШ шапка печатается на первой странице, а на
    следующих страницах её может не быть вовсе: без памяти о шапке колонка
    названия определялась бы эвристикой и «поехала» бы на страницу с
    объединёнными ячейками (например, на колонку с предметом).
    """
    issues: list[str] = []
    rows = [row for row in table if any(clean_cell(cell) for cell in row)]
    if len(rows) < MIN_TABLE_ROWS:
        if rows:
            issues.append(
                'Small table skipped: it looks like a document caption, not a list'
            )
        return [], issues, known_header

    header: list[str] = list(known_header or [])
    body = rows
    if _is_header_row(rows[0], rows[1] if len(rows) > 1 else None):
        header = rows[0]
        body = rows[1:]
    elif not known_header:
        issues.append(
            'Table header was not recognized, columns were detected heuristically'
        )

    name_index = _name_column_index(header, body)
    description_index = _description_column_index(header, name_index)

    records: list[OlympiadRecord] = []
    skipped_boilerplate = 0
    flagged = 0

    for position, row in enumerate(body):
        if name_index >= len(row):
            continue
        next_row = body[position + 1] if position + 1 < len(body) else None
        if _is_header_row(row, next_row):
            # Повтор шапки на следующей странице таблицы.
            continue
        raw_name = clean_cell(row[name_index])
        if not raw_name or is_noise(raw_name):
            # Ячейку названия не проверяем на «похоже на заголовок»: реальные
            # олимпиады называются «Всероссийская олимпиада школьников …».
            # Повтор шапки отсекается целиком по строке (см. _is_header_row).
            continue
        if is_boilerplate(raw_name):
            skipped_boilerplate += 1
            continue

        name = normalize_olympiad_name(raw_name)
        if not name:
            continue

        record_issues: list[str] = []
        if not mentions_olympiad(name):
            # Название без слова «олимпиада» — возможно, это не олимпиада из
            # перечня: оставляем, но помечаем для проверки администратором.
            record_issues.append(
                'В названии нет слова «олимпиада» — проверьте, что это олимпиада'
            )
            flagged += 1

        description = None
        if description_index is not None and description_index < len(row):
            description = clean_description(row[description_index])
        records.append(
            OlympiadRecord(
                name=name,
                name_norm=name_key(name),
                description=description,
                page=page,
                row=position,
                raw=raw_name,
                issues=record_issues,
            )
        )

    if skipped_boilerplate:
        issues.append(
            f'{skipped_boilerplate} служебных строк документа пропущено '
            '(шапка/реквизиты)'
        )
    if flagged:
        issues.append(
            f'{flagged} записей без слова «олимпиада» в названии — требуют проверки'
        )

    return records, issues, header or None


def _same_shape(first: list[list[str]], second: list[list[str]]) -> bool:
    """Совпадает ли ширина таблиц (признак продолжения той же таблицы)."""
    if not first or not second:
        return False
    return len(first[-1]) == len(second[0])


def parse_pages(pages: list[PageTables]) -> tuple[list[OlympiadRecord], list[str]]:
    """Собрать записи об олимпиадах из всех страниц документа.

    Возвращает записи и список предупреждений: результат импорта не должен
    быть «пустым и тихим» — администратор должен видеть, что нашлось и что
    вызвало подозрение.
    """
    records: list[OlympiadRecord] = []
    warnings: list[str] = []
    # Шапка по ширине таблицы: на первой странице перечня она есть, на
    # следующих — обычно нет, но раскладка колонок та же.
    headers: dict[int, list[str]] = {}

    for page in pages:
        warnings.extend(f'p.{page.page}: {issue}' for issue in page.issues)
        for table in page.tables:
            if not table:
                continue
            width = max((len(row) for row in table), default=0)
            page_records, page_issues, header = _table_records(
                table,
                page.page,
                known_header=headers.get(width),
            )
            if header and width not in headers:
                headers[width] = header
            records.extend(page_records)
            warnings.extend(f'p.{page.page}: {issue}' for issue in page_issues)

    logger.info('rsosh: parsed %s records', len(records))
    return records, _finalize_warnings(records, warnings)


def _finalize_warnings(
    records: list[OlympiadRecord],
    warnings: list[str],
) -> list[str]:
    """Убрать повторы предупреждений и отметить совпадения внутри документа.

    Одна и та же олимпиада в перечне встречается в разделах по предметам
    (например, «Физтех» есть и в математике, и в физике) — это нормальная
    ситуация: в каталоге останется одна запись, а повтор в документе
    отмечается предупреждением для администратора.
    """
    seen: set[str] = set()
    repeated: set[str] = set()
    for record in records:
        if record.name_norm in seen:
            repeated.add(record.name)
        seen.add(record.name_norm)

    warnings = list(warnings)
    for name in sorted(repeated):
        warnings.append(
            f'Олимпиада «{name}» встречается в документе несколько раз — '
            'в каталог попадёт одна запись'
        )

    unique: list[str] = []
    for warning in warnings:
        if warning and warning not in unique:
            unique.append(warning)
    return unique
