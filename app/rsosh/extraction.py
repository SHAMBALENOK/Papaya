"""Чтение документов РСОШ: PDF, XLSX и изображения.

Три входных формата, три разных источника данных, один общий результат —
страницы с таблицами и отчётом о том, как они получены:

* **XLSX** — нативное чтение ячеек через openpyxl (без OCR): объединённые
  ячейки и переносы строк доступны точно;
* **PDF с текстовым слоем** — таблицы восстанавливаются из структуры
  документа (pdfplumber использует линии рамки);
* **PDF-скан и изображение** — страница рендерится в растр, ориентация
  определяется, дальше работает OCR + реконструкция таблицы по геометрии.

Текстовый слой всегда проверяется первым: OCR там, где текст уже есть, —
это потеря качества и времени.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.rsosh import filetypes, ocr, preprocessing, tables
from app.rsosh.types import Method, RsoshError

logger = logging.getLogger('papaya.rsosh.extraction')

# Страница считается пригодной для текстового слоя, если на ней есть текст.
MIN_TEXT_CHARS_PER_PAGE = 200
# Страницы без текстового слоя (скан) обрабатываются OCR.
MIN_CHARS_FOR_OCR_PAGE = 120


@dataclass
class PageTables:
    """Таблицы одной страницы/листа документа."""

    page: int
    method: Method
    orientation: int = 0
    tables: list[list[list[str]]] = field(default_factory=list)
    chars: int = 0
    confidence: float = 1.0
    issues: list[str] = field(default_factory=list)

    @property
    def rows(self) -> int:
        return sum(len(table) for table in self.tables)


def extract_document(path: str | Path) -> list[PageTables]:
    """Прочитать документ любого поддерживаемого формата."""
    file_path = str(path)
    kind = filetypes.detect(file_path)
    logger.info('rsosh: reading %s as %s', Path(file_path).name, kind)
    if kind == filetypes.XLSX:
        return _extract_xlsx(file_path)
    if kind == filetypes.PDF:
        return _extract_pdf(file_path)
    return [_extract_image_file(file_path)]


# --------------------------------------------------------------------------- XLSX


def _extract_xlsx(path: str) -> list[PageTables]:
    """XLSX: нативное чтение ячеек, без OCR."""
    import openpyxl

    try:
        book = openpyxl.load_workbook(path, data_only=True, read_only=False)
    except Exception as exc:  # noqa: BLE001 - причина в тексте исключения openpyxl
        raise RsoshError(f'Cannot read XLSX: {exc}') from exc

    pages: list[PageTables] = []
    try:
        for index, sheet in enumerate(book.worksheets, start=1):
            issues: list[str] = []
            rows: list[list[str]] = []
            for row in sheet.iter_rows(values_only=True):
                values = [_cell_text(value) for value in row]
                while values and not values[-1]:
                    values.pop()
                if any(value for value in values):
                    rows.append(values)
            if not rows:
                issues.append('Sheet is empty')
            rows = _propagate_merged_cells(sheet, rows)
            tables_ = [rows] if rows else []
            pages.append(
                PageTables(
                    page=index,
                    method='xlsx',
                    tables=tables_,
                    chars=sum(len(cell) for row in rows for cell in row),
                    confidence=1.0,
                    issues=issues,
                )
            )
    finally:
        book.close()
    return pages


def _cell_text(value) -> str:
    if value is None:
        return ''
    return str(value).strip()


def _propagate_merged_cells(sheet, rows: list[list[str]]) -> list[list[str]]:
    """Раздать значение объединённой ячейки по всем строкам диапазона.

    openpyxl отдаёт значение объединённой ячейки только в её левой верхней
    ячейке, поэтому строки внутри диапазона выглядят «пустыми» в этой
    колонке. Без раздачи значения многострочная запись олимпиады распалась бы
    на несколько строк, и в каталоге появились бы обрывки названия.
    """
    try:
        ranges = list(sheet.merged_cells.ranges)
    except AttributeError:  # pragma: no cover - лист без объединений
        return rows
    if not ranges or not rows:
        return rows

    # Номера строк листа соответствуют индексам в rows только если в листе нет
    # полностью пустых строк сверху, поэтому сопоставляем по счётчику.
    for cell_range in ranges:
        if cell_range.max_row == cell_range.min_row:
            continue
        first_row_index = cell_range.min_row - 1
        if not (0 <= first_row_index < len(rows)):
            continue
        source_row = rows[first_row_index]
        if cell_range.min_col > len(source_row):
            continue
        value = source_row[cell_range.min_col - 1]
        if not value:
            continue
        for offset in range(cell_range.max_row - cell_range.min_row + 1):
            row_index = cell_range.min_row - 1 + offset
            if row_index >= len(rows):
                break
            target = rows[row_index]
            while len(target) < cell_range.min_col:
                target.append('')
            if not target[cell_range.min_col - 1]:
                target[cell_range.min_col - 1] = value
    return rows


# --------------------------------------------------------------------------- PDF


def _extract_pdf(path: str) -> list[PageTables]:
    """PDF: сначала текстовый слой, при его нехватке — рендеринг + OCR."""
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - зависимость обязательна
        raise RsoshError('pdfplumber is required to read PDF documents') from exc

    try:
        pdf = pdfplumber.open(path)
    except Exception as exc:  # noqa: BLE001
        raise RsoshError(f'Cannot open PDF: {exc}') from exc

    pages: list[PageTables] = []
    try:
        for index, page in enumerate(pdf.pages, start=1):
            chars = len(page.chars)
            rotation = int(getattr(page, 'rotation', 0) or 0)
            if chars >= MIN_TEXT_CHARS_PER_PAGE:
                text_tables = _tables_from_text_layer(page)
                if text_tables:
                    pages.append(
                        PageTables(
                            page=index,
                            method='text',
                            orientation=rotation % 360,
                            tables=text_tables,
                            chars=chars,
                            confidence=1.0,
                        )
                    )
                    continue
                pages.append(
                    PageTables(
                        page=index,
                        method='text',
                        orientation=rotation % 360,
                        tables=[],
                        chars=chars,
                        confidence=1.0,
                        issues=['No tables found in the text layer'],
                    )
                )
                continue

            # Текстового слоя нет (скан) или он слишком мал — работает OCR.
            pages.append(_ocr_pdf_page(path, index, rotation, chars))
    finally:
        pdf.close()
    return pages


def _tables_from_text_layer(page) -> list[list[list[str]]]:
    """Таблицы страницы из структуры PDF (линии рамки + координаты слов)."""
    tables: list[list[list[str]]] = []
    try:
        found = page.find_tables()
    except Exception:  # noqa: BLE001 - битая геометрия страницы
        return tables

    for table in found:
        try:
            data = table.extract()
        except Exception:  # noqa: BLE001
            continue
        rows = [
            [_cell_text(cell) for cell in row]
            for row in data
            if any(_cell_text(cell) for cell in row)
        ]
        if rows:
            tables.append(rows)
    return tables


def _ocr_pdf_page(
    path: str,
    page_number: int,
    rotation: int,
    chars: int,
) -> PageTables:
    """Отрендерить страницу PDF и распознать её через OCR."""
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover
        raise RsoshError('pypdfium2 is required to rasterize PDF pages') from exc

    from app.core.config import RSOSH_PDF_DPI

    document = pdfium.PdfDocument(path)
    try:
        page = document[page_number - 1]
        scale = (RSOSH_PDF_DPI or 300) / 72.0
        bitmap = page.render(scale=scale)
        image = _pil_to_bgr(bitmap.to_pil())
    except Exception as exc:  # noqa: BLE001
        raise RsoshError(f'Cannot render PDF page {page_number}: {exc}') from exc
    finally:
        try:
            document.close()
        except Exception:  # noqa: BLE001
            pass

    result = _ocr_image(image, page=page_number)
    result.chars = chars
    if chars:
        result.issues.append('Page has a partial text layer, OCR was used as a fallback')
    return result


def _pil_to_bgr(image):
    """PIL-изображение -> BGR-массив OpenCV."""
    import numpy as np

    array = np.array(image.convert('RGB'))
    if array.ndim == 3:
        return np.ascontiguousarray(array[:, :, ::-1])
    return array


# --------------------------------------------------------------------- изображения


def _extract_image_file(path: str) -> PageTables:
    """Изображение (PNG/JPG/JPEG): предобработка + OCR + реконструкция."""
    image = preprocessing.load_image(path)
    return _ocr_image(image, page=1)


def _ocr_image(image, *, page: int) -> PageTables:
    """Общий путь для скана: подготовка, ориентация, OCR, таблица."""
    prepared = preprocessing.prepare(image)
    binary = prepared['image']

    if prepared['ink_ratio'] < 0.002:
        return PageTables(
            page=page,
            method='ocr',
            orientation=0,
            tables=[],
            chars=0,
            confidence=0.0,
            issues=['Page is blank or contains no recognizable text'],
        )

    orientation, orientation_confidence, orientation_issues = _resolve_orientation(
        binary,
        candidates=prepared['candidates'],
    )
    if orientation:
        binary = preprocessing.rotate_cw(binary, orientation)

    binary, skew = preprocessing.straighten(binary)

    words = ocr.ocr_words(binary)
    issues = list(orientation_issues)
    if not words:
        return PageTables(
            page=page,
            method='ocr',
            orientation=orientation,
            tables=[],
            chars=0,
            confidence=0.0,
            issues=issues + ['OCR did not recognize any text on the page'],
        )

    if orientation:
        issues.append(f'Page was rotated by {orientation}° before OCR')
    if skew:
        issues.append(f'Page skew of {skew}° was straightened')

    table = tables.build_table(binary, words)
    matrix = table.as_matrix()
    confidences = [word['conf'] for word in words]
    mean_confidence = round(sum(confidences) / len(confidences) / 100, 3)
    chars = sum(len(word['text']) for word in words)

    return PageTables(
        page=page,
        method='ocr',
        orientation=orientation,
        tables=[matrix] if matrix else [],
        chars=chars,
        confidence=round(mean_confidence * (0.5 + 0.5 * orientation_confidence), 3)
        if orientation
        else mean_confidence,
        issues=issues + table.issues,
    )


def _resolve_orientation(
    binary,
    *,
    candidates: tuple[int, ...],
) -> tuple[int, float, list[str]]:
    """Определить, на сколько градусов по часовой стрелке повернуть страницу.

    Сначала используется OSD tesseract: он определяет угол, не распознавая
    текст, и потому заметно дешевле пробного OCR. Если OSD недоступен или
    отказал, угол выбирается сравнительным распознаванием: для каждого
    кандидата выполняется OCR, и выигрывает вариант, в котором распознано
    больше слов с более высокой уверенностью.
    """
    osd = ocr.osd_rotation(binary)
    if osd is not None:
        rotation, confidence = osd
        if rotation in (0, 90, 180, 270):
            return rotation, confidence, []

    words_per_candidate: dict[int, tuple[int, float]] = {}
    for candidate in candidates:
        rotated = preprocessing.rotate_cw(binary, candidate) if candidate else binary
        words = ocr.ocr_words(rotated)
        if not words:
            words_per_candidate[candidate] = (0, 0.0)
            continue
        mean = sum(word['conf'] for word in words) / len(words)
        words_per_candidate[candidate] = (len(words), mean)

    best = max(words_per_candidate, key=lambda angle: words_per_candidate[angle])
    best_count, best_confidence = words_per_candidate[best]
    if best_count == 0:
        return 0, 0.0, [
            'Page orientation could not be determined: OCR found no text '
            'in any rotation'
        ]

    ordered = sorted(words_per_candidate.values(), reverse=True)
    runner_up = ordered[1] if len(ordered) > 1 else (0, 0.0)
    margin = (best_count - runner_up[0]) / max(1, best_count)
    return best, round(min(1.0, margin), 3), [
        'Page orientation was determined by trial OCR'
    ]
