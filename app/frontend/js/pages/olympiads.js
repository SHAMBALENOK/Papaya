/* ==========================================================================
 * pages/olympiads.js — каталог олимпиад и страница олимпиады.
 *
 *   #/olympiads          → GET /api/v1/olympiads
 *   #/olympiads/{id}     → GET /api/v1/olympiads/{id}
 *                          GET /api/v1/olympiads/{id}/seasons?profiles=true
 *                          GET /api/v1/olympiads/{id}/benefits?season_id=…
 *
 * Страница олимпиады показывает сезоны, профили выбранного сезона и правила
 * льгот именно этого сезона. Данные разных сезонов не смешиваются: у каждого
 * сезона свои профили, уровни РСОШ и правила. Архивный сезон остаётся
 * доступным — история не удаляется.
 * ========================================================================== */

async function renderOlympiads() {
    const page = document.getElementById('page');
    page.innerHTML = `
    <section class="pt-4 pb-16 md:pb-20">
        <p class="${UI.eyebrow}">Каталог</p>
        <h1 class="mt-3 text-3xl md:text-4xl font-extrabold tracking-tight leading-[1.1]">Олимпиады</h1>
        <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Единый каталог олимпиад перечня РСОШ. На странице олимпиады видно,
            за какие сезоны и профили университеты дают льготы при поступлении.
        </p>
        <form id="oly-search" class="mt-10 max-w-2xl" role="search">
            <label for="oly-search-input" class="sr-only">Поиск олимпиады</label>
            <div class="flex flex-col sm:flex-row gap-3">
                <input id="oly-search-input" name="q" type="search" autocomplete="off" value="${escAttr(store.searchQuery)}"
                       class="${UI.input} flex-1" placeholder="Например: олимпиада школьников «Физтех»">
                <button type="submit" class="${UI.btn} ${UI.btnPrimary} shrink-0">Найти</button>
            </div>
        </form>
        <label class="mt-6 inline-flex items-center gap-3 text-sm text-ink-soft">
            <input id="oly-archived" type="checkbox" class="w-4 h-4">
            Показывать архивные (не в перечне РСОШ)
        </label>
    </section>
    <section id="oly-list" aria-live="polite">${loadingHtml()}</section>`;

    document.getElementById('oly-search').addEventListener('submit', e => {
        e.preventDefault();
        store.setSearchQuery(document.getElementById('oly-search-input').value.trim());
        loadOlympiads();
    });
    document.getElementById('oly-archived').addEventListener('change', () => loadOlympiads());
    loadOlympiads();
}

async function loadOlympiads() {
    const box = document.getElementById('oly-list');
    if (!box) return;
    const includeArchived = document.getElementById('oly-archived')
        && document.getElementById('oly-archived').checked;
    box.innerHTML = loadingHtml();
    const res = await api.listOlympiads(store.searchQuery, includeArchived);
    if (!res.ok) {
        box.innerHTML = alertHtml(errorText(res), 'error');
        return;
    }
    const items = res.data.olympiads || [];
    box.innerHTML = items.length
        ? `<h2 class="sr-only">Результаты поиска</h2>
           <p class="text-sm text-ink-faint mb-6">Найдено: ${items.length}</p>
           <div class="grid gap-8 sm:grid-cols-2 xl:grid-cols-3">${items.map(olympiadCardHtml).join('')}</div>`
        : emptyHtml('Олимпиады не найдены',
                    'Попробуйте другое название: каталог ищет по названию и описанию.',
                    '<a href="#/olympiads" class="' + UI.btn + ' ' + UI.btnSecondary + '">Сбросить поиск</a>');
}

async function renderOlympiad(olympiadId) {
    const page = document.getElementById('page');
    if (!olympiadId) { renderNotFound(); return; }
    page.innerHTML = loadingHtml('Открываем олимпиаду…');

    const [olyRes, srcRes, seasonRes] = await Promise.all([
        api.getOlympiad(olympiadId),
        api.getOlympiadSource(olympiadId).catch(() => ({ ok: false })),
        api.listSeasons(olympiadId, { include_archived: true, profiles: true })
            .catch(() => ({ ok: false })),
    ]);

    if (!olyRes.ok || !olyRes.data) {
        page.innerHTML = emptyHtml('Олимпиада не найдена',
            'Возможно, она была удалена или ссылка неверна.',
            '<a href="#/olympiads" class="' + UI.btn + ' ' + UI.btnSecondary + '">К каталогу олимпиад</a>');
        return;
    }

    const olympiad = olyRes.data;
    const source = (srcRes.ok && srcRes.data) || null;
    const seasons = (seasonRes.ok && seasonRes.data && seasonRes.data.seasons) || [];
    const isAdmin = store.isAdmin();
    const isArchived = olympiad.status === 'ARCHIVED';

    page.innerHTML = `
    <article class="max-w-narrow mx-auto pb-16 md:pb-24">
        <a href="#/olympiads" class="inline-flex items-center gap-2 text-ink-soft font-semibold hover:text-ink transition-colors rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-brand">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5M12 19l-7-7 7-7"></path></svg>
            Все олимпиады
        </a>

        ${(olympiad.image || olympiad.preview_image) ? `
        <div class="mt-12 bg-mist shadow-elev-1">
            <img src="${escAttr(olympiad.image || olympiad.preview_image)}" alt="${escAttr(olympiad.name)}" class="w-full max-h-[22rem] object-cover"
                 onerror="this.onerror=null;this.parentElement.style.display='none'">
        </div>` : ''}

        <header class="mt-14">
            ${olympiadStatusBadge(olympiad.status)}
            <h1 class="mt-4 text-3xl md:text-4xl font-extrabold tracking-tight leading-[1.1]">${escHtml(olympiad.name)}</h1>
            ${olympiad.organizer
                ? `<p class="mt-4 text-lg text-ink-soft leading-relaxed">Организатор: ${escHtml(olympiad.organizer)}</p>`
                : ''}
        </header>

        <section class="mt-8 flex flex-wrap gap-3">
            ${olympiad.official_url
                ? `<a href="${escAttr(olympiad.official_url)}" target="_blank" rel="noopener noreferrer"
                      class="${UI.btn} ${UI.btnPrimary}">Официальный сайт олимпиады</a>`
                : `<p class="text-ink-soft leading-relaxed">Официальный сайт олимпиады пока не указан в каталоге.</p>`}
            ${summarySourceLinks(source, olympiadId)}
        </section>

        ${isArchived ? `
        <div class="mt-8">${alertHtml(archivedOlympiadNotice(), 'error')}</div>` : ''}

        ${olympiad.description ? `
        <section class="mt-14">
            <h2 class="${UI.eyebrow}">Описание</h2>
            <p class="mt-6 text-lg text-ink leading-[1.8] whitespace-pre-wrap wrap-anywhere">${escHtml(olympiad.description)}</p>
        </section>` : ''}

        ${sourceBlockHtml(source, olympiadId)}

        ${isAdmin ? `
        <section class="mt-12">
            <button type="button" id="oly-edit" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Редактировать олимпиаду</button>
        </section>` : ''}

        <section class="mt-20 md:mt-28" aria-labelledby="oly-seasons-title">
            <p class="${UI.eyebrow}">Сезоны и профили</p>
            <h2 id="oly-seasons-title" class="mt-5 text-3xl font-extrabold tracking-tight leading-[1.1]">Когда и в каком профиле действует льгота</h2>
            <p class="mt-6 text-lg text-ink-soft leading-relaxed">
                Уровень РСОШ принадлежит профилю конкретного сезона. Выберите сезон,
                чтобы увидеть его профили и правила льгот — данные разных сезонов
                не смешиваются.
            </p>
            <div id="oly-season-shell" class="mt-10"></div>
        </section>
    </article>`;

    const editBtn = document.getElementById('oly-edit');
    if (editBtn) {
        editBtn.addEventListener('click', () =>
            openOlympiadFormModal(olympiad, () => renderOlympiad(olympiadId)));
    }

    renderOlympiadSeasons(olympiadId, seasons);
}


/** Блок сезонов: переключатель актуальные/архивные, выбор сезона, профили и
 * правила выбранного сезона. */
function renderOlympiadSeasons(olympiadId, seasons) {
    const shell = document.getElementById('oly-season-shell');
    if (!shell) return;

    if (!seasons.length) {
        shell.innerHTML = emptyHtml('Сезоны не заведены',
            'Профили и правила появятся после того, как администратор добавит сезон.');
        return;
    }

    const actual = seasons.filter(item => !item.is_archived);
    const archived = seasons.filter(item => item.is_archived);
    let mode = actual.length ? 'actual' : 'archived';

    shell.innerHTML = `
        <div class="flex flex-wrap items-center gap-3" role="tablist" aria-label="Актуальные и архивные сезоны">
            <button type="button" data-season-mode="actual" class="${UI.btn} ${UI.btnSmall}" role="tab">
                Актуальные (${actual.length})
            </button>
            <button type="button" data-season-mode="archived" class="${UI.btn} ${UI.btnSmall}" role="tab">
                Архивные (${archived.length})
            </button>
        </div>
        <div id="oly-season-pills" class="mt-6 flex flex-wrap gap-2"></div>
        <div id="oly-season-content" class="mt-8"></div>`;

    let currentSeasonId = null;

    function setMode(next) {
        mode = next;
        const list = mode === 'actual' ? actual : archived;
        currentSeasonId = list.length
            ? (list.some(item => String(item.id) === String(currentSeasonId))
                ? currentSeasonId
                : list[0].id)
            : null;
        drawModeButtons();
        drawSeasonPills();
        drawSeasonContent();
    }

    function drawModeButtons() {
        shell.querySelectorAll('[data-season-mode]').forEach(btn => {
            const active = btn.dataset.seasonMode === mode;
            const list = mode === 'actual' ? actual : archived;
            btn.className = `${UI.btn} ${UI.btnSmall} ${active ? UI.btnPrimary : UI.btnGhost}`;
            btn.setAttribute('aria-selected', active ? 'true' : 'false');
            btn.disabled = (btn.dataset.seasonMode === 'archived' && !archived.length)
                || (btn.dataset.seasonMode === 'actual' && !actual.length);
        });
    }

    function drawSeasonPills() {
        const box = document.getElementById('oly-season-pills');
        if (!box) return;
        const list = mode === 'actual' ? actual : archived;
        if (!list.length) {
            box.innerHTML = `<p class="text-sm text-ink-soft">${
                mode === 'actual' ? 'Актуальных сезонов нет.' : 'Архивных сезонов нет.'
            }</p>`;
            return;
        }
        box.innerHTML = list.map(item => {
            const active = String(item.id) === String(currentSeasonId);
            return `<button type="button" data-season-id="${escAttr(item.id)}"
                class="rounded-md border px-4 py-2 text-sm font-semibold transition-colors
                    ${active
                        ? 'border-brand bg-brand-soft text-brand-strong'
                        : 'border-line bg-white text-ink-soft hover:border-brand/40 hover:text-ink'}">
                ${escHtml(item.season_label)}${item.is_archived ? ' · архив' : ''}
            </button>`;
        }).join('');
        box.querySelectorAll('[data-season-id]').forEach(btn => {
            btn.addEventListener('click', () => {
                currentSeasonId = btn.dataset.seasonId;
                drawSeasonPills();
                drawSeasonContent();
            });
        });
    }

    function drawSeasonContent() {
        const box = document.getElementById('oly-season-content');
        if (!box) return;
        const season = seasons.find(item => String(item.id) === String(currentSeasonId));
        if (!season) {
            box.innerHTML = emptyHtml('Сезон не выбран', 'Выберите сезон из списка выше.');
            return;
        }
        const profiles = season.profiles || [];
        box.innerHTML = `
            <div class="${UI.card} px-8 py-7">
                <div class="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <p class="text-sm font-semibold text-ink-soft">Сезон</p>
                        <p class="mt-1 text-2xl font-extrabold tracking-tight">${escHtml(season.season_label)}</p>
                    </div>
                    ${season.is_archived
                        ? `<span class="${UI.badge} ${UI.badgeNeutral}">Архивный сезон</span>`
                        : `<span class="${UI.badge} ${UI.badgeSuccess}">Актуальный сезон</span>`}
                </div>
                <div class="mt-8">
                    <p class="${UI.eyebrow}">Профили сезона</p>
                    ${profiles.length ? `<ul class="mt-4 space-y-3">${profiles.map(profile => `
                        <li class="border-t border-mist pt-3 first:border-0 first:pt-0">
                            <p class="font-semibold text-ink">${escHtml(profile.name)}</p>
                            <p class="mt-1 text-sm text-ink-soft">
                                ${profile.rsosh_level
                                    ? `Уровень РСОШ: ${escHtml(profile.rsosh_level)}`
                                    : 'Уровень РСОШ не указан'}
                                ${profile.description ? ` · ${escHtml(profile.description)}` : ''}
                            </p>
                        </li>`).join('')}</ul>`
                        : '<p class="mt-4 text-sm text-ink-soft">Профили сезона не заведены.</p>'}
                </div>
            </div>
            <div id="oly-season-benefits" class="mt-8">${loadingHtml('Загружаем льготы сезона…')}</div>
            <div id="oly-season-benefits-more" class="mt-6"></div>`;
        loadOlympiadSeasonBenefits(olympiadId, season.id);
    }

    setMode(mode);
}

/* Постраничная загрузка правил одного сезона: сезоны не смешиваются, а
   «Показать ещё» добавляет строки только этого сезона. */
let olympiadBenefitsState = { seasonId: null, rules: [], total: 0, offset: 0 };

async function loadOlympiadSeasonBenefits(olympiadId, seasonId) {
    const box = document.getElementById('oly-season-benefits');
    if (!box) return;
    if (String(olympiadBenefitsState.seasonId) !== String(seasonId)) {
        olympiadBenefitsState = { seasonId, rules: [], total: 0, offset: 0 };
    }
    const res = await api.listOlympiadBenefits(olympiadId, {
        season_id: seasonId,
        limit: 100,
        offset: olympiadBenefitsState.offset,
    });
    if (!res.ok) {
        box.innerHTML = alertHtml(errorText(res), 'error');
        return;
    }
    const rules = (res.data && res.data.rules) || [];
    olympiadBenefitsState.total = res.data && res.data.total != null ? res.data.total : rules.length;
    olympiadBenefitsState.rules = olympiadBenefitsState.rules.concat(rules);
    olympiadBenefitsState.offset = olympiadBenefitsState.rules.length;

    box.innerHTML = `<p class="${UI.eyebrow}">Льготы сезона</p>` + olympiadBenefitsHtml(
        olympiadBenefitsState.rules, benefitUniversityNames(olympiadBenefitsState.rules));

    const more = document.getElementById('oly-season-benefits-more');
    if (more) {
        more.innerHTML = olympiadBenefitsState.rules.length < olympiadBenefitsState.total
            ? `<div class="text-center"><button type="button" id="oly-benefits-more-btn"
                    class="${UI.btn} ${UI.btnSecondary}">Показать ещё</button></div>`
            : '';
        const btn = document.getElementById('oly-benefits-more-btn');
        if (btn) btn.addEventListener('click', () => loadOlympiadSeasonBenefits(olympiadId, seasonId));
    }
}

/* Публичный ответ правила уже содержит названия вуза и олимпиады, поэтому
   отдельный справочник вузов не нужен: карточка строится по rule. */
function benefitUniversityNames(rules) {
    const map = new Map();
    (rules || []).forEach(rule => {
        if (!map.has(String(rule.university_id))) {
            map.set(String(rule.university_id), {
                id: rule.university_id,
                name: rule.university_name,
                short_name: rule.university_short_name,
            });
        }
    });
    return map;
}

function summarySourceLinks(source, olympiadId) {
    const title = (source && source.title) || '';
    if (!title) return '';
    const fileLink = source && source.has_file
        ? ` · <a href="${escAttr(api.olympiadSourceFileUrl(olympiadId))}" target="_blank"
               rel="noopener noreferrer" class="underline decoration-line hover:decoration-brand">скачать документ</a>`
        : '';
    return `<p class="self-center text-sm text-ink-soft">Источник: ${escHtml(title)}${fileLink}</p>`;
}


/** Текст архивной олимпиады для публичной страницы. */
function archivedOlympiadNotice() {
    return 'Олимпиада не входит в актуальный каталог Papaya. '
         + 'Информация об олимпиаде, официальный сайт, сезоны, профили и '
         + 'ранее подтверждённые правила сохранены.';
}

/** Блок «Откуда взялась информация». */
function sourceBlockHtml(source, olympiadId) {
    const title = (source && source.title) || '';
    const hasFile = !!(source && source.has_file);

    const downloadHtml = hasFile
        ? `<a href="${escAttr(api.olympiadSourceFileUrl(olympiadId))}" target="_blank" rel="noopener noreferrer"
              class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall} mt-5">Скачать документ-источник</a>`
        : '';

    return `
        <section class="mt-14">
            <h2 class="${UI.eyebrow}">Откуда взялась информация</h2>
            <p class="mt-4 text-base font-semibold">${escHtml(title || 'Источник не указан')}</p>
            ${downloadHtml}
        </section>`;
}

/** Льготы, которые университеты дают за олимпиаду.
 *
 * Публичный список отдаёт опубликованные правила, включая непроверенные:
 * они честно помечены «Не проверено Papaya». Группировка по вузу отвечает на
 * вопрос «что именно даёт этот университет за диплом этой олимпиады».
 */
function olympiadBenefitsHtml(rules, universityNames) {
    if (!rules || !rules.length) {
        return emptyHtml('Льгот по этому сезону нет',
            'Правила появятся, когда представители университетов добавят их и '
            + 'опубликуют.');
    }

    const groups = new Map();
    rules.forEach(rule => {
        const key = String(rule.university_id);
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(rule);
    });

    const cards = [...groups.entries()].map(([universityId, items]) => {
        const university = universityNames.get(universityId);
        const universityName = university
            ? (university.short_name || university.name)
            : 'Университет';
        const universityHtml = university
            ? `<a href="#/universities/${escAttr(university.id)}"
                   class="underline decoration-mist hover:decoration-ink">${escHtml(universityName)}</a>`
            : escHtml(universityName);

        const rows = items.map(rule => {
            const typeLabel = benefitTypeLabel(rule.benefit_type);
            const result = benefitResultText(rule);
            const ege = benefitEgeLine(rule);
            return `
            <li class="border-t border-mist pt-4 first:border-0 first:pt-0">
                <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div class="min-w-0">
                        <p class="font-semibold text-ink leading-snug">
                            ${escHtml(typeLabel)}${result ? ` · ${escHtml(result)}` : ''}
                        </p>
                        <p class="mt-1 text-sm text-ink-soft">
                            ${rule.profile_name ? escHtml(rule.profile_name) : 'Профиль не указан'}
                            ${rule.profile_rsosh_level ? ` · уровень РСОШ ${escHtml(rule.profile_rsosh_level)}` : ''}
                        </p>
                        ${ege ? `<p class="mt-1 text-sm text-ink-soft">${escHtml(ege)}</p>` : ''}
                        ${rule.doc && rule.doc.name
                            ? `<p class="mt-1 text-xs text-ink-faint">Документ: ${
                                rule.doc.source_url
                                    ? `<a href="${escAttr(rule.doc.source_url)}" target="_blank" rel="noopener noreferrer"
                                           class="underline">${escHtml(rule.doc.name)}</a>`
                                    : escHtml(rule.doc.name)
                            }</p>`
                            : ''}
                    </div>
                    <div class="shrink-0 flex flex-wrap gap-2">
                        ${benefitStatusBadge(rule.verification_status)}
                        ${rule.needs_review ? `<span class="${UI.badge} ${UI.badgeDanger}">Требует уточнения</span>` : ''}
                    </div>
                </div>
            </li>`;
        }).join('');

        return `
        <div class="${UI.card} px-8 py-7">
            <p class="font-bold text-ink">${universityHtml}</p>
            <ul class="mt-4 space-y-4">${rows}</ul>
        </div>`;
    }).join('');

    return `
        <div class="mt-6 space-y-5">${cards}</div>`;
}
