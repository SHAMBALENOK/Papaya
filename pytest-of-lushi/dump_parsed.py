import json
import os
import sys

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

from app.rsosh import list_parser  # noqa: E402

doc = list_parser.parse_official_list(
    r'C:\Users\lushi\OneDrive\Desktop\Projects\dataset-rsosh\original\26-27.pdf',
    max_pages=9,
)
with open('pytest-of-lushi/parsed_26_27.json', 'w', encoding='utf-8') as handle:
    json.dump(doc.to_dict(), handle, ensure_ascii=False, indent=1)
print('rows', len(doc.rows), 'season', doc.season_label, 'header', doc.header_source)
