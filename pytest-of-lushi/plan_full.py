import json
import os
import sys

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

from app.rsosh import list_plan
from app.rsosh.list_parser import OfficialList

year = sys.argv[1] if len(sys.argv) > 1 else '26-27'
with open(f'pytest-of-lushi/full_{year}.json', encoding='utf-8') as handle:
    parsed = OfficialList.from_dict(json.load(handle))

catalog = list_plan.Catalog(olympiads=[], by_norm={}, seasons={})
plan = list_plan.build_plan(parsed, doc_id='doc', catalog=catalog)
print('season', plan['season_label'], 'complete', plan['complete'])
print('summary', plan['summary'])
print('missing_allowed', plan['missing_allowed'])
print('errors', len(plan['errors']))
for error in plan['errors'][:20]:
    print('  -', error)
print('warnings', len(plan['warnings']))
for warning in plan['warnings'][:10]:
    print('  *', warning)
olympiads = plan['olympiads']
print('olympiads with no profiles:',
      sum(1 for item in olympiads if not item['profiles']))
print('olympiads with unrecognized name:')
for item in olympiads:
    name = item['name']
    letters = sum(1 for ch in name if ch.isalpha() and ch.lower() in
                  'абвгдеёжзийклмнопрстуфхцчшщъыьэюя')
    if letters < 8:
        print('  -', repr(name[:80]), 'letters', letters)
