"""Сверка документации с реальной схемой API.

Документация разъезжается с кодом тихо: маршрут переименовали, а таблица в
docs осталась, и это замечают пользователи. Здесь проверяется то, что ломается
чаще всего и дороже всего:

- каждый путь и метод, упомянутые в ``docs/responses.md`` и ``English.md``,
  существует в схеме;
- публичные ответы не содержат служебных полей импорта и модерации;
- поля, которые документация обещает в ответе, действительно есть в схеме;
- контракт подтверждения импорта содержит ``allow_outdated`` и 409.
"""

import re
from pathlib import Path

from app.main import app

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = app.openapi()
PATHS = SCHEMA['paths']

#: Поля импорта и панели, которые не должны попадать в публичный ответ.
INTERNAL_FIELDS = {
    'name_norm', 'source_doc_id', 'createdAt', 'updatedAt', 'archive_reason',
}

#: Публичные маршруты, где утечка этих полей — нарушение контракта.
PUBLIC_ROUTES = [
    '/api/v1/universities/{university_id}',
    '/api/v1/universities',
    '/api/v1/olympiads/{olympiad_id}',
    '/api/v1/olympiads',
    '/api/v1/search',
    '/api/v1/universities/{university_id}/olympiads',
    '/api/v1/olympiads/{olympiad_id}/universities',
]


def _models() -> dict:
    return SCHEMA['components']['schemas']


def _resolve(schema: dict | None) -> dict:
    """Разворачивает ``$ref``/``anyOf``, чтобы увидеть поля модели.

    Необязательное тело описывается как ``anyOf: [ConfirmRequest, null]``, а
    наследование схем — как ``allOf``: и то и другое надо развернуть, иначе
    проверка видит пустое множество полей.
    """
    if not isinstance(schema, dict):
        return {}
    ref = schema.get('$ref')
    if isinstance(ref, str) and ref.startswith('#/components/schemas/'):
        return _models().get(ref.rsplit('/', 1)[-1], {})
    for key in ('anyOf', 'oneOf'):
        branches = schema.get(key)
        if isinstance(branches, list):
            for branch in branches:
                resolved = _resolve(branch)
                if resolved.get('properties'):
                    return resolved
    all_of = schema.get('allOf')
    if isinstance(all_of, list):
        merged: dict = {'properties': {}}
        for branch in all_of:
            resolved = _resolve(branch)
            merged['properties'].update(resolved.get('properties', {}))
        return merged
    return schema


def _fields(schema: dict | None) -> set[str]:
    return set(_resolve(schema).get('properties', {}))


def _json_body(operation: dict, code: str = '200') -> dict:
    return (
        operation.get('responses', {})
        .get(code, {})
        .get('content', {})
        .get('application/json', {})
        .get('schema', {})
    )


def _public_models_for(route: str) -> list[str]:
    """Имена моделей, из которых клиент читает ответ на маршрут."""
    operation = PATHS.get(route, {}).get('get')
    if not operation:
        return []
    root = _resolve(_json_body(operation))
    if not root:
        return []
    names = []
    ref = root.get('$ref')
    if isinstance(ref, str):
        names.append(ref.rsplit('/', 1)[-1])
    else:
        names.append('<inline>')
    # Контейнеры вида {"olympiads": [...]} раскрываем до элемента.
    for value in root.get('properties', {}).values():
        if not isinstance(value, dict):
            continue
        item = _resolve(value.get('items') or {})
        if 'properties' in item:
            names.extend(
                [n for n in (item.get('$ref'),) if isinstance(n, str)]
                or ['<inline-item>']
            )
    return names


def _normalize_route(route: str) -> str:
    """``/a/{id}`` и ``/a/{university_id}`` — один и тот же путь.

    Документация использует ``<id>`` и ``<olympiad_id>`` для читаемости, а
    схема — настоящие имена параметров. Сравниваем по сегментам, считая любой
    параметр одним и тем же плейсхолдером: иначе проверка ругается на стиль
    документации, а не на расхождение по существу.
    """
    parts = []
    for segment in route.split('/'):
        if segment.startswith('{') and segment.endswith('}'):
            parts.append('{}')
        elif segment.startswith('<') and segment.endswith('>'):
            parts.append('{}')
        else:
            parts.append(segment)
    return '/'.join(parts)


def test_documented_routes_exist():
    """Каждый маршрут из таблиц документации есть в схеме API."""
    pattern = re.compile(r'\|\s*`(GET|POST|PUT|PATCH|DELETE)`\s*\|\s*`([^`]+)`')
    real_routes = {_normalize_route(p) for p in PATHS}
    problems = []
    for doc in ('docs/responses.md', 'English.md'):
        text = (ROOT / doc).read_text(encoding='utf-8')
        for method, raw in pattern.findall(text):
            for piece in raw.split('`, `'):
                piece = piece.strip().strip('`').strip()
                if not piece.startswith('/'):
                    continue
                route = re.sub(r'<([^>]+)>', r'{\1}', piece)
                route = route.split('?')[0].rstrip('/')
                if _normalize_route(route) not in real_routes:
                    problems.append(f'{doc}: {method} {route} — нет в схеме')
                    continue
                real = {
                    m for m in PATHS[route]
                    if m in {'get', 'post', 'put', 'patch', 'delete'}
                } if route in PATHS else set()
                if real and method.lower() not in real:
                    problems.append(
                        f'{doc}: {method} {route} — в схеме нет этого метода'
                    )
    assert not problems, '\n'.join(problems)


def test_public_responses_hide_internal_fields():
    """Публичные ответы не отдают служебные поля импорта и панели."""
    models = _models()
    leaks = []
    for route in PUBLIC_ROUTES:
        for name in _public_models_for(route):
            leaked = INTERNAL_FIELDS & set(
                models.get(name, {}).get('properties', {})
            )
            if leaked:
                leaks.append(f'{route} ({name}): {sorted(leaked)}')
    assert not leaks, '\n'.join(leaks)


def test_public_models_are_not_admin_models():
    """Публичный маршрут не отдаёт админскую модель целиком."""
    problems = []
    for route in PUBLIC_ROUTES:
        for name in _public_models_for(route):
            if name in ('UniversityResponse', 'OlympiadResponse', 'UserResponse'):
                problems.append(f'{route} отдаёт админскую модель {name}')
    assert not problems, '\n'.join(problems)


def test_promised_fields_are_present():
    """Обещанные документацией поля есть в схеме."""
    problems = []
    promised = {
        '/api/v1/olympiads/{olympiad_id}': {'is_archived', 'source_url'},
        '/api/v1/olympiads/{olympiad_id}/universities': {'is_historical'},
        '/api/v1/universities/{university_id}/olympiads': {'is_historical'},
    }
    for route, fields in promised.items():
        operation = PATHS.get(route, {}).get('get')
        available = _fields(_json_body(operation)) if operation else set()
        root = _resolve(_json_body(operation))
        for value in root.get('properties', {}).values():
            if isinstance(value, dict):
                available |= _fields(value.get('items'))
        for field in fields - available:
            problems.append(f'{route}: нет обещанного поля {field}')
    assert not problems, '\n'.join(problems)


def test_bvi_request_response_hides_moderation_fields():
    """Ответ на заявку БВИ не содержит полей модерации."""
    operation = PATHS['/api/v1/universities/{university_id}/bvi']['post']
    props = _fields(_json_body(operation, '201'))
    assert props, 'у POST /bvi нет описанного ответа 201'
    for field in ('createdBy', 'confirmedBy', 'createdAt', 'updatedAt'):
        assert field not in props, f'{field} не должен отдаваться представителю'
    assert 'is_historical' in props, 'признак исторической связи должен отдаваться'


def test_confirm_contract_matches_documentation():
    """Подтверждение импорта: allow_outdated, 409 и итог с причиной."""
    operation = PATHS['/api/v1/imports/{import_id}/confirm']['post']
    body = (
        operation.get('requestBody', {})
        .get('content', {})
        .get('application/json', {})
        .get('schema', {})
    )
    props = _fields(body)
    for field in ('skip', 'archive_missing', 'allow_outdated'):
        assert field in props, f'в confirm нет документированного поля {field}'
    assert '409' in operation['responses'], 'в confirm нет ответа 409'

    status_props = _fields(_json_body(PATHS['/api/v1/imports/{import_id}']['get']))
    assert 'confirm' in status_props, (
        'статус импорта должен отдавать итог применения, включая '
        'archive_skipped_reason'
    )


def test_legacy_status_route_is_not_documented_or_present():
    """Старый маршрут смены статуса БВИ не вернулся."""
    assert not [p for p in PATHS if p.endswith('/status') and '/bvi' in p]
    text = (ROOT / 'docs/responses.md').read_text(encoding='utf-8')
    assert '/bvi/{olympiad_id}/status' not in text
    english = (ROOT / 'English.md').read_text(encoding='utf-8')
    assert 'bvi/<olympiad_id>/status' not in english