"""Инварианты, добавленные после ревизии 0.7.1.1.

Проверяются правила, которые легко нарушить «по пути», потому что каждое из
них выглядит мелочью, а ломает состояние данных:

- архивная олимпиада не принимает новых заявок БВИ, но сохраняет старые;
- ``confirmedBy`` живёт ровно вместе с ``CONFIRMED``;
- назначить представителя можно только ``POST /admin/role/{user_id}``;
- ссылки каталога — только ``http``/``https``;
- последнего активного администратора нельзя заблокировать или понизить.
"""

import uuid

from tests.conftest import (
    admin_client,
    create_olympiad,
    create_university,
    register_user,
    set_user_role,
    university_rep_client,
)


# ------------------------- Архивная олимпиада и БВИ -------------------------


async def _link(client, university_id, olympiad_id):
    return await client.post(
        f'/api/v1/universities/{university_id}/bvi',
        json={'olympiad_id': olympiad_id},
    )


async def test_rep_cannot_request_link_to_archived_olympiad(client):
    """Архивная олимпиада — историческая запись, новых связей не получает.

    Заявка БВИ означает «университет принимает поступление по этой олимпиаде
    сейчас». Для олимпиады, которой нет в актуальном перечне РСОШ, это неверно,
    поэтому заявка отклоняется, а связь не создаётся.
    """
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада вне перечня')
    await university_rep_client(client, university['id'])

    response = await _link(client, university['id'], olympiad['id'])
    assert response.status_code == 201, 'до архива заявка должна проходить'

    # Архивирует администратор, представитель на это не влияет.
    await admin_client(client)
    archived = await client.post(
        f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=true"
    )
    assert archived.status_code == 200
    assert archived.json()['status'] == 'ARCHIVED'

    # Второй вуз пытается заявить связь с той же архивной олимпиадой.
    other = await create_university(client, 'Университет МФТИ')
    rep = await university_rep_client(client, other['id'])
    assert rep['id']

    denied = await _link(client, other['id'], olympiad['id'])
    assert denied.status_code == 409
    assert 'архив' in denied.json()['detail'].lower()

    # Новая связь не создалась: в очереди осталась только та, что была до архива.
    await admin_client(client)
    queue = await client.get('/api/v1/admin/bvi')
    assert queue.status_code == 200
    links = queue.json()['links']
    assert [row['university_id'] for row in links] == [university['id']]
    assert other['id'] not in [row['university_id'] for row in links]


async def test_archived_olympiad_keeps_confirmed_link(client):
    """Архив не отменяет подтверждённые связи — он меняет только актуальность.

    Университет действительно давал БВИ, пока олимпиада была в перечне.
    """
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада с историей')
    await university_rep_client(client, university['id'])
    assert (await _link(client, university['id'], olympiad['id'])).status_code == 201

    await admin_client(client)
    confirmed = await client.post(
        f"/api/v1/universities/{university['id']}/bvi/{olympiad['id']}/status",
        json={'status': 'CONFIRMED'},
    )
    assert confirmed.status_code == 200

    archived = await client.post(
        f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=true"
    )
    assert archived.status_code == 200

    # Подтверждённая связь видна с обеих сторон и после архива.
    on_university = await client.get(f"/api/v1/universities/{university['id']}/olympiads")
    assert on_university.status_code == 200
    ids = [row['id'] for row in on_university.json()['olympiads']]
    assert olympiad['id'] in ids

    on_olympiad = await client.get(f"/api/v1/olympiads/{olympiad['id']}/universities")
    assert on_olympiad.status_code == 200
    university_ids = [row['id'] for row in on_olympiad.json()['universities']]
    assert university['id'] in university_ids


async def test_unknown_olympiad_is_404_not_409(client):
    """Отсутствующая олимпиада и архивная — разные ситуации и разные коды."""
    university = await create_university(client, 'Университет ИТМО')
    await university_rep_client(client, university['id'])

    response = await _link(client, university['id'], str(uuid.uuid4()))
    assert response.status_code == 404


# ------------------------- confirmedBy и статус -------------------------


async def test_confirmed_by_is_set_and_cleared_with_status(client):
    """Подтверждение и его автор существуют только вместе.

    ``PENDING`` означает «ещё никто не подтвердил», поэтому ``confirmedBy``
    обязан быть пустым: иначе по записи нельзя понять, кто сейчас отвечает за
    связь.
    """
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада для модерации')
    await university_rep_client(client, university['id'])

    created = await _link(client, university['id'], olympiad['id'])
    assert created.status_code == 201
    assert created.json()['status'] == 'PENDING'
    assert created.json()['confirmedBy'] is None

    admin = await admin_client(client)
    confirmed = await client.post(
        f"/api/v1/universities/{university['id']}/bvi/{olympiad['id']}/status",
        json={'status': 'CONFIRMED'},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()['status'] == 'CONFIRMED'
    assert confirmed.json()['confirmedBy'] == admin['id']

    dropped = await client.post(
        f"/api/v1/universities/{university['id']}/bvi/{olympiad['id']}/status",
        json={'status': 'PENDING'},
    )
    assert dropped.status_code == 200
    assert dropped.json()['status'] == 'PENDING'
    assert dropped.json()['confirmedBy'] is None


async def test_reconfirmation_sets_confirmed_by_again(client):
    """Повторное подтверждение снова фиксирует автора."""
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада для повтора')
    await university_rep_client(client, university['id'])
    await _link(client, university['id'], olympiad['id'])

    admin = await admin_client(client)
    url = f"/api/v1/universities/{university['id']}/bvi/{olympiad['id']}/status"
    await client.post(url, json={'status': 'CONFIRMED'})
    await client.post(url, json={'status': 'PENDING'})

    again = await client.post(url, json={'status': 'CONFIRMED'})
    assert again.status_code == 200
    assert again.json()['confirmedBy'] == admin['id']


# ------------------------- Один способ назначить представителя -------------------------


async def test_legacy_university_assignment_endpoint_is_gone(client):
    """Назначить представителя можно только через /admin/role.

    Отдельный маршрут «привязать университет» означал бы второй способ выдать
    права в обход инвариантов роли, поэтому его больше нет.
    """
    user = await register_user(client)
    await admin_client(client)

    response = await client.post(
        f"/api/v1/admin/university/{user['id']}",
        json={'university_id': str(uuid.uuid4())},
    )
    # Маршрута нет: 404 (пути не совпало) или 405 (совпало, но не тем методом) —
    # в обоих случаях назначить представителя этим путём нельзя.
    assert response.status_code in (404, 405), response.text

    # Точнее: пути нет в схеме API вообще.
    schema = await client.get('/openapi.json')
    assert schema.status_code == 200
    paths = schema.json()['paths']
    assert not [path for path in paths if 'university' in path and 'admin' in path], (
        'в API не должно быть маршрутов назначения университета админом'
    )


async def test_role_endpoint_is_the_working_way(client):
    """Единственный рабочий контракт назначения — /admin/role."""
    university = await create_university(client, 'Университет ИТМО')
    user = await register_user(client)
    await admin_client(client)

    response = await set_user_role(client, user['id'], 'EDITOR', university['id'])
    assert response.status_code == 200
    assert response.json()['role'] == 'EDITOR'
    assert response.json()['university_id'] == university['id']


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
            source_url=url,
        )
        assert created['official_url'] == url
        assert created['image'] == url
        assert created['source_url'] == url


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
    """Снятие роли у последнего активного администратора запрещено."""
    # Ровно один вызов admin_client: он заводит администратора, повторный вызов
    # завёл бы второго, и понижение было бы законным.
    admin = await admin_client(client)

    response = await client.post(f"/api/v1/admin/demote_admin/{admin['id']}")
    assert response.status_code == 409
    assert 'администратор' in response.json()['detail'].lower()


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

    response = await client.post(f"/api/v1/admin/demote_admin/{first['id']}")
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

    response = await client.post(f"/api/v1/admin/demote_admin/{user['id']}")
    assert response.status_code == 200
    assert response.json()['role'] == 'USER'
