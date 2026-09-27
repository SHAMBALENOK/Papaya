"""OCR-слой импорта РСОШ.

Обёртка над Tesseract, которая отдаёт слова вместе с их координатами и
уверенностью. Координаты нужны для реконструкции таблицы (строки/столбцы
восстанавливаются по геометрии, а не по порядку слов в тексте).

Язык — русский + английский: в названиях олимпиад смешиваются кириллица,
латиница, римские цифры уровней и годы.
"""

import logging
import shutil

import numpy as np

from app.rsosh.types import RsoshError

logger = logging.getLogger('papaya.rsosh.ocr')

LANG = 'rus+eng'
# page-segmentation mode 6: «единый блок текста» — лучший режим для таблиц,
# где tesseract не может понять структуру колонок, но строки читает верно.
DEFAULT_PSM = 6


class OcrUnavailable(RsoshError):
    """Tesseract недоступен в окружении."""


def available_languages() -> list[str]:
    """Список языков, установленных в tesseract (для диагностики)."""
    try:
        import pytesseract

        return sorted(pytesseract.get_languages(config=''))
    except Exception:  # noqa: BLE001 - диагностика, детали не важны
        return []


def ensure_available() -> None:
    """Проверить, что tesseract и нужные языки установлены.

    Импорт PDF-скана без OCR невозможен, поэтому отсутствие tesseract —
    явная ошибка с подсказкой, а не «пустой» результат импорта.
    """
    if shutil.which('tesseract') is None:
        raise OcrUnavailable(
            'Tesseract OCR is not installed in the service environment; '
            'scanned documents cannot be imported'
        )
    languages = available_languages()
    if languages and not ({'rus', 'eng'} & set(languages)):
        raise OcrUnavailable(
            'Tesseract has no Russian or English language data (rus/eng) installed'
        )


def ocr_words(
    image: np.ndarray,
    *,
    psm: int = DEFAULT_PSM,
    min_confidence: float = 30.0,
) -> list[dict]:
    """Распознать изображение и вернуть слова с координатами.

    Каждое слово: ``text``, ``x0``, ``y0``, ``x1``, ``y1``, ``conf``
    (уверенность tesseract, 0..100). Слова с низкой уверенностью и мусором
    (пустые строки, одиночные символы вне контекста) отбрасываются.
    """
    ensure_available()
    import pytesseract
    from pytesseract import Output

    try:
        data = pytesseract.image_to_data(
            image,
            lang=LANG,
            config=f'--psm {psm}',
            output_type=Output.DICT,
        )
    except Exception as exc:  # noqa: BLE001 - причина в тексте исключения tesseract
        raise RsoshError(f'OCR failed: {exc}') from exc

    words: list[dict] = []
    count = len(data.get('text', []))
    for index in range(count):
        text = (data['text'][index] or '').strip()
        if not text:
            continue
        try:
            confidence = float(data['conf'][index])
        except (TypeError, ValueError):
            confidence = -1.0
        if confidence < min_confidence:
            continue
        left = int(data['left'][index])
        top = int(data['top'][index])
        width = int(data['width'][index])
        height = int(data['height'][index])
        if width <= 0 or height <= 0:
            continue
        words.append({
            'text': text,
            'x0': left,
            'y0': top,
            'x1': left + width,
            'y1': top + height,
            'conf': confidence,
        })

    logger.debug('ocr: %s words from image', len(words))
    return words


def osd_rotation(image: np.ndarray) -> tuple[int, float] | None:
    """Определить поворот страницы через OSD tesseract.

    ``image_to_osd`` возвращает, на сколько градусов по часовой стрелке нужно
    повернуть страницу, чтобы текст читался слева направо. Это самый
    дешёвый способ определить ориентацию: он не распознаёт текст, поэтому
    работает в разы быстрее пробного OCR.

    OSD требует языковых данных ``osd`` и достаточного количества текста, поэтому
    на бедных страницах он может отказать — тогда вызывающий код определяет
    ориентацию пробным OCR (см. ``app.rsosh.extraction``).
    """
    if shutil.which('tesseract') is None:
        return None
    import pytesseract

    try:
        data = pytesseract.image_to_osd(
            image,
            output_type=pytesseract.Output.DICT,
        )
    except Exception:  # noqa: BLE001 - OSD отказывает на бедных страницах
        return None

    try:
        rotation = int(data.get('rotate', 0)) % 360
    except (TypeError, ValueError):
        return None
    try:
        confidence = float(data.get('orientation_conf', 0.0)) / 100
    except (TypeError, ValueError):
        confidence = 0.0
    return rotation, round(min(1.0, confidence), 3)
