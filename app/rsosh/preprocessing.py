"""Предобработка изображений и определение ориентации страницы.

Сканы документов РСОШ приходят с произвольной ориентацией (0/90/180/270),
с разным качеством и шумом. Здесь изображение приводится к виду, пригодному
для OCR, и определяется угол поворота страницы.

Всё построено на OpenCV: тяжёлые модели не нужны — для таблиц РСОШ достаточно
классических признаков (проекция профиля, минимальный ограничивающий
прямоугольник по маске текста).
"""

import logging

import cv2
import numpy as np

logger = logging.getLogger('papaya.rsosh.preprocessing')


class PreprocessError(Exception):
    """Изображение нельзя подготовить к OCR."""


def load_image(path: str) -> np.ndarray:
    """Прочитать изображение как BGR-массив (поддерживает не-ASCII пути)."""
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise PreprocessError('Cannot decode image')
    return image


def save_image(path: str, image: np.ndarray) -> None:
    """Записать BGR-изображение в файл (поддерживает не-ASCII пути)."""
    ext = path[path.rfind('.') + 1:] if '.' in path else 'png'
    params = []
    if ext.lower() in ('jpg', 'jpeg'):
        params = [cv2.IMWRITE_JPEG_QUALITY, 95]
    ok, buffer = cv2.imencode(f'.{ext}', image, params)
    if not ok:
        raise PreprocessError('Cannot encode image')
    buffer.tofile(path)


def to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _max_dimension(image: np.ndarray, limit: int = 3000) -> np.ndarray:
    """Уменьшить слишком крупный растр: OCR всё равно работает по контуру текста."""
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= limit:
        return image
    scale = limit / longest
    return cv2.resize(
        image,
        (int(width * scale), int(height * scale)),
        interpolation=cv2.INTER_AREA,
    )


def binarize(gray: np.ndarray) -> np.ndarray:
    """Локальная адаптивная бинаризация.

    Документы РСОШ часто сканируют с uneven-подсветкой: глобальный порог
    «съедает» бледные строки, поэтому используется адаптивный порог по
    локальному окну.
    """
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        12,
    )


def _text_mask(binary: np.ndarray) -> np.ndarray:
    """Маска пикселей, принадлежащих тексту/линиям таблицы."""
    ink = cv2.bitwise_not(binary)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    return cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel)


def estimate_skew(binary: np.ndarray, limit: float = 12.0) -> float:
    """Оценить наклон страницы в градусах (для «выпрямления» скана)."""
    mask = _text_mask(binary)
    if not mask.any():
        return 0.0
    lines = mask
    points = cv2.findNonZero(lines)
    if points is None or len(points) < 10:
        return 0.0
    try:
        angle = cv2.minAreaRect(points)[-1]
    except cv2.error:
        return 0.0
    if angle > 45:
        angle -= 90
    if abs(angle) > limit:
        return 0.0
    return float(angle)


def deskew(binary: np.ndarray, angle: float) -> np.ndarray:
    """Повернуть бинаризованное изображение на угол по горизонтали."""
    if abs(angle) < 0.1:
        return binary
    height, width = binary.shape[:2]
    center = (width / 2, height / 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        binary,
        matrix,
        (width, height),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )


def rotate(image: np.ndarray, degrees: float) -> np.ndarray:
    """Повернуть изображение на угол (положительный угол — против часовой)."""
    height, width = image.shape[:2]
    center = (width / 2, height / 2)
    matrix = cv2.getRotationMatrix2D(center, degrees, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_width = int((height * sin) + (width * cos))
    new_height = int((height * cos) + (width * sin))
    matrix[0, 2] += (new_width / 2) - center[0]
    matrix[1, 2] += (new_height / 2) - center[1]
    return cv2.warpAffine(
        image,
        matrix,
        (new_width, new_height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )


def rotate_cw(image: np.ndarray, degrees: float) -> np.ndarray:
    """Повернуть изображение по часовой стрелке (как результат OSD tesseract)."""
    return image if not degrees else rotate(image, -degrees)


def text_direction_candidates(binary: np.ndarray) -> tuple[int, ...]:
    """Кандидаты ориентации страницы по направлению текста.

    У правильно повёрнутой страницы текст идёт горизонтально: горизонтальное
    морфологическое открытие «склеивает» буквы в строки и оставляет больше
    чернил, чем вертикальное. Для страницы, повёрнутой на 90°, соотношение
    обратное. Так определяется семейство углов, а конкретный угол внутри него
    выбирает OSD tesseract (см. ``app.rsosh.ocr``).
    """
    import cv2

    ink = cv2.bitwise_not(binary)
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3))
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, horizontal_kernel)
    vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN, vertical_kernel)
    horizontal_ink = cv2.countNonZero(horizontal)
    vertical_ink = cv2.countNonZero(vertical)
    if horizontal_ink >= vertical_ink:
        return (0, 180)
    return (90, 270)


def prepare(image: np.ndarray, *, correct_orientation: bool = True) -> dict:
    """Предобработка страницы без определения ориентации.

    Бинаризация, ограничение размера растра и оценка качества. Ориентация
    определяется отдельно (``text_direction_candidates`` + OSD), потому что
    для повёрнутой страницы нужен поворот на кратное 90°, а для «заваленной»
    страницы — произвольный угол.
    """
    image = _max_dimension(image)
    gray = to_gray(image)
    binary = binarize(gray)
    return {
        'image': binary,
        'candidates': text_direction_candidates(binary),
        'ink_ratio': round(float(cv2.bitwise_not(binary).mean() / 255), 4),
    }


def straighten(binary: np.ndarray) -> tuple[np.ndarray, float]:
    """Выпрямить «заваленную» страницу; вернуть изображение и угол наклона."""
    skew = estimate_skew(binary)
    return deskew(binary, skew), round(skew, 2)
