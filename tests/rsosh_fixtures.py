"""Генераторы тестовых документов РСОШ для importer-тестов.

Фикстуры повторяют реальные особенности документов РСОШ:

- многострочные ячейки с переносами строк;
- объединённые по вертикали ячейки (продолжение строки в XLSX);
- многостраничные таблицы с повтором шапки;
- сканы без текстового слоя;
- страницы, повёрнутые на 90/180/270 градусов;
- изображение таблицы (PNG/JPEG) вместо текстового PDF.

Всё генерируется на лету из кода: бинарные файлы не хранятся в репозитории и
не требуют сторонних библиотек, кроме уже используемых в проекте
(openpyxl, pypdfium2, OpenCV).
"""

import io

# Строки тестового перечня: название (с переносом строки), предмет, уровень,
# вид диплома. Название многострочное — как в настоящих перечнях РСОШ.
OLYMPIAD_ROWS = [
    ('Всероссийская олимпиада школьников\n«Высшая проба»', 'Информатика', '1', 'Победитель или призер'),
    ('Всероссийская олимпиада школьников\nпо информатике и программированию', 'Информатика', '1, 2', 'Победитель или призер'),
    ('Олимпиада школьников «Ломоносов»', 'Математика', '1 или 2', 'Победитель'),
    ('Олимпиада школьников «Физтех»', 'Физика', '2 или 3', 'Победитель или призер'),
    ('Открытая олимпиада школьников\nпо программированию', 'Информатика', '2', 'Победитель'),
]
HEADER = ('Наименование олимпиады', 'Профиль', 'Уровень', 'Диплом')

RSOSH_SAMPLE_PDF = 'app/tables/rsosh_bvi/rsosh_bvi.pdf'


def xlsx_bytes(row_count: int | None = None) -> bytes:
    """XLSX с шапкой, многострочными ячейками и объединённой ячейкой.

    ``row_count`` ограничивает число олимпиад в перечне: нужен, чтобы
    смоделировать следующий, более короткий перечень РСОШ (олимпиады, исчезнувшие
    из него, должны уйти в архив).
    """
    import openpyxl

    rows = OLYMPIAD_ROWS if row_count is None else OLYMPIAD_ROWS[:row_count]
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = 'Перечень'
    sheet.append(list(HEADER))
    for name, profile, level, diploma in rows:
        sheet.append([name, profile, level, diploma])

    # Объединённая по вертикали ячейка: пустой предмет во второй строке.
    if len(rows) > 1:
        sheet.merge_cells(start_row=4, start_column=2, end_row=5, end_column=2)

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def empty_xlsx_bytes() -> bytes:
    """XLSX без строк данных: импорт должен честно сообщить, что ничего нет."""
    import openpyxl

    book = openpyxl.Workbook()
    sheet = book.active
    sheet['A1'] = 'Пустой перечень'
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


# --------------------------------------------------------------------------- PDF


def _render_page(pdf_path: str, page_number: int, dpi: int = 200):
    """Отрисовать страницу PDF в BGR-массив (как это делает импортёр)."""
    import numpy as np
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(pdf_path)
    try:
        bitmap = document[page_number - 1].render(scale=dpi / 72.0)
        array = np.array(bitmap.to_pil().convert('RGB'))
        return np.ascontiguousarray(array[:, :, ::-1])
    finally:
        document.close()


def rotate_image(image, degrees: int):
    """Повернуть растр на 90/180/270 градусов."""
    import cv2

    if degrees == 0:
        return image
    return cv2.rotate(
        image,
        {
            90: cv2.ROTATE_90_CLOCKWISE,
            180: cv2.ROTATE_180,
            270: cv2.ROTATE_90_COUNTERCLOCKWISE,
        }[degrees],
    )


def page_image(pdf_path: str = RSOSH_SAMPLE_PDF, page_number: int = 2, degrees: int = 0):
    """Скан страницы документа как BGR-массив (опционально повёрнутый)."""
    return rotate_image(_render_page(pdf_path, page_number), degrees)


def image_bytes(
    pdf_path: str = RSOSH_SAMPLE_PDF,
    page_number: int = 2,
    degrees: int = 0,
    ext: str = 'png',
) -> bytes:
    """Скан страницы документа как изображение (опционально повёрнутое)."""
    import cv2

    ok, buffer = cv2.imencode(f'.{ext}', page_image(pdf_path, page_number, degrees))
    if not ok:
        raise RuntimeError('cannot encode fixture image')
    return buffer.tobytes()


def scanned_pdf_bytes(
    pdf_path: str = RSOSH_SAMPLE_PDF,
    page_number: int = 2,
    degrees: int = 0,
) -> bytes:
    """PDF без текстового слоя: страница сохранена как картинка.

    Так выглядит настоящий скан документа РСОШ — именно его импортёр обязан
    обрабатывать через OCR (в получившемся файле нет ни одного символа).
    """
    from PIL import Image

    image = page_image(pdf_path, page_number, degrees)
    buffer = io.BytesIO()
    Image.fromarray(image[:, :, ::-1]).save(
        buffer,
        format='PDF',
        resolution=72.0,
    )
    return buffer.getvalue()


def broken_bytes() -> bytes:
    """Файл с неверной сигнатурой — не документ вовсе."""
    return b'this is not a document at all' * 16


def broken_pdf_bytes() -> bytes:
    """PDF-заголовок без содержимого: загрузка пройдёт, чтение — нет.

    Нужен, чтобы проверить сообщение об ошибке импорта: файл выглядит
    поддерживаемым по сигнатуре, но разобрать его невозможно.
    """
    return b'%PDF-1.7\n' + b'broken pdf body' * 64
