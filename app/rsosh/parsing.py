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
import re

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
# Сколько первых строк таблицы проверяются на шапку: на первой странице
# перечня шапка занимает несколько строк и идёт после реквизитов приказа.
HEADER_SEARCH_ROWS = 4
# Слово из трёх и более кириллических букв — признак настоящего текста
# в отличие от мусора по краям скана («|», «.», «,»).
RUSSIAN_WORD = re.compile(r'[А-Яа-яЁё]{3,}')
# Слова, которыми в перечне РСОШ начинаются названия олимпиад.
TITLE_KEYWORDS = frozenset({
    'всероссийская', 'всероссийский', 'всероссийские', 'всероссийский',
    'международная', 'международный', 'международные',
    'межрегиональная', 'межрегиональный', 'межрегиональные',
    'межвузовская', 'межшкольная', 'многопредметная', 'многопрофильная',
    'московская', 'городская', 'областная', 'краевая', 'региональная',
    'открытая', 'открытый', 'школьная', 'юношеская',
    'олимпиада', 'олимпиады', 'конкурс',
})
# Названия внутри ячейки отделяются в том числе кавычками и переводом строки.
NAME_SEPARATORS = ('\n', '\r', ';', '»')
# Признаки того, что перед словом кончилось предыдущее название.
BOUNDARY_BEFORE = ' \t\n\r|-—–,.;:'
# Резкий край фрагмента: рамки ячейки и запятые, но не кавычки названия.
EDGE_TRIM = ' \t\n\r|,;-—–.'
# Номер строки перечня: одна-три цифры, иногда с мусором от скана по краям.
ROW_NUMBER = re.compile(r'^[^\d]{0,4}\d{1,3}[.,]?$')
# Юридическое лицо в колонке названия — это ячейка организатора, а не олимпиада.
LEGAL_MARKERS = (
    'федеральн',
    'государственн',
    'образовательн',
    'учреждени',
    'университ',
    'ниверсит',
    'министерств',
    'бюджетн',
    'автономн',
    'казенн',
    'академи',
)
# Служебные тексты документа: они стоят в колонках таблицы, но не названия.
SCAFFOLD_MARKERS = (
    'утвержден',
    'приложени',
    'приказ',
    'укрупненн',
    'специальност',
)
# Отметки для агрегации: отдельное предупреждение на каждую страницу — шум.
IMPLAUSIBLE_ISSUE = re.compile(r'^(\d+) rows skipped: no plausible name$')
FLAGGED_RECORDS_ISSUE = re.compile(r'^(\d+) записей без слова')
BOILERPLATE_ISSUE = re.compile(r'^(\d+) служебных строк документа пропущено')

# Предупреждения таблиц, которые собираются счётчиком по документу, а не
# повторяются на каждую страницу. Первые два — это ещё и маркеры «перечень
# прочитан не полностью», по которым persist решает, можно ли архивировать
# исчезнувшие олимпиады, поэтому их текст сохраняется дословно.
HEADER_UNRECOGNIZED_ISSUE = (
    'Table header was not recognized, columns were detected heuristically'
)
SMALL_TABLE_SKIPPED_ISSUE = (
    'Small table skipped: it looks like a document caption, not a list'
)

# Штатные условия чтения страницы: поворот и наклон скана, пробный подбор угла,
# восстановление строк без линеек — это норма для многостраничного перечня, а
# не ошибка. Постранично не показываются.
ROUTINE_PAGE_ISSUE_PREFIXES = (
    'Page was rotated by',
    'Page skew of',
    'Page orientation was determined by trial OCR',
    'Row borders were not detected',
    'Table borders were not detected',
)
# Реальные проблемы страницы, которые нужны в отчёте (агрегированно).
OCR_FAILED_ISSUE = 'OCR did not recognize any text on the page'
BLANK_PAGE_ISSUE = 'Page is blank or contains no recognizable text'
ORIENTATION_FAILED_PREFIX = 'Page orientation could not be determined'
PARTIAL_TEXT_LAYER_ISSUE = (
    'Page has a partial text layer, OCR was used as a fallback'
)

def _title_matches(text: str) -> list[tuple[int, str]]:
    """Все позиции слов-начал в тексте (без пересечений)."""
    lowered = text.lower()
    found: list[tuple[int, str]] = []
    occupied: list[tuple[int, int]] = []
    for keyword in TITLE_KEYWORDS:
        start = 0
        while True:
            index = lowered.find(keyword, start)
            if index < 0:
                break
            if all(end <= index or begin >= index + len(keyword)
                   for begin, end in occupied):
                occupied.append((index, index + len(keyword)))
                found.append((index, keyword))
            start = index + len(keyword)
    return sorted(found)


def _split_title_keywords(text: str) -> list[str]:
    """Разрезать ячейку перед началом второго названия олимпиады.

    Новое название начинается с заглавной буквы: «Олимпиада …», «Открытая
    олимпиада …». Строчное «олимпиада» после прилагательного — это та же
    фраза («Всероссийская олимпиада школьников»), и разрезать её нельзя:
    иначе в каталоге появляется пустая запись из одного слова.
    """
    matches = _title_matches(text)
    if len(matches) < 2:
        return [text]

    bounds = [0]
    started = False
    for index, keyword in matches:
        # Заглавная буква берётся из самого текста: словарь написан
        # строчными, а названия в перечне начинаются с заглавной.
        if not text[index].isupper():
            continue
        if index == 0 or not started:
            started = True
            continue
        if text[index - 1] not in BOUNDARY_BEFORE:
            continue
        if _previous_word(text[:index]) in TITLE_KEYWORDS:
            continue
        bounds.append(index)
    bounds.append(len(text))
    return [
        text[begin:end] for begin, end in zip(bounds, bounds[1:])
        if text[begin:end].strip(EDGE_TRIM)
    ]


def _previous_word(text: str) -> str:
    """Слово, которое стоит непосредственно перед ``text``."""
    match = re.search(r'(\S+)\s*$', text)
    if not match:
        return ''
    return match.group(1).strip(EDGE_TRIM).casefold()


def _close_quotes(text: str) -> str:
    """Вернуть кавычку, съеденную разделителем «»."""
    opened = text.count('«')
    if opened > text.count('»'):
        return text + '»' * (opened - text.count('»'))
    return text


def split_olympiad_names(text: str) -> list[str]:
    """Разрезать ячейку с несколькими названиями на отдельные олимпиады.

    В перечне РСОШ в одну строку может попасть несколько олимпиад — особенно
    когда они идут в одну строчку по колонке «полное наименование». Такие
    ячейки раньше превращались в одну слитную запись, а в каталоге должны
    быть разные олимпиады.
    """
    pieces = [text]
    for separator in NAME_SEPARATORS:
        pieces = [part for chunk in pieces for part in chunk.split(separator)]
    result: list[str] = []
    for piece in pieces:
        for part in _split_title_keywords(piece):
            part = _close_quotes(part.strip(EDGE_TRIM))
            if part:
                result.append(part)
    return result


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

    # Шапка бесполезна: выбираем самую «текстовую» колонку. При равенстве
    # предпочтение у колонки, где встречается слово «олимпиада»: именно там
    # лежит название, а в соседней колонке — наименование организатора.
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
        with_name = sum(1 for value in values if mentions_olympiad(value))
        score = mean_length * share * (2.0 if with_name else 1.0)
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


def _has_russian_word(value: str) -> bool:
    """Есть ли в тексте слово из трёх и более кириллических букв."""
    return bool(RUSSIAN_WORD.search(value))


def _voted_name_index(rows: list[list[str]]) -> int | None:
    """Колонка названия по голосованию содержимого всех строк таблицы.

    По одной странице колонку названия выбрать нельзя: на части страниц
    ячейка названия пустая — олимпиада названа на предыдущей странице, —
    и тогда побеждает более длинная колонка организаторов.

    Поэтому сначала считается, в скольких строках каждой колонки есть
    русский текст, а затем берётся самая левая из колонок, заполненных
    почти так же полно. Левая колонка выигрывает потому, что у перечня
    РСОШ название стоит перед наименованием организатора, а слева от него
    лежит только поле номера и края скана, где вместо текста — мусор из
    точек и вертикальных чёрточек.
    """
    width = max((len(row) for row in rows), default=0)
    if width == 0:
        return None

    filled: list[int] = []
    for index in range(width):
        count = sum(
            1 for row in rows
            if index < len(row)
            and _has_russian_word(clean_cell(row[index]))
        )
        filled.append(count)

    best = max(filled)
    if best <= 0:
        return None
    # Порог допускает колонку, заполненную чуть реже победителя, но не
    # выбирает колонку, где текста почти нет.
    threshold = max(1.0, best * 0.6)
    for index, count in enumerate(filled):
        if count >= threshold:
            return index
    return None


def _header_and_body(rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """Разделить таблицу на шапку и тело."""
    position = _find_header_row(rows)
    if position is None:
        return [], rows
    return rows[position], rows[position + 1:]


def _find_header_row(rows: list[list[str]]) -> int | None:
    """Позиция строки-шапки среди первых строк таблицы.

    На первой странице перечня РСОШ перед шапкой идут реквизиты приказа
    («УТВЕРЖДЕНЫ Министерством…»), а сама шапка занимает несколько строк.
    Поэтому шапка ищется не только в первой строке.
    """
    limit = min(HEADER_SEARCH_ROWS, len(rows))
    for index in range(limit):
        following = rows[index + 1] if index + 1 < len(rows) else None
        if _is_header_row(rows[index], following):
            return index
    return None


def _is_row_number(value: str) -> bool:
    """Ячейка похожа на номер строки перечня («14», «| 12», «21.»)."""
    return bool(ROW_NUMBER.match(value.strip()))


def _merge_continuation_rows(body: list[list[str]], width: int) -> list[list[str]]:
    """Собрать строку перечня, разорванную на несколько строк таблицы.

    В перечне РСОШ одна строка нередко занимает больше одной строки таблицы:
    номер и название стоят в начале, а организатор и предметы продолжаются
    ниже — иногда уже на следующей странице. Такие продолжения дают в
    колонке названия обрывки чужого текста («федерального государственного»),
    и каталог засорялся бы вместо того, чтобы пополняться.

    Признаком начала новой строки служит её номер. Ячейка без цифр — либо
    пустая, либо мусор скана («|», «.»), — значит, это продолжение предыдущей
    строки. Если в колонке номеров не встретилось ни одного номера, таблица
    склеивается как есть: без номеров продолжение от первой строки не
    отличить от новой.
    """
    cells_by_row = [(list(row) + [''] * width)[:width] for row in body]
    if not any(_is_row_number(row[0]) for row in cells_by_row):
        return body

    merged: list[list[str]] = []
    numbered: list[bool] = []
    for cells in cells_by_row:
        number = cells[0]
        continuation = (
            bool(merged)
            and not re.sub(r'\D', '', number)
            and numbered[-1]
        )
        if continuation:
            for index in range(1, len(cells)):
                part = cells[index]
                if part.strip():
                    previous = merged[-1][index]
                    merged[-1][index] = (
                        f'{previous} {part}'.strip() if previous else part
                    )
            continue
        merged.append(cells)
        numbered.append(_is_row_number(number))
    return merged


def _legal_markers_in(text: str) -> tuple[set[str], int]:
    """Реквизиты организатора в тексте и позиция самого раннего из них.

    Маркеры ищутся только на границе слова: иначе «ниверситет» внутри
    «университет» считался бы вторым реквизитом, и название вида
    «Университетская олимпиада» отбрасывалось бы как реквизит.
    """
    lowered = text.lower()
    hits: set[str] = set()
    positions: list[int] = []
    for marker in LEGAL_MARKERS:
        start = 0
        while True:
            index = lowered.find(marker, start)
            if index < 0:
                break
            start = index + len(marker)
            before = lowered[index - 1] if index else ''
            if before.isalnum() or before == '_':
                continue
            hits.add(marker)
            positions.append(index)
    return hits, min(positions) if positions else -1


def _plausible_name(name: str) -> str | None:
    """Название, похожее на название олимпиады, — или ``None``, если это не оно.

    Фильтр отделяет реальные названия от обрывков, которые появляются, когда
    граница строки проходит внутри ячейки: предметы вместо названия («математика»),
    реквизиты организатора («Федеральное государственное учреждение») и обрывки
    одной фразы, разрезанной на несколько строк («Всесибирская» + «Школьников»).

    Реквизиты в конце названия возвращаются отрезанными, а не обрывают название
    целиком: «Открытая олимпиада Северо-Кавказского федерального университета» —
    это настоящая олимпиада, а длинный список организаторов в соседней колонке — нет.
    """
    text = clean_cell(name)
    if len(text) < 5 or not RUSSIAN_WORD.search(text):
        return None
    folded = text.casefold()
    if any(marker in folded for marker in SCAFFOLD_MARKERS):
        return None
    markers, start = _legal_markers_in(text)
    if len(markers) >= 2:
        # Название, целиком состоящее из реквизитов, обрезать нечего: в нём
        # даже не упомянута олимпиада.
        if 'олимпиад' not in folded and 'конкурс' not in folded:
            return None
        if start <= 0:
            return None
        return _plausible_name(text[:start].strip(EDGE_TRIM))
    # Название начинается с заглавной буквы: строчное начало — это продолжение
    # чужой фразы («по агрогенетике…», «федерального государственного»).
    stripped = text.lstrip(' \t«"\'>|_—–-')
    if not stripped or not (stripped[0].isupper() or stripped[0].isdigit()):
        return None
    tokens = [token for token in re.split(r'\s+', text) if token.strip(' |,.«»"-')]
    if len(tokens) < 2:
        return None
    return text


def _table_records(
    table: list[list[str]],
    page: int,
    *,
    known_header: list[str] | None = None,
    known_name_index: int | None = None,
    allow_short: bool = False,
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

    header: list[str] = list(known_header or [])
    body = rows
    header_position = _find_header_row(rows)
    if header_position is not None:
        header = rows[header_position]
        body = rows[header_position + 1:]
    elif known_header:
        header = list(known_header)
    elif rows:
        issues.append(
            'Table header was not recognized, columns were detected heuristically'
        )

    # Таблица считается перечнем, если шапка найдена, строк достаточно или
    # такая же ширина уже подтверждена как перечень на другой странице: в
    # реальном перечне РСОШ на страницу попадает всего одна-две строки, и
    # без этого они молча выпадали бы из каталога. Иначе это реквизиты
    # приказа или подпись.
    if len(body) < MIN_TABLE_ROWS and not header and not allow_short:
        if rows:
            issues.append(
                'Small table skipped: it looks like a document caption, not a list'
            )
        return [], issues, known_header

    if known_name_index is not None:
        name_index = known_name_index
    else:
        name_index = _name_column_index(header, body)
    description_index = _description_column_index(header, name_index)

    # Одна строка перечня может занимать несколько строк таблицы — тогда
    # колонки склеиваются, и только после этого из строки берётся название.
    width = max((len(row) for row in rows), default=0)
    body = _merge_continuation_rows(body, width)

    records: list[OlympiadRecord] = []
    skipped_boilerplate = 0
    skipped_implausible = 0
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

        # В одной ячейке может быть несколько олимпиад подряд — тогда это
        # разные записи каталога, а не одна слитная строка.
        names = split_olympiad_names(raw_name)
        if not names:
            continue
        if all(is_boilerplate(name) for name in names):
            skipped_boilerplate += 1
            continue

        description = None
        if description_index is not None and description_index < len(row):
            description = clean_description(row[description_index])

        for fragment in names:
            if is_boilerplate(fragment):
                skipped_boilerplate += 1
                continue
            name = normalize_olympiad_name(fragment)
            if not name:
                continue
            name = _plausible_name(name)
            if name is None:
                skipped_implausible += 1
                continue

            record_issues: list[str] = []
            if not mentions_olympiad(name):
                # Название без слова «олимпиада» — возможно, это не олимпиада из
                # перечня: оставляем, но помечаем для проверки администратором.
                record_issues.append(
                    'В названии нет слова «олимпиада» — проверьте, что это олимпиада'
                )
                flagged += 1

            records.append(
                OlympiadRecord(
                    name=name,
                    name_norm=name_key(name),
                    description=description,
                    page=page,
                    row=position,
                    raw=fragment,
                    issues=record_issues,
                )
            )

    if skipped_boilerplate:
        issues.append(
            f'{skipped_boilerplate} служебных строк документа пропущено '
            '(шапка/реквизиты)'
        )
    if skipped_implausible:
        issues.append(f'{skipped_implausible} rows skipped: no plausible name')
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
    tables: list[tuple[PageTables, list[list[str]]]] = []
    for page in pages:
        for table in page.tables:
            if not table:
                continue
            tables.append((page, table))

    # Колонка названия выбирается сразу по всем таблицам одной ширины: по
    # одной странице её определить нельзя, там почти всегда есть пустые
    # ячейки названия, и вместо него выбирается колонка организаторов.
    prepared: list[tuple[PageTables, list[list[str]], list[list[str]], int]] = []
    name_indexes: dict[int, int | None] = {}
    data_widths: set[int] = set()
    for page, table in tables:
        rows = [row for row in table if any(clean_cell(cell) for cell in row)]
        width = max((len(row) for row in table), default=0)
        header, body = _header_and_body(rows)
        prepared.append((page, table, rows, width))
        if header or len(body) >= MIN_TABLE_ROWS:
            data_widths.add(width)
        if width in name_indexes:
            continue
        name_indexes[width] = (
            _name_column_index(header, body) if header else _voted_name_index(rows)
        )

    # Счётчики проблем по всему документу. Постраничные предупреждения
    # («страница была повёрнута», «восстановлено по промежуткам» и т.п.) — это
    # шум: пятьдесят одинаковых строк ничего не добавляют к ответу. В отчёт
    # попадают несколько итоговых строк: администратор должен видеть, что
    # недочитано и что вызвало подозрение, а не ленту одинаковых повторов.
    counts = {
        'rotated': 0,
        'orientation_failed': 0,
        'unread': 0,
        'partial_layer': 0,
        'implausible': 0,
        'flagged': 0,
        'boilerplate': 0,
        'header_unrecognized': 0,
        'small_tables': 0,
    }
    for page, table, rows, width in prepared:
        for issue in page.issues:
            if issue == PARTIAL_TEXT_LAYER_ISSUE:
                counts['partial_layer'] += 1
            elif issue in (OCR_FAILED_ISSUE, BLANK_PAGE_ISSUE):
                counts['unread'] += 1
            elif issue.startswith(ORIENTATION_FAILED_PREFIX):
                counts['orientation_failed'] += 1
            elif issue.startswith('Page was rotated by'):
                counts['rotated'] += 1
            elif issue.startswith(ROUTINE_PAGE_ISSUE_PREFIXES):
                # Поворот, наклон, пробный подбор угла, строки без линеек —
                # нормальные условия чтения, не ошибка.
                continue
            else:
                # Всё остальное (внешние страницы, пустой лист и т.п.)
                # показывается как есть.
                warnings.append(f'p.{page.page}: {issue}')

        page_records, page_issues, header = _table_records(
            table,
            page.page,
            known_header=headers.get(width),
            known_name_index=name_indexes.get(width),
            allow_short=width in data_widths,
        )
        if header and width not in headers:
            headers[width] = header
        records.extend(page_records)
        for issue in page_issues:
            skipped = IMPLAUSIBLE_ISSUE.match(issue)
            if skipped:
                counts['implausible'] += int(skipped.group(1))
                continue
            flagged_issue = FLAGGED_RECORDS_ISSUE.match(issue)
            if flagged_issue:
                counts['flagged'] += int(flagged_issue.group(1))
                continue
            boilerplate = BOILERPLATE_ISSUE.match(issue)
            if boilerplate:
                counts['boilerplate'] += int(boilerplate.group(1))
                continue
            if issue == HEADER_UNRECOGNIZED_ISSUE:
                counts['header_unrecognized'] += 1
                continue
            if issue == SMALL_TABLE_SKIPPED_ISSUE:
                counts['small_tables'] += 1
                continue
            warnings.append(f'p.{page.page}: {issue}')

    if counts['rotated']:
        warnings.append(
            f'Повёрнуто страниц перед распознаванием: {counts["rotated"]} — '
            'наклон устранён автоматически'
        )
    if counts['orientation_failed']:
        warnings.append(
            f'Страниц с неопределённой ориентацией: {counts["orientation_failed"]} — '
            'угол подобран пробным распознаванием'
        )
    if counts['unread']:
        warnings.append(f'Страниц с нераспознанным текстом: {counts["unread"]}')
    if counts['partial_layer']:
        warnings.append(
            f'Страниц с частичным текстовым слоем: {counts["partial_layer"]} — '
            'OCR использован как запасной путь'
        )
    if counts['header_unrecognized']:
        warnings.append(
            f'Table header was not recognized, columns were detected heuristically '
            f'(таблиц: {counts["header_unrecognized"]})'
        )
    if counts['small_tables']:
        warnings.append(
            f'Small table skipped (пропущено таблиц: {counts["small_tables"]}) — '
            'выглядят как подписи документа, а не перечень'
        )
    if counts['boilerplate']:
        warnings.append(
            f'{counts["boilerplate"]} служебных строк документа пропущено '
            '(шапка/реквизиты)'
        )
    if counts['implausible']:
        warnings.append(
            f'{counts["implausible"]} строк перечня пропущено: название не похоже на '
            'олимпиаду — проверьте, что нужные олимпиады на месте'
        )
    if counts['flagged']:
        warnings.append(
            f'{counts["flagged"]} записей без слова «олимпиада» в названии — '
            'требуют проверки'
        )

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
