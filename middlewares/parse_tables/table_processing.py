import re
from pathlib import Path

import easyocr
from openpyxl import Workbook
from openpyxl.styles import Border, Side, PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter


# ── Стили ────────────────────────────────────────────────────────────────────

THIN     = Side(style="thin")
BORDER   = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HDR_FILL = PatternFill("solid", fgColor="4F81BD")
HDR_FONT = Font(bold=True, color="FFFFFF", size=11)
ALT_FILL = PatternFill("solid", fgColor="DCE6F1")
STD_FILL = PatternFill("solid", fgColor="FFFFFF")
STD_FONT = Font(size=11)


# ── OCR + кластеризация ──────────────────────────────────────────────────────

def _extract_rows_from_image(
    img_path: Path,
    reader: easyocr.Reader,
    row_tolerance: int = 15,
) -> list[list[str]]:
    """
    Распознаёт текст на изображении и группирует слова в строки и столбцы.

    Args:
        img_path:       Путь к PNG-файлу.
        reader:         Инициализированный EasyOCR Reader.
        row_tolerance:  Допуск по Y (px) для объединения слов в одну строку.

    Returns:
        Двумерный список: строки × столбцы.
    """
    # EasyOCR возвращает: [(bbox, text, confidence), ...]
    # bbox = [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
    raw_results = reader.readtext(
        str(img_path),
        detail=1,
        paragraph=False,
    )

    # Фильтруем: только уверенные и непустые
    words = []
    for bbox, text, conf in raw_results:
        text = text.strip()
        if not text or conf < 0.25:
            continue
        # Средняя Y-координата (центр слова по вертикали)
        y_center = sum(pt[1] for pt in bbox) / len(bbox)
        # Левая X-координата
        x_left = min(pt[0] for pt in bbox)
        # Правая X-координата
        x_right = max(pt[0] for pt in bbox)
        words.append({
            "text":    text,
            "y":       y_center,
            "x_left":  x_left,
            "x_right": x_right,
        })

    if not words:
        return []

    # ── 1. Кластеризация по Y → строки ───────────────────────────────────────
    words.sort(key=lambda w: w["y"])

    rows: list[list[dict]] = []
    current_row: list[dict] = [words[0]]
    row_y = words[0]["y"]

    for word in words[1:]:
        if abs(word["y"] - row_y) <= row_tolerance:
            current_row.append(word)
        else:
            rows.append(current_row)
            current_row = [word]
            row_y = word["y"]
    rows.append(current_row)

    # Сортируем слова внутри каждой строки по X
    for row in rows:
        row.sort(key=lambda w: w["x_left"])

    # ── 2. Определение столбцов ──────────────────────────────────────────────
    # Находим глобальные X-границы всех слов для определения колонок
    # Используем самую длинную строку как референс
    ref_row = max(rows, key=len)
    n_cols = len(ref_row)

    if n_cols == 0:
        return []

    # Центры столбцов из референсной строки
    col_centers = [
        (w["x_left"] + w["x_right"]) / 2 for w in ref_row
    ]

    def assign_col(word: dict) -> int:
        """Назначает слово ближайшему столбцу по X-координате."""
        word_center = (word["x_left"] + word["x_right"]) / 2
        return min(range(n_cols), key=lambda c: abs(word_center - col_centers[c]))

    # ── 3. Сборка таблицы ────────────────────────────────────────────────────
    table: list[list[str]] = []
    for row_words in rows:
        cells = [""] * n_cols
        for word in row_words:
            col = assign_col(word)
            if cells[col]:
                cells[col] += " " + word["text"]
            else:
                cells[col] = word["text"]
        table.append(cells)

    return table


# ── Запись в Excel ───────────────────────────────────────────────────────────

def _write_table_to_sheet(
    ws,
    all_rows: list[list[str]],
    has_header: bool = True,
) -> None:
    """Записывает единую таблицу на лист Excel со стилями."""
    if not all_rows:
        ws.cell(row=1, column=1, value="Таблиц не обнаружено")
        return

    n_cols = max(len(row) for row in all_rows)

    for row_idx, row_data in enumerate(all_rows):
        excel_row = row_idx + 1
        is_header = has_header and row_idx == 0
        is_alt    = (not is_header) and (row_idx % 2 == 0)

        for col_idx in range(n_cols):
            value = row_data[col_idx] if col_idx < len(row_data) else ""
            cell  = ws.cell(row=excel_row, column=col_idx + 1, value=value)

            cell.border    = BORDER
            cell.alignment = Alignment(
                wrap_text=True,
                vertical="center",
                horizontal="center" if is_header else "left",
            )

            if is_header:
                cell.fill = HDR_FILL
                cell.font = HDR_FONT
            elif is_alt:
                cell.fill = ALT_FILL
                cell.font = STD_FONT
            else:
                cell.fill = STD_FILL
                cell.font = STD_FONT

        ws.row_dimensions[excel_row].height = 18

    # Авто-ширина столбцов
    for col_idx in range(1, n_cols + 1):
        max_len = max(
            (len(str(row[col_idx - 1]))
             for row in all_rows if col_idx - 1 < len(row)),
            default=8,
        )
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 60)


# ── Основная функция ─────────────────────────────────────────────────────────

def convert_to_xlsx(pdfname: str) -> Path:
    """
    Извлекает таблицы из PNG-изображений и объединяет их
    в единую таблицу на одном листе .xlsx.

    Использует EasyOCR (без Tesseract, без img2table).

    Args:
        pdfname: Имя файла (например, "document.pdf" или "document").

    Returns:
        Путь к созданному .xlsx-файлу.
    """
    # ── 1. Пути ──────────────────────────────────────────────────────────────
    folder_name = pdfname.split(".")[0]
    base_dir    = Path("../../tables") / folder_name
    input_dir   = base_dir / "tables"
    output_file = base_dir / f"{folder_name}_tables.xlsx"

    if not input_dir.exists():
        raise FileNotFoundError(
            f"Входная папка не найдена: {input_dir.resolve()}"
        )

    # ── 2. Поиск и сортировка файлов ─────────────────────────────────────────
    file_pattern = re.compile(r"^table_.*_(\d+)\.png$")

    matched: list[tuple[int, Path]] = [
        (int(m.group(1)), f)
        for f in input_dir.iterdir()
        if (m := file_pattern.match(f.name))
    ]

    if not matched:
        raise ValueError(
            f"Файлы по маске не найдены в {input_dir.resolve()}"
        )

    matched.sort(key=lambda t: t[0])

    # ── 3. Инициализация EasyOCR ─────────────────────────────────────────────
    # Модели скачиваются один раз в ~/.EasyOCR/model/
    print("Инициализация EasyOCR ...", flush=True)
    reader = easyocr.Reader(["ru", "en"], gpu=False, verbose=False)

    # ── 4. Сбор всех строк ───────────────────────────────────────────────────
    all_rows: list[list[str]] = []
    header_saved = False

    for rank, (index, img_path) in enumerate(matched, start=1):
        print(f"  [{rank}/{len(matched)}] {img_path.name} ...", end=" ", flush=True)

        try:
            rows = _extract_rows_from_image(img_path, reader)
        except Exception as exc:
            print(f"ОШИБКА: {exc}")
            continue

        if not rows:
            print("пусто")
            continue

        if not header_saved:
            # Первый файл — берём целиком (с заголовком)
            all_rows.extend(rows)
            header_saved = True
        else:
            # Последующие — пропускаем первую строку (дубль заголовка)
            all_rows.extend(rows[1:])

        print(f"OK ({len(rows)} строк)")

    # ── 5. Запись в Excel ────────────────────────────────────────────────────
    wb = Workbook()
    ws = wb.active
    ws.title = folder_name[:31]

    _write_table_to_sheet(ws, all_rows, has_header=True)
    ws.freeze_panes = "A2"

    # ── 6. Сохранение ────────────────────────────────────────────────────────
    output_file.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_file)

    total_data = max(len(all_rows) - 1, 0)
    total_cols = max((len(r) for r in all_rows), default=0)
    print(f"\n✓ Готово: {output_file.resolve()}")
    print(f"  Строк данных: {total_data}  |  Столбцов: {total_cols}")
    return output_file