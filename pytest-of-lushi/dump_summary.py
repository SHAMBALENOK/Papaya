import collections
import glob
import os
import sys

import openpyxl

sys.stdout.reconfigure(encoding='utf-8')

for path in sorted(glob.glob(r'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\table\*.xlsx')):
    wb = openpyxl.load_workbook(path)
    ws = wb.worksheets[1]
    print('===', os.path.basename(path), repr(ws.title), ws.max_row, ws.max_column)
    print('widths', {k: v.width for k, v in ws.column_dimensions.items()})
    print('freeze', ws.freeze_panes, 'filter', ws.auto_filter.ref)
    for r in range(1, 5):
        print(' row', r, [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)],
              'height', ws.row_dimensions[r].height)
    for addr in ('A1', 'B1', 'C1', 'D1', 'A2', 'B2', 'C2', 'D2'):
        c = ws[addr]
        print('  ', addr, 'bold', c.font.b, 'color', c.font.color.rgb if c.font.color else None,
              'fill', c.fill.fill_type, c.fill.fgColor.rgb if c.fill.fgColor else None,
              'align', c.alignment.horizontal, c.alignment.vertical, c.alignment.wrap_text,
              'numfmt', c.number_format, 'border', c.border.left.style)
    levels = collections.Counter(ws.cell(row=r, column=4).value for r in range(2, ws.max_row + 1))
    print('levels', levels.most_common(12))
