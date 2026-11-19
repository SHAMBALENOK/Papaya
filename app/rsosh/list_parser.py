"""Разбор официального перечня РСОШ из PDF-скана.

Официальный перечень — это не «текст с табуляцией», а многостраничная
таблица с шестью колонками:

    № | олимпиада | организатор | профиль | предметы | уровень

Клетки названия и организатора объединены по вертикали: название олимпиады
занимает несколько профилей, поэтому в PDF оно встречается один раз, а в
XLSX повторяется в каждой строке профиля. Строки таблицы продолжаются на
следующей странице, шапка повторяется, а сканы часто повёрнуты на 90°.

Модуль читает скан страница за страницей, восстанавливает геометрию таблицы
по линиям рамки, относит слова OCR к колонкам и «сшивает» строки между
собой. На выходе — :class:`OfficialList`: сезон, шапка, строки профилей и
постраничный отчёт. Ни одно значение не подставляется «на глаз»: если
клетка не распознана, она остаётся пустой, а в ``issues`` появляется
причина.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.core.config import RSOSH_PDF_DPI
from app.rsosh import ocr, preprocessing
from app.rsosh.normalization import clean_cell
from app.rsosh.types import PageReport, RsoshError

logger = logging.getLogger('papaya.rsosh.list_parser')

#: Минимальная высота вертикальной линии таблицы как доля высоты страницы.
MIN_VERTICAL_SPAN = 0.22
#: Максимальная толщина линии (в пикселях) — толстые чёрные пятна не линии.
MAX_LINE_THICKNESS = 24
#: Минимальный горизонтальный отрезок как доля ширины страницы.
MIN_HORIZONTAL_SPAN = 0.28
#: Ширина ядра для поиска горизонтальных линий как доля ширины страницы.
#: Достаточно короткая, чтобы поймать тонкую линию с небольшим наклоном,
#: но длиннее любого слова, поэтому текст за линию не принимается.
HORIZONTAL_KERNEL_SPAN = 0.12
#: Расстояние, в пределах которого линии считаются одной.
LINE_CLUSTER_TOLERANCE = 14
#: Минимальное число вертикальных линий, при котором страница считается
#: таблицей: рамка + пять разделителей колонок.
MIN_TABLE_COLUMNS = 5

#: Пропорции колонок официального перечня — запасной вариант, если линии
#: рамки не распознаны. Значения сняты с реальных сканов (ширина 3000 px).
FALLBACK_COLUMNS = (0.055, 0.097, 0.248, 0.544, 0.696, 0.890, 0.975)

#: С каких слов начинается название олимпиады. Нужно, когда номер строки не
#: распознан: продолжение названия с предыдущей страницы начинается со
#: строчного слова («…интеллекту», «…школьников»), а новая олимпиада — с
#: заглавного («Отраслевая олимпиада школьников…»).
NAME_STARTERS = (
    'всероссийская', 'международная', 'межрегиональная', 'межвузовская',
    'общероссийская', 'объединенная', 'открытая', 'отраслевая',
    'многопрофильная', 'многопредметная', 'московская',
    'санкт-петербургская', 'всесибирская', 'герценовская', 'инженерная',
    'интернет-олимпиада', 'кутафинская', 'плехановская',
    'северо-восточная', 'телевизионная', 'турнир', 'региональный',
    'университетская',
)

_ROMAN_LEVELS = {
    'I': '1', 'II': '2', 'III': '3',
    '1': '1', '2': '2', '3': '3',
    'І': '1', 'ІІ': '2', 'ІІІ': '3',  # кириллическая «І» после OCR
}
_NUMBER = re.compile(r'^\D{0,4}(\d{1,3})[.,)]?$')
_SEASON = re.compile(
    r'(?<!\d)(20\d{2})\s*[/\\–—−-]\s*(\d{2,4})(?!\d)'
)
_ROMAN_TOKEN = re.compile(r'\b(I{1,3}|1|2|3|І{1,3})\b')
_RUSSIAN_WORD = re.compile(r'[А-Яа-яЁё]{3,}')

#: Слова, по которым проверяется ориентация страницы. Это не «словарь
#: олимпиад», а самые частые слова официального перечня: по ним видно, где
#: текст читается, а где перевёрнут.
_ORIENTATION_WORDS = frozenset({
    'олимпиада', 'олимпиады', 'школьников', 'всероссийская', 'перечень',
    'уровень', 'профиль', 'предметы', 'организатор', 'наименование',
    'федеральное', 'государственное', 'образовательное', 'учреждение',
    'высшего', 'образования', 'университет', 'российской', 'федерации',
    'министерство', 'науки', 'приказ', 'год', 'учебный',
})

_HEADER_MARKERS = (
    'наименование', 'организатор', 'профиль', 'профил', 'уровень',
    'предмет', 'специальност', 'направлен', '№', 'п/п',
)


@dataclass
class ListRow:
    """Одна строка перечня: профиль олимпиады в конкретном сезоне."""

    number: str | None
    olympiad: str
    organizer: str
    profile: str
    subjects: str
    level: str | None
    level_raw: str
    page: int
    source_row: int
    source_band: int
    method: str = 'ocr'
    confidence: float = 1.0
    raw: dict[str, str] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    #: Организаторы именно этой строки. В перечне клетка организатора часто
    #: занимает несколько профилей, но у соседних профилей набор организаторов
    #: может отличаться. ``organizer`` остаётся объединением по олимпиаде (его
    #: берёт каталог), а это значение показывает, что стоит в клетке строки.
    organizer_row: str = ''

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ListRow':
        known = {f for f in cls.__dataclass_fields__}  # noqa: SLF001
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class OfficialList:
    """Результат разбора официального перечня."""

    season_label: str | None = None
    title: str | None = None
    headers: list[str] = field(default_factory=list)
    header_source: str | None = None
    rows: list[ListRow] = field(default_factory=list)
    pages: list[PageReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: Перечень прочитан целиком: сезон найден, все таблицы разобраны,
    #: ни одна страница не потеряна. Только по такому документу можно
    #: утверждать, что олимпиада «исчезла из перечня».
    complete: bool = False
    source_pages: int = 0
    detected_tables: int = 0
    text_chars: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            'season_label': self.season_label,
            'title': self.title,
            'headers': list(self.headers),
            'header_source': self.header_source,
            'rows': [row.to_dict() for row in self.rows],
            'pages': [page.to_dict() for page in self.pages],
            'warnings': list(self.warnings),
            'complete': self.complete,
            'source_pages': self.source_pages,
            'detected_tables': self.detected_tables,
            'text_chars': self.text_chars,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'OfficialList':
        known = {f for f in cls.__dataclass_fields__}  # noqa: SLF001
        values = {k: v for k, v in data.items() if k in known}
        if 'rows' in values:
            values['rows'] = [ListRow.from_dict(item) for item in values['rows']]
        if 'pages' in values:
            values['pages'] = [
                PageReport(**item) if isinstance(item, dict) else item
                for item in values['pages']
            ]
        return cls(**values)

    @property
    def olympiads(self) -> list[str]:
        """Уникальные названия олимпиад в порядке первого появления."""
        seen: set[str] = set()
        result: list[str] = []
        for row in self.rows:
            key = row.olympiad.casefold()
            if key and key not in seen:
                seen.add(key)
                result.append(row.olympiad)
        return result


def _is_blank(value: str) -> bool:
    return not (value or '').strip()


def _normalize_number(value: str) -> str | None:
    text = clean_cell(value)
    if not text:
        return None
    match = _NUMBER.match(text)
    if match:
        return str(int(match.group(1)))
    # Номер, склеенный с названием («1 Всероссийская…»), — ошибка OCR;
    # номер всё равно нужен для структуры, но название не обрезается.
    match = re.match(r'^(\d{1,3})\s+', text)
    if match:
        return str(int(match.group(1)))
    return None


def _normalize_level(raw: str) -> tuple[str | None, list[str]]:
    text = clean_cell(raw).upper().replace('І', 'I')
    if not text:
        return None, ['Уровень не распознан']
    tokens = _ROMAN_TOKEN.findall(text)
    levels = {_ROMAN_LEVELS.get(token.upper() or token) for token in tokens}
    levels.discard(None)
    if len(levels) == 1:
        return levels.pop(), []
    if not levels:
        return None, [f'Уровень «{raw}» не похож на I, II или III']
    return None, [f'В уровне «{raw}» несколько значений — проверьте вручную']


def _vertical_bars(
    binary,
    band: tuple[float, float],
    top: float,
    bottom: float,
    *,
    margin: int = 12,
) -> int:
    """Сосчитать вертикальные штрихи в клетке.

    Римские уровни I/II/III и номер «1» в сканах состоят из вертикальных
    штрихов, которые Tesseract часто читает как «|», «H», «fF» или вообще
    теряет. Количество штрихов — это измерение картинки, а не догадка о
    значении: 1, 2 или 3 штриха однозначно соответствуют I, II, III.
    """
    import cv2

    height, width = binary.shape[:2]
    left, right = band
    x0 = max(0, int(left) + margin)
    x1 = min(width, int(right) - margin)
    y0 = max(0, int(top) + 8)
    y1 = min(height, int(bottom) - 8)
    if x1 <= x0 or y1 <= y0:
        return 0
    crop = binary[y0:y1, x0:x1]
    if crop.size == 0:
        return 0
    ink = cv2.bitwise_not(crop)
    # Штрихи считаются по вертикальной проекции: столбцы, в которых чернил
    # больше половины высоты знака, — это вертикальные штрихи. Так «III»
    # распознаётся даже тогда, когда тонкие засечки слипают все три штриха в
    # одну широкую компоненту.
    columns = (ink > 0).sum(axis=0)
    peak = int(columns.max()) if columns.size else 0
    if peak >= 12:
        runs = 0
        active = False
        for value in columns:
            if value >= peak * 0.5:
                if not active:
                    runs += 1
                    active = True
            else:
                active = False
        if 1 <= runs <= 3:
            return runs
    # Запасной путь — отдельные узкие компоненты (старое поведение).
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(ink, 8)
    bars = 0
    for index in range(1, count):
        _x, _y, component_width, component_height, area = stats[index]
        if area < 12 or component_height < 12:
            continue
        if component_width <= max(10, component_height * 0.65):
            bars += 1
    return bars


def _glyph_number(binary, band: tuple[float, float], top: float, bottom: float):
    """Номер строки по картинке, если OCR потерял одиночную «1»."""
    if _vertical_bars(binary, band, top, bottom) == 1:
        return '1'
    return None


def _glyph_level(binary, band: tuple[float, float], top: float, bottom: float):
    """Уровень по числу вертикальных штрихов (I/II/III)."""
    bars = _vertical_bars(binary, band, top, bottom)
    return {1: '1', 2: '2', 3: '3'}.get(bars)


def _cell_crop(
    binary,
    band: tuple[float, float],
    top: float,
    bottom: float,
    *,
    margin: int = 10,
):
    """Вырезать клетку таблицы с полями, чтобы буквы не касались края."""
    import cv2

    height, width = binary.shape[:2]
    x0 = max(0, int(band[0]) + margin)
    x1 = min(width, int(band[1]) - margin)
    y0 = max(0, int(top) + 4)
    y1 = min(height, int(bottom) - 4)
    if x1 <= x0 or y1 <= y0:
        return None
    crop = binary[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    return cv2.copyMakeBorder(crop, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=255)


def _ocr_cell(
    binary,
    band: tuple[float, float],
    top: float,
    bottom: float,
    *,
    whitelist: str | None = None,
) -> str:
    """Распознать одну клетку.

    Узкие колонки (номер и уровень) на полностраничном OCR теряются: одна
    цифра или римская «I» не образуют «блок текста». Вырезанная клетка с
    белыми полями читается как обычная строка.
    """
    import pytesseract

    crop = _cell_crop(binary, band, top, bottom)
    if crop is None:
        return ''
    config = '--psm 6'
    if whitelist:
        config += f' -c tessedit_char_whitelist={whitelist}'
    try:
        text = pytesseract.image_to_string(
            crop, lang=ocr.LANG, config=config, timeout=ocr.OCR_TIMEOUT
        )
    except Exception:  # noqa: BLE001 - OCR недоступен, остаётся картинка
        return ''
    return clean_cell(text.replace('\n', ' '))


def _read_number(
    binary,
    band: tuple[float, float],
    top: float,
    bottom: float,
    *,
    fallback: str,
) -> str | None:
    """Номер строки: сначала клетка, затем штрих «1», затем текст колонки."""
    text = _ocr_cell(binary, band, top, bottom, whitelist='0123456789')
    number = _normalize_number(text)
    if number:
        return number
    number = _normalize_number(fallback)
    if number:
        return number
    if not text.strip():
        return _glyph_number(binary, band, top, bottom)
    return None


def _read_level(
    binary,
    band: tuple[float, float],
    top: float,
    bottom: float,
    *,
    fallback: str,
) -> tuple[str | None, str, list[str]]:
    """Уровень строки: текст колонки, клетка, затем число штрихов.

    Возвращает уровень в формате БД (``'1'/'2'/'3'``), исходный текст и
    замечания. Пустая клетка уровня — это не «нет уровня», а пропуск
    распознавания, поэтому она попадает в замечания.
    """
    level, issues = _normalize_level(fallback)
    if level:
        # Колонка уровня часто отдаёт «I» там, где в документе «II» или
        # «III»: одиночный штрих Tesseract читает как букву. Число штрихов
        # надёжнее текста, поэтому для «I» оно проверяется ещё раз.
        if level == '1':
            bars = _vertical_bars(binary, band, top, bottom)
            if bars in (2, 3):
                return str(bars), fallback, []
        return level, fallback, []

    text = _ocr_cell(binary, band, top, bottom, whitelist='IVX123')
    level, cell_issues = _normalize_level(text)
    if level:
        return level, text, []

    bars = _vertical_bars(binary, band, top, bottom)
    glyph = {1: '1', 2: '2', 3: '3'}.get(bars)
    if glyph:
        return glyph, text or 'I' * bars, []

    raw = fallback or text
    return None, raw, issues or cell_issues or ['Уровень не распознан']


def _season_from_text(text: str) -> str | None:
    candidates: list[str] = []
    for match in _SEASON.finditer(text or ''):
        start = int(match.group(1))
        end_raw = match.group(2)
        if len(end_raw) == 2:
            end = (start // 100) * 100 + int(end_raw)
            if end != start + 1:
                end = start + 1
        else:
            end = int(end_raw)
        if 2000 <= start <= 2100 and end == start + 1:
            candidates.append(f'{start}/{end}')
    if not candidates:
        return None
    # Первое упоминание — заголовок приказа; остальные повторы таблицы.
    return candidates[0]


def _short_season(season_label: str | None) -> str | None:
    if not season_label:
        return None
    match = re.match(r'^(\d{4})/(\d{4})$', season_label)
    if not match:
        return season_label
    return f'{match.group(1)}-{match.group(2)[2:]}'


def _score_text(text: str) -> int:
    lowered = (text or '').lower().replace('ё', 'е')
    words = set(_RUSSIAN_WORD.findall(lowered))
    return sum(1 for word in _ORIENTATION_WORDS if word in words)


def _trial_orientation(image, candidates: tuple[int, ...]) -> tuple[int, float]:
    """Определить поворот пробным OCR, если OSD не уверен.

    Пробный OCR выполняется на уменьшенной копии: для выбора из четырёх
    углов достаточно контура текста, а полный размер страницы здесь только
    замедлил бы импорт.
    """
    import pytesseract

    small = image.copy()
    small.thumbnail((1500, 1500))
    best_angle = 0
    best_score = -1
    scores: list[tuple[int, int]] = []
    for angle in candidates:
        rotated = small.rotate(-angle, expand=True) if angle else small
        try:
            text = pytesseract.image_to_string(
                rotated,
                lang=ocr.LANG,
                config='--psm 6',
                timeout=ocr.OCR_TIMEOUT,
            )
        except Exception:  # noqa: BLE001 - OCR недоступен, остаётся OSD
            continue
        score = _score_text(text)
        scores.append((angle, score))
        if score > best_score:
            best_angle, best_score = angle, score
    if best_score <= 0:
        return 0, 0.0
    ordered = sorted((score for _, score in scores), reverse=True)
    runner_up = ordered[1] if len(ordered) > 1 else 0
    confidence = (best_score - runner_up) / max(1, best_score)
    return best_angle, round(min(1.0, 0.4 + confidence), 3)


def _resolve_orientation(binary) -> tuple[int, float]:
    """На сколько градусов по часовой стрелке повернуть страницу перед OCR."""
    osd = ocr.osd_rotation(binary)
    if osd is not None:
        rotation, confidence = osd
        if rotation in (0, 90, 180, 270) and confidence >= 0.10:
            return rotation, confidence
    candidates = preprocessing.text_direction_candidates(binary)
    angle, confidence = _trial_orientation(
        _to_pil(binary), tuple(dict.fromkeys((*candidates, 0, 90, 180, 270)))
    )
    return angle, confidence


def _to_pil(binary):
    from PIL import Image

    return Image.fromarray(binary)


def _line_pixels(binary, *, axis: str):
    """Найти линии рамки таблицы морфологическим открытием.

    Возвращает центры линий и их длину. Вертикальные линии ищутся высоким
    ядром (1 × 12% высоты): строка текста такой фильтр не переживает.
    Горизонтальные — широким ядром, но заметно короче ширины страницы:
    разделители строк в объединённых ячейках бывают частичными.
    """
    import cv2
    import numpy as np

    ink = cv2.bitwise_not(binary)
    height, width = ink.shape[:2]
    if axis == 'v':
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (1, max(20, int(height * 0.12)))
        )
        minimum_span, maximum_thickness = height * MIN_VERTICAL_SPAN, MAX_LINE_THICKNESS
    else:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (max(20, int(width * HORIZONTAL_KERNEL_SPAN)), 1)
        )
        minimum_span, maximum_thickness = width * MIN_HORIZONTAL_SPAN, MAX_LINE_THICKNESS

    opened = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(
        opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    found: list[tuple[int, int]] = []
    for contour in contours:
        x, y, box_width, box_height = cv2.boundingRect(contour)
        if axis == 'v':
            span, thickness = box_height, box_width
            center = x + box_width // 2
        else:
            span, thickness = box_width, box_height
            center = y + box_height // 2
        if span >= minimum_span and thickness <= maximum_thickness:
            found.append((center, int(span)))
    return found


def _cluster(values: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Схлопнуть близкие линии в одну (скан даёт двойные края).

    Возвращает ``(центр, суммарная_длина)``. Длина нужна, чтобы отличить
    рамку таблицы от случайного штриха.
    """
    if not values:
        return []
    ordered = sorted(values)
    clusters: list[list[tuple[int, int]]] = [[ordered[0]]]
    for item in ordered[1:]:
        if item[0] - clusters[-1][-1][0] <= LINE_CLUSTER_TOLERANCE:
            clusters[-1].append(item)
        else:
            clusters.append([item])
    result: list[tuple[int, int]] = []
    for cluster in clusters:
        total = sum(span for _, span in cluster) or 1
        center = round(sum(center * span for center, span in cluster) / total)
        result.append((center, total))
    return result


def _table_geometry(binary):
    """Вертикальные и горизонтальные линии таблицы на странице."""
    height, width = binary.shape[:2]
    vertical = _cluster(_line_pixels(binary, axis='v'))
    horizontal = _cluster(_line_pixels(binary, axis='h'))
    # Край сканера даёт длинную линию у самой границы листа — это не рамка.
    vertical = [
        item for item in vertical
        if width * 0.018 < item[0] < width * 0.982
    ]
    return sorted(vertical), sorted(horizontal)


def _table_columns(
    binary,
    *,
    vertical: list[tuple[int, int]] | None = None,
    horizontal: list[tuple[int, int]] | None = None,
) -> list[tuple[float, float]] | None:
    """Границы шести колонок таблицы или ``None``, если таблицы нет."""
    height, width = binary.shape[:2]
    if vertical is None or horizontal is None:
        vertical, horizontal = _table_geometry(binary)
    if len(vertical) < MIN_TABLE_COLUMNS or len(horizontal) < 2:
        return None

    # Ровно семь линий — рамка и пять разделителей: это и есть шесть колонок.
    lines = sorted(vertical)
    if len(lines) > 7:
        # Лишние линии — артефакты внутри ячейки. Оставляем семь самых
        # длинных, сохраняя порядок по X.
        longest = sorted(vertical, key=lambda item: item[1], reverse=True)[:7]
        lines = sorted(longest)
    edges = [float(center) for center, _ in lines]
    if len(edges) < 7:
        # Меньше семи линий: рамка могла потеряться. Растягиваем эталонные
        # пропорции на найденный диапазон, а при одной линии — на страницу.
        left = edges[0] if edges else width * 0.03
        right = edges[-1] if len(edges) > 1 else width * 0.98
        if right - left < width * 0.4:
            left, right = width * 0.03, width * 0.98
        span = right - left
        edges = [left + span * start for start in FALLBACK_COLUMNS]
    return list(zip(edges, edges[1:]))[:6]


def _orient_page(binary):
    """Повернуть страницу и вернуть её геометрию.

    OSD ошибается на страницах, целиком занятых таблицей: линии сбивают
    оценку, и он может выбрать угол не той оси. Поэтому выбранный OSD угол
    сверяется с направлением штрихов текста: оно задаёт ось «книжная» (0/180)
    или «альбомная» (90/270) независимо от линий. Если оси расходятся,
    проверяются только два угла оси — по тому, на котором OCR читает текст.
    """
    base, confidence = _resolve_orientation(binary)

    def candidate(angle):
        rotated = preprocessing.rotate_cw(binary, angle) if angle else binary
        rotated, skew = preprocessing.straighten(rotated)
        vertical, horizontal = _table_geometry(rotated)
        return rotated, skew, vertical, horizontal

    # Направление штрихов текста задаёт ось («книжная» 0/180 или
    # «альбомная» 90/270) независимо от линий таблицы. Если OSD выбрал
    # другую ось, сбитый на весь лист таблицей, перепроверяем только углы
    # этой оси. Раньше здесь сравнивалось число горизонтальных и
    # вертикальных линий: у альбомной таблицы на книжной странице строки
    # короче колонок, и эвристика переворачивала правильно прочитанную
    # страницу на 180°, превращая её в мусор.
    candidates = preprocessing.text_direction_candidates(binary)
    if candidates and base not in candidates:
        trial_angle, trial_confidence = _trial_orientation(
            _to_pil(binary), tuple(dict.fromkeys(candidates))
        )
        if trial_confidence >= 0.3:
            base = trial_angle
            confidence = max(confidence, trial_confidence)

    rotated, skew, vertical, horizontal = candidate(base)
    return base, confidence, rotated, skew, vertical, horizontal


def _letters(value: str) -> str:
    return re.sub(r'[^а-яa-z]', '', (value or '').casefold().replace('ё', 'е'))


def _has_marker(text: str, marker: str) -> bool:
    """Найти маркер шапки как отдельное слово, а не часть слова.

    «многопрофильная олимпиада» содержит «профиль» как подстроку, но это
    название олимпиады, а не шапка. Маркер из букв ищется только в начале
    слова, поэтому «многопрофильная» его не активирует.
    """
    if marker.isalpha():
        return re.search(
            rf'(?<![а-яёa-z]){re.escape(marker)}', text
        ) is not None
    return marker in text


def _header_marker_count(text: str) -> int:
    """Сколько разных маркеров шапки встречается в тексте."""
    lowered = (text or '').casefold().replace('ё', 'е')
    return sum(1 for marker in _HEADER_MARKERS if _has_marker(lowered, marker))


def _looks_like_header(text: str) -> bool:
    """Похож ли текст полосы на шапку перечня.

    OCR шапки ошибается в одной-двух буквах («нанменование»), поэтому кроме
    точных маркеров используется сравнение с официальными формулировками.
    Без этого шапка на титульной странице принимается за строку данных.
    """
    lowered = (text or '').casefold().replace('ё', 'е')
    markers = _header_marker_count(lowered)
    if markers >= 1 and (
        'наименование' in lowered
        or 'организатор' in lowered
        or 'уровень' in lowered
        or 'профил' in lowered
        or 'предмет' in lowered
    ):
        return True
    letters = _letters(lowered)
    if len(letters) < 8:
        return False
    from difflib import SequenceMatcher

    references = (_HEADER_A, _HEADER_B, _HEADER_C, _HEADER_D, _HEADER_F,
                  *_HEADER_E_VARIANTS)
    best = 0.0
    for reference in references:
        best = max(
            best,
            SequenceMatcher(None, letters, _letters(reference)).ratio(),
        )
        if best >= 0.62:
            return True
    return False


def _header_band(text: str) -> bool:
    return _looks_like_header(text)


def _cell_text(words: list[dict], *, newline: bool = False) -> str:
    """Собрать текст клетки из слов в порядке чтения.

    Слова уже отобраны по колонке; внутри клетки они могут идти в несколько
    строк. Для названия строки склеиваются пробелом (это одна фраза), для
    организатора — переводом строки (в XLSX каждая организация с новой
    строки).
    """
    if not words:
        return ''
    ordered = sorted(words, key=lambda word: (word['y0'], word['x0']))
    lines: list[list[dict]] = []
    for word in ordered:
        if not lines:
            lines.append([word])
            continue
        previous = lines[-1][-1]
        height = max(1, previous['y1'] - previous['y0'])
        if word['y0'] - previous['y0'] > height * 0.7:
            lines.append([word])
        else:
            lines[-1].append(word)
    parts: list[str] = []
    for line in lines:
        line.sort(key=lambda word: word['x0'])
        parts.append(' '.join(word['text'] for word in line))
    separator = '\n' if newline else ' '
    text = clean_cell(separator.join(parts)).replace('|', ' ').strip()
    return _repair_ocr_text(text)


#: Мусор, который Tesseract ставит вместо знаков препинания: нижняя запятая,
#: подчёркивание, случайные кавычки. Это не часть названия олимпиады.
_OCR_JUNK = re.compile(r'[‚`_]+')
#: Одиночные согласные в конце клетки — обрывок распознавания, а не слово:
#: в русском тексте отдельной согласной буквы быть не может. За буквой может
#: остаться и цифра из соседней колонки.
_TRAILING_LETTER = re.compile(
    r'(?<=\s)[бгджзйлмнпртфхцчшщ](?=\s*\d*\s*$)', re.IGNORECASE
)
#: Устойчивые ошибки распознавания в перечнях: буквы, которые Tesseract
#: регулярно путает («д» и «о», «и» и «н»), и слова, где это уже проверено по
#: сканам. Замены не добавляют информацию — они восстанавливают то, что в
#: документе написано, но прочитано с ошибкой.
_OCR_WORDS = (
    (re.compile(r'\bраднотехник', re.IGNORECASE), 'радиотехник'),
    (re.compile(r'\bбнотехнолог', re.IGNORECASE), 'биотехнолог'),
    (re.compile(r'\bбпотехническ', re.IGNORECASE), 'биотехническ'),
    (re.compile(r'\bнаукн\b', re.IGNORECASE), 'науки'),
    (re.compile(r'\bолимпнада\b', re.IGNORECASE), 'олимпиада'),
    (re.compile(r'\bнамих\b', re.IGNORECASE), 'нами'),
)


#: Строка, в которой нет ни буквы, ни смысла: одинокое число из соседней
#: колонки или россыпь знаков. В перечне такая строка не несёт значения.
_JUNK_LINE = re.compile(r'^\s*(?:\d{1,3}|[^\wА-Яа-яЁё]+)\s*$')
#: Аббревиатуры, которые обязаны остаться заглавными.
_UPPER_KEEP = frozenset({
    'ИКТ', 'ИЗО', 'НТИ', 'ЕГЭ', 'ОГЭ', 'РСОШ', 'СПО', 'ВО', 'ИТ', 'БПЛА',
})


def _soften_caps(value: str, *, min_length: int = 3) -> str:
    """Вернуть строчные буквы слову, распознанному целиком капсом.

    Капс в названии предмета или олимпиады — дефект начертания, а не
    содержание: официальный перечень пишет названия строчными. Правило
    срабатывает только в тексте, где строчных слов уже большинство, и не
    трогает аббревиатуры.
    """
    if len(re.findall(r'[а-яё]{2,}', value)) < 2:
        return value
    pattern = re.compile(rf'\b[А-ЯЁ]{{{min_length},}}\b')
    return pattern.sub(
        lambda match: match.group(0)
        if match.start() == 0 or match.group(0) in _UPPER_KEEP
        else match.group(0).lower(),
        value,
    )


def _repair_ocr_text(text: str) -> str:
    """Убрать типичный мусор OCR, не додумывая содержание.

    Сюда попадают только однозначные дефекты распознавания: перенос внутри
    слова («бизнес- процессов»), нижняя запятая вместо пробела, одиночная
    согласная, приклеившаяся к концу фразы, и путаница «H»/«Н» с «и». Ни одно
    правило не дописывает слова, которых нет в скане.
    """
    if not text:
        return text
    value = _OCR_JUNK.sub(' ', text)
    # Дефис внутри слова не отделяется пробелом: «бизнес-процессов».
    # Заглавная буква после дефиса — тоже часть слова: «Южно-Российская».
    value = re.sub(
        r'(?<=[а-яёa-zА-ЯЁA-Z])-\s+(?=[а-яёa-zА-ЯЁA-Z])', '-', value
    )
    # «H» между русскими словами — это союз «и», а не латинская буква.
    value = re.sub(r'(?<=[а-яё])\s+[HН]\s+(?=[а-яё])', ' и ', value)
    for pattern, replacement in _OCR_WORDS:
        value = pattern.sub(replacement, value)
    value = re.sub(r'[ \t]{2,}', ' ', value)
    lines = []
    for line in value.split('\n'):
        if _JUNK_LINE.match(line):
            continue
        lines.append(_TRAILING_LETTER.sub('', line).rstrip())
    value = '\n'.join(lines).strip()
    # Хвостовой знак «=» — распознанная кавычка «»»: если открытая кавычка
    # осталась без пары, знак в конце строки её закрывает.
    if re.search(r'=\s*$', value) and value.count('«') > value.count('»'):
        value = re.sub(r'\s*=\s*$', '»', value)
    return value.rstrip('= ').strip()


def _tidy_name(text: str) -> str:
    """Поправить регистр только в перечислении предметов внутри названия.

    Название олимпиады может быть намеренно набрано капсом («ИНФОЗНАЙКА»),
    поэтому трогать его целиком нельзя. А список предметов в скобках — это
    обычный текст перечня, там капс означает ошибку распознавания.
    """
    if not text:
        return text
    return re.sub(
        r'\(([^()]*)\)',
        lambda match: f'({_soften_caps(match.group(1))})',
        text,
    )


def _tidy_profile(text: str) -> str:
    """Убрать из названия профиля хвосты соседних клеток.

    В колонке профиля иногда оказывается одинокое число (номер строки из
    соседней колонки) или обрывок заглавными буквами, оставшийся от
    названия олимпиады. Название профиля — это русская фраза, поэтому такой
    хвост отбрасывается, а не исправляется догадкой.
    """
    if not text:
        return text
    value = re.sub(r'\s+\d{1,3}$', '', text)
    # Обрывок может прийти и отдельной клеткой при переносе строки на новую
    # страницу: тогда перед ним нет пробела, поэтому разделитель необязателен.
    value = re.sub(r'(?:^|\s+)[А-ЯЁ]{2,4}\s*[\[\(\{«]\s*$', '', value)
    value = _soften_caps(value)
    value = value.strip(' ,;')
    # Если от названия остались только заглавные буквы без строчных, это не
    # профиль, а обломок соседней клетки.
    if value and not re.search(r'[а-яё]', value):
        return ''
    return value


def _tidy_subjects(text: str) -> str:
    """Привести перечисление предметов к запятым.

    В перечне предметы разделены запятыми, но в скане запятая часто
    сливается с точкой, и OCR читает «науки. информатика». Между тем точка с
    запятой внутри названия предмета не встречается, поэтому «точка +
    пробел» перед строчной буквой — это разделитель.
    """
    if not text:
        return text
    value = re.sub(r'\.\s+(?=[а-яёa-z])', ', ', text)
    value = re.sub(r'\.(?=\s*,)', '', value)
    value = re.sub(r'\s*,\s*', ', ', value)
    # Предметы в перечне пишутся строчными; капс — ошибка распознавания
    # начертания. Аббревиатуры из списка не трогаем.
    value = _soften_caps(value)
    value = re.sub(r'^([А-ЯЁ])([а-яё]+)', lambda m: m.group(1).lower() + m.group(2), value)
    return value.strip(' ,.:;')


def _words_in_band(
    words: list[dict],
    bands: list[tuple[float, float]],
    top: float,
    bottom: float,
) -> list[list[dict]]:
    columns: list[list[dict]] = [[] for _ in bands]
    for word in words:
        center_x = (word['x0'] + word['x1']) / 2
        center_y = (word['y0'] + word['y1']) / 2
        if center_y < top or center_y >= bottom:
            continue
        index = 0
        for position, (left, right) in enumerate(bands):
            if left <= center_x < right:
                index = position
                break
            if center_x < left:
                index = position
                break
            index = position
        columns[index].append(word)
    return columns


def _mean_confidence(words: list[dict]) -> float:
    if not words:
        return 0.0
    return round(sum(float(w.get('conf', 0.0)) for w in words) / len(words) / 100.0, 3)


def _ocr_columns(
    binary, bands: list[tuple[float, float]]
) -> list[list[dict]]:
    """OCR каждой колонки отдельно.

    Полностраничный Tesseract плохо читает шестиколоночную таблицу: слова
    соседних колонок попадают в один «блок текста», а узкие колонки уровней
    теряются. Колонка, вырезанная по линиям рамки, читается как обычный
    текст, а координаты слов смещаются обратно на страницу.
    """
    height, width = binary.shape[:2]
    result: list[list[dict]] = []
    for left, right in bands:
        x0 = max(0, int(left) + 2)
        x1 = min(width, int(right) - 2)
        if x1 <= x0:
            result.append([])
            continue
        crop = binary[:, x0:x1]
        words = ocr.ocr_words(crop, psm=6, min_confidence=25.0)
        for word in words:
            word['x0'] += x0
            word['x1'] += x0
        result.append(words)
    return result


def _columns_of_band(
    columns: list[list[dict]], top: float, bottom: float
) -> list[list[dict]]:
    """Слова каждой колонки, попадающие в горизонтальную полосу строки."""
    result: list[list[dict]] = []
    for column in columns:
        result.append([
            word for word in column
            if top <= (word['y0'] + word['y1']) / 2 < bottom
        ])
    return result


def _header_values(columns: list[list[dict]]) -> list[str]:
    headers = [
        _cell_text(column)
        for column in columns
    ]
    return [value or '' for value in headers]


#: Официальные формулировки шапки перечня. Колонки A–D и F не менялись,
#: менялась только формулировка колонки E — поэтому она выбирается по
#: распознанному тексту документа, а не задаётся одной фразой на все годы.
_HEADER_A = '№ п/п'
_HEADER_B = 'Полное наименование олимпиады'
_HEADER_C = 'Полное наименование организатора (организаторов) олимпиады'
_HEADER_D = 'Профиль олимпиады'
_HEADER_F = 'Уровень олимпиады'
_HEADER_E_VARIANTS = (
    'Общеобразовательные предметы или специальность(и) и направления '
    'подготовки высшего образования',
    'Общеобразовательные предметы или специальность(и) и направление '
    'подготовки высшего образования',
    'Общеобразовательные предметы или укрупненные группы специальностей и '
    'направлений подготовки',
)


def _similarity(first: str, second: str) -> float:
    from difflib import SequenceMatcher

    return SequenceMatcher(
        None,
        (first or '').casefold().replace('ё', 'е'),
        (second or '').casefold().replace('ё', 'е'),
    ).ratio()


def _pick_header(
    header_text: str, season_label: str | None
) -> tuple[list[str], str]:
    """Собрать официальную шапку, выбрав формулировку колонки E.

    Формулировка E приходит из приказа конкретного года: до 2023 года —
    «специальность(и) и направления подготовки», с 2023 — «укрупненные
    группы специальностей и направлений подготовки». Сначала она
    подтверждается распознанным текстом шапки; если шапка не читается,
    восстанавливается по редакции приказа, и импорт помечает это как
    ``inferred``.
    """
    letters = _letters(header_text)
    best_variant = None
    source = 'inferred'
    if 'укрупнен' in letters:
        best_variant = _HEADER_E_VARIANTS[2]
        source = 'document'
    elif 'специальностиинаправлениеподготовки' in letters:
        best_variant = _HEADER_E_VARIANTS[1]
        source = 'document'
    elif 'специальностиинаправленияподготовки' in letters:
        best_variant = _HEADER_E_VARIANTS[0]
        source = 'document'

    if best_variant is None:
        # Серия приказов 2023+ использует «укрупненные группы», более ранние —
        # «специальность(и) и направления». Это не выбор «любимой фразы», а
        # восстановление официальной формулировки по редакции приказа.
        start = 0
        if season_label:
            match = re.match(r'^(\d{4})/', season_label)
            start = int(match.group(1)) if match else 0
        best_variant = (
            _HEADER_E_VARIANTS[2] if start >= 2023 else _HEADER_E_VARIANTS[0]
        )
    return [
        _HEADER_A,
        _HEADER_B,
        _HEADER_C,
        _HEADER_D,
        best_variant,
        _HEADER_F,
    ], source


def _season_from_pages(pages_text: list[str]) -> tuple[str | None, str | None]:
    for text in pages_text:
        season = _season_from_text(text)
        if season:
            return season, None
    return None, (
        'Сезон не найден в документе: не удалось определить учебный год '
        'перечня'
    )


def _page_title(text: str) -> str | None:
    lines = [line.strip() for line in (text or '').splitlines() if line.strip()]
    for line in lines[:8]:
        if 'перечень' in line.casefold():
            return line
    return None


def parse_official_list(
    path: str | Path,
    *,
    max_pages: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> OfficialList:
    """Разобрать официальный перечень РСОШ из PDF-скана.

    ``max_pages`` ограничивает число страниц — нужно для тестов и быстрой
    диагностики. Ограничение выставляет ``complete=False``: по части
    документа нельзя судить об исчезнувших олимпиадах.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover - зависимость обязательна
        raise RsoshError('pypdfium2 is required to rasterize PDF pages') from exc

    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise RsoshError('Document file not found')

    ocr.ensure_available()
    document = pdfium.PdfDocument(str(pdf_path))
    total = len(document)
    limit = min(total, max_pages) if max_pages else total
    result = OfficialList(source_pages=total)
    result.complete = True

    state = _Stitcher()
    header_texts: list[str] = []
    header_collected = False
    season_texts: list[str] = []
    scale = (RSOSH_PDF_DPI or 300) / 72.0
    structure_failed = False

    try:
        for index in range(limit):
            if progress:
                progress(index + 1, limit)
            page_number = index + 1
            try:
                bitmap = document[index].render(scale=scale)
                image = bitmap.to_pil().convert('RGB')
            except Exception as exc:  # noqa: BLE001
                raise RsoshError(
                    f'Cannot render PDF page {page_number}: {exc}'
                ) from exc

            import numpy as np

            array = np.ascontiguousarray(np.array(image)[:, :, ::-1])
            prepared = preprocessing.prepare(array)
            binary = prepared['image']
            angle, orientation_confidence, binary, skew, vertical, horizontal = (
                _orient_page(binary)
            )

            bands = _table_columns(
                binary, vertical=vertical, horizontal=horizontal
            )

            page_issues: list[str] = []
            if angle:
                page_issues.append(f'Page was rotated by {angle}° before OCR')
            if skew:
                page_issues.append(f'Page skew of {skew}° was corrected')

            if bands is None:
                # Страница без таблицы: приказ, титул, пустой лист. Для
                # сезона важен текст приказа, поэтому ориентация проверяется
                # ещё и пробным OCR на первых страницах.
                words = ocr.ocr_words(binary)
                page_text = _cell_text(words)
                if len(page_text) < 20 or page_number <= 6:
                    trial_angle, trial_confidence = _trial_orientation(
                        _to_pil(binary), (0, 90, 180, 270)
                    )
                    if trial_confidence >= 0.45 and trial_angle != angle:
                        angle = trial_angle
                        rotated = (
                            preprocessing.rotate_cw(binary, angle)
                            if angle else binary
                        )
                        rotated, skew = preprocessing.straighten(rotated)
                        binary = rotated
                        words = ocr.ocr_words(binary)
                        page_text = _cell_text(words)
                if len(page_text) >= 20:
                    season_texts.append(page_text)
                result.pages.append(
                    PageReport(
                        page=page_number,
                        method='ocr',
                        orientation=angle,
                        rotation_applied=angle,
                        tables=0,
                        rows=0,
                        chars=len(page_text),
                        confidence=orientation_confidence,
                        issues=page_issues,
                    )
                )
                continue

            result.detected_tables += 1
            # Каждую колонку читаем отдельно: полностраничный OCR путает
            # соседние колонки и теряет однобуквенные (номер, уровень).
            columns = _ocr_columns(binary, bands)
            words = [word for column in columns for word in column]
            page_text = _cell_text(words)
            if len(page_text) >= 20:
                season_texts.append(page_text)
            result.text_chars += len(page_text)
            height, width = binary.shape[:2]
            horizontal_values = [center for center, _ in horizontal]
            table_top = _table_top(horizontal, width, height)
            if len(horizontal_values) < 2:
                # Таблица с вертикальными линиями, но без горизонтальных:
                # строки придётся собирать по разрывам между словами.
                horizontal_values = _rows_from_words(words, height)
                table_top = horizontal_values[0] if horizontal_values else 0
                page_issues.append(
                    'Table borders were not detected: rows were reconstructed '
                    'from text lines'
                )
                structure_failed = True

            # Всё выше первой длинной горизонтальной линии — заголовок
            # приказа и название перечня, а не строки таблицы.
            boundaries = sorted(
                {table_top, *[value for value in horizontal_values if value > table_top], height}
            )
            # Слишком близкие границы дают пустые строки — схлопываем.
            boundaries = _dedupe_boundaries(boundaries, height)

            if not header_collected:
                for header_top, header_bottom in zip(boundaries, boundaries[1:]):
                    header_row = _columns_of_band(
                        columns, header_top, header_bottom
                    )
                    values = [_cell_text(column) for column in header_row]
                    combined = ' '.join(values)
                    if _header_band(combined):
                        header_texts.append(combined)
                        continue
                    if any(values):
                        header_collected = True
                        break

            emitted = state.consume_page(
                columns=columns,
                boundaries=boundaries,
                binary=binary,
                bands=bands,
                page_number=page_number,
            )

            page_issues.extend(state.page_issues)
            state.page_issues = []

            result.pages.append(
                PageReport(
                    page=page_number,
                    method='ocr',
                    orientation=angle,
                    rotation_applied=angle,
                    tables=1,
                    rows=emitted,
                    chars=len(page_text),
                    confidence=min(
                        orientation_confidence or 0.0,
                        _mean_confidence(words),
                    ),
                    issues=page_issues,
                )
            )
    finally:
        try:
            document.close()
        except Exception:  # noqa: BLE001
            pass

    if limit < total:
        result.complete = False
        result.warnings.append(
            f'Обработано {limit} из {total} страниц: перечень прочитан не '
            'полностью'
        )

    season, season_warning = _season_from_pages(season_texts)
    result.season_label = season
    if season_warning:
        result.warnings.append(season_warning)
        result.complete = False

    headers, header_source = _pick_header(' '.join(header_texts), season)
    result.headers = headers
    result.header_source = header_source
    if header_source != 'document':
        structure_failed = True
        result.warnings.append(
            'Table header was not recognized: columns were detected by '
            'geometry'
        )

    result.title = _page_title('\n'.join(season_texts[:3]))

    state.finalize(result)

    if state.pending_name and not state.pending_rows:
        result.warnings.append(
            'В конце документа осталась олимпиада без строк профилей — '
            'проверьте последнюю страницу'
        )
        structure_failed = True

    if not result.rows:
        structure_failed = True
        result.warnings.append(
            'В документе не найдено ни одной строки перечня: проверьте, что '
            'это официальный перечень РСОШ'
        )
    elif len(result.rows) < 10:
        structure_failed = True
        result.warnings.append(
            'Слишком мало строк для официального перечня: результат похож на '
            'частично распознанный документ'
        )

    if structure_failed:
        result.complete = False

    # Повторяющиеся предупреждения (по одному на каждую страницу) схлопываем.
    result.warnings = list(dict.fromkeys(result.warnings))
    return result


def _table_top(
    boundaries: list[tuple[int, int]], width: int, height: int
) -> int:
    """Верх таблицы: первая длинная горизонтальная линия.

    Над таблицей на титульной странице стоит заголовок приказа. Он не должен
    попасть в строки перечня, поэтому верхняя граница — не 0, а линия рамки.
    """
    for center, span in boundaries:
        if span >= width * 0.35:
            return center
    return 0


def _dedupe_boundaries(boundaries: list[int], height: int) -> list[int]:
    merged: list[int] = []
    minimum = max(12, int(height * 0.012))
    for value in sorted(boundaries):
        if not merged or value - merged[-1] >= minimum:
            merged.append(value)
    return merged


def _rows_from_words(words: list[dict], height: int) -> list[int]:
    """Горизонтальные границы строк по проекции слов, если линий нет."""
    if not words:
        return [0, height]
    tops = sorted({word['y0'] for word in words})
    boundaries = [0]
    for top in tops:
        if top - boundaries[-1] > max(12, height * 0.012):
            boundaries.append(top)
    boundaries.append(height)
    return boundaries


def _collect_header(
    columns: list[list[dict]],
    boundaries: list[int],
) -> list[list[dict]]:
    """Собрать шапку: полосы непосредственно перед первой строкой данных.

    Заголовок приказа и название перечня стоят выше таблицы и не должны
    попасть в шапку XLSX. Поэтому сбор идёт не сверху, а снизу: от первой
    строки с номером и названием — вверх, пока полосы выглядят как шапка.
    """
    band_columns: list[list[list[dict]]] = []
    for top, bottom in zip(boundaries, boundaries[1:]):
        row = _columns_of_band(columns, top, bottom)
        texts = [_cell_text(column) for column in row]
        if _normalize_number(texts[0]) and len(texts[1]) > 15:
            break
        band_columns.append(row)

    header: list[list[dict]] = [[] for _ in columns]
    collected = 0
    for row in reversed(band_columns):
        texts = [_cell_text(column) for column in row]
        if not _header_band(' '.join(texts)):
            break
        for position, column in enumerate(row):
            header[position] = list(column) + header[position]
        collected += 1
        if collected >= 4:
            break
    return header


class _Stitcher:
    """Сшивает полосы строк в записи «олимпиада + профиль».

    Клетки названия и организатора в официальном перечне объединены по
    вертикали: одна олимпиада занимает несколько строк профилей, а её
    название может быть разорвано горизонтальными линиями и даже страницами.
    Поэтому сначала собираются группы «олимпиада» (номер, куски названия,
    куски организатора, строки профилей), и только в конце — готовые
    :class:`ListRow` с полным названием и организатором.
    """

    def __init__(self) -> None:
        self.groups: list[dict] = []
        self.current: dict | None = None
        self.page_issues: list[str] = []
        self.row_counts: dict[int, int] = {}
        self.last_number: int | None = None

    def _data_start(
        self,
        columns: list[list[dict]],
        bands_on_page: list[tuple[float, float]],
    ) -> int:
        """Индекс первой полосы данных: всё до шапки — бланк приказа.

        Над таблицей на первой странице стоит штамп «УТВЕРЖДЕНЫ приказом…».
        Он попадает в полосу с линиями рамки и читается как строка перечня.
        Поэтому данные начинаются после последней шапки в верхней части
        страницы. Шапкой считается полоса с двумя и более разными маркерами:
        у строки данных их не больше одного.
        """
        for index, (top, bottom) in enumerate(bands_on_page[:4]):
            row = _columns_of_band(columns, top, bottom)
            text = ' '.join(_cell_text(column) for column in row)
            if _header_band(text) and _header_marker_count(text) >= 2:
                start = index
                while start < len(bands_on_page):
                    row = _columns_of_band(
                        columns, *bands_on_page[start]
                    )
                    text = ' '.join(_cell_text(column) for column in row)
                    if not text.strip() or (
                        _header_band(text) and _header_marker_count(text) >= 2
                    ):
                        start += 1
                        continue
                    break
                return start
        return 0

    def consume_page(
        self,
        *,
        columns: list[list[dict]],
        boundaries: list[int],
        binary,
        bands: list[tuple[float, float]],
        page_number: int,
    ) -> int:
        """Разобрать одну страницу; вернуть число строк профилей."""
        emitted = 0
        bands_on_page = list(zip(boundaries, boundaries[1:]))
        start = self._data_start(columns, bands_on_page)
        # Полоса-«хвост организатора» на границе страницы: после неё новая
        # олимпиада может начинаться без распознанного номера.
        tail_only = False
        for band_index, (top, bottom) in enumerate(
            bands_on_page[start:], start=start
        ):
            tail_before, tail_only = tail_only, False
            row = _columns_of_band(columns, top, bottom)
            texts = [_cell_text(column) for column in row]
            if not any(texts):
                continue

            number = _read_number(
                binary, bands[0], top, bottom, fallback=texts[0]
            )
            name = _tidy_name(texts[1])
            organizer = _cell_text(row[2], newline=True)
            profile = _tidy_profile(texts[3])
            subjects = _tidy_subjects(texts[4])
            level_raw = texts[5]

            # Шапка иногда попадает в полосу данных: номер в первой клетке
            # («№ п/п») читается как число, а название клетки — как название
            # олимпиады. Настоящая шапка набирает несколько разных маркеров
            # (наименование, организатор, профиль, уровень), а в названии
            # олимпиады встречается максимум один («по комплексу предметов»).
            combined = ' '.join(texts)
            if _header_band(combined):
                if _header_marker_count(combined) >= 2 or not number:
                    continue

            if number:
                if _number_is_out_of_order(number, self.last_number):
                    self.page_issues.append(
                        f'Страница {page_number}, полоса {band_index + 1}: '
                        f'номер «{number}» нарушает порядок нумерации — '
                        'проверьте номер строки'
                    )
                self.last_number = _number_value(number) or self.last_number
                self._start_group(number, name, organizer)
                if not name:
                    self.page_issues.append(
                        f'Страница {page_number}, полоса {band_index + 1}: '
                        'номер без названия олимпиады'
                    )
            elif name:
                if self.current is None or (
                    tail_before and _starts_new_olympiad(name)
                ):
                    # Номер потерян, но после хвоста организатора начинается
                    # заголовок новой олимпиады, а не продолжение прошлой.
                    self._start_group(None, name, organizer)
                    self.page_issues.append(
                        f'Страница {page_number}, полоса {band_index + 1}: '
                        'номер олимпиады не распознан'
                    )
                else:
                    self._append_name(name)
                    if organizer:
                        self._append_organizer(organizer)
            elif organizer and not profile and not subjects:
                # Хвост списка организаторов, перенесённый на новую страницу.
                self._append_organizer(organizer)
                if self.current is not None and self.current['rows']:
                    # Это продолжение клетки последней строки, а не всего
                    # перечня: в XLSX оно должно остаться в её строке.
                    last = self.current['rows'][-1]
                    previous = last['raw'].get('organizer') or ''
                    if organizer not in previous:
                        last['raw']['organizer'] = '\n'.join(
                            part for part in (previous, organizer) if part
                        )
                tail_only = True
                continue

            if not (profile or subjects):
                continue

            # Организатор в полосе без названия тоже относится к олимпиаде:
            # без этого клетка организатора обрывается на первой полосе.
            self._append_organizer(organizer)

            # Обрывок, продолжающий клетку предыдущей строки, остаётся в ней:
            # иначе организатор строки обрывается на середине фразы.
            row_organizer = organizer
            if (
                organizer
                and organizer[:1].islower()
                and self.current['rows']
            ):
                last = self.current['rows'][-1]
                previous = last['raw'].get('organizer') or ''
                if previous:
                    last['raw']['organizer'] = f'{previous} {organizer}'
                row_organizer = ''

            level, level_text, level_issues = _read_level(
                binary, bands[5], top, bottom, fallback=level_raw
            )

            # Разрыв страницы пришёлся на середину строки: хвост профиля и
            # предметов идёт без номера и уровня. Это продолжение предыдущей
            # строки, а не новая запись (название при этом уже дописано выше).
            # Продолжение возможно только в начале страницы: в середине
            # пустой уровень означает ошибку OCR, а не перенос, и склеивать
            # две разные строки нельзя.
            if (
                not number
                and level is None
                and band_index - start <= 2
                and self.current is not None
                and self.current['rows']
                and (profile or subjects)
            ):
                last = self.current['rows'][-1]
                if profile and _is_profile_text(profile):
                    last['profile'] = _tidy_profile(
                        _join_words(last['profile'], profile)
                    )
                if subjects:
                    last['subjects'] = _join_continuation(
                        last['subjects'], subjects
                    )
                last['raw']['subjects'] = last['subjects']
                last['issues'].append(
                    'Строка продолжена с предыдущей страницы'
                )
                continue

            if self.current is None:
                self.page_issues.append(
                    f'Страница {page_number}, полоса {band_index + 1}: '
                    'профиль без названия олимпиады — строка пропущена'
                )
                continue

            issues: list[str] = list(level_issues)
            if not profile:
                issues.append('Профиль не распознан')
            if not self._organizer_text():
                issues.append('Организатор не распознан')

            confidence = _mean_confidence(
                [word for column in row for word in column]
            )
            self.current['rows'].append({
                'profile': profile,
                'subjects': subjects,
                'level': level,
                'level_raw': level_text,
                'page': page_number,
                'source_band': band_index + 1,
                'confidence': confidence,
                'raw': {
                    'number': texts[0],
                    'olympiad': name,
                    'organizer': row_organizer,
                    'profile': profile,
                    'subjects': subjects,
                    'level': level_text,
                },
                'issues': issues,
            })
            emitted += 1

        self.row_counts[page_number] = emitted
        return emitted

    def _start_group(self, number, name: str, organizer: str) -> None:
        group = {
            'number': number,
            'name_parts': [name] if name else [],
            'organizer_parts': [organizer] if organizer else [],
            'rows': [],
        }
        self.groups.append(group)
        self.current = group

    def _append_name(self, name: str) -> None:
        if self.current is None or not name:
            return
        existing = ' '.join(self.current['name_parts'])
        existing_norm = existing.casefold().replace('ё', 'е')
        name_norm = name.casefold().replace('ё', 'е')
        if not existing_norm:
            self.current['name_parts'] = [name]
        elif name_norm in existing_norm:
            return
        elif existing_norm in name_norm:
            self.current['name_parts'] = [name]
        else:
            self.current['name_parts'].append(name)

    def _append_organizer(self, organizer: str) -> None:
        """Дописать клетку организатора, не разрывая перенесённую строку.

        Клетка организатора в перечне часто шире одной полосы: текст
        переносится на следующую строку таблицы и приходит отдельным
        обрывком, который начинается со строчного слова («образования
        «Бурятский государственный университет»…»). Такой обрывок —
        продолжение предыдущего, а не новый организатор.
        """
        organizer = (organizer or '').strip()
        if self.current is None or not organizer:
            return
        parts = self.current['organizer_parts']
        existing = '\n'.join(parts)
        if organizer in existing:
            return
        if parts and organizer[:1].islower():
            parts[-1] = f'{parts[-1]} {organizer}'.strip()
            return
        parts.append(organizer)

    def _organizer_text(self) -> str:
        if self.current is None:
            return ''
        return '\n'.join(
            part for part in self.current['organizer_parts'] if part
        )

    def finalize(self, result: OfficialList) -> None:
        """Превратить группы в строки и добавить их в результат."""
        source_row = 0
        for group in self.groups:
            name = clean_cell(' '.join(group['name_parts']))
            organizer = self._organizer_text_for(group)
            if not name:
                if group['rows']:
                    self.page_issues.append(
                        'Олимпиада без названия: строки профилей пропущены'
                    )
                continue
            for row_data in group['rows']:
                source_row += 1
                # Клетка организатора может быть общей на несколько профилей:
                # тогда у строки своего текста нет и берётся общий список.
                row_organizer = (
                    row_data['raw'].get('organizer') or organizer
                )
                result.rows.append(ListRow(
                    number=group['number'],
                    olympiad=name,
                    organizer=organizer,
                    organizer_row=row_organizer,
                    profile=row_data['profile'],
                    subjects=row_data['subjects'],
                    level=row_data['level'],
                    level_raw=row_data['level_raw'],
                    page=row_data['page'],
                    source_row=source_row,
                    source_band=row_data['source_band'],
                    method='ocr',
                    confidence=row_data['confidence'],
                    raw=row_data['raw'],
                    issues=row_data['issues'],
                ))

    @staticmethod
    def _organizer_text_for(group: dict) -> str:
        return '\n'.join(
            part for part in group['organizer_parts'] if part
        )

    @property
    def pending_name(self) -> str:
        if self.current is None:
            return ''
        return clean_cell(' '.join(self.current['name_parts']))

    @property
    def pending_rows(self) -> int:
        if self.current is None:
            return 0
        return len(self.current['rows'])


def _number_value(number: str) -> int | None:
    """Числовой номер строки, если он читается как целое."""
    try:
        return int(str(number).strip())
    except (TypeError, ValueError):
        return None


def _number_is_out_of_order(number: str, previous: int | None) -> bool:
    """Номер повторяется или идёт назад — значит, он прочитан неверно.

    Номера в перечне строго возрастают. Повтор номера или шаг назад не
    исправляется догадкой: клетка остаётся как прочитана, а администратор
    видит предупреждение и проверяет её по скану.
    """
    value = _number_value(number)
    if value is None or previous is None:
        return False
    return value <= previous


def _starts_new_olympiad(name: str) -> bool:
    """Начинается ли полоса с первой строки новой олимпиады.

    Номер строки иногда не распознаётся (номер стёрт или попал в соседнюю
    колонку). Тогда единственный признак новой записи — заглавное слово, с
    которого начинаются названия: «Отраслевая олимпиада школьников…»,
    «Всероссийская…», «Турнир…». Продолжение названия с предыдущей страницы
    начинается со строчного слова или с римского номера года издания.
    """
    text = _tidy_name(name or '')
    if not text:
        return False
    first = text.split()[0]
    if re.fullmatch(r'[IVX]{1,6}', first):
        return True
    if not first[0].isupper():
        return False
    lowered = text.casefold()
    return any(
        lowered == starter or lowered.startswith(starter + ' ')
        for starter in NAME_STARTERS
    )


def _is_profile_text(value: str) -> bool:
    """Похож ли обрывок на профиль, а не на мусор OCR.

    Профиль — это русское название («инфохимия», «в финансовых
    технологиях»). Строка из заглавных букв и скобок («НИЯ [») профилем не
    является и не должна приклеиваться к предыдущей записи.
    """
    return bool(re.search(r'[а-яё]{2}', (value or '').casefold()))


def _join_words(current: str, addition: str) -> str:
    current = (current or '').strip()
    addition = (addition or '').strip()
    if not current:
        return addition
    if not addition:
        return current
    if addition.startswith((',', ';', ':', ')', '.')):
        return f'{current}{addition}'
    if current.endswith(('-', '—', '(')):
        return f'{current}{addition}'
    return f'{current} {addition}'


def _join_continuation(current: str, addition: str) -> str:
    """Приклеить продолжение разорванной клетки к её началу."""
    current = (current or '').strip()
    addition = (addition or '').strip()
    if not current:
        return addition
    if not addition:
        return current
    if current.endswith((',', ';', ':')):
        return f'{current} {addition}'
    if addition.startswith((',', ';', ':')):
        return f'{current}{addition}'
    return f'{current}, {addition}'


def _join_organizer(current: str, addition: str) -> str:
    if not current:
        return addition
    if not addition:
        return current
    return f'{current}\n{addition}'
