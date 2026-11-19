"""Контракт фронтенда: архив, история, модерация, отсутствие легаси."""

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[1] / 'app' / 'frontend' / 'js'


def _read(*parts: str) -> str:
    return FRONTEND.joinpath(*parts).read_text(encoding='utf-8')

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
    body = re.search(r'function sourceBlockHtml\(source, olympiadId\) \{(.*?)\n\}', source, re.S)
    assert body, 'sourceBlockHtml(source) не найден'
    assert 'return `' in body.group(1)
    # Ранний выход «нет ни названия, ни ссылки» — как раз то, что убираем.
    assert 'if (!title && !hasFile)' not in body.group(1)


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
    assert 'Каталог университетов' in home
    universities_pos = home.index('Каталог университетов')
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

def test_frontend_uses_benefit_verification_endpoints():
    """Клиент подтверждает и отклоняет правило через явные маршруты.

    Отдельного процесса модерации БВИ больше нет: льгота создаётся правилом,
    представитель оставляет её непроверенной, а подтверждение и отклонение —
    действия администратора по документу-основанию.
    """
    api = _read('api.js')
    assert 'verifyBenefit' in api
    assert 'rejectBenefit' in api
    assert '/verify' in api
    assert '/reject' in api
    assert 'moderateBvi' not in api
    assert 'setBviStatus' not in api
    assert '/bvi' not in api
    assert '/admin/sources' not in api


def test_admin_panel_offers_verify_and_reject_with_reason():
    """В панели есть подтверждение и отклонение правила, отказ объясняется."""
    admin = _read('pages', 'admin.js')
    assert 'verifyBenefit' in admin
    assert 'rejectBenefit' in admin
    assert 'openRejectBenefitModal' in admin
    assert 'Причина отклонения' in admin
    assert 'dropBvi' not in admin
    assert 'confirmBvi' not in admin
    assert 'rejectBvi' not in admin
    assert 'revokeBvi' not in admin


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


def test_university_benefit_cards_show_season_and_profile():
    """Карточка льготы отвечает на вопрос «за какой сезон и профиль»."""
    universities = _read('pages', 'universities.js')
    body = re.search(
        r'function benefitCardsHtml\(rules\) \{(.*?)\n\}',
        universities,
        re.S,
    )
    assert body, 'benefitCardsHtml не найден'
    card = body.group(1)
    assert 'season_label' in card, 'карточка должна показывать сезон'
    assert 'profile_name' in card, 'карточка должна показывать профиль'
    assert 'profile_rsosh_level' in card, 'уровень РСОШ относится к профилю'
    assert 'benefitEgeLine' in card, 'требование ЕГЭ показывается отдельно'
    assert 'benefitStatusBadge' in card, 'статус проверки обязателен'
    assert 'needs_review' in card, 'неполное правило помечается'


def test_university_programs_are_independent_reference():
    """Программы — справочник вуза, а не привязка правила к программам."""
    universities = _read('pages', 'universities.js')
    assert 'Образовательные программы' in universities
    assert 'programs.map' in universities
    assert 'program_ids' not in universities


def test_olympiad_page_splits_actual_and_archived_seasons():
    """Страница олимпиады переключает актуальные и архивные сезоны.

    Один общий список смешивал сезоны, и страница переставала отвечать на
    вопрос «что действует сейчас». Архив сохраняет профили и правила.
    """
    source = _read('pages', 'olympiads.js')
    assert 'include_archived: true' in source, 'архив запрашивается явно'
    assert "mode === 'actual'" in source, 'нет режима актуальных сезонов'
    assert 'archived' in source
    assert 'Актуальные (' in source and 'Архивные (' in source
    assert 'season.profiles' in source, 'профили берутся из выбранного сезона'
    assert 'Архивный сезон' in source


def test_olympiad_page_does_not_mix_season_rules():
    """Правила загружаются только для выбранного сезона."""
    source = _read('pages', 'olympiads.js')
    assert 'loadOlympiadSeasonBenefits(olympiadId, seasonId)' in source
    assert 'season_id: seasonId' in source
    assert 'api.listOlympiadBenefits(olympiadId)' not in source


def test_benefit_statuses_have_text_not_only_color():
    """Статус проверки читается словами, а не только цветом."""
    app = _read('app.js')
    body = re.search(r'function benefitStatusBadge\(status\) \{(.*?)\n\}', app, re.S)
    assert body, 'benefitStatusBadge не найден'
    function = body.group(1)
    assert 'Не проверено Papaya' in function
    assert 'Проверено' in function
    assert 'Отклонено' in function


def test_rep_cabinet_shows_rule_versions_and_history():
    """В кабинете представителя есть история версий и откат."""
    source = _read('pages', 'myuniversity.js')
    assert 'data-rollback' in source
    assert 'rollbackBenefit' in source
    assert 'benefitVersionsManage' in source
    assert 'benefitStatusHistoryManage' in source
    assert 'Версия ${' in source


def test_rep_cabinet_can_request_missing_entities():
    """Отсутствующие олимпиады, сезоны и профили запрашиваются из кабинета."""
    source = _read('pages', 'myuniversity.js')
    assert 'createEntityRequest' in source
    assert 'listEntityRequests' in source
    assert 'entity_type' in source
    assert 'parent_id' in source


def test_no_false_bvi_claims():
    """Тексты не обещают поступление без оговорки «в этом университете».

    Papaya знает только пары «университет → олимпиада». Фраза «по диплому этой
    олимпиады можно поступить» без контекста обещает льготу во всех вузах сразу,
    чего в данных нет.
    """
    forbidden = [
        'по диплому этой олимпиады можно поступить',
        'поступление без вступительных испытаний за дипломы этих олимпиад',
    ]
    for path in FRONTEND.rglob('*.js'):
        source = path.read_text(encoding='utf-8')
        for phrase in forbidden:
            assert phrase not in source, f'{path.name}: {phrase}'


def test_archived_seasons_are_requested_explicitly():
    """Архивные сезоны не смешиваются с актуальными в общем запросе."""
    source = _read('pages', 'olympiads.js')
    assert 'include_archived: true' in source
    assert "filter(item => !item.is_archived)" in source
    assert "filter(item => item.is_archived)" in source


def test_rep_cabinet_explains_rule_state_and_missing_document():
    """В кабинете видно, почему правило нельзя подтвердить."""
    source = _read('pages', 'myuniversity.js')
    assert 'Нужно заполнить' in source
    assert 'Не выбран документ-основание' in source
    assert 'Причина отказа' in source


def test_frontend_has_no_delete_actions():
    """В интерфейсе нет физического удаления олимпиады или университета."""
    banned = ('deleteOlympiad', 'delete_university', 'deleteOlympiad(')
    for path in FRONTEND.rglob('*.js'):
        source = path.read_text(encoding='utf-8')
        for needle in banned:
            assert needle not in source, f'{path.name}: {needle}'


def test_picker_uses_current_catalog_only():
    """Выбор олимпиады для нового правила берёт только актуальные записи.

    ``listOlympiads`` без ``include_archived`` возвращает ``PUBLISHED``,
    поэтому архивную олимпиаду нельзя выбрать даже до серверной проверки.
    """
    source = _read('pages', 'myuniversity.js')
    match = re.search(r'api\.listOlympiads\((.*?)\)', source)
    assert match, 'вызов listOlympiads не найден'
    assert 'include_archived' not in match.group(1)
    assert 'true' not in match.group(1)


def test_import_confirm_refuses_outdated_snapshot_without_offering_a_way_around():
    """Устаревший перечень отклоняется, и обхода в интерфейсе не предлагается.

    В прошлой версии панель показывала диалог с кнопкой «Применить всё равно» и
    отправляла ``allow_outdated: true``. Такого пути в продукте быть не должно:
    актуальный каталог определяется последним подтверждённым перечнем.
    """
    source = _read('pages', 'admin.js')
    assert '409' in source, 'отказ по устаревшему перечню должен обрабатываться'
    assert 'allow_outdated' not in source, (
        'в панели не должно быть флага, отключающего проверку актуальности'
    )
    assert 'Применить всё равно' not in source, (
        'в панели не должно быть кнопки принудительного применения'
    )
    # Отказ объясняется, а не прячется: администратор должен понимать причину.
    assert 'showOutdatedImportNotice' in source
    assert 'нельзя' in source or 'невозможно' in source


def test_import_result_shows_archive_skipped_reason():
    """Причина пропущенного архивирования показывается администратору.

    Молчаливое «импорт применён» выглядит как «перечень актуален», хотя
    пропавшие олимпиады остались в каталоге.
    """
    source = _read('pages', 'admin.js')
    assert 'archive_skipped_reason' in source
    assert 'Архивирование пропущено' in source


def test_frontend_has_no_legacy_role_endpoints():
    """Управление ролью идёт только через /admin/role/{id}.

    Отдельные ``grant_admin``/``demote_admin`` удалены из API: они меняли роль
    без привязки, то есть давали второй путь, на котором инварианты роли могли
    разойтись. В интерфейсе таких вызовов быть не должно, а возможность повысить
    и снять роль остаётся через ``setUserRole``.
    """
    api = _read('api.js')
    assert '/admin/grant_admin/' not in api
    assert '/admin/demote_admin/' not in api
    assert 'grantAdmin' not in api
    assert 'demoteAdmin' not in api
    # Канонический вызов остался.
    assert '/admin/role/' in api

    for name in ('admin.js', 'myuniversity.js', 'profile.js', 'app.js'):
        source = _read('pages', name) if name != 'app.js' else _read('app.js')
        for banned in ('grantAdmin', 'demoteAdmin', 'grant_admin', 'demote_admin'):
            assert banned not in source, '{}: {}'.format(name, banned)

    # Отдельной кнопки-ярлыка «Сделать админом»/«Снять админа» в списке нет:
    # роль меняется только через выбор роли и общий «Сохранить роль», чтобы был
    # единственный путь и единственный источник истины о правах.
    admin = _read('pages', 'admin.js')
    assert 'Сделать админом' not in admin
    assert 'Снять админа' not in admin
    assert 'setUserRole' in admin


def test_admin_ui_shows_manual_archive_distinction():
    """Панель различает причины архива, иначе решение не объяснимо.

    Ручной архив администратора и «нет в перечне РСОШ» — разные вещи: первый
    возвращается только руками, второй — импортом. Если панель показывает
    одинаковое «Архивная», решение администратора выглядит отменённым при
    первом же импорте, и вернуть олимпиаду потом нечем.

    Тексты живут в общем помощнике ``archiveReasonText``, а в списке олимпиад
    панели ветка ``RSOSH_ABSENT`` выбирается явно, поэтому проверяются оба.
    """
    app_js = _read('app.js')
    assert 'MANUAL' in app_js, 'в панели должно быть объяснение ручного архива'
    assert 'RSOSH_ABSENT' in app_js or 'RSOSH_ABSENT' in _read('pages', 'admin.js'), (
        'в панели должно быть объяснение архива «нет в перечне РСОШ»'
    )
    # Формулировки обеих причин должны говорить, что с ними будет.
    assert 'Вернуть её в актуальные можно' in app_js
    assert 'вернётся автоматически' in app_js.lower()


def test_preview_import_is_a_side_effect_action():
    """Вход в preview — переход по маршруту, а не обработка ответа API.

    ``previewImport`` вызывает ``navigate`` (возвращает ``undefined``). Если он
    не в ``ADMIN_SIDE_EFFECT_ACTIONS``, ``handleAdminClick`` читает ``res.ok`` у
    ``undefined`` и показывает ложную «Сетевую ошибку» после каждого перехода.
    """
    admin = _read('pages', 'admin.js')
    body = re.search(
        r'const ADMIN_SIDE_EFFECT_ACTIONS = new Set\(\[(.*?)\]\);',
        admin,
        re.S,
    )
    assert body, 'ADMIN_SIDE_EFFECT_ACTIONS не найден'
    assert 'previewImport' in body.group(1), (
        'previewImport должен быть в ADMIN_SIDE_EFFECT_ACTIONS'
    )


def test_import_review_banners_for_finished_states():
    """Состояния вне review объясняются баннерами, а не падают ошибкой."""
    admin = _read('pages', 'admin.js')
    for phrase in ('Импорт уже применён', 'Результаты импорта отклонены',
                   'Импорт ещё обрабатывается'):
        assert phrase in admin, phrase


def test_rejected_import_cannot_be_restarted_from_frontend():
    """Кнопка «Запустить импорт» не рисуется для отклонённого прогона.

    ``REJECTED`` невозможно перезапустить по правилам бэкенда (повторный
    ``claim`` возвращает 409/400), поэтому фронтенд не предлагает действие,
    которое гарантированно упадёт. Кнопка остаётся для всех остальных
    состояний.
    """
    admin = _read('pages', 'admin.js')
    assert 'runImportAction' in admin, 'обработчик должен оставаться'
    guard = re.search(
        r"\$\{state === 'rejected' \? '' : `<button data-act=\"runImport\"",
        admin,
    )
    assert guard, (
        'кнопка runImport должна быть условной для REJECTED: '
        "`state === 'rejected' ? '' : '...'`"
    )
    # Баннер отклонённого прогона не обещает перезапуск.
    start = admin.index('Результаты импорта отклонены')
    rejected_branch = admin[start:admin.index("if (state === 'failed')", start)]
    assert 'перезапустить нельзя' in rejected_branch
    assert 'Запустите импорт заново' not in rejected_branch


def test_approved_import_stats_come_from_confirm_result():
    """Счётчики применённого импорта читаются из факта подтверждения.

    Для ``approved`` кандидаты — прошлый план: применённое известно только из
    ``imp.confirm`` (created/updated/archived/skipped) и read-only. Для
    ``failed`` блока статистики нет вовсе.
    """
    admin = _read('pages', 'admin.js')
    body = re.search(r'function statsHtml\(\) \{(.*?)\n    \}', admin, re.S)
    assert body, 'statsHtml не найден'

    segment = body.group(1)
    assert "state === 'approved'" in segment
    assert 'cr.created' in segment
    assert 'cr.updated' in segment
    assert 'cr.archived' in segment
    assert 'cr.skipped' in segment
    assert "state === 'failed'" in segment


def test_finished_import_stats_read_plan_from_candidates():
    """Вне review счётчики «Объединено/Новых» считаются из самих кандидатов.

    У завершённого прогона подтверждений нет (confirmedKeys пуст), поэтому
    план должен браться из ``action`` кандидатов, а не из пустого выбора.
    """
    admin = _read('pages', 'admin.js')
    body = re.search(r'function stats\(\) \{(.*?)\n    \}', admin, re.S)
    assert body, 'stats() не найден'
    assert 'reviewable' in body.group(1)
    assert "c.action === 'merge'" in body.group(1)
    assert "c.action === 'create'" in body.group(1)


def test_import_review_is_readonly_for_finished_imports():
    """Завершённые импорты показывают результаты без интерактивных кнопок.

    Кандидаты подтверждённого/отклонённого/упавшего импорта рендерятся
    отдельной карточкой без ``data-ri``-кнопок: изменять выбор уже нельзя.
    """
    admin = _read('pages', 'admin.js')
    body = re.search(
        r'function readonlyCandidateCardHtml\(c\) \{(.*?)\n    \}',
        admin,
        re.S,
    )
    assert body, 'readonlyCandidateCardHtml не найден'
    assert 'data-ri=' not in body.group(1), (
        'read-only карточка не должна содержать интерактивных кнопок'
    )
    # Интерактивные действия остаются, но только для review-ветки.
    assert 'data-ri="confirm"' in admin
    assert 'data-ri="delete"' in admin
    assert 'data-ri="edit"' in admin
    assert 'data-ri="unconfirm"' in admin


def test_import_review_has_no_manual_olympiad_flow():
    """Ручное добавление олимпиад убрано из окна импорта РСОШ.

    Остался один способ ручного создания — каталог олимпиад
    (``add_olympiad``). Из preview импорта «добавить вручную» исключено: это
    был второй путь записи олимпиады, не имеющей отношения к перечню.
    """
    admin = _read('pages', 'admin.js')
    for needle in ('openManualAdd', 'openManualEdit', 'manualCardHtml',
                   'confirm-manual', 'unconfirm-manual', 'delete-manual',
                   'edit-manual', 'data-ri="add"', 'Добавить олимпиаду вручную'):
        assert needle not in admin, needle


def test_modal_close_always_removes_keydown_listener():
    """Закрытие модалки снимает слушатель клавиатуры из любого пути.

    Раньше ``removeEventListener('keydown', onEsc)`` выполнялся только внутри
    обработчика Escape: закрытие по крестику или клику по подложке оставляло
    перехватчик нажатий. Снятие переехало в ``close()``, и оно идемпотентно.
    """
    app_js = _read('app.js')
    start = app_js.index('document.body.appendChild(overlay);')
    end = app_js.index('return { overlay, close };')
    tail = app_js[start:end]
    assert "if (e.key === 'Escape') close();" in tail, (
        'обработчик Escape только вызывает close, не снимает слушатель сам'
    )
    assert "document.removeEventListener('keydown', onEsc)" in tail, (
        'close() обязана снимать слушатель клавиатуры'
    )
    assert 'isConnected' in tail, (
        'close() должна быть идемпотентной (guard isConnected для повтора)'
    )


def test_admin_requests_queue_supports_status_filter_and_pagination():
    """Очередь запросов фильтруется по статусу и грузится порциями.

    Запросы на отсутствующие олимпиады, сезоны и профили — отдельная очередь:
    после одобрения сущность создаётся один раз, повторное одобрение даёт 409.
    """
    admin = _read('pages', 'admin.js')
    assert 'adminRequestsHtml' in admin
    assert 'data-request-status' in admin
    assert 'data-act="searchRequests"' in admin
    assert 'data-act="loadMoreRequests"' in admin
    assert 'data-act="approveRequest"' in admin
    assert 'data-act="rejectRequest"' in admin
    assert 'openRejectRequestModal' in admin
    assert 'rejectEntityRequest' in admin
    assert "label: 'Запросы в каталог'" in admin
    # Старого раздела и очереди БВИ больше нет.
    assert 'groupBviLinksByUniversity' not in admin
    assert 'loadMoreBvi' not in admin
    assert 'confirmAllBvi' not in admin
    assert '/admin/bvi' not in admin


def test_admin_has_no_sources_section():
    """Отдельного раздела источников в панели нет."""
    admin = _read('pages', 'admin.js')
    assert 'admin/sources' not in admin
    assert 'listSources' not in admin
    assert 'source_id' not in admin


def test_admin_benefits_filter_supports_needs_review():
    """Очередь модерации умеет показать только требующие уточнения правила."""
    admin = _read('pages', 'admin.js')
    assert 'data-benefit-needs-review' in admin
    assert 'Только требующие уточнения' in admin
    assert 'searchBenefits' in admin
    assert 'loadMoreBenefits' in admin


def test_admin_can_create_and_edit_benefit_rules():
    """Администратор добавляет и правит правила льгот из своей панели.

    Вкладка «Льготы» получает кнопку создания и действие правки, а форма
    открывается в админском режиме — с выбором университета.
    """
    admin = _read('pages', 'admin.js')
    assert 'data-act="newBenefit"' in admin
    assert 'data-act="editBenefit"' in admin
    assert 'Добавить правило' in admin
    assert 'openBenefitFormModal(null, null, [], () => reloadAdmin(), { admin: true })' in admin
    assert 'openBenefitFormModal(null, rule, [], () => reloadAdmin(), { admin: true })' in admin
    assert "'newBenefit', 'editBenefit'" in admin


def test_admin_benefit_form_chooses_university_and_reloads_docs():
    """В админской форме правило привязывается к выбранному вузу.

    Документы-основания и программы подгружаются для этого вуза, а не для
    кабинета представителя, поэтому выбор университета обязателен при создании.
    """
    cabinet = _read('pages', 'myuniversity.js')
    assert 'loadAdminUniversityOptions' in cabinet
    assert 'api.adminUniversities' in cabinet
    assert "id: 'benefit-university'" in cabinet
    assert 'adminMode' in cabinet
    assert 'options.admin' in cabinet
    assert 'loadOrderDocs' in cabinet
    assert 'benefit-doc-hint' in cabinet


def test_olympiad_edit_modal_contains_seasons_panel():
    """Добавление сезона живёт в окне правки олимпиады, рядом с её полями.

    Отдельная кнопка «Создать сезон» во вкладке «Сезоны» убрана: сезон — часть
    олимпиады, и выбирать её заново в другом окне больше не нужно.
    """
    app_js = _read('app.js')
    assert "id=\"ol-seasons-box\"" in app_js
    assert 'loadOlympiadSeasonsBox' in app_js
    assert "id=\"ol-season-add\"" in app_js
    assert 'api.createSeason(olympiadId' in app_js
    assert "size: isEdit ? 'xl' : 'lg'" in app_js
    assert 'lg:grid-cols-' in app_js

    admin = _read('pages', 'admin.js')
    assert 'data-act="newSeason"' not in admin
    assert 'Сезон добавляется в окне правки олимпиады' in admin


def test_reject_benefit_sends_reason_and_explains_empty_reason():
    """Отклонение отправляет непустую причину и не шлёт ``null``.

    Пустой body раньше давал техническое «Field required» от валидатора;
    теперь фронтенд проверяет причину до запроса и объясняет её по-русски.
    """
    admin = _read('pages', 'admin.js')
    start = admin.index('function openRejectBenefitModal(')
    end = admin.index('\n}', admin.index("showModalError(overlay, res);", start))
    body = admin[start:end]
    assert 'Укажите причину отклонения' in body
    assert 'const reason = (fd.get(\'reason\') || \'\').trim();' in body
    assert 'api.rejectBenefit(id, { reason })' in body
    assert 'reason: ' not in body
    assert 'null' not in body


def test_run_import_button_disabled_while_processing():
    """«Запустить импорт» неактивна, пока импорт уже идёт.

    Повторный старт во время ``processing`` — гарантированный 409, поэтому
    кнопка не должна выглядеть доступной.
    """
    admin = _read('pages', 'admin.js')
    button = next(
        line for line in admin.splitlines()
        if 'data-act="runImport"' in line
    )
    assert "state === 'processing'" in button
    assert 'disabled' in button


# ----------------------------------------------


def test_admin_nav_hides_my_university():
    """Администратору кабинет представителя не показывается в меню.

    Раздел «Мой университет» — это кабинет представителя; у администратора
    модерация БВИ уже есть в панели, и вкладка лишь дублировала бы её. Ссылка
    гейтится ``isUniversityRep`` (роль EDITOR + вуз), а не ``canManageUniversity``,
    который включает администратора.
    """
    app = _read('app.js')
    body = re.search(r'function navLinks\(\) \{(.*?)\n\}', app, re.S)
    assert body, 'navLinks не найден'
    segment = body.group(1)
    assert "'#/my-university'" in segment, 'ссылка на кабинет должна остаться для представителя'
    before = segment[:segment.index("'#/my-university'")]
    assert 'isUniversityRep' in before
    assert 'canManageUniversity' not in before, (
        'администратор не должен видеть вкладку «Мой университет»'
    )




