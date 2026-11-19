import os
import sys

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

from app.rsosh import list_parser  # noqa: E402

orig = list_parser._header_band


def patched(text):
    result = orig(text)
    low = (text or '').lower()
    if 'профил' in low and ('олимп' in low or 'общеобразоват' in low):
        print('BAND header=', result, 'text=', repr(text[:220]))
    return result


list_parser._header_band = patched
doc = list_parser.parse_official_list(
    r'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\original\17-18.pdf',
    max_pages=3,
)
print('rows', len(doc.rows))
for row in doc.rows:
    print(
        row.number, '| p', row.page, '|', repr(row.profile[:55]),
        '|', repr(row.olympiad[:55]), '|', repr(row.subjects[:55]),
        '|', row.level,
    )
