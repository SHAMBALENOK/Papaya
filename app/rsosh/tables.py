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
    return _cluster_positions(centers, tolerance=6)


def detect_vertical_rules(binary, words: list[dict]) -> list[int]:
    """Найти вертикальные линии рамки таблицы (координаты X)."""
    import cv2

    if not words:
        return []
    top = min(word['y0'] for word in words)
    bottom = max(word['y1'] for word in words)
    min_height = max(30, int((bottom - top) * 0.2))

    inverted = cv2.bitwise_not(binary)
    kernel_height = min(min_height, inverted.shape[0])
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_height))
    vertical = cv2.morphologyEx(inverted, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(vertical, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    centers: list[int] = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if height >= min_height and width <= max(12, (bottom - top) * 0.02):
            centers.append(x + width // 2)
    return _cluster_positions(centers, tolerance=6)


def _cluster_positions(positions: list[int], tolerance: int) -> list[int]:
    if not positions:
        return []
    ordered = sorted(positions)
    clusters = [ordered]
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

    # Полосы строк: между горизонтальными линиями рамки.
    if len(horizontal_rules) >= 2:
        bounds = horizontal_rules
        row_groups: list[list[int]] = []
        for index, line in enumerate(lines):
            center = (line[0]['y0'] + line[-1]['y1']) / 2
            band = _band_index(bounds, center)
            row_groups.append((band, index))
        rows_by_band: dict[int, list[int]] = {}
        for band, index in row_groups:
            rows_by_band.setdefault(band, []).append(index)
        row_index_map = [
            (band, sorted(indexes)) for band, indexes in sorted(rows_by_band.items())
        ]
    else:
        row_index_map = [
            (index, indexes) for index, indexes in enumerate(_rows_from_gaps(lines))
        ]

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

    table = Table()
    for row_number, (_band, line_indexes) in enumerate(row_index_map):
        row_cells: dict[int, list[dict]] = {}
        bounds: dict[int, list[float]] = {}
        for line_index in line_indexes:
            for word in lines[line_index]:
                center = (word['x0'] + word['x1']) / 2
                column = _column_index(column_bands, center)
                row_cells.setdefault(column, []).append(word)
                current = bounds.setdefault(
                    column, [word['x0'], word['y0'], word['x1'], word['y1']]
                )
                current[0] = min(current[0], word['x0'])
                current[1] = min(current[1], word['y0'])
                current[2] = max(current[2], word['x1'])
                current[3] = max(current[3], word['y1'])

        cells: list[Cell] = []
        for column in sorted(row_cells):
            x0, y0, x1, y1 = bounds[column]
            cells.append(
                Cell(
                    text=_cell_text(row_cells[column]),
                    row=row_number,
                    column=column,
                    x0=x0,
                    y0=y0,
                    x1=x1,
                    y1=y1,
                )
            )
        if cells:
            table.rows.append(cells)

    if len(column_bands) == 1 and len(table.rows) > 3:
        table.issues.append(
            'Table borders were not detected, columns were recovered heuristically'
        )
    return table


def _band_index(bounds: list[int], value: float) -> int:
    for index in range(len(bounds) - 1):
        if bounds[index] <= value <= bounds[index + 1]:
            return index
    if value < bounds[0]:
        return 0
    return len(bounds) - 2
