"""Инварианты канонической модели MVP.

Проверяются правила, которые легко нарушить «по пути», потому что каждое из
них выглядит мелочью, а ломает состояние данных:

- правило льготы всегда привязано к олимпиаде, сезону и профилю;
- сезон принадлежит олимпиаде, профиль — сезону, документ — вузу;
- представитель создаёт правило только непроверенным и не может его подтвердить;
- публично видны опубликованные правила, кроме отклонённых;
- откат версии требует ожидаемую текущую версию и создаёт новую версию;
- архивная олимпиада не принимает новых правил, но сохраняет существующие.
"""

import uuid

from tests.conftest import (
    admin_client,
    create_benefit_rule,
    create_olympiad,
    create_profile,
    create_season,
    create_university,
    register_user,
    set_user_role,
    university_rep_client,
    upload_university_doc,
)

RULE_FIELDS = ('season_id', 'profile_id', 'benefit_type', 'required_result_type',
               'doc_id', 'ege_requirement', 'needs_review')


async def _rule_context(client, university_name='Университет ИТМО'):
    """Вуз, олимпиада, сезон, профиль и приказ — всё для одного правила."""
    await admin_client(client)
    university = await create_university(client, university_name)
    olympiad = await create_olympiad(client, f'Олимпиада {university_name}')
    season = await create_season(client, olympiad['id'])
    profile = await create_profile(client, season['id'])
    doc = await upload_university_doc(client, university['id'])
    return university, olympiad, season, profile, doc


async def _post_rule(client, university_id, **overrides):
    payload = {
        'olympiad_id': overrides.pop('olympiad_id'),
        'season_id': overrides.pop('season_id'),
        'profile_id': overrides.pop('profile_id'),
        'benefit_type': 'BVI',
        'required_result_type': 'WINNER',
        'doc_id': overrides.pop('doc_id'),
        **overrides,
    }
    return await client.post(
        f'/api/v1/universities/{university_id}/benefits', json=payload
    )


# ------------------------- Связность правила -------------------------


async def test_rep_cannot_create_rule_for_foreign_university(client):
    """Представитель не может создать правило чужому вузу."""
    university, olympiad, season, profile, doc = await _rule_context(client)
    own, _, _, _, _ = await _rule_context(client, 'Второй университет')
    # Сессия клиента — представитель второго вуза.
    await university_rep_client(client, own['id'])

    response = await _post_rule(
        client, university['id'],
        olympiad_id=olympiad['id'], season_id=season['id'],
        profile_id=profile['id'], doc_id=doc['id'],
    )
    assert response.status_code == 403


async def test_rule_requires_season_and_profile(client):
    """Без сезона и профиля правило не создаётся: 422, а не пустые поля."""
    university, olympiad, season, profile, doc = await _rule_context(client)
    response = await client.post(
        f"/api/v1/universities/{university['id']}/benefits",
        json={
            'olympiad_id': olympiad['id'],
            'benefit_type': 'BVI',
            'required_result_type': 'WINNER',
            'doc_id': doc['id'],
        },
    )
    assert response.status_code == 422
    assert 'season' in response.text.lower()


async def test_rule_rejects_season_of_other_olympiad(client):
    """Сезон другой олимпиады — 422: сезоны не смешиваются."""
    university, olympiad, season, profile, doc = await _rule_context(client)
    other_olympiad = await create_olympiad(client, 'Другая олимпиада')
    other_season = await create_season(client, other_olympiad['id'], '2024/2025')

    response = await _post_rule(
        client, university['id'],
        olympiad_id=olympiad['id'], season_id=other_season['id'],
        profile_id=profile['id'], doc_id=doc['id'],
    )
    assert response.status_code == 422
    assert 'season' in response.json()['detail'].lower()


async def test_rule_rejects_profile_of_other_season(client):
    """Профиль другого сезона — 422: профиль принадлежит конкретному сезону."""
    university, olympiad, season, profile, doc = await _rule_context(client)
    other_season = await create_season(client, olympiad['id'], '2024/2025')
    other_profile = await create_profile(client, other_season['id'], 'Физика', '2')

    response = await _post_rule(
        client, university['id'],
        olympiad_id=olympiad['id'], season_id=season['id'],
        profile_id=other_profile['id'], doc_id=doc['id'],
    )
    assert response.status_code == 422
    assert 'profile' in response.json()['detail'].lower()


async def test_rule_rejects_document_of_other_university(client):
    """Документ-основание обязан принадлежать тому же вузу."""
    university, olympiad, season, profile, doc = await _rule_context(client)
    other, _, _, _, other_doc = await _rule_context(client, 'Второй университет')
    await admin_client(client)

    response = await _post_rule(
        client, university['id'],
        olympiad_id=olympiad['id'], season_id=season['id'],
        profile_id=profile['id'], doc_id=other_doc['id'],
    )
    assert response.status_code == 422
    assert 'document' in response.json()['detail'].lower()


async def test_rule_rejects_document_that_is_not_university_order(client):
    """Основанием правила может быть только приказ университета."""
    university, olympiad, season, profile, doc = await _rule_context(client)
    await admin_client(client)
    other_doc = await upload_university_doc(
        client, university['id'], 'list.pdf', doc_type='OTHER',
    )

    response = await _post_rule(
        client, university['id'],
        olympiad_id=olympiad['id'], season_id=season['id'],
        profile_id=profile['id'], doc_id=other_doc['id'],
    )
    assert response.status_code == 422
    assert 'order' in response.json()['detail'].lower()


# ------------------------- Проверка и публикация -------------------------


async def test_rep_rule_is_unverified_and_cannot_be_verified_by_rep(client):
    """Представитель создаёт непроверенное правило и не подтверждает его сам."""
    university, olympiad, season, profile, doc = await _rule_context(client)
    await university_rep_client(client, university['id'])

    created = await _post_rule(
        client, university['id'],
        olympiad_id=olympiad['id'], season_id=season['id'],
        profile_id=profile['id'], doc_id=doc['id'],
    )
    assert created.status_code == 200, created.text
    rule = created.json()
    assert rule['verification_status'] == 'unverified'
    assert rule['needs_review'] is False

    verified = await client.post(f"/api/v1/benefits/{rule['id']}/verify")
    assert verified.status_code == 403


async def test_admin_verification_requires_document(client):
    """Подтвердить правило без документа-основания нельзя."""
    university, olympiad, season, profile, doc = await _rule_context(client)
    await admin_client(client)
    created = await _post_rule(
        client, university['id'],
        olympiad_id=olympiad['id'], season_id=season['id'],
        profile_id=profile['id'], doc_id=doc['id'],
    )
    assert created.status_code == 200

    # Убираем документ у правила: тогда подтверждение должно быть отклонено.
    from app.database.database import AsyncSessionLocal
    from app.models.benefits import BenefitRule
    from sqlalchemy import update

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(BenefitRule)
            .where(BenefitRule.id == uuid.UUID(created.json()['id']))
            .values(doc_id=None)
        )
        await session.commit()

    response = await client.post(
        f"/api/v1/benefits/{created.json()['id']}/verify"
    )
    assert response.status_code in (409, 422)
    assert 'документ' in response.text.lower() or 'document' in response.text.lower()


async def test_public_shows_unverified_published_but_hides_draft_and_rejected(client):
    """Публично: unverified + is_published видно, черновик и отклонённое — нет."""
    university, olympiad, season, profile, doc = await _rule_context(client)
    await admin_client(client)
    created = await _post_rule(
        client, university['id'],
        olympiad_id=olympiad['id'], season_id=season['id'],
        profile_id=profile['id'], doc_id=doc['id'],
    )
    rule = created.json()

    public = await client.get('/api/v1/benefits')
    assert public.status_code == 200
    ids = [item['id'] for item in public.json()['rules']]
    assert rule['id'] in ids, 'непроверенное опубликованное правило должно быть видно'

    rejected = await client.post(
        f"/api/v1/benefits/{rule['id']}/reject",
        json={'reason': 'Нет подтверждения из приказа'},
    )
    assert rejected.status_code == 200

    public = await client.get('/api/v1/benefits')
    ids = [item['id'] for item in public.json()['rules']]
    assert rule['id'] not in ids, 'отклонённое правило не показывается'

    detail = await client.get(f"/api/v1/benefits/{rule['id']}")
    assert detail.status_code == 404


async def test_reject_requires_reason(client):
    """Отклонение без причины — 422: причина нужна для истории и автору."""
    university, olympiad, season, profile, doc = await _rule_context(client)
    await admin_client(client)
    created = await _post_rule(
        client, university['id'],
        olympiad_id=olympiad['id'], season_id=season['id'],
        profile_id=profile['id'], doc_id=doc['id'],
    )

    response = await client.post(
        f"/api/v1/benefits/{created.json()['id']}/reject",
        json={'reason': '   '},
    )
    assert response.status_code in (400, 422)
    stored = await client.get(
        f"/api/v1/benefits/{created.json()['id']}/manage"
    )
    assert stored.json()['verification_status'] != 'rejected'


# ------------------------- Версии и откат -------------------------


async def test_rollback_requires_expected_version_and_creates_new_version(client):
    """Откат атомарен: несовпадение версии — 409, успех создаёт новую версию."""
    university, olympiad, season, profile, doc = await _rule_context(client)
    await admin_client(client)
    created = await _post_rule(
        client, university['id'],
        olympiad_id=olympiad['id'], season_id=season['id'],
        profile_id=profile['id'], doc_id=doc['id'],
    )
    rule = created.json()

    updated = await client.put(
        f"/api/v1/benefits/{rule['id']}",
        json={
            'version': rule['version'],
            'required_result_type': 'PRIZE',
        },
    )
    assert updated.status_code == 200, updated.text
    current = updated.json()
    assert current['version'] == rule['version'] + 1

    conflict = await client.post(
        f"/api/v1/benefits/{rule['id']}/rollback",
        json={'version': 1, 'expected_version': 999},
    )
    assert conflict.status_code == 409

    rolled = await client.post(
        f"/api/v1/benefits/{rule['id']}/rollback",
        json={'version': 2, 'expected_version': current['version']},
    )
    assert rolled.status_code == 200, rolled.text
    restored = rolled.json()
    # Откат не переписывает историю: создаётся новая версия поверх текущей.
    assert restored['version'] == current['version'] + 1
    assert restored['required_result_type'] == 'PRIZE'
    assert restored['verification_status'] == 'unverified'

    versions = await client.get(
        f"/api/v1/benefits/{rule['id']}/versions/manage"
    )
    assert versions.status_code == 200
    numbers = [item['version_number'] for item in versions.json()['versions']]
    assert restored['version'] in numbers


async def test_rollback_to_unknown_version_is_404(client):
    """Откат на несуществующую версию — 404, а не тихо пустая операция."""
    university, olympiad, season, profile, doc = await _rule_context(client)
    await admin_client(client)
    created = await _post_rule(
        client, university['id'],
        olympiad_id=olympiad['id'], season_id=season['id'],
        profile_id=profile['id'], doc_id=doc['id'],
    )
    rule = created.json()

    missing = await client.post(
        f"/api/v1/benefits/{rule['id']}/rollback",
        json={'version': 999, 'expected_version': rule['version']},
    )
    assert missing.status_code == 404


# ------------------------- Архив олимпиады -------------------------


async def test_archived_olympiad_keeps_existing_rule_but_rejects_new(client):
    """Архив не удаляет историю, но новые правила по олимпиаде не принимает."""
    university, olympiad, season, profile, doc = await _rule_context(client)
    await admin_client(client)
    created = await _post_rule(
        client, university['id'],
        olympiad_id=olympiad['id'], season_id=season['id'],
        profile_id=profile['id'], doc_id=doc['id'],
    )
    assert created.status_code == 200

    archived = await client.post(
        f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=true"
    )
    assert archived.status_code == 200

    kept = await client.get(f"/api/v1/benefits/{created.json()['id']}/manage")
    assert kept.status_code == 200
    assert kept.json()['id'] == created.json()['id']

    denied = await _post_rule(
        client, university['id'],
        olympiad_id=olympiad['id'], season_id=season['id'],
        profile_id=profile['id'], doc_id=doc['id'],
        required_result_type='PRIZE',
    )
    assert denied.status_code == 422
    assert 'archived' in denied.json()['detail'].lower()


# ------------------------- Публичный контракт олимпиады -------------------------


async def test_public_olympiad_has_no_technical_fields(client):
    """Публичная карточка не отдаёт служебные поля импорта и модерации."""
    olympiad = await create_olympiad(client, 'Олимпиада для публичной схемы')
    await admin_client(client)
    await client.post(
        f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=true"
    )

    detail = await client.get(f"/api/v1/olympiads/{olympiad['id']}")
    assert detail.status_code == 200
    body = detail.json()
    for field in ('name_norm', 'source_doc_id', 'createdAt', 'updatedAt',
                  'archive_reason', 'source_url'):
        assert field not in body, f'{field} не должен попадать в публичный ответ'
    assert set(body) == {
        'id', 'name', 'description', 'official_url', 'preview_image', 'image',
        'organizer', 'status', 'is_archived',
    }
    assert body['status'] == 'ARCHIVED'
    assert body['is_archived'] is True


async def test_legacy_bvi_endpoints_are_gone(client):
    """Отдельного процесса БВИ и источников больше нет в API."""
    schema = await client.get('/openapi.json')
    paths = schema.json()['paths']
    assert not [p for p in paths if '/bvi' in p], (
        'маршруты отдельной заявки БВИ должны быть удалены'
    )
    assert not [p for p in paths if p.endswith('/sources')], (
        'отдельной сущности источников быть не должно'
    )


# ------------------------- Один способ назначить представителя -------------------------


async def test_legacy_university_assignment_endpoint_is_gone(client):
    """Назначить представителя можно только через /admin/role."""
    user = await register_user(client)
    await admin_client(client)

    response = await client.post(
        f"/api/v1/admin/university/{user['id']}",
        json={'university_id': str(uuid.uuid4())},
    )
    assert response.status_code in (404, 405), response.text

    schema = await client.get('/openapi.json')
    paths = schema.json()['paths']
    assign_paths = [
        path for path in paths
        if 'university' in path and 'admin' in path
        and not path.endswith('/archive')
    ]
    assert not assign_paths


async def test_role_endpoint_is_the_working_way(client):
    """Единственный рабочий контракт назначения — /admin/role."""
    university = await create_university(client, 'Университет ИТМО')
    user = await register_user(client)
    await admin_client(client)

    response = await set_user_role(client, user['id'], 'EDITOR', university['id'])
    assert response.status_code == 200
    assert response.json()['role'] == 'EDITOR'
    assert response.json()['university_id'] == university['id']


async def test_self_edit_cannot_grant_rights(client):
    """Правка своего профиля не может выдать роль, вуз или разблокировку."""
    user = await register_user(client)

    response = await client.post(
        f"/api/v1/user/{user['id']}/edit_info",
        json={
            'name': 'Попытка повысить себя',
            'role': 'ADMIN',
            'isActive': True,
            'university_id': str(uuid.uuid4()),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()['role'] == 'USER'
    assert response.json()['university_id'] is None

    me = await client.get('/api/v1/')
    assert me.status_code == 200
    assert me.json()['role'] == 'USER'
    assert me.json()['university_id'] is None

    schema = await client.get('/openapi.json')
    body = schema.json()
    edit = body['paths']['/api/v1/user/{user_id}/edit_info']['post']
    referenced = set()
    for ref in edit.get('requestBody', {}).get('content', {}).values():
        schema_ref = ref.get('schema', {}).get('$ref', '')
        if schema_ref:
            name = schema_ref.rsplit('/', 1)[-1]
            referenced.add(name)
            referenced |= set(body['components']['schemas'][name].get('properties', {}))
    assert 'role' not in referenced
    assert 'isActive' not in referenced
    assert 'university_id' not in referenced


# ------------------------- Признак архива в публичном контракте -------------------------


async def test_is_archived_is_serialized_and_consistent(client):
    """Признак архива доезжает в JSON и совпадает со статусом."""
    olympiad = await create_olympiad(client, 'Олимпиада с признаком архива')

    fresh = await client.get(f"/api/v1/olympiads/{olympiad['id']}")
    assert fresh.status_code == 200
    assert fresh.json()['is_archived'] is False

    await admin_client(client)
    await client.post(
        f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=true"
    )

    archived = await client.get(f"/api/v1/olympiads/{olympiad['id']}")
    assert archived.json()['is_archived'] is True

    listing = await client.get('/api/v1/olympiads')
    assert listing.status_code == 200
    assert olympiad['id'] not in [
        entry['id'] for entry in listing.json()['olympiads']
    ]

    with_archived = await client.get('/api/v1/olympiads?include_archived=true')
    assert with_archived.status_code == 200
    item = next(
        entry for entry in with_archived.json()['olympiads']
        if entry['id'] == olympiad['id']
    )
    assert item['is_archived'] is True
    assert item['status'] == 'ARCHIVED'


# ------------------------- Валидация ссылок -------------------------
# ------------------------- Валидация ссылок -------------------------


BAD_URLS = [
    'javascript:alert(1)',
    'data:text/html;base64,PHNjcmlwdD4=',
    'file:///etc/passwd',
    'vbscript:msgbox(1)',
    'невалидная строка',
    'example.com',
    'https://',
]

GOOD_URLS = [
    'https://example.com',
    'http://example.com',
    'https://example.com/path?query=1#fragment',
    'https://sub.domain.example.ru/olympiad',
]


async def test_university_accepts_http_and_https(client):
    for url in GOOD_URLS:
        created = await create_university(
            client, f'Университет {url}', website=url, preview_image=url, image=url
        )
        assert created['website'] == url
        assert created['preview_image'] == url
        assert created['image'] == url


async def test_olympiad_accepts_http_and_https(client):
    for url in GOOD_URLS:
        created = await create_olympiad(
            client,
            f'Олимпиада {url}',
            official_url=url,
            preview_image=url,
            image=url,
        )
        assert created['official_url'] == url
        assert created['image'] == url


async def test_university_rejects_unsafe_urls(client):
    await admin_client(client)
    for url in BAD_URLS:
        response = await client.post(
            '/api/v1/universities/add_university',
            json={'name': f'Университет {url}', 'website': url},
        )
        assert response.status_code == 422, f'{url} должен отклоняться'


async def test_olympiad_rejects_unsafe_urls(client):
    await admin_client(client)
    for url in BAD_URLS:
        response = await client.post(
            '/api/v1/olympiads/add_olympiad',
            json={'name': f'Олимпиада {url}', 'official_url': url},
        )
        assert response.status_code == 422, f'{url} должен отклоняться'


async def test_image_urls_are_validated_too(client):
    """Картинки приходят в ``src``, поэтому схема важна там не меньше."""
    await admin_client(client)
    for field in ('preview_image', 'image'):
        response = await client.post(
            '/api/v1/universities/add_university',
            json={'name': f'Университет с {field}', field: 'javascript:alert(1)'},
        )
        assert response.status_code == 422, field

        olympiad = await client.post(
            '/api/v1/olympiads/add_olympiad',
            json={'name': f'Олимпиада с {field}', field: 'data:text/html,x'},
        )
        assert olympiad.status_code == 422, field


async def test_edit_also_validates_urls(client):
    """Правка проверяется так же, как создание: иначе обход через edit."""
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада ИТМО')

    bad_university = await client.post(
        f"/api/v1/universities/edit_university/{university['id']}",
        json={'website': 'javascript:alert(1)'},
    )
    assert bad_university.status_code == 422

    bad_olympiad = await client.post(
        f"/api/v1/olympiads/edit_olympiad/{olympiad['id']}",
        json={'official_url': 'file:///etc/passwd'},
    )
    assert bad_olympiad.status_code == 422


async def test_empty_url_becomes_absent(client):
    """Пустая ссылка — это «ссылки нет», а не ошибка ввода."""
    university = await create_university(client, 'Университет ИТМО', website='')
    assert university['website'] is None


# ------------------------- Защита единственного администратора -------------------------


async def test_last_admin_cannot_be_demoted(client):
    """Защиту последнего администратора нельзя обойти другим маршрутом.

    Раньше здесь стоял вызов ``/admin/demote_admin/{id}``. Маршрута больше нет,
    и это часть защиты: снять роль можно только через ``/role``, где запрет на
    последнего администратора проверяется атомарно. Сам запрет проверяет
    ``test_last_admin_cannot_be_demoted_through_role_endpoint`` — здесь
    удостоверяется, что обойти его нечем.
    """
    # Ровно один вызов admin_client: он заводит администратора, повторный вызов
    # завёл бы второго, и понижение было бы законным.
    admin = await admin_client(client)

    response = await client.post(f"/api/v1/admin/demote_admin/{admin['id']}")
    assert response.status_code in (404, 405), response.text

    # И по единственному существующему пути понижение всё ещё запрещено.
    guarded = await set_user_role(client, admin['id'], 'USER')
    assert guarded.status_code == 409
    assert 'администратор' in guarded.json()['detail'].lower()


async def test_last_admin_cannot_be_banned(client):
    """Блокировка последнего активного администратора запрещена."""
    admin = await admin_client(client)

    response = await client.post(f"/api/v1/admin/ban/{admin['id']}")
    assert response.status_code == 409


async def test_last_admin_cannot_be_demoted_through_role_endpoint(client):
    """Тот же запрет действует на общем маршруте смены роли.

    Иначе правило обходилось бы одной сменой роли в выпадающем списке.
    """
    admin = await admin_client(client)

    response = await set_user_role(client, admin['id'], 'USER')
    assert response.status_code == 409


async def test_admin_can_be_demoted_when_another_remains(client):
    """Со вторым администратором понижение допустимо."""
    first = await admin_client(client)
    second = await register_user(client)
    await admin_client(client)
    await set_user_role(client, second['id'], 'ADMIN')

    response = await set_user_role(client, first['id'], 'USER')
    assert response.status_code == 200
    assert response.json()['role'] == 'USER'


async def test_admin_can_be_banned_when_another_remains(client):
    """Блокировка допустима, пока в системе есть другой активный администратор."""
    first = await admin_client(client)
    second = await register_user(client)
    await admin_client(client)
    await set_user_role(client, second['id'], 'ADMIN')

    response = await client.post(f"/api/v1/admin/ban/{first['id']}")
    assert response.status_code == 200
    assert response.json()['isActive'] is False


async def test_banning_a_regular_user_is_not_blocked_by_admin_rules(client):
    """Правило про администраторов не мешает блокировать обычных пользователей."""
    user = await register_user(client)
    await admin_client(client)

    response = await client.post(f"/api/v1/admin/ban/{user['id']}")
    assert response.status_code == 200


async def test_demoting_inactive_admin_is_allowed(client):
    """Заблокированный администратор не держит систему: он и не считается активным."""
    from sqlalchemy import update

    from app.database.database import AsyncSessionLocal
    from app.models.users import Users

    first = await admin_client(client)
    user = await register_user(client)
    await admin_client(client)
    await set_user_role(client, user['id'], 'ADMIN')

    # Гасим первого администратора напрямую в БД — так выглядела бы поломка
    # данных, и она не должна оставлять систему «вечно запертой».
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Users).where(Users.id == first['id']).values(isActive=False)
        )
        await session.commit()

    response = await set_user_role(client, user['id'], 'USER')
    assert response.status_code == 200
    assert response.json()['role'] == 'USER'
