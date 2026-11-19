"""План импорта официального перечня: сопоставление с каталогом.

Разбор PDF отвечает на вопрос «что написано в документе», а план — на вопрос
«что из этого уже есть в каталоге и что с этим делать». Эти вещи нельзя
смешивать: администратор должен увидеть план до записи в базу, исправить
сопоставление и только потом подтвердить импорт.

Правила сопоставления намеренно консервативные:

* автоматически принимается только точное совпадение нормализованного
  названия (``name_norm``);
* похожие названия показываются кандидатами, но никогда не склеиваются сами:
  «олимпиада имени Вернадского» и «олимпиада имени Вернадского 2026» могут
  быть как одной записью, так и разными;
* профиль сезона сравнивается по нормализованному названию; изменение уровня
  — это обновление профиля, а не новый профиль, и оно попадает в историю;
* отсутствующие олимпиады фиксируются только по полному, успешно
  разобранному перечню. Частичный скан не доказывает, что олимпиады нет.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.search import normalize_name
from app.models.olympiads import Olympiads
from app.models.seasons import OlympiadSeason

#: Порог, начиная с которого название показывается кандидатом.
CANDIDATE_THRESHOLD = 0.60
#: Сколько кандидатов показывать: больше — шум, а не помощь администратору.
MAX_CANDIDATES = 5


@dataclass
class Catalog:
    """Снимок каталога, нужный для построения плана."""

    olympiads: list[dict]
    by_norm: dict[str, dict]
    seasons: dict[str, list[dict]]

    def season(self, olympiad_id, season_label: str) -> dict | None:
        for season in self.seasons.get(str(olympiad_id), []):
            if season['season_label'] == season_label:
                return season
        return None


async def load_catalog() -> Catalog:
    """Прочитать олимпиады, сезоны и профили одним снимком.

    План строится по одному снимку, а не запросами на каждую строку: иначе
    на перечне из трёхсот строк панель делает сотни запросов и показывает
    разные состояния каталога в разных строках.
    """
    from app.database.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        olympiads = (
            await session.execute(
                select(Olympiads).order_by(Olympiads.name_norm, Olympiads.id)
            )
        ).scalars().all()
        seasons = (
            await session.execute(
                select(OlympiadSeason).options(
                    selectinload(OlympiadSeason.profiles)
                )
            )
        ).scalars().all()

    seasons_by_olympiad: dict[str, list[dict]] = defaultdict(list)
    for season in seasons:
        seasons_by_olympiad[str(season.olympiad_id)].append({
            'id': str(season.id),
            'season_label': season.season_label,
            'is_archived': bool(season.is_archived),
            'profiles': [
                {
                    'id': str(profile.id),
                    'name': profile.name,
                    'name_norm': profile.name_norm,
                    'rsosh_level': profile.rsosh_level,
                }
                for profile in season.profiles
            ],
        })

    items = [
        {
            'id': str(olympiad.id),
            'name': olympiad.name,
            'name_norm': olympiad.name_norm,
            'status': olympiad.status,
            'archive_reason': olympiad.archive_reason,
            'organizer': olympiad.organizer,
        }
        for olympiad in olympiads
    ]
    by_norm = {item['name_norm']: item for item in items}
    return Catalog(
        olympiads=items,
        by_norm=by_norm,
        seasons=dict(seasons_by_olympiad),
    )


def _ratio(first: str, second: str) -> float:
    return SequenceMatcher(None, first, second).ratio()


def _candidates(name_norm: str, catalog: Catalog) -> list[dict]:
    scored = []
    for item in catalog.olympiads:
        ratio = _ratio(name_norm, item['name_norm'])
        if ratio >= CANDIDATE_THRESHOLD:
            scored.append((ratio, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1]['name_norm']))
    return [
        {
            'olympiad_id': item['id'],
            'name': item['name'],
            'score': round(ratio, 3),
            'status': item['status'],
        }
        for ratio, item in scored[:MAX_CANDIDATES]
    ]


def _match_name(name: str, catalog: Catalog) -> dict:
    name_norm = normalize_name(name)
    existing = catalog.by_norm.get(name_norm)
    if existing is not None:
        return {
            'action': 'use',
            'olympiad_id': existing['id'],
            'name_norm': name_norm,
            'confidence': 'ok',
            'candidates': _candidates(name_norm, catalog),
            'existing_status': existing['status'],
        }
    candidates = _candidates(name_norm, catalog)
    if candidates:
        return {
            'action': 'review',
            'olympiad_id': None,
            'name_norm': name_norm,
            'confidence': 'review',
            'candidates': candidates,
            'existing_status': None,
        }
    return {
        'action': 'create',
        'olympiad_id': None,
        'name_norm': name_norm,
        'confidence': 'ok',
        'candidates': [],
        'existing_status': None,
    }


def _group_rows(rows: list) -> list[dict]:
    """Сгруппировать строки профилей по олимпиаде, сохраняя порядок."""
    groups: list[dict] = []
    index: dict[str, dict] = {}
    for source_row, row in enumerate(rows, start=1):
        key = normalize_name(row.olympiad)
        group = index.get(key)
        if group is None:
            group = {
                'name': row.olympiad,
                'name_norm': key,
                'number': row.number,
                'organizer': row.organizer,
                'page': row.page,
                'source_rows': [],
                'profiles': [],
                'issues': [],
                'duplicate': False,
            }
            index[key] = group
            groups.append(group)
        elif row.number and group['number'] and row.number != group['number']:
            # Одна и та же олимпиада ещё раз со своим номером — дубль
            # раздела перечня, а не продолжение списка профилей.
            group['duplicate'] = True
        group['source_rows'].append(source_row)
        group['profiles'].append({
            'source_row': source_row,
            'name': row.profile,
            'name_norm': normalize_name(row.profile),
            'subjects': row.subjects,
            'level': row.level,
            'level_raw': row.level_raw,
            'page': row.page,
            'issues': list(row.issues or []),
            'match': {'action': 'create', 'profile_id': None},
            'previous_level': None,
        })
        if row.issues:
            group['issues'].extend(row.issues)
    return groups


def _plan_profiles(group: dict, season: dict | None, errors: list[str]) -> None:
    """Сопоставить профили документа с профилями сезона."""
    existing = {
        profile['name_norm']: profile
        for profile in (season or {}).get('profiles', [])
    }
    seen: dict[str, dict] = {}
    for profile in group['profiles']:
        key = profile['name_norm']
        if not key:
            errors.append(
                f'Строка {profile["source_row"]}: профиль не распознан'
            )
            profile['match'] = {'action': 'skip', 'profile_id': None}
            # Метка нужна, чтобы ошибка не исчезла при пересчёте плана:
            # «skip» ставится и администратором, а нераспознанную строку
            # обязательно нужно исправить, а не просто пропустить.
            profile['unrecognized'] = True
            continue
        if key in seen:
            errors.append(
                f'Строка {profile["source_row"]}: профиль «{profile["name"]}» '
                'повторяется в перечне'
            )
            profile['duplicate_of'] = seen[key]['source_row']
        seen.setdefault(key, profile)

        match = existing.get(key)
        if match is None:
            profile['match'] = {
                'action': 'create',
                'profile_id': None,
                'confidence': 'ok',
                'candidates': [],
            }
            if not profile['level']:
                errors.append(
                    f'Строка {profile["source_row"]}: у профиля '
                    f'«{profile["name"]}» не распознан уровень'
                )
            continue

        previous_level = match['rsosh_level']
        level = profile['level']
        changed = bool(level) and str(level) != str(previous_level or '')
        profile['previous_level'] = previous_level
        profile['match'] = {
            'action': 'update' if changed else 'use',
            'profile_id': match['id'],
            'confidence': 'ok',
            'candidates': [],
        }
        if changed:
            profile['level_change'] = {
                'from': previous_level,
                'to': level,
            }
        if not level:
            profile['match']['action'] = 'use'


def build_plan(
    parsed,
    *,
    doc_id: str,
    catalog: Catalog,
) -> dict:
    """Построить редактируемый план импорта.

    ``parsed`` — :class:`app.rsosh.list_parser.OfficialList`. План хранит
    только решения и ссылки на каталог; строки таблицы остаются отдельно,
    чтобы план можно было править, не переписывая распознанный документ.
    """
    warnings: list[str] = list(parsed.warnings or [])
    # Номера строк читаются хуже всего, а именно по ним видно потерянную
    # запись. Постраничные замечания о нумерации поднимаем в предупреждения
    # плана: в самом плане администратор их иначе не увидит.
    for report in parsed.pages or []:
        issues = report.get('issues') if isinstance(report, dict) else getattr(
            report, 'issues', None
        )
        for issue in issues or []:
            if 'номер' in issue.casefold():
                warnings.append(issue)
    errors: list[str] = []
    season_label = parsed.season_label
    if not season_label:
        errors.append(
            'В документе не найден учебный год: сезон не определён, '
            'сопоставление невозможно'
        )

    groups = _group_rows(parsed.rows)
    olympiads: list[dict] = []
    used_names: set[str] = set()

    for group in groups:
        match = _match_name(group['name'], catalog)
        if match['name_norm'] in used_names:
            errors.append(
                f'Олимпиада «{group["name"]}» встречается в перечне несколько раз'
            )
            match = {
                **match,
                'action': 'review',
                'confidence': 'review',
            }
        used_names.add(match['name_norm'])

        season = None
        season_action = 'create'
        if match['action'] == 'use' and season_label:
            season = catalog.season(match['olympiad_id'], season_label)
            if season is not None:
                season_action = 'use'

        _plan_profiles(group, season, errors)

        if match['action'] == 'review':
            warnings.append(
                f'Олимпиада «{group["name"]}»: есть похожие записи каталога — '
                'выберите существующую или создайте новую'
            )
        if match['action'] == 'use' and match.get('existing_status') == 'ARCHIVED':
            warnings.append(
                f'Олимпиада «{group["name"]}» найдена в архиве: импорт вернёт '
                'её в актуальный перечень'
            )

        olympiads.append({
            'name': group['name'],
            'name_norm': match['name_norm'],
            'number': group['number'],
            'organizer': group['organizer'],
            'page': group['page'],
            'source_rows': group['source_rows'],
            'match': match,
            'season': {
                'season_label': season_label,
                'action': season_action,
                'season_id': season['id'] if season else None,
            },
            'profiles': group['profiles'],
            'issues': list(dict.fromkeys(group['issues'])),
            'duplicate': group['duplicate'],
        })

    missing_pool: list[dict] = []
    for item in catalog.olympiads:
        season = catalog.season(item['id'], season_label) if season_label else None
        if season is None or season.get('is_archived'):
            continue
        missing_pool.append({
            'olympiad_id': item['id'],
            'name': item['name'],
            'name_norm': item['name_norm'],
            'season_id': season['id'],
            'season_label': season_label,
        })

    plan = {
        'doc_id': str(doc_id),
        'season_label': season_label,
        'title': parsed.title,
        'headers': list(parsed.headers or []),
        'complete': bool(parsed.complete),
        'source_pages': parsed.source_pages,
        'detected_tables': parsed.detected_tables,
        'olympiads': olympiads,
        'missing': [],
        'missing_pool': missing_pool,
        'missing_allowed': False,
        'duplicates': [
            item['name'] for item in olympiads if item.get('duplicate')
        ],
        'summary': {},
        'warnings': list(dict.fromkeys(warnings)),
        'errors': [],
    }
    if not (bool(parsed.complete) and bool(season_label)):
        if season_label:
            plan['warnings'].append(
                'Отсутствие олимпиад не фиксируется: перечень прочитан не '
                'полностью или содержит ошибки'
            )
    _recompute(plan)
    return plan


def _plan_errors(plan: dict) -> list[str]:
    """Ошибки плана, которые администратор обязан устранить до применения."""
    errors: list[str] = []
    if not plan.get('season_label'):
        errors.append(
            'В документе не найден учебный год: сезон не определён, '
            'сопоставление невозможно'
        )
    if plan.get('duplicates'):
        errors.append(
            'Олимпиады повторяются в перечне: ' + ', '.join(plan['duplicates'])
        )
    for item in plan.get('olympiads') or []:
        action = (item.get('match') or {}).get('action')
        if action == 'review':
            errors.append(
                f'Олимпиада «{item.get("name")}»: не выбрано совпадение '
                'с каталогом'
            )
        for profile in item.get('profiles') or []:
            profile_action = (profile.get('match') or {}).get('action')
            if profile.get('unrecognized') and (
                (profile.get('match') or {}).get('confidence') != 'manual'
            ):
                # Автоматический пропуск нераспознанной строки — это потеря
                # данных, а не решение. Явный пропуск администратором
                # (confidence=manual) допустим: скан мог быть нечитаемым.
                errors.append(
                    f'Строка {profile.get("source_row")}: профиль не распознан — '
                    'укажите название и уровень'
                )
                continue
            if profile.get('duplicate_of'):
                errors.append(
                    f'Строка {profile.get("source_row")}: профиль '
                    f'«{profile.get("name")}» повторяет строку '
                    f'{profile["duplicate_of"]}'
                )
            if profile_action == 'skip':
                continue
            if not (profile.get('name') or '').strip():
                errors.append(
                    f'Строка {profile.get("source_row")}: профиль без названия'
                )
            elif profile_action == 'create' and not profile.get('level'):
                errors.append(
                    f'Строка {profile.get("source_row")}: у профиля '
                    f'«{profile["name"]}» не указан уровень'
                )
    return errors


def _recompute(plan: dict) -> dict:
    """Пересчитать сводку, отсутствующие олимпиады и ошибки плана.

    Вызывается и после сборки, и после правок администратора: сводка должна
    описывать текущее состояние плана, иначе панель показывает «12 новых»
    рядом с исправленным планом, где новых уже 10.
    """
    olympiads = plan.get('olympiads') or []
    present_ids = {
        (item.get('match') or {}).get('olympiad_id')
        for item in olympiads
        if (item.get('match') or {}).get('action') == 'use'
    }
    present_norms = {
        item.get('name_norm') for item in olympiads
    }
    missing = [
        {**entry, 'reason': 'Олимпиада есть в каталоге за этот сезон, но не '
                            'найдена в документе'}
        for entry in plan.get('missing_pool') or []
        if entry['olympiad_id'] not in present_ids
        and entry['name_norm'] not in present_norms
    ]
    errors = _plan_errors(plan)
    allowed = bool(
        plan.get('complete') and plan.get('season_label') and not errors
    )
    plan['missing_allowed'] = allowed
    # Отсутствие доказуемо только по полному перечню без ошибок. Пока план
    # неполный или в нём есть неразрешённые строки, список пропавших пуст:
    # иначе администратор увидел бы «пропали», хотя документ просто не дочитан.
    plan['missing'] = missing if allowed else []
    plan['errors'] = errors
    plan['summary'] = {
        'olympiads': len(olympiads),
        'create': sum(
            1 for item in olympiads
            if (item.get('match') or {}).get('action') == 'create'
        ),
        'use': sum(
            1 for item in olympiads
            if (item.get('match') or {}).get('action') == 'use'
        ),
        'review': sum(
            1 for item in olympiads
            if (item.get('match') or {}).get('action') == 'review'
        ),
        'skip': sum(
            1 for item in olympiads
            if (item.get('match') or {}).get('action') == 'skip'
        ),
        'profiles': sum(len(item.get('profiles') or []) for item in olympiads),
        'profiles_create': sum(
            1 for item in olympiads for profile in item.get('profiles') or []
            if (profile.get('match') or {}).get('action') == 'create'
        ),
        'profiles_update': sum(
            1 for item in olympiads for profile in item.get('profiles') or []
            if (profile.get('match') or {}).get('action') == 'update'
        ),
        'profiles_skip': sum(
            1 for item in olympiads for profile in item.get('profiles') or []
            if (profile.get('match') or {}).get('action') == 'skip'
        ),
        'missing': len(missing),
        'errors': len(errors),
    }
    return plan


#: Действия над олимпиадой, которые администратор может выбрать руками.
OLYMPIAD_ACTIONS = ('create', 'use', 'skip')
#: Действия над профилем сезона.
PROFILE_ACTIONS = ('create', 'use', 'update', 'skip')


def apply_changes(plan: dict | None, changes: dict | None) -> dict:
    """Применить правки администратора к плану.

    Правки адресуются по ``name_norm`` олимпиады и ``source_row`` профиля, а
    не по индексам массива: клиент может прислать их в любом порядке, и
    переиндексация после предыдущей правки не сломает адресацию.

    Сопоставление, выбранное администратором, принимается как есть, но не
    проверяется на «похожесть»: ручной выбор — это решение, а не догадка
    алгоритма, и второй раз угадывать за человека нельзя.
    """
    if not plan:
        raise ValueError('План импорта не найден')
    changes = changes or {}

    # Внутри модуля normalize_name уже импортирован; локальный импорт
    # избавляет от цикла при чтении плана из метаданных документа.
    by_norm = {item['name_norm']: item for item in plan['olympiads']}

    for change in changes.get('olympiads') or []:
        item = by_norm.get(change.get('name_norm'))
        if item is None:
            raise ValueError(
                f'Олимпиада «{change.get("name_norm")}» не найдена в плане'
            )
        name = (change.get('name') or '').strip()
        if name and name != item['name']:
            new_norm = normalize_name(name)
            if not new_norm:
                raise ValueError('Название олимпиады не может быть пустым')
            clash = by_norm.get(new_norm)
            if clash is not None and clash is not item:
                raise ValueError(
                    f'Название «{name}» уже используется другой олимпиадой '
                    'в этом же перечне'
                )
            by_norm.pop(item['name_norm'], None)
            item['name'] = name
            item['name_norm'] = new_norm
            by_norm[new_norm] = item
        if change.get('organizer') is not None:
            item['organizer'] = (change['organizer'] or '').strip()
        action = change.get('action')
        if action is not None:
            if action not in OLYMPIAD_ACTIONS:
                raise ValueError(f'Недопустимое действие «{action}»')
            match = item.setdefault('match', {})
            match['action'] = action
            if action == 'use':
                olympiad_id = change.get('olympiad_id')
                if not olympiad_id:
                    raise ValueError(
                        f'Для олимпиады «{item["name"]}» нужно выбрать запись '
                        'каталога'
                    )
                match['olympiad_id'] = str(olympiad_id)
                match['confidence'] = 'manual'
            else:
                match['olympiad_id'] = None
                match['confidence'] = 'manual' if action == 'skip' else 'ok'
            season = item.setdefault('season', {})
            if action != 'use':
                season['action'] = 'create'
                season['season_id'] = None

    for change in changes.get('profiles') or []:
        item = by_norm.get(change.get('olympiad'))
        if item is None:
            raise ValueError(
                f'Олимпиада «{change.get("olympiad")}» не найдена в плане'
            )
        source_row = change.get('source_row')
        profile = next(
            (
                candidate for candidate in item.get('profiles') or []
                if candidate.get('source_row') == source_row
            ),
            None,
        )
        if profile is None:
            raise ValueError(
                f'Строка {source_row} не найдена у олимпиады «{item["name"]}»'
            )
        name = (change.get('name') or '').strip()
        if name:
            profile['name'] = name
            profile['name_norm'] = normalize_name(name)
            if profile.pop('unrecognized', None) and change.get('action') is None:
                # Администратор дал название нераспознанной строке — теперь это
                # обычный новый профиль сезона, а не пропущенная строка.
                match = profile.setdefault('match', {})
                match['action'] = 'create'
                match['profile_id'] = None
                match['confidence'] = 'manual'
        level = change.get('level')
        if level is not None:
            level = str(level).strip() or None
            if level not in (None, '1', '2', '3'):
                raise ValueError(
                    f'Недопустимый уровень «{level}»: ожидается I, II или III'
                )
            profile['level'] = level
        action = change.get('action')
        if action is not None:
            if action not in PROFILE_ACTIONS:
                raise ValueError(f'Недопустимое действие «{action}»')
            match = profile.setdefault('match', {})
            if action in ('use', 'update'):
                if not match.get('profile_id'):
                    raise ValueError(
                        f'Строка {source_row}: у профиля нет записи каталога '
                        'для изменения'
                    )
            elif action == 'create':
                match['profile_id'] = None
                profile['previous_level'] = None
            match['action'] = action
            match['confidence'] = 'manual'

    return _recompute(plan)
