"""Связь «университет → олимпиада → БВИ»: обе стороны и права.

Главный сценарий Papaya: университет показывает олимпиады, дающие БВИ, а
олимпиада — университеты, которые её принимают. Представитель университета
выбирает существующие олимпиады и не создаёт новые.
"""

import uuid

from tests.conftest import (
    admin_client,
    create_olympiad,
    create_university,
    register_user,
    university_rep_client,
)


async def _confirmed_link(client, university, olympiad):
    """Связать вуз с олимпиадой от имени представителя и подтвердить её."""
    rep = await university_rep_client(client, university['id'])
    created = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert created.status_code == 201, created.text
    assert created.json()['status'] == 'PENDING'

    await admin_client(client)
    confirmed = await client.post(
        f"/api/v1/universities/{university['id']}/bvi/{olympiad['id']}/status",
        json={'status': 'CONFIRMED'},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()['status'] == 'CONFIRMED'
    return rep


async def test_link_is_visible_on_both_sides(client):
    university = await create_university(client, 'Университет ИТМО', short_name='ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await _confirmed_link(client, university, olympiad)

    page = await client.get(f"/api/v1/universities/{university['id']}/olympiads")
    assert page.status_code == 200
    olympiads = page.json()['olympiads']
    assert [item['id'] for item in olympiads] == [olympiad['id']]
    assert olympiads[0]['bvi_status'] == 'CONFIRMED'

    back = await client.get(f"/api/v1/olympiads/{olympiad['id']}/universities")
    assert back.status_code == 200
    universities = back.json()['universities']
    assert [item['id'] for item in universities] == [university['id']]


async def test_pending_link_is_hidden_from_public_lists(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await university_rep_client(client, university['id'])

    created = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert created.status_code == 201

    client.cookies.clear()
    public = await client.get(f"/api/v1/universities/{university['id']}/olympiads")
    assert public.json()['olympiads'] == []

    public_back = await client.get(f"/api/v1/olympiads/{olympiad['id']}/universities")
    assert public_back.json()['universities'] == []


async def test_repeated_request_does_not_duplicate_link(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await university_rep_client(client, university['id'])

    first = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    second = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()['id'] == second.json()['id']

    await admin_client(client)
    links = await client.get('/api/v1/admin/bvi')
    assert links.status_code == 200
    matching = [
        link for link in links.json()['links']
        if link['olympiad_id'] == olympiad['id']
    ]
    assert len(matching) == 1


async def test_confirmed_link_stays_confirmed_after_repeated_request(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await _confirmed_link(client, university, olympiad)

    repeated = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert repeated.status_code == 201
    assert repeated.json()['status'] == 'CONFIRMED'


async def test_rep_cannot_create_olympiad(client):
    """Представитель выбирает существующие олимпиады, но не создаёт новые."""
    university = await create_university(client, 'Университет ИТМО')
    await university_rep_client(client, university['id'])

    response = await client.post(
        '/api/v1/olympiads/add_olympiad',
        json={'name': 'Олимпиада, созданная представителем'},
    )
    assert response.status_code == 403


async def test_rep_cannot_manage_foreign_university(client):
    first = await create_university(client, 'Университет ИТМО')
    other = await create_university(client, 'Университет МФТИ')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')

    await university_rep_client(client, first['id'])

    response = await client.post(
        f"/api/v1/universities/{other['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert response.status_code == 403

    edit = await client.post(
        f"/api/v1/universities/edit_university/{other['id']}",
        json={'name': 'Взлом'},
    )
    assert edit.status_code == 403


async def test_rep_sees_own_pending_requests(client):
    university = await create_university(client, 'Университет ИТМО')
    other = await create_university(client, 'Университет МФТИ')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await university_rep_client(client, university['id'])

    await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )

    own = await client.get(
        f"/api/v1/universities/{university['id']}/olympiads?include_pending=true"
    )
    assert own.status_code == 200
    assert len(own.json()['olympiads']) == 1

    foreign = await client.get(
        f"/api/v1/universities/{other['id']}/olympiads?include_pending=true"
    )
    assert foreign.status_code == 403


async def test_guest_cannot_view_pending_requests(client):
    university = await create_university(client, 'Университет ИТМО')
    client.cookies.clear()

    response = await client.get(
        f"/api/v1/universities/{university['id']}/olympiads?include_pending=true"
    )
    assert response.status_code == 401


async def test_anonymous_user_cannot_create_link(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    client.cookies.clear()

    response = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert response.status_code == 401


async def test_plain_user_cannot_manage_links(client):
    """Без роли представителя доступа к чужим каталогам нет."""
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')

    user = await register_user(client)
    from tests.conftest import promote_role

    await promote_role(user['id'], 'USER')

    response = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )
    assert response.status_code == 403


async def test_database_rejects_representative_without_university(client):
    """Инвариант роли защищён и на уровне БД, а не только в приложении."""
    import pytest
    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError

    from app.database.database import AsyncSessionLocal
    from app.models.users import Users

    user = await register_user(client)
    async with AsyncSessionLocal() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                update(Users)
                .where(Users.id == user['id'])
                .values(role='EDITOR', university_id=None)
            )
            await session.commit()
        await session.rollback()


async def test_admin_confirms_and_unconfirms_link(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await university_rep_client(client, university['id'])
    await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )

    await admin_client(client)
    confirmed = await client.post(
        f"/api/v1/universities/{university['id']}/bvi/{olympiad['id']}/status",
        json={'status': 'CONFIRMED'},
    )
    assert confirmed.status_code == 200

    dropped = await client.post(
        f"/api/v1/universities/{university['id']}/bvi/{olympiad['id']}/status",
        json={'status': 'PENDING'},
    )
    assert dropped.status_code == 200
    assert dropped.json()['status'] == 'PENDING'

    public = await client.get(f"/api/v1/universities/{university['id']}/olympiads")
    assert public.json()['olympiads'] == []


async def test_status_update_requires_admin(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await university_rep_client(client, university['id'])
    await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )

    response = await client.post(
        f"/api/v1/universities/{university['id']}/bvi/{olympiad['id']}/status",
        json={'status': 'CONFIRMED'},
    )
    assert response.status_code == 403


async def test_rep_removes_own_pending_request(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await university_rep_client(client, university['id'])
    await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )

    removed = await client.post(
        f"/api/v1/universities/{university['id']}/bvi/remove",
        json={'olympiad_id': olympiad['id']},
    )
    assert removed.status_code == 200

    again = await client.post(
        f"/api/v1/universities/{university['id']}/bvi/remove",
        json={'olympiad_id': olympiad['id']},
    )
    assert again.status_code == 404


async def test_rep_cannot_remove_confirmed_link(client):
    """Подтверждённая связь — публичный факт: снимает её администратор."""
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await _confirmed_link(client, university, olympiad)

    await university_rep_client(client, university['id'])
    await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': olympiad['id']},
    )

    denied = await client.post(
        f"/api/v1/universities/{university['id']}/bvi/remove",
        json={'olympiad_id': olympiad['id']},
    )
    assert denied.status_code == 409
    assert 'администратор' in denied.json()['detail']

    # Связь осталась на месте и по-прежнему видна публично.
    client.cookies.clear()
    public = await client.get(f"/api/v1/universities/{university['id']}/olympiads")
    assert [item['id'] for item in public.json()['olympiads']] == [olympiad['id']]


async def test_admin_can_remove_confirmed_link(client):
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await _confirmed_link(client, university, olympiad)

    removed = await client.post(
        f"/api/v1/universities/{university['id']}/bvi/remove",
        json={'olympiad_id': olympiad['id']},
    )
    assert removed.status_code == 200

    public = await client.get(f"/api/v1/universities/{university['id']}/olympiads")
    assert public.json()['olympiads'] == []


async def test_admin_revoke_keeps_link_but_hides_it(client):
    """Снятие подтверждения возвращает связь в статус заявки, а не удаляет её."""
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await _confirmed_link(client, university, olympiad)

    revoked = await client.post(
        f"/api/v1/universities/{university['id']}/bvi/{olympiad['id']}/status",
        json={'status': 'PENDING'},
    )
    assert revoked.status_code == 200
    assert revoked.json()['status'] == 'PENDING'

    client.cookies.clear()
    public = await client.get(f"/api/v1/universities/{university['id']}/olympiads")
    assert public.json()['olympiads'] == []


async def test_archived_olympiad_keeps_confirmed_link(client):
    """Архивная олимпиада не теряет подтверждённую связь с вузом."""
    university = await create_university(client, 'Университет ИТМО')
    olympiad = await create_olympiad(client, 'Олимпиада школьников «Физтех»')
    await _confirmed_link(client, university, olympiad)

    await client.post(f"/api/v1/admin/archive_olympiad/{olympiad['id']}")
    client.cookies.clear()

    public = await client.get(f"/api/v1/universities/{university['id']}/olympiads")
    assert [item['id'] for item in public.json()['olympiads']] == [olympiad['id']]
    assert public.json()['olympiads'][0]['status'] == 'ARCHIVED'

    back = await client.get(f"/api/v1/olympiads/{olympiad['id']}/universities")
    assert [item['id'] for item in back.json()['universities']] == [university['id']]


async def test_link_to_unknown_olympiad_is_404(client):
    university = await create_university(client, 'Университет ИТМО')
    await university_rep_client(client, university['id'])

    response = await client.post(
        f"/api/v1/universities/{university['id']}/bvi",
        json={'olympiad_id': str(uuid.uuid4())},
    )
    assert response.status_code == 404
