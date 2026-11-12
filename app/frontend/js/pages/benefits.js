/* ==========================================================================
 * pages/benefits.js — публичный каталог льгот.
 *
 *   #/benefits → GET /api/v1/benefits
 *
 * Каталог отвечает на вопрос «какие льготы даёт вуз за олимпиаду», поэтому
 * показывает только проверенные и опубликованные правила. Фильтры — вуз, тип
 * льготы и текстовый поиск по предмету и условиям.
 * ========================================================================== */

const BENEFIT_CATALOG_PAGE_SIZE = 24;

let benefitCatalogState = {
    rules: [],
    total: 0,
    search: '',
    benefitType: '',
    universityId: '',
    limit: BENEFIT_CATALOG_PAGE_SIZE,
    offset: 0,
};

/* Названия вузов и олимпиад нужны карточкам, а публичный список правил
   отдаёт только их id. Оба каталога публичные и небольшие, поэтому
   подгружаются один раз на страницу. */
let benefitCatalogNames = { universities: new Map(), olympiads: new Map() };

async function renderBenefits() {
    const page = document.getElementById('page');
    page.innerHTML = `
    <section class="pt-4 pb-12 md:pb-16">
        <p class="${UI.eyebrow}">Каталог</p>
        <h1 class="mt-4 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">Льготы</h1>
        <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Проверенные правила: какие олимпиады и результаты университеты
            засчитывают для БВИ, 100 баллов или другой льготы при поступлении.
        </p>
        <form id="benefits-filter" class="mt-10" role="search">
            <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_16rem_16rem_auto]">
                <div>
                    <label for="benefits-search" class="sr-only">Поиск по льготам</label>
                    <input id="benefits-search" name="search" type="search" autocomplete="off"
                           class="${UI.input}" placeholder="Предмет, условие, олимпиада">
                </div>
                <div>
                    <label for="benefits-type" class="sr-only">Тип льготы</label>
                    <select id="benefits-type" name="benefit_type" class="${UI.input}">
                        <option value="">Все типы льгот</option>
                        <option value="BVI">БВИ</option>
                        <option value="EGE_100">100 баллов ЕГЭ</option>
                        <option value="DVI_100">100 баллов ДВИ</option>
                        <option value="OTHER">Другая льгота</option>
                    </select>
                </div>
                <div>
                    <label for="benefits-university" class="sr-only">Университет</label>
                    <select id="benefits-university" name="university_id" class="${UI.input}">
                        <option value="">Все университеты</option>
                    </select>
                </div>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary} shrink-0">Показать</button>
            </div>
        </form>
        <p id="benefits-count" class="mt-5 text-sm text-ink-faint"></p>
    </section>
    <section id="benefits-list" aria-live="polite">${loadingHtml()}</section>
    <div class="mt-10" id="benefits-more"></div>`;

    await loadBenefitCatalogNames();
    fillBenefitCatalogUniversities();

    document.getElementById('benefits-filter').addEventListener('submit', e => {
        e.preventDefault();
        applyBenefitCatalogFilters();
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

function applyBenefitCatalogFilters() {
    benefitCatalogState.search = (document.getElementById('benefits-search') || {}).value || '';
    benefitCatalogState.search = benefitCatalogState.search.trim();
    benefitCatalogState.benefitType = (document.getElementById('benefits-type') || {}).value || '';
    benefitCatalogState.universityId = (document.getElementById('benefits-university') || {}).value || '';
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

    const params = {
        search: benefitCatalogState.search,
        benefit_type: benefitCatalogState.benefitType,
        university_id: benefitCatalogState.universityId,
        limit: benefitCatalogState.limit,
        offset: benefitCatalogState.offset,
    };
    const res = await api.listBenefits(params);
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
            : '';
    }

    if (!benefitCatalogState.rules.length) {
        list.innerHTML = emptyHtml('Льготы не найдены',
            'Попробуйте изменить фильтры: каталог показывает только проверенные '
            + 'и опубликованные правила.');
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

function benefitCatalogName(map, id, fallback) {
    const item = map.get(String(id));
    return (item && (item.short_name || item.name)) || fallback;
}

function benefitCatalogCardHtml(rule) {
    const university = benefitCatalogNames.universities.get(String(rule.university_id));
    const olympiad = benefitCatalogNames.olympiads.get(String(rule.olympiad_id));
    const universityLabel = benefitCatalogName(
        benefitCatalogNames.universities, rule.university_id, 'Университет не найден');
    const olympiadLabel = benefitCatalogName(
        benefitCatalogNames.olympiads, rule.olympiad_id, 'Олимпиада не найдена');
    const typeLabel = (typeof BENEFIT_TYPE_LABELS !== 'undefined'
        ? BENEFIT_TYPE_LABELS[rule.benefit_type] : null) || rule.benefit_type || 'Льгота';
    const result = (typeof publicBenefitResultText === 'function'
        ? publicBenefitResultText(rule) : rule.required_result || '');

    const universityHtml = university
        ? `<a href="#/universities/${escAttr(university.id)}" class="underline decoration-mist hover:decoration-ink">${escHtml(universityLabel)}</a>`
        : escHtml(universityLabel);
    const olympiadHtml = olympiad
        ? `<a href="#/olympiads/${escAttr(olympiad.id)}" class="underline decoration-mist hover:decoration-ink">${escHtml(olympiadLabel)}</a>`
        : escHtml(olympiadLabel);

    return `
    <article class="${UI.card} px-8 py-6">
        <div class="flex flex-col lg:flex-row lg:items-start justify-between gap-5">
            <div class="min-w-0 flex-1">
                <p class="font-bold text-ink leading-snug">
                    ${escHtml(typeLabel)}${rule.subject ? ` · ${escHtml(rule.subject)}` : ''}
                </p>
                <p class="mt-2 text-sm text-ink-soft">${universityHtml} · ${olympiadHtml}</p>
                ${result ? `<p class="mt-3 text-sm text-ink-soft">Условие: ${escHtml(result)}</p>` : ''}
                ${rule.additional_requirements
                    ? `<p class="mt-2 text-sm text-ink-soft">Дополнительно: ${escHtml(rule.additional_requirements)}</p>`
                    : ''}
                ${rule.source_url
                    ? `<p class="mt-3 text-sm"><a href="${escAttr(rule.source_url)}" target="_blank"
                           rel="noopener noreferrer" class="underline">Источник</a></p>`
                    : ''}
            </div>
            <div class="shrink-0">${benefitStatusBadge(rule.verification_status)}</div>
        </div>
    </article>`;
}
