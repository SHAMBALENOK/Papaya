import os
import sys
import tempfile

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

import openpyxl  # noqa: E402

from app.rsosh import list_plan, list_xlsx  # noqa: E402
from app.rsosh.list_parser import ListRow, OfficialList  # noqa: E402


def row(number='1', olympiad='Олимпиада имени Теста', profile='профиль',
        subjects='математика', level='1', source_row=1):
    return ListRow(
        number=number, olympiad=olympiad, organizer='Организатор',
        profile=profile, subjects=subjects, level=level, level_raw=level or '',
        page=2, source_row=source_row, source_band=1,
    )


headers = [
    '№ п/п',
    'Полное наименование олимпиады',
    'Полное наименование организатора (организаторов) олимпиады',
    'Профиль олимпиады',
    'Общеобразовательные предметы или укрупненные группы специальностей и '
    'направлений подготовки высшего образования',
    'Уровень олимпиады',
]
parsed = OfficialList(
    season_label='2026/2027',
    title='Перечень олимпиад школьников на 2026/27 учебный год',
    headers=headers,
    header_source='document',
    rows=[
        row(number='1', olympiad='Первая', profile='профиль А', level='2'),
        row(number='1', olympiad='Первая', profile='профиль Б', level='3', source_row=2),
        row(number='2', olympiad='Вторая', profile='профиль В', level='1', source_row=3),
    ],
    complete=True,
    source_pages=86,
    detected_tables=80,
)

with tempfile.TemporaryDirectory() as tmp:
    path = list_xlsx.save(parsed, os.path.join(tmp, 'list.xlsx'))
    html = list_xlsx.render_html(parsed)
    open(os.path.join(tmp, 'list.html'), 'w', encoding='utf-8').write(html)
    wb = openpyxl.load_workbook(path)
    print('sheets', wb.sheetnames)
    sheet = wb.worksheets[0]
    print('header A1', sheet['A1'].value)
    print('header E1', sheet['E1'].value[:50])
    print('fill', sheet['A1'].fill.fgColor.rgb, 'bold', sheet['A1'].font.bold,
          'color', sheet['A1'].font.color.rgb)
    print('widths', {c: sheet.column_dimensions[c].width for c in 'ABCDEF'})
    print('freeze', sheet.freeze_panes, 'filter', sheet.auto_filter.ref)
    print('row2', [sheet.cell(row=2, column=c).value for c in range(1, 7)],
          'height', sheet.row_dimensions[2].height)
    summary = wb.worksheets[1]
    print('summary', [[summary.cell(row=r, column=c).value for c in range(1, 5)]
                      for r in range(1, 4)])
    print('html head ok', '<table>' in html and 'Сводка' in html)
    parsed.rows[0].profile = '<script>x</script>'
    print('escaped', '<script>x</script>' not in list_xlsx.render_html(parsed))

summary_rows = list_xlsx.summary(parsed.rows)
print('summary model', [(s.olympiad, s.profiles, s.levels) for s in summary_rows])

catalog = list_plan.Catalog(olympiads=[], by_norm={}, seasons={})
plan = list_plan.build_plan(parsed, doc_id='doc', catalog=catalog)
print('plan olympiads', len(plan['olympiads']), 'summary', plan['summary'])
print('plan errors', plan['errors'])
print('missing_allowed', plan['missing_allowed'])

norm = plan['olympiads'][0]['name_norm']
try:
    list_plan.apply_changes(plan, {'olympiads': [{'name_norm': 'нет такой', 'action': 'skip'}]})
    print('ERROR: unknown olympiad accepted')
except ValueError as exc:
    print('unknown rejected:', exc)

plan2 = list_plan.build_plan(parsed, doc_id='doc', catalog=catalog)
updated = list_plan.apply_changes(plan2, {'profiles': [{
    'olympiad': plan2['olympiads'][0]['name_norm'], 'source_row': 1,
    'name': 'инфохимия', 'level': '3'}]})
profile = updated['olympiads'][0]['profiles'][0]
print('fixed profile', profile['name'], profile['level'], 'errors', updated['errors'])
