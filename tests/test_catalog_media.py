"""Картинки каталога, источник данных и архивирование олимпиад.

Три независимых правила, которые легко сломать по отдельности:

- у сущности две картинки: превью для карточек и большая для страницы; обе
  независимы, и страница не должна оставаться без картинки, если заполнено
  только превью (и наоборот);
- пользователь должен видеть, откуда взялись данные об олимпиаде, не получая
  доступа к самому документу;
- архив означает «нет в перечне РСОШ», и вернуть олимпиаду в актуальные
  можно не всегда: запись, исчезнувшую из перечня, возвращает импорт, а
  исключённую вручную — администратор.
"""

import os
import uuid

from app import database

from tests.conftest import (
    admin_client,
    create_olympiad,
    create_university,
    promote_role,
    register_user,
    set_user_role,
    upload_document,
)


# ------------------------------ Картинки ------------------------------


async def test_university_keeps_two_images(client):
    """Превью для карточек и большая картинка страницы — разные поля."""
    university = await create_university(
        client,
        'Университет ИТМО',
        preview_image='https://cdn.example/itmo/preview.png',
        image='https://cdn.example/itmo/hero.png',
    )
    assert university['preview_image'] == 'https://cdn.example/itmo/preview.png'
    assert university['image'] == 'https://cdn.example/itmo/hero.png'

    detail = await client.get(f"/api/v1/universities/{university['id']}")
    assert detail.status_code == 200
    assert detail.json()['preview_image'] == 'https://cdn.example/itmo/preview.png'
    assert detail.json()['image'] == 'https://cdn.example/itmo/hero.png'


async def test_olympiad_keeps_two_images(client):
    """Картинки олимпиады не смешиваются: превью не заменяет большую."""
    olympiad = await create_olympiad(
        client,
        'Олимпиада школьников «Ломоносов»',
        preview_image='https://cdn.example/lom/preview.png',
        image='https://cdn.example/lom/hero.png',
    )
    assert olympiad['preview_image'] == 'https://cdn.example/lom/preview.png'
    assert olympiad['image'] == 'https://cdn.example/lom/hero.png'

    catalog = await client.get('/api/v1/olympiads')
    assert catalog.status_code == 200
    item = next(row for row in catalog.json()['olympiads'] if row['id'] == olympiad['id'])
    # Карточкам каталога нужен превью-URL — он должен доезжать в списке.
    assert item['preview_image'] == 'https://cdn.example/lom/preview.png'


async def test_images_are_independently_optional(client):
    """Заполнено одно поле — второе остаётся пустым, а не копируется."""
    only_preview = await create_olympiad(
        client,
        'Олимпиада с превью',
        preview_image='https://cdn.example/only-preview.png',
    )
    assert only_preview['preview_image'] == 'https://cdn.example/only-preview.png'
    assert only_preview['image'] is None

    only_image = await create_university(
        client,
        'Университет с большой картинкой',
        image='https://cdn.example/only-hero.png',
    )
    assert only_image['image'] == 'https://cdn.example/only-hero.png'
    assert only_image['preview_image'] is None


async def test_admin_can_change_images(client):
    university = await create_university(client, 'Университет ИТМО')

    edited = await client.post(
        f"/api/v1/universities/edit_university/{university['id']}",
        json={'preview_image': 'https://cdn.example/new-preview.png'},
    )
    assert edited.status_code == 200
    assert edited.json()['preview_image'] == 'https://cdn.example/new-preview.png'


# ------------------------------ Источник ------------------------------


async def test_olympiad_source_of_manual_olympiad(client):
    """Ручная олимпиада — нормальное состояние, а не ошибка.

    У неё нет документа РСОШ, но источник данных всё равно существует: его завёл
    администратор. Раньше «нет документа» грозил ошибкой, и такая олимпиада
    выглядела сломанной.
    """
    olympiad = await create_olympiad(client, 'Олимпиада без документа')

    response = await client.get(f"/api/v1/olympiads/{olympiad['id']}/source")
    assert response.status_code == 200
    assert response.json() == {
        'title': 'Создано администратором Papaya',
        'has_file': False,
    }


async def test_olympiad_source_ignores_removed_source_url(client):
    """Поле ``source_url`` убрано из каталога олимпиад.

    Ссылка-источник заменена парой «заголовок источника + локальный файл»
    (``has_file``, скачивание через ``/source/file``). Легаси-поле в payload
    игнорируется и наружу не выходит ни в карточке, ни в источнике.
    """
    olympiad = await create_olympiad(
        client,
        'Олимпиада со ссылкой',
        source_url='https://rsr-olymp.ru/manual',
    )
    assert 'source_url' not in olympiad

    response = await client.get(f"/api/v1/olympiads/{olympiad['id']}/source")
    assert response.status_code == 200
    assert response.json() == {
        'title': 'Создано администратором Papaya',
        'has_file': False,
    }


async def test_olympiad_source_does_not_leak_internals(client):
    """Публичный источник отдаёт ровно два пользовательских поля.

    Внутренний UUID документа, имя файла, хеш и статус обработки — не
    пользовательская информация, и наружу они не выходят.
    """
    olympiad = await create_olympiad(client, 'Олимпиада без документа')
    response = await client.get(f"/api/v1/olympiads/{olympiad['id']}/source")
    assert response.status_code == 200
    assert set(response.json()) == {'title', 'has_file'}


async def test_public_olympiad_hides_source_doc_id(client):
    """Внутренний идентификатор документа не публикуется.

    ``source_doc_id`` нужен системе (импорт, архивирование) и администратору, но
    посетителю каталога он ничего не даёт, а рассказывает об устройстве
    импорта. Для источника есть отдельный маршрут.
    """
    olympiad = await create_olympiad(client, 'Олимпиада для проверки')

    detail = await client.get(f"/api/v1/olympiads/{olympiad['id']}")
    assert detail.status_code == 200
    assert 'source_doc_id' not in detail.json()

    catalog = await client.get('/api/v1/olympiads')
    assert 'source_doc_id' not in catalog.json()['olympiads'][0]


async def test_admin_still_sees_source_doc_id(client):
    """Администратору источник записи нужен: он управляет импортом и архивом."""
    olympiad = await create_olympiad(client, 'Олимпиада для админа')

    created = await client.post(
        f"/api/v1/olympiads/add_olympiad",
        json={'name': 'Олимпиада из ответа админа'},
    )
    assert created.status_code == 201
    assert 'source_doc_id' in created.json()

    admin_list = await client.get('/api/v1/admin/olympiads')
    assert admin_list.status_code == 200
    assert 'source_doc_id' in admin_list.json()['olympiads'][0]


async def test_olympiad_source_of_unknown_olympiad_is_404(client):
    response = await client.get(f'/api/v1/olympiads/{uuid.uuid4()}/source')
    assert response.status_code == 404


async def test_olympiad_source_has_file_matches_disk(client):
    """``has_file`` отражает реальный файл, а не только запись в БД.

    Запись о документе может пережить ручное удаление файла: тогда
    ``has_file=true`` обещал бы скачивание, ведущее в 404.
    """
    olympiad = await create_olympiad(client, 'Олимпиада с документом')
    doc = await upload_document(client, 'source.pdf', b'%PDF-1.4 fake')
    await database.olympiads.edit_olympiad(
        olympiad['id'], {'source_doc_id': doc['id']}
    )

    present = await client.get(f"/api/v1/olympiads/{olympiad['id']}/source")
    assert present.status_code == 200
    assert present.json()['has_file'] is True

    # Файл пропал с диска, но запись документа осталась.
    os.remove(os.path.join(os.environ['DOCS_DIR'], doc['storage_key']))

    missing = await client.get(f"/api/v1/olympiads/{olympiad['id']}/source")
    assert missing.json()['has_file'] is False


async def test_archived_olympiad_source_has_no_downloadable_file(client):
    """У архивной олимпиады файл-источник недоступен — ``has_file=false``.

    Публичная выдача файла разрешена только опубликованной олимпиаде, поэтому
    ``has_file`` не должен обещать кнопку скачивания для архивной записи.
    """
    olympiad = await create_olympiad(client, 'Олимпиада с документом')
    doc = await upload_document(client, 'source.pdf', b'%PDF-1.4 fake')
    await database.olympiads.edit_olympiad(
        olympiad['id'], {'source_doc_id': doc['id']}
    )
    archived = await client.post(
        f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=true"
    )
    assert archived.status_code == 200

    source = await client.get(f"/api/v1/olympiads/{olympiad['id']}/source")
    assert source.status_code == 200
    assert source.json()['has_file'] is False

    download = await client.get(f"/api/v1/olympiads/{olympiad['id']}/source/file")
    assert download.status_code == 404


# ------------------------------ Архив ------------------------------


async def test_manual_archive_and_restore(client):
    """Исключённую вручную олимпиаду можно вернуть — решение администратора."""
    olympiad = await create_olympiad(client, 'Олимпиада для ручного архива')

    archived = await client.post(
        f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=true"
    )
    assert archived.status_code == 200
    assert archived.json()['status'] == 'ARCHIVED'
    assert archived.json()['archive_reason'] == 'MANUAL'

    public = await client.get('/api/v1/olympiads')
    ids = [row['id'] for row in public.json()['olympiads']]
    assert olympiad['id'] not in ids

    restored = await client.post(
        f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=false"
    )
    assert restored.status_code == 200
    assert restored.json()['status'] == 'PUBLISHED'
    assert restored.json()['archive_reason'] is None


async def test_status_is_not_editable_through_olympiad_form(client):
    """Актуальность меняется только через архив-маршрут, а не правкой полей.

    Иначе причину архива можно было бы забыть: запись объявили бы
    актуальной, не вернув её в перечень РСОШ.
    """
    olympiad = await create_olympiad(client, 'Олимпиада без архива')

    response = await client.post(
        f"/api/v1/olympiads/edit_olympiad/{olympiad['id']}",
        json={'status': 'PUBLISHED', 'description': 'Описание'},
    )
    assert response.status_code == 200
    # Статус в ответе не изменился: неизвестные поля игнорируются.
    assert response.json()['status'] == 'PUBLISHED'
    assert response.json()['description'] == 'Описание'


async def test_archive_requires_admin(client):
    olympiad = await create_olympiad(client, 'Олимпиада под защитой')

    user = await register_user(client)
    response = await client.post(
        f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=true"
    )
    assert response.status_code == 403

    await promote_role(user['id'], 'ADMIN')
    allowed = await client.post(
        f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=true"
    )
    assert allowed.status_code == 200


async def test_archived_olympiad_is_visible_in_admin_with_reason(client):
    """Администратор видит архив и понимает, почему олимпиада там оказалась."""
    olympiad = await create_olympiad(client, 'Олимпиада в архиве')
    await client.post(f"/api/v1/admin/archive_olympiad/{olympiad['id']}?archived=true")

    listing = await client.get('/api/v1/olympiads?include_archived=true')
    assert listing.status_code == 200
    item = next(row for row in listing.json()['olympiads'] if row['id'] == olympiad['id'])
    assert item['status'] == 'ARCHIVED'
    assert item['is_archived'] is True
    # Причина архива — техническое значение для панели, не для посетителя.
    assert 'archive_reason' not in item

    admin_listing = await client.get('/api/v1/admin/olympiads')
    assert admin_listing.status_code == 200
    admin_item = next(
        row for row in admin_listing.json()['olympiads']
        if row['id'] == olympiad['id']
    )
    assert admin_item['archive_reason'] == 'MANUAL'


async def test_unknown_olympiad_archive_is_404(client):
    await admin_client(client)
    response = await client.post(
        f'/api/v1/admin/archive_olympiad/{uuid.uuid4()}?archived=true'
    )
    assert response.status_code == 404
