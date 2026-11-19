/* ==========================================================================
 * pages/benefits.js — публичный каталог правил льгот.
 *
 *   #/benefits → GET /api/v1/benefits
 *
 * Каталог отвечает на вопрос «какая олимпиада что даёт в конкретном вузе».
 * Фильтры комбинируются на сервере: вуз, олимпиада, сезон, профиль, уровень
 * РСОШ, тип льготы и поиск. Пагинация сохраняет фильтры, `total` приходит из
 * API, поэтому счётчик не врёт.
 *
 * Правило — олимпиада + сезон + профиль + тип льготы + требуемый результат +
 * документ университета. Требование ЕГЭ — необязательная часть правила.
 * ========================================================================== */

const BENEFIT_CATALOG_PAGE_SIZE = 24;

let benefitCatalogState = {
    rules: [],
    total: 0,
    search: '',
    benefitType: '',
    universityId: '',
    olympiadId: '',
    seasonId: '',
    level: '',
    limit: BENEFIT_CATALOG_PAGE_SIZE,
    offset: 0,
};

/* Названия вузов и олимпиад нужны карточкам, а серверный список правил отдаёт
   их одним JOIN-ом. Здесь остаются только подписи фильтров. */
let benefitCatalogNames = { universities: new Map(), olympiads: new Map() };

/* Сезоны выбранной олимпиады: сезон нельзя выбрать без олимпиады. */
let benefitCatalogSeasons = [];

async function renderBenefits() {
    const page = document.getElementById('page');
    page.innerHTML = `
    <section class="pt-2 pb-10 md:pb-12">
        <p class="${UI.eyebrow}">Каталог</p>
        <h1 class="mt-3 text-3xl md:text-4xl font-extrabold tracking-tight leading-[1.1]">Льготы</h1>
        <p class="mt-4 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Правила университетов: за какую олимпиаду, сезон и профиль вуз даёт
            БВИ, 100 баллов или другую льготу, и какой документ это подтверждает.
        </p>
        <form id="benefits-filter" class="mt-8 rounded-xl bg-mist p-4 md:p-5" role="search">
            <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <div class="lg:col-span-2">
                    <label for="benefits-search" class="sr-only">Поиск по льготам</label>
                    <input id="benefits-search" name="search" type="search" autocomplete="off"
                           class="${UI.input} bg-white" placeholder="Олимпиада, профиль, университет…">
                </div>
                <div>
                    <label for="benefits-type" class="sr-only">Тип льготы</label>
                    <select id="benefits-type" name="benefit_type" class="${UI.input} bg-white">
                        <option value="">Все типы льгот</option>
                        <option value="BVI">БВИ</option>
                        <option value="EGE_100">100 баллов ЕГЭ</option>
                        <option value="DVI_100">100 баллов ДВИ</option>
                        <option value="OTHER">Другая льгота</option>
                    </select>
                </div>
                <div>
                    <label for="benefits-university" class="sr-only">Университет</label>
                    <select id="benefits-university" name="university_id" class="${UI.input} bg-white">
                        <option value="">Все университеты</option>
                    </select>
                </div>
                <div>
                    <label for="benefits-olympiad" class="sr-only">Олимпиада</label>
                    <select id="benefits-olympiad" name="olympiad_id" class="${UI.input} bg-white">
                        <option value="">Все олимпиады</option>
                    </select>
                </div>
                <div>
                    <label for="benefits-season" class="sr-only">Сезон</label>
                    <select id="benefits-season" name="season_id" class="${UI.input} bg-white" disabled>
                        <option value="">Сначала выберите олимпиаду</option>
                    </select>
                </div>
                <div>
                    <label for="benefits-level" class="sr-only">Уровень РСОШ</label>
                    <select id="benefits-level" name="level" class="${UI.input} bg-white">
                        <option value="">Любой уровень РСОШ</option>
                        <option value="1">Уровень 1</option>
                        <option value="2">Уровень 2</option>
                        <option value="3">Уровень 3</option>
                    </select>
                </div>
                <div class="flex items-end gap-3">
                    <button type="submit" class="${UI.btn} ${UI.btnPrimary} shrink-0">Показать</button>
                    <button type="button" id="benefits-reset" class="${UI.btn} ${UI.btnGhost} shrink-0">Сбросить</button>
                </div>
            </div>
        </form>
        <p id="benefits-count" class="mt-4 text-sm text-ink-faint" aria-live="polite"></p>
    </section>
    <section id="benefits-list" aria-live="polite">${loadingHtml()}</section>
    <div class="mt-10" id="benefits-more"></div>`;

    await loadBenefitCatalogNames();
    fillBenefitCatalogUniversities();
    fillBenefitCatalogOlympiads();

    document.getElementById('benefits-filter').addEventListener('submit', e => {
        e.preventDefault();
        applyBenefitCatalogFilters();
    });
    document.getElementById('benefits-reset').addEventListener('click', () => {
        document.getElementById('benefits-filter').reset();
        benefitCatalogSeasons = [];
        fillBenefitCatalogSeasonSelect('', true);
        applyBenefitCatalogFilters();
    });
    document.getElementById('benefits-olympiad').addEventListener('change', async e => {
        await loadBenefitCatalogSeasons(e.target.value);
    });

    await loadBenefitCatalog(true);
}

async function loadBenefitCatalogNames() {
    const [uniRes, olyRes] = await Promise.all([
        api.listUniversities().catch(() => ({ ok: false })),
        api.listOlympiads('').catch(() => ({ ok: false })),
    ]);
    benefitCatalogNames.universities = new Map(
        ((uniRes.ok && uniRes.data && uniRes.data.universities) || [])
            .map(item => [String(item.id), item])
    );
    benefitCatalogNames.olympiads = new Map(
        ((olyRes.ok && olyRes.data && olyRes.data.olympiads) || [])
            .map(item => [String(item.id), item])
    );
}

function fillBenefitCatalogUniversities() {
    const select = document.getElementById('benefits-university');
    if (!select) return;
    const items = [...benefitCatalogNames.universities.values()]
        .sort((a, b) => String(a.name || '').localeCompare(String(b.name || ''), 'ru'));
    select.innerHTML = '<option value="">Все университеты</option>' + items.map(item => `
        <option value="${escAttr(item.id)}">${escHtml(item.short_name || item.name || 'Университет')}</option>`
    ).join('');
    select.value = benefitCatalogState.universityId;
}

function fillBenefitCatalogOlympiads() {
    const select = document.getElementById('benefits-olympiad');
    if (!select) return;
    const items = [...benefitCatalogNames.olympiads.values()]
        .sort((a, b) => String(a.name || '').localeCompare(String(b.name || ''), 'ru'));
    select.innerHTML = '<option value="">Все олимпиады</option>' + items.map(item => `
        <option value="${escAttr(item.id)}">${escHtml(item.name || 'Олимпиада')}</option>`
    ).join('');
    select.value = benefitCatalogState.olympiadId;
}

function fillBenefitCatalogSeasonSelect(selected, keepDisabled) {
    const select = document.getElementById('benefits-season');
    if (!select) return;
    if (keepDisabled) {
        select.innerHTML = '<option value="">Сначала выберите олимпиаду</option>';
        select.disabled = true;
        select.value = '';
        return;
    }
    select.disabled = false;
    select.innerHTML = '<option value="">Все сезоны</option>' + benefitCatalogSeasons.map(item => `
        <option value="${escAttr(item.id)}">${escHtml(item.season_label)}${item.is_archived ? ' (архив)' : ''}</option>`
    ).join('');
    select.value = selected || '';
}

async function loadBenefitCatalogSeasons(olympiadId, selected) {
    if (!olympiadId) {
        benefitCatalogSeasons = [];
        fillBenefitCatalogSeasonSelect('', true);
        return;
    }
    const res = await api.listSeasons(olympiadId, { include_archived: true });
    benefitCatalogSeasons = (res.ok && res.data && res.data.seasons) || [];
    fillBenefitCatalogSeasonSelect(selected || '');
}

function applyBenefitCatalogFilters() {
    benefitCatalogState.search = ((document.getElementById('benefits-search') || {}).value || '').trim();
    benefitCatalogState.benefitType = (document.getElementById('benefits-type') || {}).value || '';
    benefitCatalogState.universityId = (document.getElementById('benefits-university') || {}).value || '';
    benefitCatalogState.olympiadId = (document.getElementById('benefits-olympiad') || {}).value || '';
    benefitCatalogState.seasonId = (document.getElementById('benefits-season') || {}).value || '';
    benefitCatalogState.level = (document.getElementById('benefits-level') || {}).value || '';
    loadBenefitCatalog(true);
}

async function loadBenefitCatalog(reset) {
    const list = document.getElementById('benefits-list');
    const more = document.getElementById('benefits-more');
    if (!list) return;
    if (reset) {
        benefitCatalogState.offset = 0;
        list.innerHTML = loadingHtml('Ищем льготы…');
        if (more) more.innerHTML = '';
    }

    const res = await api.listBenefits({
        search: benefitCatalogState.search,
        benefit_type: benefitCatalogState.benefitType,
        university_id: benefitCatalogState.universityId,
        olympiad_id: benefitCatalogState.olympiadId,
        season_id: benefitCatalogState.seasonId,
        level: benefitCatalogState.level,
        limit: benefitCatalogState.limit,
        offset: benefitCatalogState.offset,
    });
    if (!res.ok) {
        list.innerHTML = alertHtml(errorText(res), 'error');
        return;
    }

    const rules = (res.data && res.data.rules) || [];
    benefitCatalogState.total = res.data && res.data.total != null ? res.data.total : rules.length;
    benefitCatalogState.rules = reset ? rules : benefitCatalogState.rules.concat(rules);
    benefitCatalogState.offset = benefitCatalogState.rules.length;

    const count = document.getElementById('benefits-count');
    if (count) {
        count.textContent = benefitCatalogState.total
            ? `Найдено: ${benefitCatalogState.total}`
            : 'Ничего не найдено';
    }

    if (!benefitCatalogState.rules.length) {
        list.innerHTML = emptyHtml('Льготы не найдены',
            'Попробуйте изменить фильтры: каталог показывает опубликованные правила, '
            + 'включая непроверенные — они помечены предупреждением.');
        return;
    }

    list.innerHTML = `<div class="space-y-5">${benefitCatalogState.rules
        .map(benefitCatalogCardHtml).join('')}</div>`;

    if (more) {
        more.innerHTML = benefitCatalogState.rules.length < benefitCatalogState.total
            ? `<div class="text-center"><button type="button" id="benefits-more-btn"
                    class="${UI.btn} ${UI.btnSecondary}">Показать ещё</button></div>`
            : '';
        const btn = document.getElementById('benefits-more-btn');
        if (btn) btn.addEventListener('click', () => loadBenefitCatalog(false));
    }
}

function benefitContextLine(rule) {
    const parts = [];
    if (rule.season_label) parts.push(`сезон ${rule.season_label}`);
    if (rule.profile_name) {
        parts.push(rule.profile_rsosh_level
            ? `${rule.profile_name} · уровень РСОШ ${rule.profile_rsosh_level}`
            : rule.profile_name);
    }
    return parts.join(' · ');
}

function benefitCatalogCardHtml(rule) {
    const university = benefitCatalogNames.universities.get(String(rule.university_id));
    const olympiad = benefitCatalogNames.olympiads.get(String(rule.olympiad_id));
    const universityLabel = benefitCatalogName(
        benefitCatalogNames.universities, rule.university_id,
        rule.university_short_name || rule.university_name || 'Университет');
    const olympiadLabel = benefitCatalogName(
        benefitCatalogNames.olympiads, rule.olympiad_id,
        rule.olympiad_name || 'Олимпиада');

    const universityHtml = university
        ? `<a href="#/universities/${escAttr(university.id)}" class="underline decoration-line hover:decoration-brand">${escHtml(universityLabel)}</a>`
        : escHtml(universityLabel);
    const olympiadHtml = olympiad
        ? `<a href="#/olympiads/${escAttr(olympiad.id)}" class="underline decoration-line hover:decoration-brand">${escHtml(olympiadLabel)}</a>`
        : escHtml(olympiadLabel);

    const typeLabel = benefitTypeLabel(rule.benefit_type);
    const result = benefitResultText(rule);
    const context = benefitContextLine(rule);
    const ege = benefitEgeLine(rule);
    const docName = rule.doc && rule.doc.name;
    const docUrl = rule.doc && rule.doc.source_url;

    return `
    <article class="rounded-lg bg-white border border-line px-5 py-5 md:px-6">
        <div class="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
            <div class="min-w-0 flex-1">
                <p class="font-bold text-ink leading-snug">
                    ${escHtml(typeLabel)}${result ? ` · ${escHtml(result)}` : ''}
                </p>
                <p class="mt-1.5 text-sm text-ink-soft">${universityHtml} · ${olympiadHtml}</p>
                ${context ? `<p class="mt-2 text-sm text-ink-soft">${escHtml(context)}</p>` : ''}
                ${ege ? `<p class="mt-2 text-sm text-ink-soft">${escHtml(ege)}</p>` : ''}
                ${docName ? `<p class="mt-2.5 text-sm text-ink-faint">Документ: ${
                    docUrl
                        ? `<a href="${escAttr(docUrl)}" target="_blank" rel="noopener noreferrer"
                               class="underline decoration-line hover:decoration-brand">${escHtml(docName)}</a>`
                        : escHtml(docName)
                }</p>` : ''}
            </div>
            <div class="shrink-0 flex flex-wrap lg:flex-col items-start gap-2">
                ${benefitStatusBadge(rule.verification_status)}
                ${rule.needs_review ? `<span class="${UI.badge} ${UI.badgeDanger}">Требует уточнения</span>` : ''}
            </div>
        </div>
    </article>`;
}

function benefitCatalogName(map, id, fallback) {
    const item = map.get(String(id));
    return (item && (item.short_name || item.name)) || fallback;
}
