"""Контракт фронтенда: архив, история, модерация, отсутствие легаси."""

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[1] / 'app' / 'frontend' / 'js'


def _read(*parts: str) -> str:
    return FRONTEND.joinpath(*parts).read_text(encoding='utf-8')

def _entity_title_body() -> str:
    """╨в╨╡╨╗╨╛ ``entityTitleHtml`` тАФ ╨╛╨▒╤Й╨╕╨╣ ╨║╨╛╨╝╨┐╨╛╨╜╨╡╨╜╤В ╨╖╨░╨│╨╛╨╗╨╛╨▓╨║╨░ ╨║╨░╤А╤В╨╛╤З╨║╨╕."""
    source = _read('pages', 'home.js')
    match = re.search(
        r'function entityTitleHtml\(entity\) \{(.*?)\n\}',
        source,
        re.S,
    )
    assert match, 'entityTitleHtml ╨╜╨╡ ╨╜╨░╨╣╨┤╨╡╨╜ ╨▓ pages/home.js'
    return match.group(1)


def _entity_title_body() -> str:
    """Тело ``entityTitleHtml`` — общий компонент заголовка карточки."""
    source = _read('pages', 'home.js')
    match = re.search(
        r'function entityTitleHtml\(entity\) \{(.*?)\n\}',
        source,
        re.S,
    )
    assert match, 'entityTitleHtml не найден в pages/home.js'
    return match.group(1)


# ----------------------------------------------


def test_card_title_shows_short_name_first():
    """Краткое название идёт первым, полное — уточнением под ним.

    Порядок — часть концепции: карточка отвечает на вопрос «это МФТИ?», а не
    «какая у МФТИ полная форма имени». Обе ветки проверяются: с кратким именем
    и без него.
    """
    body = _entity_title_body()

    # Тело функции делится на две ветки: без краткого названия (условие
    # `if (!shortName ...) { ... }`) и с ним (остаток после скобки).
    branch = re.search(r'if \(!shortName[^)]*\) \{(.*?)\n    \}', body, re.S)
    assert branch, 'не найдена ветка без краткого названия'
    without_short = branch.group(1)
    with_short = body[branch.end():]

    # Без краткого названия единственным остаётся полное.
    fallback_h3 = re.search(r'<h3[^>]*>(.*?)</h3>', without_short, re.S)
    assert fallback_h3, 'в ветке без краткого названия нет заголовка'
    assert '${name}' in fallback_h3.group(1)

    # С кратким названием: заголовок — краткое, полное — строкой ниже.
    main_h3 = re.search(r'<h3[^>]*>(.*?)</h3>', with_short, re.S)
    assert main_h3, 'в ветке с кратким названием нет заголовка'
    assert '${shortName}' in main_h3.group(1), 'в заголовке ожидается краткое название'
    assert re.search(r'<p[^>]*>\$\{name\}</p>', with_short), (
        'полное название должно идти отдельной строкой под кратким'
    )


def test_entity_title_never_hides_full_name():
    """Полное название не прячется, даже если совпадает с кратким."""
    body = _entity_title_body()
    assert 'name' in body
    assert 'escHtml(entity.name' in body


def test_no_page_prefers_full_name_over_short_name():
    """Ни одна страница не ставит полное название выше краткого."""
    offenders = []
    for path in FRONTEND.rglob('*.js'):
        text = path.read_text(encoding='utf-8')
        # Прямое «сначала name, потом short_name» в разметке заголовков.
        for match in re.finditer(
            r'escHtml\(\s*([A-Za-z_.]+)\.name\s*\)[\s\S]{0,400}?'
            r'escHtml\(\s*\1\.short_name\s*\)',
            text,
        ):
            offenders.append(f'{path.name}:{text[:match.start()].count(chr(10)) + 1}')
    assert not offenders, 'полное название идёт раньше краткого: ' + ', '.join(
        offenders
    )


def test_university_pages_use_short_name_as_heading():
    """Заголовки страниц и кабинета — краткое имя, полное под ним."""
    page = _read('pages', 'universities.js')
    assert "escHtml(university.short_name || university.name)" in page

    cabinet = _read('pages', 'myuniversity.js')
    assert "escHtml(university.short_name || university.name)" in cabinet


# ----------------------------------------------


def test_source_block_always_rendered():
    """Блок источника показывается всегда, а не только когда есть ссылка.

    Иначе ручная запись выглядела бы как «источника нет», хотя источник есть —
    это за администратора.
    """
    source = _read('pages', 'olympiads.js')
    assert 'function sourceBlockHtml' in source
    body = re.search(r'function sourceBlockHtml\(source\) \{(.*?)\n\}', source, re.S)
    assert body, 'sourceBlockHtml(source) не найден'
    assert 'return `' in body.group(1)
    # Ранний выход «нет ни названия, ни ссылки» — как раз то, что убираем.
    assert 'if (!title && !url)' not in body.group(1)


def test_frontend_calls_source_endpoint():
    api = _read('api.js')
    assert 'getOlympiadSource' in api
    assert '/source' in api


# ----------------------------------------------


def test_no_frontend_call_to_removed_endpoint():
    """Клиент не должен знать про удалённый маршрут привязки."""
    for path in FRONTEND.rglob('*.js'):
        text = path.read_text(encoding='utf-8')
        assert '/admin/university' not in text, path.name
        assert 'assignUniversity' not in text, path.name


def test_role_is_saved_through_role_endpoint():
    api = _read('api.js')
    assert 'setUserRole' in api
    assert '/admin/role/' in api


def test_role_payload_sends_role_and_university_together():
    """Роль и привязка уходят одним запросом — иначе это два способа выдать права."""
    api = _read('api.js')
    match = re.search(r'setUserRole\([^)]*\)\s*\{(.*?)\n    \}', api, re.S)
    assert match, 'setUserRole не найден в api.js'
    body = match.group(1)
    assert 'role' in body
    assert 'university_id' in body


# ----------------------------------------------


def test_home_does_not_say_universities_come_from_rsosh():
    """РСОШ — источник каталога олимпиад, а не университетов."""
    home = _read('pages', 'home.js')
    assert 'Университеты заводит администратор Papaya' in home
    assert 'вручную или из документов РСОШ' not in home
    assert 'Олимпиады добавляются импортом документов РСОШ или вручную' not in home


def test_universities_are_the_main_catalog():
    """Главная: университеты — главный раздел, олимпиады — вторичный."""
    home = _read('pages', 'home.js')
    assert 'Каталог БВИ университетов' in home
    universities_pos = home.index('Каталог БВИ университетов')
    olympiads_pos = home.index('Перечень олимпиад РСОШ')
    assert universities_pos < olympiads_pos


def test_removed_service_block_is_absent():
    """Служебные даты на странице олимпиады убраны."""
    assert 'Служебное' not in _read('pages', 'olympiads.js')


def test_images_have_fallback_in_cards_and_pages():
    """Картинок две: превью для карточек, большая для страницы — с fallback."""
    home = _read('pages', 'home.js')
    assert 'function cardImageHtml' in home
    body = re.search(r'function cardImageHtml\(entity\) \{(.*?)\n\}', home, re.S)
    assert body, 'cardImageHtml не найден'
    assert 'preview_image || entity.image' in body.group(1)

    olympiads = _read('pages', 'olympiads.js')
    assert 'olympiad.image || olympiad.preview_image' in olympiads

    universities = _read('pages', 'universities.js')
    assert 'university.image || university.preview_image' in universities


@pytest.mark.parametrize(
    'filename',
    [
        'app.js',
        'api.js',
        'store.js',
        'router.js',
        'pages/admin.js',
        'pages/home.js',
        'pages/myuniversity.js',
        'pages/olympiads.js',
        'pages/search.js',
        'pages/universities.js',
    ],
)
def test_frontend_file_exists(filename):
    """Файлы фронтенда на месте: страница падает на отсутствующем скрипте."""
    assert FRONTEND.joinpath(filename).exists()

def test_frontend_uses_moderation_endpoint():
    """Клиент вызывает /moderation, а не произвольную смену статуса."""
    api = _read('api.js')
    assert 'moderateBvi' in api
    assert '/moderation' in api
    assert 'setBviStatus' not in api
    assert '/bvi/${olympiadId}/status' not in api


def test_admin_panel_offers_explicit_moderation_actions():
    """В панели есть подтвердить, отклонить и отозвать — по отдельности."""
    admin = _read('pages', 'admin.js')
    for action in ('confirmBvi', 'rejectBvi', 'revokeBvi'):
        assert action in admin, action
    assert 'dropBvi' not in admin
    for action in ('confirm', 'reject', 'revoke'):
        assert f"'{action}'" in admin, action


# ----------------------------------------------


def test_public_pages_do_not_render_archive_reason():
    """Публичные страницы не показывают технические enum-значения.

    `RSOSH_ABSENT` / `MANUAL` — внутренние значения для панели; посетитель
    видит понятный текст. Проверяется именно отрисованная разметка: enum может
    упоминаться в комментарии или в сравнении, но не попасть в HTML.
    """
    for name in ('pages/olympiads.js', 'pages/universities.js',
                 'pages/home.js', 'pages/myuniversity.js'):
        source = _read(*name.split('/'))
        # Публичные страницы вообще не знают про archive_reason.
        assert 'archive_reason' not in source, name
        # В разметке (внутри ${...} шаблонов) enum-значений нет.
        for match in re.finditer(r'\$\{([^}]*)\}', source):
            rendered = match.group(1)
            assert 'RSOSH_ABSENT' not in rendered, name
            assert "=== 'MANUAL'" not in rendered, name


def test_admin_panel_renders_reason_as_text():
    """Панель показывает причину архива словами, а не enum-значением.

    Сравнивать с enum-значением функция обязана — по нему выбирается текст, но
    наружу enum попадать не должен.
    """
    app = _read('app.js')
    body = re.search(r'function archiveReasonText\(reason\) \{(.*?)\n\}', app, re.S)
    assert body, 'archiveReasonText не найден'
    function = body.group(1)

    returned = re.findall(r"return ([^;]+);", function)
    assert returned, 'функция ничего не возвращает'
    for text in returned:
        assert 'RSOSH_ABSENT' not in text, text
        assert 'MANUAL' not in text, text
        assert 'архивирована' in text.lower() or 'перечн' in text.lower()


def test_archived_page_has_explicit_notice():
    """На странице архивной олимпиады есть явное объяснение."""
    source = _read('pages', 'olympiads.js')
    assert 'function archivedOlympiadNotice' in source
    body = re.search(
        r'function archivedOlympiadNotice\(\) \{(.*?)\n\}', source, re.S
    )
    assert body, 'archivedOlympiadNotice без тела'
    notice = body.group(1)
    assert 'не входит в актуальный' in notice
    # Обещание, что информация сохранена: архив не удаление.
    assert 'сохранены' in notice


def test_bvi_cards_distinguish_historical_links():
    """Карточки БВИ различают действующую и историческую связь."""
    universities = _read('pages', 'universities.js')
    body = re.search(
        r'function bviOlympiadCardHtml\(olympiad\) \{(.*?)\n\}',
        universities,
        re.S,
    )
    assert body, 'bviOlympiadCardHtml не найден'
    card = body.group(1)
    assert 'is_historical' in card
    assert 'Архивная олимпиада' in card
    assert 'Историческая связь' in card
    # Зелёное «БВИ» остаётся только для актуальных олимпиад.
    assert 'historical' in card


def test_olympiad_page_marks_universities_as_historical_when_archived():
    """На странице архивной олимпиады вузы показаны историческими, не выброшены."""
    source = _read('pages', 'olympiads.js')
    assert 'isArchived' in source
    assert 'Историческая связь' in source
    # Университеты не удаляются из списка при архиве.
    assert 'universities.map' in source


def test_rep_cabinet_shows_archived_links_as_historical():
    """В кабинете представителя архивная связь видна и объяснена."""
    source = _read('pages', 'myuniversity.js')
    assert 'is_historical' in source or "item.status === 'ARCHIVED'" in source
    assert 'Связь историческая' in source


# ----------------------------------------------


def test_frontend_has_no_delete_actions():
    """В интерфейсе нет физического удаления олимпиады или университета."""
    banned = ('deleteOlympiad', 'delete_university', 'deleteOlympiad(')
    for path in FRONTEND.rglob('*.js'):
        source = path.read_text(encoding='utf-8')
        for needle in banned:
            assert needle not in source, f'{path.name}: {needle}'


def test_picker_uses_current_catalog_only():
    """Выбор олимпиады для новой заявки берёт только актуальные записи.

    `listOlympiads` без `include_archived` возвращает `PUBLISHED`, поэтому
    архивную олимпиаду нельзя выбрать даже до серверной проверки.
    """
    source = _read('pages', 'myuniversity.js')
    match = re.search(r'api\.listOlympiads\((.*?)\)', source)
    assert match, 'вызов listOlympiads не найден'
    assert 'include_archived' not in match.group(1)
    assert 'true' not in match.group(1)
