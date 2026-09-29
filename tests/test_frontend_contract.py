"""Контракт фронтенда: порядок названий, источник, роли, отсутствие легаси.

Статические файлы не исполняются в pytest, поэтому проверяются инварианты,
которые иначе ломаются молча: перевёрнутый порядок названий, удалённый
``short_name``, текст про университеты «из РСОШ» и остатки удалённого
``/admin/university`` в клиентском коде.
"""

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[1] / 'app' / 'frontend' / 'js'


def _read(*parts: str) -> str:
    return (FRONTEND.joinpath(*parts)).read_text(encoding='utf-8')


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


# ------------------------------ Названия ------------------------------


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


# ------------------------------ Источник ------------------------------


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


# ------------------------------ Роли ------------------------------


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


# ------------------------------ Концепция ------------------------------


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
