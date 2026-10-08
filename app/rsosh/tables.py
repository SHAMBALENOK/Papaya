"""Реконструкция таблиц из результатов OCR.

Реальные таблицы РСОШ — это не «текст с табуляцией»:

- ячейки многострочные (название олимпиады занимает 2–4 строки, а соседние
  колонки в это время содержат одну строку);
- часть ячеек объединена по вертикали и горизонтали;
- таблица продолжается на следующей странице, иногда с повтором шапки;
- у страницы может быть повернута и/или «завалена» разметка.

Поэтому таблица восстанавливается по геометрии:

1. слова группируются в строки по вертикальному перекрытию;
2. горизонтальные и вертикальные линии рамки (морфологическая фильтрация)
   дают границы строк и столбцов;
3. ячейка = пересечение полосы строки и полосы столбца, текст собирается
   в порядке чтения, поэтому многострочные и объединённые ячейки не ломаются;
4. если линеек нет (таблица без рамок), применяется запасная эвристика по
   вертикальным промежуткам и горизонтальным разрывам между словами.
"""

import statistics
from dataclasses import dataclass, field

import numpy as np

# Минимальная доля строк, где линия рамки должна иметь чернила. У настоящей
# линии она около 0.8 (линия не тянется через поля скана), у колонки
# плотного текста — около 0.05.
MIN_RULE_CONTINUITY = 0.6


@dataclass
class Cell:
    """Ячейка таблицы."""

    text: str
    row: int
    column: int
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0
    spans: tuple[int, int] = (1, 1)  # (сколько строк, сколько столбцов) занято


@dataclass
class Table:
    """Таблица страницы: строки ячеек + предупреждения."""

    rows: list[list[Cell]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def width(self) -> int:
        return max((len(row) for row in self.rows), default=0)

    def as_matrix(self) -> list[list[str]]:
        return [[cell.text for cell in row] for row in self.rows]

    def is_empty(self) -> bool:
        return not any(
            cell.text.strip() for row in self.rows for cell in row
        )


def _line_tolerance(words: list[dict]) -> float:
    """Вертикальный допуск группировки слов в строку."""
    heights = [word['y1'] - word['y0'] for word in words] or [10.0]
    return max(4.0, statistics.median(heights) * 0.6)


def group_lines(words: list[dict]) -> list[list[dict]]:
    """Сгруппировать слова в строки по вертикальному перекрытию.

    Сортировка по верхней границе, затем строки объединяются, пока их
    вертикальные интервалы перекрываются больше чем на половину меньшего.
    """
    if not words:
        return []
    tolerance = _line_tolerance(words)
    ordered = sorted(words, key=lambda word: (word['y0'], word['x0']))
    lines: list[list[dict]] = []
    current: list[dict] = [ordered[0]]
    current_top = ordered[0]['y0']
    current_bottom = ordered[0]['y1']

    for word in ordered[1:]:
        overlap = min(current_bottom, word['y1']) - max(current_top, word['y0'])
        smaller = min(current_bottom - current_top, word['y1'] - word['y0'])
        if smaller > 0 and overlap >= smaller * 0.5:
            current.append(word)
            current_top = min(current_top, word['y0'])
            current_bottom = max(current_bottom, word['y1'])
            continue
        lines.append(current)
        current = [word]
        current_top = word['y0']
        current_bottom = word['y1']

    lines.append(current)
    for line in lines:
        line.sort(key=lambda word: word['x0'])
    return lines


def _line_boxes(lines: list[list[dict]]) -> list[tuple[int, int]]:
    return [(min(word['y0'] for word in line), max(word['y1'] for word in line)) for line in lines]


def detect_horizontal_rules(binary, words: list[dict]) -> list[int]:
    """Найти горизонтальные линии рамки таблицы (координаты Y).

    Линия — это горизонтальная полоса шириной не меньше трети ширины
    содержимого страницы. Находятся морфологическим открытием с длинным
    горизонтальным ядром.
    """
    import cv2

    if not words:
        return []
    left = min(word['x0'] for word in words)
    right = max(word['x1'] for word in words)
    min_width = max(40, int((right - left) * 0.3))

    inverted = cv2.bitwise_not(binary)
    kernel_width = min(min_width, inverted.shape[1])
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, 1))
    horizontal = cv2.morphologyEx(inverted, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(horizontal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    centers: list[int] = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width >= min_width and height <= max(12, (right - left) * 0.02):
            centers.append(y + height // 2)
    kept = _drop_frame_borders(centers, inverted.shape[0])
    return _cluster_positions(kept, tolerance=6)


def detect_vertical_rules(binary, words: list[dict]) -> list[int]:
    """Найти вертикальные линии рамки таблицы (координаты X).

    Линия рамки тянется через всё содержимое страницы, поэтому ищется
    вертикальное ядро, которое длиннее половины высоты содержимого: такое ядро
    «склеивает» межстрочные промежутки внутри ячейки, но не переходит через
    настоящий разрыв между строками. Плотный текст такое ядро не даёт — в
    колонке букв всегда остаются вертикальные разрывы.

    Чёрная рамка самого скана (по краям кадра) отбрасывается: она относится к
    изображению, а не к таблице, и иначе «съела» бы первую и последнюю
    колонки.
    """
    import cv2

    if not words:
        return []
    inverted = cv2.bitwise_not(binary)
    ink = inverted > 0
    height, width = ink.shape

    # Границы содержимого — по реальному «чернилу», а не по словам: служебные
    # знаки у края скана иначе растягивают высоту содержимого вдвое.
    ink_rows = np.flatnonzero(ink.any(axis=1))
    if ink_rows.size == 0:
        return []
    top = int(ink_rows[0])
    bottom = int(ink_rows[-1])
    content_height = bottom - top
    if content_height <= 0:
        return []

    # Ядро чуть короче половины содержимого: достаточно, чтобы пережить
    # межстрочные разрывы внутри ячейки, но недостаточно для текста.
    kernel_height = max(12, int(content_height * 0.35))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_height))
    vertical = cv2.morphologyEx(inverted, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(vertical, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_height = content_height * 0.45
    max_width = max(8, content_height * 0.01)
    span = ink[top:bottom + 1]
    centers: list[int] = []
    for contour in contours:
        x, y, box_width, box_height = cv2.boundingRect(contour)
        if box_height < min_height or box_width > max_width:
            continue
        center = x + box_width // 2
        if _ink_continuity(span, center) >= MIN_RULE_CONTINUITY:
            centers.append(center)

    kept = _drop_frame_borders(centers, width)
    return _cluster_positions(kept, tolerance=6)


def _ink_continuity(span, center: int) -> float:
    """Доля строк, где в узком окне вокруг ``center`` есть чернила.

    Линия рамки непрерывна по всей высоте, а колонка плотного текста —
    нет: между строками остаются вертикальные разрывы. Это и отличает
    настоящую границу колонки от случайного сгустка букв.
    """
    width = span.shape[1]
    low = max(0, center - 2)
    high = min(width, center + 3)
    if high <= low:
        return 0.0
    return float(span[:, low:high].any(axis=1).mean())


def _drop_frame_borders(centers: list[int], extent: int) -> list[int]:
    """Убрать чёрную рамку скана, а не линии рамки таблицы.

    Скан часто окружён сплошной рамкой в несколько пикселей по краям кадра.
    Она совпадает с краем изображения, поэтому отсекается по границам кадра, а
    настоящие линии таблицы остаются. Работает и по X, и по Y: ``extent`` —
    длина изображения вдоль искомой оси.
    """
    margin = max(4, extent * 0.015)
    return [x for x in centers if margin < x < extent - margin]


def _cluster_positions(positions: list[int], tolerance: int) -> list[int]:
    if not positions:
        return []
    ordered = sorted(positions)
    clusters: list[list[int]] = [[ordered[0]]]
    for value in ordered[1:]:
        if value - clusters[-1][-1] <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [int(statistics.median(cluster)) for cluster in clusters]


def _column_bands_from_gaps(
    lines: list[list[dict]],
    min_gap: float,
) -> list[tuple[float, float]]:
    """Границы столбцов по горизонтальным разрывам между словами."""
    gaps: list[tuple[float, float]] = []
    for line in lines:
        for previous, current in zip(line, line[1:]):
            gap = current['x0'] - previous['x1']
            if gap >= min_gap:
                gaps.append((previous['x1'], current['x0']))
    if not gaps:
        return []

    left = min(word['x0'] for lines_group in lines for word in lines_group)
    right = max(word['x1'] for lines_group in lines for word in lines_group)
    bands: list[tuple[float, float]] = []
    cursor = left
    for gap_start, gap_end in sorted(gaps):
        # Разрыв слишком широк — это уже другая колонка, а не пробел.
        if gap_end - gap_start > (right - left) * 0.25:
            continue
        if gap_start >= cursor:
            bands.append((cursor, gap_start))
            cursor = gap_end
    bands.append((cursor, right))
    return [band for band in bands if band[1] - band[0] > 1]


def _column_index(bands: list[tuple[float, float]], x_center: float) -> int:
    for index, (start, end) in enumerate(bands):
        if start <= x_center <= end:
            return index
    # Центр слова вне полос (редко из-за поворота) — ближайшая полоса.
    distances = [
        (min(abs(x_center - start), abs(x_center - end)), index)
        for index, (start, end) in enumerate(bands)
    ]
    return min(distances)[1] if distances else 0


def _rows_from_gaps(lines: list[list[dict]]) -> list[list[int]]:
    """Сгруппировать строки в строки таблицы по вертикальным промежуткам."""
    boxes = _line_boxes(lines)
    if not boxes:
        return []

    gaps = []
    for index in range(1, len(boxes)):
        gap = boxes[index][0] - boxes[index - 1][1]
        gaps.append(gap)
    if not gaps:
        return [list(range(len(boxes)))]

    heights = [end - start for start, end in boxes]
    line_height = statistics.median(heights) if heights else 10.0
    # Между строками одной ячейки промежуток примерно равен высоте строки,
    # между строками таблицы — заметно больше.
    threshold = max(line_height * 1.6, statistics.median(gaps) * 1.8)

    rows: list[list[int]] = [[0]]
    for index in range(1, len(lines)):
        if gaps[index - 1] > threshold:
            rows.append([index])
        else:
            rows[-1].append(index)
    return rows


def _column_words(words: list[dict], band: tuple[float, float]) -> list[dict]:
    """Слова, целиком попавшие в полосу столбца."""
    start, end = band
    return [word for word in words if start <= word['x0'] and word['x1'] <= end]


def vote_row_boundaries(
    words: list[dict],
    column_bands: list[tuple[float, float]],
    *,
    gap_factor: float = 1.6,
    merge_distance: float = 24.0,
    min_column_ratio: float = 0.5,
) -> list[float]:
    """Границы строк по голосованию вертикальных промежутков.

    У части документов РСОШ таблица нарисована без горизонтальных линий
    рамки: колонки разделены вертикальными линиями, а строки отбиты только
    вертикальным пробелом. Тогда промежуток между строками таблицы виден
    сразу в нескольких колонках, а внутри многострочной ячейки — только в
    одной.

    Поэтому для каждой колонки ищутся её собственные промежутки (заметно
    больше её собственного межстрочного шага), а границей строки считается
    только та, которую подтвердило достаточно колонок с текстом. Так
    пустая строка внутри ячейки не разрезает таблицу.
    """
    filled: list[tuple[float, float, list[list[dict]]]] = []
    for band in column_bands:
        column_words = _column_words(words, band)
        lines = group_lines(column_words)
        if len(lines) >= 2:
            filled.append((band[0], band[1], lines))

    if len(filled) < 2:
        return []

    proposals: list[float] = []
    for _start, _end, lines in filled:
        boxes = _line_boxes(lines)
        steps = [boxes[i + 1][0] - boxes[i][0] for i in range(len(boxes) - 1)]
        step = statistics.median(steps) if steps else 0.0
        for index in range(1, len(boxes)):
            gap = boxes[index][0] - boxes[index - 1][1]
            if gap > max(6.0, step * gap_factor):
                proposals.append((boxes[index - 1][1] + boxes[index][0]) / 2)

    if not proposals:
        return []

    # Близкие предложения (от соседних колонок) объединяются в одну границу.
    votes: list[list[float]] = []
    for y in sorted(proposals):
        if votes and y - votes[-1][-1] <= merge_distance:
            votes[-1].append(y)
        else:
            votes.append([y])

    needed = max(2, int(len(filled) * min_column_ratio))
    return [statistics.median(group) for group in votes if len(group) >= needed]


def _bands_from_edges(edges: list[float]) -> list[tuple[float, float]]:
    """Полосы между соседними границами, без пустых и пересекающихся."""
    ordered = sorted(set(edges))
    bands = [
        (ordered[index], ordered[index + 1])
        for index in range(len(ordered) - 1)
    ]
    return [band for band in bands if band[1] - band[0] > 1]


def _bands_from_line_groups(
    lines: list[list[dict]],
    page_top: float,
    page_bottom: float,
) -> list[tuple[float, float]]:
    """Полосы строк по разрывам между строками текста (запасной путь)."""
    groups = _rows_from_gaps(lines)
    if not groups:
        return [(page_top, page_bottom)]
    bounds = [page_top]
    for group in groups[:-1]:
        last = lines[group[-1]]
        bounds.append(max(word['y1'] for word in last))
    bounds.append(page_bottom)
    return _bands_from_edges(bounds)


def _cell_text(words: list[dict]) -> str:
    """Собрать текст ячейки в порядке чтения."""
    ordered = sorted(words, key=lambda word: (word['y0'], word['x0']))
    parts: list[str] = []
    for word in ordered:
        text = word['text']
        if parts and _needs_space(parts[-1], text):
            parts.append(text)
        else:
            parts.append(text)
    return ' '.join(parts).strip()


def _needs_space(previous: str, current: str) -> bool:
    """Не ставить пробел там, где перенос строки разорвал слово."""
    if previous.endswith('-') and current[:1].islower():
        return False
    return True


def build_table(binary, words: list[dict]) -> Table:
    """Построить таблицу страницы по словам OCR и бинаризованному изображению."""
    if not words:
        return Table()

    lines = group_lines(words)
    heights = [word['y1'] - word['y0'] for word in words]
    line_height = statistics.median(heights) if heights else 10.0

    horizontal_rules = detect_horizontal_rules(binary, words)
    vertical_rules = detect_vertical_rules(binary, words)

    # Полосы столбцов: по вертикальным линиям рамки, иначе — по разрывам.
    min_gap = max(line_height * 1.2, 6.0)
    if len(vertical_rules) >= 2:
        column_bands = [
            (float(vertical_rules[index]), float(vertical_rules[index + 1]))
            for index in range(len(vertical_rules) - 1)
        ]
    else:
        column_bands = _column_bands_from_gaps(lines, min_gap)
    if not column_bands:
        column_bands = [(float(min(word['x0'] for word in words)),
                         float(max(word['x1'] for word in words)))]

    # Полосы строк: между горизонтальными линиями рамки, иначе — по вертикальным
    # промежуткам, которые подтверждает сразу несколько колонок.
    page_top = min(word['y0'] for word in words)
    page_bottom = max(word['y1'] for word in words)
    if len(horizontal_rules) >= 2:
        row_edges = [float(page_top), *map(float, horizontal_rules), float(page_bottom)]
        row_bands = _bands_from_edges(row_edges)
    else:
        boundaries = vote_row_boundaries(words, column_bands)
        if boundaries:
            row_edges = [float(page_top), *boundaries, float(page_bottom)]
            row_bands = _bands_from_edges(row_edges)
        else:
            row_bands = _bands_from_line_groups(lines, page_top, page_bottom)

    table = Table()
    column_count = len(column_bands)

    for row_number, band in enumerate(row_bands):
        top, bottom = band
        cells: list[Cell] = []
        for column, (x_start, x_end) in enumerate(column_bands):
            cell_words = [
                word for word in words
                if word['y1'] > top and word['y0'] < bottom
                and _column_index(column_bands, (word['x0'] + word['x1']) / 2)
                == column
            ]
            text = _cell_text(cell_words) if cell_words else ''
            if cell_words:
                x0 = min(word['x0'] for word in cell_words)
                y0 = min(word['y0'] for word in cell_words)
                x1 = max(word['x1'] for word in cell_words)
                y1 = max(word['y1'] for word in cell_words)
            else:
                x0, y0, x1, y1 = x_start, top, x_end, bottom
            cells.append(
                Cell(
                    text=text,
                    row=row_number,
                    column=column,
                    x0=x0,
                    y0=y0,
                    x1=x1,
                    y1=y1,
                )
            )
        # Пустая строка целиком (например, рамка без текста) не нужна.
        if any(cell.text.strip() for cell in cells):
            table.rows.append(cells)

    if column_count == 1 and len(table.rows) > 3:
        table.issues.append(
            'Table borders were not detected, columns were recovered heuristically'
        )
    if not horizontal_rules and len(table.rows) > 1:
        table.issues.append(
            'Row borders were not detected, rows were recovered by vertical gaps'
        )
    return table


def _band_index(bounds: list[int], value: float) -> int:
    for index in range(len(bounds) - 1):
        if bounds[index] <= value <= bounds[index + 1]:
            return index
    if value < bounds[0]:
        return 0
    return len(bounds) - 2
