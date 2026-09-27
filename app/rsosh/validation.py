"""Проверка качества распознавания и извлечённых записей.

Импортёр не должен молча заносить в каталог мусор. Каждая запись получает
оценку качества и список замечаний, а подозрительные записи помечаются для
проверки администратором (в preview они видны отдельным статусом).

Оценка складывается из трёх частей:

- **распознавание** — средняя уверенность OCR на странице (для XLSX и
  текстового слоя PDF это 1.0);
- **структура** — нашлась ли шапка таблицы и колонка с названием;
- **содержание** — длина названия, отсутствие «мусорных» знаков.
"""

from app.rsosh.normalization import clean_cell, is_noise
from app.rsosh.types import OlympiadRecord, PageReport

# Порог, ниже которого запись помечается для ручной проверки.
LOW_CONFIDENCE_THRESHOLD = 0.55
# Название короче этого — почти наверняка обрывок, а не олимпиада.
MIN_NAME_LENGTH = 6
# Слишком длинное «название» — вероятно, склеились несколько строк таблицы.
MAX_NAME_LENGTH = 400
GARBAGE_CHARS = set('~^`_|{}\\/*')


def validate_record(record: OlympiadRecord) -> OlympiadRecord:
    """Добавить к записи замечания и понизить уверенность."""
    issues: list[str] = []
    confidence = record.confidence
    name = clean_cell(record.name)

    if not name:
        issues.append('Пустое название')
        confidence = 0.0
    elif len(name) < MIN_NAME_LENGTH:
        issues.append('Название слишком короткое — проверьте результат OCR')
        confidence = min(confidence, 0.4)
    elif len(name) > MAX_NAME_LENGTH:
        issues.append(
            'Название очень длинное — возможно, склеились несколько строк таблицы'
        )
        confidence = min(confidence, 0.6)
    elif is_noise(name):
        issues.append('Значение не похоже на название олимпиады')
        confidence = min(confidence, 0.2)

    if any(character in GARBAGE_CHARS for character in name):
        issues.append('В названии встречаются технические символы')
        confidence = min(confidence, 0.5)

    upper = sum(1 for character in name if character.isalpha() and character.isupper())
    letters = sum(1 for character in name if character.isalpha())
    if letters >= 12 and upper / letters > 0.9:
        issues.append('Название выглядит как набранное капсом — проверьте оригинал')
        confidence = min(confidence, 0.5)

    record.issues = list(dict.fromkeys([*record.issues, *issues]))
    record.confidence = round(confidence, 3)
    return record


def build_page_reports(
    pages,
    *,
    method: str,
    orientation: int = 0,
) -> list[PageReport]:
    """Отчёт по страницам для превью импорта."""
    return [
        PageReport(
            page=page.page,
            method=page.method or method,
            orientation=page.orientation or orientation,
            tables=len(page.tables),
            rows=page.rows,
            chars=page.chars,
            confidence=page.confidence,
            issues=list(page.issues),
        )
        for page in pages
    ]
