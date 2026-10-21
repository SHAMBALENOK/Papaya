"""Превращение таблиц приказа университета в записи «олимпиада → БВИ».

Приказ вуза отличается от перечня РСОШ по структуре: колонки шире и
разнообразнее (направление подготовки, наименование олимпиады, профиль,
предмет, уровень, диплом), шапка часто выведена зеркально, а первая колонка
объединена по вертикали и заполнена только в первой строке группы.

Задача модуля — извлечь из каждой строки **название олимпиады** (по нему
строка сопоставляется с существующей олимпиадой каталога) и распознанные
характеристики строки (направление, профиль, предмет, уровень, диплом,
сезон). Характеристики не создают отдельных сущностей: Papaya не моделирует
сезоны и профили, поэтому они сохраняются как есть рядом со связью БВИ.

Названия олимпиад этот модуль НЕ создаёт: приказ ссылается на существующий
каталог, а не пополняет его.
"""

import logging
import re

from app.database.search import normalize_name
from app.rsosh.extraction import PageTables
from app.rsosh.normalization import (
    clean_cell,
    is_boilerplate,
    is_noise,
    looks_like_header,
    maybe_reverse,
    mentions_olympiad,
    normalize_olympiad_name,
)
from app.university.types import PageReport, UniversityRecord

logger = logging.getLogger('papaya.university.parsing')

# Таблица из стольких и менее строк — это шапка письма/реквизиты, а не приказ.
MIN_TABLE_ROWS = 3
# Сколько первых строк проверяются на шапку.
HEADER_SEARCH_ROWS = 4
# Строка-шапка должна быть заполнена минимум на половину.
HEADER_FILL_RATIO = 0.5

# Синонимы колонки «наименование олимпиады». Приказ вуза может называть её
# по-разному, поэтому колонка ищется по набору подстрок, а не по одной.
NAME_COLUMN_MARKERS = (
    'наименован олимпиад',
    'наименование олимпиад',
    'название олимпиад',
    'наименовани олимпиад',
    'олимпиад во',
    'олимпиад',
)
# Колонка направления подготовки / специальности (обычно самая левая,
# объединённая по вертикали).
DIRECTION_COLUMN_MARKERS = (
    'направлени',
    'специальност',
    'укрупненн',
    'образовательн программ',
    'код и наименование',
)
PROFILE_COLUMN_MARKERS = ('профил',)
SUBJECT_COLUMN_MARKERS = (
    'предмет',
    'общеобразовательн',
    'профильн предмет',
)
LEVEL_COLUMN_MARKERS = ('уровен',)
DIPLOMA_COLUMN_MARKERS = ('диплом', 'результат', 'льгот', 'прав')

# Синонимы, по которым распознаётся колонка с олимпиадой в бесполезной шапке:
# это самая текстовая колонка, упоминающая «олимпиаду».
OLYMPIAD_HINT_MARKERS = ('олимпиад',)

# Мусорные края ячейки (рамки скана, маркеры списка).
EDGE_TRIM = ' \t\n\r|,;-—–.'
# Слова из трёх и более кириллических букв — признак настоящего текста.
RUSSIAN_WORD = re.compile(r'[А-Яа-яЁё]{3,}')
# Ограничители для распознавания сезона в тексте приказа.
SEASON = re.compile(r'\b(20\d{2})\s*[/–-]\s*(20\d{2})\b')
YEAR = re.compile(r'\b(20\d{2})\b')


def _fill_ratio(row: list[str]) -> float:
    if not row:
        return 0.0
    return len([cell for cell in row if clean_cell(cell)]) / len(row)


def _fold(value: str) -> str:
    return clean_cell(maybe_reverse(value)).casefold().replace('ё', 'е')


def _reversed_lookups(value: str) -> tuple[str, str]:
    """Оба прочтения ячейки: обычное и зеркальное.

    Шапку приказа нередко печатают зеркально («еинелварпаН иквотогдоп»), и
    ``maybe_reverse`` разворачивает только те ячейки, где есть её словарь
    маркеров. Университетские заголовки («направление подготовки») в этот
    словарь не входят, поэтому колонка ищется сразу в двух прочтениях.
    """
    text = clean_cell(value)
    return text.casefold().replace('ё', 'е'), text[::-1].casefold().replace('ё', 'е')


def _is_header_row(row: list[str], next_row: list[str] | None = None) -> bool:
    """Похожа ли строка на шапку таблицы приказа.

    Шапка приказа вуза — это строка заголовков колонок. Названия олимпиад в
    ней не стоят, поэтому достаточно двух опознанных заголовков, либо одного
    короткого заголовка, когда следующая строка явно длиннее (шапка из одного
    слова над переносами строки).
    """
    if _fill_ratio(row) < HEADER_FILL_RATIO:
        return False
    filled = [clean_cell(maybe_reverse(cell)) for cell in row if clean_cell(cell)]
    matches = sum(1 for cell in filled if looks_like_header(cell))
    if matches >= 2:
        return True
    if matches == 1 and next_row is not None and all(len(cell) <= 25 for cell in filled):
        longer = [clean_cell(maybe_reverse(cell)) for cell in next_row]
        return any(len(cell) > 25 for cell in longer)
    return False


def _find_header_row(rows: list[list[str]]) -> int | None:
    limit = min(HEADER_SEARCH_ROWS, len(rows))
    for index in range(limit):
        following = rows[index + 1] if index + 1 < len(rows) else None
        if _is_header_row(rows[index], following):
            return index
    return None


def _column_by_markers(
    header: list[str],
    markers: tuple[str, ...],
    *,
    exclude: set[int] | None = None,
) -> int | None:
    """Индекс колонки шапки, чьё название совпало с одним из ``markers``.

    Совпадение ищется в обоих прочтениях ячейки (обычном и зеркальном): шапку
    приказа часто печатают зеркально. Совпавшие ранее колонки исключаются,
    иначе один и тот же заголовок с двумя маркерами («Предмет … результаты»)
    перетянул бы на себя соседнюю роль.
    """
    exclude = exclude or set()
    for index, cell in enumerate(header):
        if index in exclude:
            continue
        forward, backward = _reversed_lookups(cell)
        if not forward:
            continue
        if any(marker in forward or marker in backward for marker in markers):
            return index
    return None


def _best_name_index(rows: list[list[str]], width: int) -> int | None:
    """Колонка названия по содержимому, если шапка бесполезна.

    Название — самая «текстовая» колонка с упоминанием олимпиады. Колонка
    направления тоже длинная, но олимпиаду не называет (часто это код и
    специальность), поэтому бонус за упоминание олимпиады решающий.
    """
    filled = [0] * width
    score = [0.0] * width
    for row in rows:
        for index in range(min(width, len(row))):
            text = clean_cell(row[index])
            if not RUSSIAN_WORD.search(text or ''):
                continue
            filled[index] += 1
            score[index] += len(text) + (3000.0 if mentions_olympiad(text) else 0.0)
    if not filled or max(filled) <= 0:
        return None
    best = max(filled)
    threshold = max(1.0, best * 0.5)
    candidates = [i for i, count in enumerate(filled) if count >= threshold]
    if not candidates:
        return None
    return max(candidates, key=lambda index: (score[index], -index))


def _propagate_merged_column(rows: list[list[str]], column: int) -> None:
    """Раздать значение объединённой ячейки вниз по пустым строкам.

    В приказах вузов первая колонка (направление подготовки) объединена по
    вертикали: значение стоит только в первой строке группы, а следующие
    строки в этой колонке пусты. Без раздачи каждая строка приказа выглядела
    бы как отдельное направление, и связь теряла бы контекст.
    """
    last = ''
    for row in rows:
        if column >= len(row):
            continue
        value = clean_cell(row[column])
        if value:
            last = value
        elif last:
            row[column] = last


def _row_items(rows: list[list[str]], index: int | None) -> list[str]:
    if index is None:
        return [''] * len(rows)
    return [
        clean_cell(row[index]) if index < len(row) else '' for row in rows
    ]


def _resolve_columns(
    header: list[str],
    *,
    name_index: int | None,
) -> dict[str, int]:
    """Колонки характеристик по синонимам шапки (каждая — не более одной роли).

    Порядок назначения — от самых специфичных заголовков к общим: колонка,
    уже получившая роль, исключается из дальнейшего поиска. Так «Предмет …
    результаты …» становится предметом, а не дипломом, а «Диплом» рядом с ним
    остаётся дипломом.
    """
    used: set[int] = set()
    if name_index is not None:
        used.add(name_index)

    def take(markers: tuple[str, ...]) -> int | None:
        index = _column_by_markers(header, markers, exclude=used)
        if index is not None:
            used.add(index)
        return index

    columns = {
        'direction': take(DIRECTION_COLUMN_MARKERS),
        'level': take(LEVEL_COLUMN_MARKERS),
        'profile': take(PROFILE_COLUMN_MARKERS),
        'subject': take(SUBJECT_COLUMN_MARKERS),
        'diploma': take(DIPLOMA_COLUMN_MARKERS),
    }
    return {role: index for role, index in columns.items() if index is not None}


def _meta_from_row(
    row: list[str],
    columns: dict[str, int],
) -> dict:
    """Распознанные характеристики строки приказа по разрешённым колонкам."""

    def value_at(index: int | None) -> str | None:
        if index is None or index >= len(row):
            return None
        text = clean_cell(row[index])
        return text or None

    meta = {
        'direction': value_at(columns.get('direction')),
        'profile': value_at(columns.get('profile')),
        'subject': value_at(columns.get('subject')),
        'level': value_at(columns.get('level')),
        'diploma': value_at(columns.get('diploma')),
    }
    return {key: value for key, value in meta.items() if value}


def _plausible_name(value: str) -> str | None:
    """Название олимпиады из ячейки — или ``None``, если это не оно.

    Отделяет настоящие названия от служебных строк (шапка письма, реквизиты
    вуза) и от обрывков. Название должно содержать русский текст; строка без
    слова «олимпиада» допускается (например «Турнир имени М.В. Ломоносова»),
    но помечается отдельно вызывающим кодом.
    """
    text = normalize_olympiad_name(value)
    if not text or len(text) < 5 or not RUSSIAN_WORD.search(text):
        return None
    folded = text.casefold()
    if is_boilerplate(text):
        return None
    if is_noise(text):
        return None
    # Строка-реквизит вуза («федеральное государственное … учреждение») — это
    # не олимпиада, даже если стоит в колонке названия.
    if 'образовательн' in folded and 'учреждени' in folded:
        return None
    if 'министерств' in folded:
        return None
    tokens = [token for token in re.split(r'\s+', text) if token.strip(' |,.«»"-')]
    if len(tokens) < 2:
        return None
    stripped = text.lstrip(' \t«"\'>|_—–-')
    if not stripped or not (stripped[0].isupper() or stripped[0].isdigit()):
        return None
    return text


def extract_university(pages: list[PageTables]) -> dict:
    """Определить вуз, которому принадлежит приказ.

    Реквизиты вуза стоят в шапке письма (первая таблица каждой страницы):
    «Министерство …» и полное наименование учреждения с кратким названием в
    скобках («(Университет ИТМО)»). Возвращается лучшее найденное наименование;
    администратор подтверждает или заменяет его в окне проверки.
    """
    candidates: list[str] = []
    for page in pages:
        for table in page.tables:
            # Реквизиты вуза стоят в шапке письма — это короткая таблица (без
            # шапки колонок и без строк приказа). В большой таблице приказа
            # «университет» встречается в названиях олимпиад («… университета»),
            # и без этого ограничения вузом становилась бы олимпиада.
            rows = [row for row in table if any(clean_cell(cell) for cell in row)]
            if not rows or len(rows) >= MIN_TABLE_ROWS or _find_header_row(rows) is not None:
                continue
            for row in rows:
                for cell in row:
                    text = clean_cell(maybe_reverse(cell))
                    folded = text.casefold()
                    if not text or len(text) < 8:
                        continue
                    if 'университет' in folded or 'институт' in folded:
                        # Министерство — не вуз, хотя в его названии есть
                        # «образования»: отбрасываем строки с «министерств».
                        if 'министерств' in folded:
                            continue
                        candidates.append(text)
    if not candidates:
        return {'name': None, 'name_norm': None}

    # Самое длинное наименование — это полное название учреждения; краткое
    # («(Университет ИТМО)») идёт следом в той же ячейке, поэтому берём из
    # полного его краткую форму, если она есть в скобках.
    best = max(candidates, key=len)
    short = re.search(r'[«"]([^«»"]+)[»"]\s*\(([^()]+)\)', best)
    name = best
    if short:
        # «(Университет ИТМО)» — читаемое краткое имя: по нему вуз и ищется.
        name = clean_cell(short.group(2)) or best
    return {'name': name, 'name_norm': normalize_name(name)}


def _table_records(
    table: list[list[str]],
    page_number: int,
    *,
    known_header: list[str] | None = None,
    known_name_index: int | None = None,
) -> tuple[list[UniversityRecord], list[str], list[str] | None]:
    """Записи одной таблицы приказа, предупреждения и найденная шапка.

    ``known_header`` — шапка, найденная ранее для таблиц такой же ширины.
    В приказе шапка печатается на первой странице, а на следующих её нет:
    без памяти о шапке страница 2 и далее пропускалась бы целиком.
    """
    issues: list[str] = []
    rows = [row for row in table if any(clean_cell(cell) for cell in row)]
    if len(rows) < MIN_TABLE_ROWS and known_header is None:
        # Шапка письма (министерство + вуз) или подпись — не приказ. Порог не
        # применяется, когда шапка этой ширины уже найдена: тогда таблица
        # заведомо приказ, а короткой она может быть из-за разрыва страницы.
        return [], issues, known_header

    header: list[str] = list(known_header or [])
    body = rows
    header_position = _find_header_row(rows)
    if header_position is not None:
        header = [clean_cell(maybe_reverse(cell)) for cell in rows[header_position]]
        body = rows[header_position + 1:]
    elif not known_header:
        # Ни своей шапки, ни remembered нет: это не таблица приказа.
        return [], issues, known_header

    if not body:
        return [], issues, header or None

    width = max((len(row) for row in rows), default=0)
    name_index = known_name_index
    if name_index is None:
        name_index = _column_by_markers(header, NAME_COLUMN_MARKERS)
    if name_index is None:
        name_index = _best_name_index(body, width)
    if name_index is None:
        return [], issues, header or None

    columns = _resolve_columns(header, name_index=name_index)
    # Объединённая первая колонка (направление) раздаётся вниз до чтения meta:
    # значение стоит только в первой строке группы.
    if 'direction' in columns:
        _propagate_merged_column(body, columns['direction'])

    records: list[UniversityRecord] = []
    for position, row in enumerate(body):
        if _is_header_row(row):
            # Повтор шапки на следующей странице.
            continue
        raw = clean_cell(row[name_index]) if name_index < len(row) else ''
        if not raw or is_noise(raw) or is_boilerplate(raw):
            continue
        name = _plausible_name(raw)
        if name is None:
            continue
        meta = _meta_from_row(row, columns)
        record_issues: list[str] = []
        if not mentions_olympiad(name):
            record_issues.append(
                'В названии нет слова «олимпиада» — проверьте сопоставление'
            )
        records.append(
            UniversityRecord(
                olympiad_name=name,
                name_norm=normalize_name(name),
                meta=meta,
                page=page_number,
                row=position,
                raw=raw,
                issues=record_issues,
            )
        )
    return records, issues, header or None


def parse_pages(
    pages: list[PageTables],
) -> tuple[list[UniversityRecord], list[str], dict]:
    """Собрать записи приказа из всех страниц документа.

    Возвращает записи, предупреждения и распознанные реквизиты вуза.
    """
    records: list[UniversityRecord] = []
    warnings: list[str] = []
    seen: dict[str, int] = {}
    # Шапка и колонка названия запоминаются по ширине таблицы: на следующих
    # страницах шапки нет, но раскладка та же.
    headers: dict[int, list[str]] = {}
    name_indexes: dict[int, int | None] = {}

    for page in pages:
        for table in page.tables:
            if not table:
                continue
            width = max((len(row) for row in table), default=0)
            known_header = headers.get(width)
            known_name_index = name_indexes.get(width)
            page_records, _issues, header = _table_records(
                table,
                page.page,
                known_header=known_header,
                known_name_index=known_name_index,
            )
            if header and width not in headers:
                headers[width] = header
                name_indexes[width] = _column_by_markers(
                    header, NAME_COLUMN_MARKERS
                )
            for record in page_records:
                count = seen.get(record.name_norm, 0)
                seen[record.name_norm] = count + 1
                records.append(record)

    repeated = sorted(
        {record.olympiad_name for record in records if seen[record.name_norm] > 1}
    )
    for name in repeated:
        warnings.append(
            f'Олимпиада «{name}» встречается в документе несколько раз — '
            'связь БВИ создаётся одна'
        )

    university = extract_university(pages)
    if not university.get('name'):
        warnings.append(
            'Не удалось определить университет из документа: выберите вуз вручную'
        )

    flagged = sum(1 for record in records if record.issues)
    if flagged:
        warnings.append(
            f'{flagged} записей без слова «олимпиада» — требуют проверки'
        )

    logger.info('university: parsed %s records', len(records))
    return records, _dedupe(warnings), university


def _dedupe(warnings: list[str]) -> list[str]:
    unique: list[str] = []
    for warning in warnings:
        if warning not in unique:
            unique.append(warning)
    return unique


def build_page_reports(pages: list[PageTables]) -> list[PageReport]:
    """Отчёт по страницам: метод чтения, число таблиц, уверенность."""
    reports: list[PageReport] = []
    for page in pages:
        reports.append(
            PageReport(
                page=page.page,
                method=page.method,
                orientation=page.orientation,
                rotation_applied=0,
                tables=len(page.tables),
                rows=page.rows,
                chars=page.chars,
                confidence=page.confidence,
                issues=list(page.issues),
            )
        )
    return reports
