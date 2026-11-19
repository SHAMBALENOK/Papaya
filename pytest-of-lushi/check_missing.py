import os
import sys

sys.path.insert(0, '.')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://u:p@localhost:5432/db'

from app.rsosh import list_plan
from app.rsosh.list_parser import ListRow, OfficialList


def row(profile='профиль', level='1', olympiad='Олимпиада имени Теста'):
    return ListRow(
        number='1', olympiad=olympiad, organizer='Организатор',
        profile=profile, subjects='математика', level=level,
        level_raw=level or '', page=2, source_row=1, source_band=1,
    )


def parsed(rows=None, complete=True):
    return OfficialList(
        season_label='2026/2027',
        title='Перечень',
        headers=['№ п/п'] * 6,
        header_source='document',
        rows=rows or [row()],
        complete=complete,
        source_pages=86,
        detected_tables=80,
    )


def catalog(olympiads=None, seasons=None):
    items = olympiads or []
    return list_plan.Catalog(
        olympiads=items,
        by_norm={item['name_norm']: item for item in items},
        seasons=seasons or {},
    )


def item(name, oid):
    return {
        'id': oid,
        'name': name,
        'name_norm': list_plan.normalize_name(name),
        'status': 'PUBLISHED',
        'archive_reason': None,
        'organizer': None,
    }


cat = catalog(
    [item('Исчезнувшая', '44444444-4444-4444-4444-444444444444')],
    {'44444444-4444-4444-4444-444444444444': [{
        'id': '55555555-5555-5555-5555-555555555555',
        'season_label': '2026/2027',
        'is_archived': False,
        'profiles': [],
    }]},
)
plan = list_plan.build_plan(parsed(), doc_id='doc', catalog=cat)
print('complete missing_allowed', plan['missing_allowed'])
print('missing', plan['missing'])
print('errors', plan['errors'])
print('pool', plan['missing_pool'])

partial = list_plan.build_plan(parsed(complete=False), doc_id='doc', catalog=cat)
print('partial missing_allowed', partial['missing_allowed'])
print('partial missing', partial['missing'])
print('warnings', partial['warnings'])

plan2 = list_plan.build_plan(parsed(rows=[row(profile='', level=None)]),
                             doc_id='doc', catalog=catalog())
print('bad errors', plan2['errors'], 'allowed', plan2['missing_allowed'])
updated = list_plan.apply_changes(plan2, {'profiles': [{
    'olympiad': plan2['olympiads'][0]['name_norm'],
    'source_row': 1, 'name': 'инфохимия', 'level': '3',
}]})
print('fixed errors', updated['errors'], 'allowed', updated['missing_allowed'])
print('profile', updated['olympiads'][0]['profiles'][0])
