"""Формирование XLSX-таблицы официального перечня РСОШ.

Перечень РСОШ — это два листа:

    «Перечень 2026-27» — строки профилей, по одной на профиль;
    «Сводка»           — агрегат по олимпиадам: сколько профилей и какие
                         уровни встречаются.

XLSX здесь не «экспорт ради удобства», а промежуточный артефакт конвейера:
он собирается сразу после разбора PDF и до сопоставления с каталогом. По
нему администратор проверяет, что скан прочитан верно. Поэтому оформление
повторяет официальную таблицу: шапка с заливкой, границы, закреплённая
строка, автофильтр и высота строк по содержимому — иначе длинные названия
организаторов обрезаются и проверять нечего.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

#: Ширина колонок официального перечня (в символах Excel).
COLUMN_WIDTHS = (7, 48, 75, 34, 60, 11)
#: Высота шапки: в неё должны поместиться двух-трёхстрочные формулировки.
HEADER_HEIGHT = 60
#: Предел высоты строки в Excel; выше него openpyxl сохраняет не всё.
MAX_ROW_HEIGHT = 409

HEADER_FILL = PatternFill('solid', fgColor='1F4E78')
HEADER_FONT = Font(bold=True, color='FFFFFF')
THIN_BORDER = Side(style='thin', color='BFBFBF')
CELL_BORDER = Border(
    left=THIN_BORDER,
    right=THIN_BORDER,
    top=THIN_BORDER,
    bottom=THIN_BORDER,
)
WRAP_TOP = Alignment(vertical='top', wrap_text=True)
CENTER_TOP = Alignment(horizontal='center', vertical='top', wrap_text=True)
HEADER_ALIGNMENT = Alignment(
    horizontal='center', vertical='center', wrap_text=True
)

_ROMAN = {'1': 'I', '2': 'II', '3': 'III'}
_LEVEL_ORDER = ('1', '2', '3')


@dataclass
class SummaryRow:
    """Строка листа «Сводка»."""

    number: int | str | None
    olympiad: str
    profiles: int
    levels: str


def sheet_title(season_label: str | None) -> str:
    """Название листа вида «Перечень 2026-27»."""
    if not season_label:
        return 'Перечень'
    parts = season_label.replace('/', '-').split('-')
    if len(parts) == 2 and len(parts[1]) == 4:
        return f'Перечень {parts[0]}-{parts[1][2:]}'
    return f'Перечень {season_label}'


def _roman(level: str | None) -> str:
    return _ROMAN.get(str(level or '').strip(), '')


def _number(value) -> int | str | None:
    text = str(value or '').strip()
    if text.isdigit():
        return int(text)
    return text or None


def summary(rows: list) -> list[SummaryRow]:
    """Свернуть строки профилей в сводку по олимпиадам.

    Порядок олимпиад — порядок первого появления в перечне, а не алфавит:
    так сводка сопоставляется с исходной таблицей. Уровни считаются по
    распознанным значениям и выводятся в порядке I, II, III.
    """
    groups: list[dict] = []
    index: dict[str, dict] = {}
    for row in rows:
        name = (row.olympiad or '').strip()
        key = name.casefold().replace('ё', 'е')
        group = index.get(key)
        if group is None:
            group = {
                'number': _number(row.number),
                'olympiad': name,
                'levels': {level: 0 for level in _LEVEL_ORDER},
                'profiles': 0,
            }
            index[key] = group
            groups.append(group)
        group['profiles'] += 1
        level = str(row.level or '').strip()
        if level in group['levels']:
            group['levels'][level] += 1

    result: list[SummaryRow] = []
    for group in groups:
        parts = [
            f'{_ROMAN[level]}×{group["levels"][level]}'
            for level in _LEVEL_ORDER
            if group['levels'][level]
        ]
        result.append(
            SummaryRow(
                number=group['number'],
                olympiad=group['olympiad'],
                profiles=group['profiles'],
                levels=', '.join(parts),
            )
        )
    return result


def _lines(value, width: int) -> int:
    """Сколько строк займёт текст в колонке заданной ширины."""
    text = '' if value is None else str(value)
    if not text:
        return 1
    # Excel считает ширину в «символах» Calibri 11; для кириллицы строка
    # получается немного шире, поэтому коэффициент взят с запасом.
    per_line = max(4, int(width * 1.02))
    total = 0
    for part in text.split('\n'):
        total += max(1, math.ceil(len(part) / per_line))
    return total


def _row_height(values: list, *, minimum: float = 15.0) -> float:
    lines = max(
        _lines(value, width)
        for value, width in zip(values, COLUMN_WIDTHS)
    )
    return min(MAX_ROW_HEIGHT, max(minimum, lines * 14.5 + 2))


def _style_header(ws, columns: int) -> None:
    for column in range(1, columns + 1):
        cell = ws.cell(row=1, column=column)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = HEADER_ALIGNMENT
        cell.border = CELL_BORDER
    ws.row_dimensions[1].height = HEADER_HEIGHT


def _apply_widths(ws, widths) -> None:
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width


def _write_list_sheet(ws, headers: list[str], rows: list) -> None:
    values = list(headers or [])
    values += [''] * (6 - len(values))
    for column, header in enumerate(values[:6], start=1):
        ws.cell(row=1, column=column, value=header)
    _style_header(ws, 6)
    _apply_widths(ws, COLUMN_WIDTHS)
    ws.freeze_panes = 'A2'

    for index, row in enumerate(rows, start=2):
        cells = [
            _number(row.number),
            row.olympiad or '',
            getattr(row, 'organizer_row', '') or row.organizer or '',
            row.profile or '',
            row.subjects or '',
            _roman(row.level),
        ]
        for column, value in enumerate(cells, start=1):
            cell = ws.cell(row=index, column=column, value=value)
            cell.border = CELL_BORDER
            if column in (1, 6):
                cell.alignment = CENTER_TOP
            else:
                cell.alignment = WRAP_TOP
        ws.row_dimensions[index].height = _row_height(cells)

    last_row = max(1, len(rows) + 1)
    ws.auto_filter.ref = f'A1:F{last_row}'


def _write_summary_sheet(ws, rows: list) -> None:
    headers = ['№', 'Олимпиада', 'Профилей', 'Уровни']
    for column, value in enumerate(headers, start=1):
        ws.cell(row=1, column=column, value=value)
    _style_header(ws, 4)
    _apply_widths(ws, (6, 70, 10, 22))
    ws.freeze_panes = 'A2'

    for index, item in enumerate(summary(rows), start=2):
        cells = [item.number, item.olympiad, item.profiles, item.levels]
        for column, value in enumerate(cells, start=1):
            cell = ws.cell(row=index, column=column, value=value)
            cell.alignment = WRAP_TOP


def build_workbook(parsed) -> Workbook:
    """Собрать книгу из результата разбора перечня."""
    workbook = Workbook()
    list_sheet = workbook.active
    list_sheet.title = sheet_title(parsed.season_label)
    _write_list_sheet(list_sheet, parsed.headers, parsed.rows)

    summary_sheet = workbook.create_sheet('Сводка')
    _write_summary_sheet(summary_sheet, parsed.rows)
    return workbook


def save(parsed, path: str | Path) -> Path:
    """Записать XLSX перечня на диск и вернуть путь."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook = build_workbook(parsed)
    workbook.save(target)
    return target


_HTML_STYLE = """
body { font-family: 'Segoe UI', Arial, sans-serif; margin: 16px; color: #1a1a1a; }
h1 { font-size: 18px; margin: 0 0 4px; }
p.meta { color: #666; margin: 0 0 12px; font-size: 12px; }
table { border-collapse: collapse; width: 100%; font-size: 12px; }
th { background: #1F4E78; color: #fff; font-weight: 600; padding: 6px;
     border: 1px solid #BFBFBF; position: sticky; top: 0; }
td { padding: 4px 6px; border: 1px solid #BFBFBF; vertical-align: top; }
td.num, td.level { text-align: center; white-space: nowrap; }
tr:nth-child(even) td { background: #F7F9FC; }
h2 { font-size: 15px; margin: 24px 0 8px; }
"""


def _html_cell(value) -> str:
    text = '' if value is None else str(value)
    return (
        text.replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('\n', '<br>')
    )


def render_html(parsed) -> str:
    """HTML-представление перечня для просмотра прямо в браузере.

    XLSX удобно скачать, но не открыть в интерфейсе: браузер не умеет
    показывать таблицы Excel. Поэтому рядом с XLSX сохраняется HTML с теми же
    строками — администратор сверяет скан и таблицу, не покидая панель.
    """
    headers = list(parsed.headers or [])
    headers += [''] * (6 - len(headers))
    season = parsed.season_label or ''
    head = ''.join(f'<th>{_html_cell(value)}</th>' for value in headers[:6])
    body = []
    for row in parsed.rows:
        body.append(
            '<tr>'
            f'<td class="num">{_html_cell(_number(row.number))}</td>'
            f'<td>{_html_cell(row.olympiad)}</td>'
            f'<td>{_html_cell(row.organizer)}</td>'
            f'<td>{_html_cell(row.profile)}</td>'
            f'<td>{_html_cell(row.subjects)}</td>'
            f'<td class="level">{_html_cell(_roman(row.level))}</td>'
            '</tr>'
        )
    summary_rows = ''.join(
        '<tr>'
        f'<td class="num">{_html_cell(item.number)}</td>'
        f'<td>{_html_cell(item.olympiad)}</td>'
        f'<td class="num">{item.profiles}</td>'
        f'<td>{_html_cell(item.levels)}</td>'
        '</tr>'
        for item in summary(parsed.rows)
    )
    title = parsed.title or f'Перечень {season}'.strip()
    return (
        '<!DOCTYPE html>'
        '<html lang="ru"><head><meta charset="utf-8">'
        f'<title>{_html_cell(title)}</title>'
        f'<style>{_HTML_STYLE}</style></head><body>'
        f'<h1>{_html_cell(title)}</h1>'
        f'<p class="meta">Учебный год: {_html_cell(season)} · '
        f'строк профилей: {len(parsed.rows)}</p>'
        f'<table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'
        '<h2>Сводка</h2>'
        '<table><thead><tr><th>№</th><th>Олимпиада</th>'
        f'<th>Профилей</th><th>Уровни</th></tr></thead><tbody>{summary_rows}</tbody></table>'
        '</body></html>'
    )


def save_html(parsed, path: str | Path) -> Path:
    """Записать HTML-представление перечня и вернуть путь."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(parsed), encoding='utf-8')
    return target
