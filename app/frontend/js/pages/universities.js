/* ==========================================================================
 * pages/universities.js — каталог университетов и страница университета.
 *
 *   #/universities        → GET /api/v1/universities
 *   #/universities/{id}   → GET /api/v1/universities/{id}
 *                          GET /api/v1/universities/{id}/benefits?…
 *                          GET /api/v1/universities/{id}/programs
 *
 * Страница университета отвечает на главный вопрос продукта: какие олимпиады
 * и за какой результат этот вуз засчитывает. Источник ответа — правила льгот,
 * отдельного списка «олимпиады с БВИ» больше нет.
 * ========================================================================== */

function universitySearchFormHtml(value = '') {
    return `
    <form id="uni-search" class="mt-10 max-w-2xl" role="search">
        <label for="uni-search-input" class="sr-only">Поиск университета</label>
        <div class="flex flex-col sm:flex-row gap-3">
            <input id="uni-search-input" name="q" type="search" autocomplete="off" value="${escAttr(value)}"
                   class="${UI.input} flex-1" placeholder="Название или аббревиатура, например МФТИ">
            <button type="submit" class="${UI.btn} ${UI.btnPrimary} shrink-0">Найти</button>
        </div>
    </form>`;
}

function bindUniversitySearch(onDone) {
    const form = document.getElementById('uni-search');
    if (!form) return;
    form.addEventListener('submit', e => {
        e.preventDefault();
        onDone(document.getElementById('uni-search-input').value.trim());
    });
}

async function renderUniversities() {
    const page = document.getElementById('page');
    page.innerHTML = `
    <section class="pt-4 pb-16 md:pb-20">
        <p class="${UI.eyebrow}">Каталог</p>
        <h1 class="mt-3 text-3xl md:text-4xl font-extrabold tracking-tight leading-[1.1]">Университеты</h1>
        <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Откройте университет и посмотрите, за какие олимпиады, сезоны и
            профили он даёт льготы при поступлении.
        </p>
        ${universitySearchFormHtml(store.searchQuery)}
    </section>
    <section id="uni-list" aria-live="polite">${loadingHtml()}</section>`;

    bindUniversitySearch(query => {
        store.setSearchQuery(query);
        renderUniversities();
    });
    loadUniversities(store.searchQuery);
}

async function loadUniversities(query) {
    const box = document.getElementById('uni-list');
    if (!box) return;
    const res = await api.listUniversities(query);
    if (!res.ok) {
        box.innerHTML = alertHtml(errorText(res), 'error');
        return;
    }
    const items = res.data.universities || [];
    box.innerHTML = items.length
        ? `<h2 class="sr-only">Результаты поиска</h2>
           <p class="text-sm text-ink-faint mb-6">Найдено: ${items.length}</p>
           <div class="grid gap-8 sm:grid-cols-2 xl:grid-cols-3">${items.map(universityCardHtml).join('')}</div>`
        : emptyHtml('Университеты не найдены',
                    'Попробуйте другое название: каталог ищет по полному названию, аббревиатуре и описанию.',
                    '<a href="#/universities" class="' + UI.btn + ' ' + UI.btnSecondary + '">Сбросить поиск</a>');
}

async function renderUniversity(universityId) {
    const page = document.getElementById('page');
    if (!universityId) { renderNotFound(); return; }
    page.innerHTML = loadingHtml('Открываем университет…');

    const [uniRes, benRes, progRes] = await Promise.all([
        api.getUniversity(universityId),
        api.listUniversityBenefits(universityId, { limit: 200 }),
        api.listPrograms(universityId),
    ]);

    if (!uniRes.ok || !uniRes.data) {
        page.innerHTML = emptyHtml('Университет не найден',
            'Возможно, он был удалён или ссылка неверна.',
            '<a href="#/universities" class="' + UI.btn + ' ' + UI.btnSecondary + '">К каталогу университетов</a>');
        return;
    }

    const university = uniRes.data;
    const benefits = (benRes.ok && benRes.data && benRes.data.rules) || [];
    const total = (benRes.ok && benRes.data && benRes.data.total != null)
        ? benRes.data.total : benefits.length;
    const programs = (progRes.ok && progRes.data && progRes.data.programs) || [];
    const isAdmin = store.isAdmin();

    page.innerHTML = `
    <article class="pb-16 md:pb-24">
        <a href="#/universities" class="inline-flex items-center gap-2 text-ink-soft font-semibold hover:text-ink transition-colors rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-brand">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5M12 19l-7-7 7-7"></path></svg>
            Все университеты
        </a>

        ${(university.image || university.preview_image) ? `
        <div class="mt-12 bg-mist shadow-elev-1">
            <img src="${escAttr(university.image || university.preview_image)}" alt="${escAttr(university.name)}" class="w-full max-h-[20rem] object-cover"
                 onerror="this.onerror=null;this.parentElement.style.display='none'">
        </div>` : ''}

        <header class="mt-14">
            <p class="${UI.eyebrow}">Университет</p>
            <h1 class="mt-4 text-3xl md:text-4xl font-extrabold tracking-tight leading-[1.1]">${escHtml(university.short_name || university.name)}</h1>
            ${university.short_name && university.short_name !== university.name
                ? `<p class="mt-4 text-lg text-ink-soft leading-snug">${escHtml(university.name)}</p>`
                : ''}
        </header>

        ${university.description ? `
        <section class="mt-12">
            <h2 class="${UI.eyebrow}">Описание</h2>
            <p class="mt-6 text-lg text-ink leading-[1.8] whitespace-pre-wrap">${escHtml(university.description)}</p>
        </section>` : ''}

        <section class="mt-12">
            <h2 class="${UI.eyebrow}">Информация</h2>
            <dl class="mt-8 grid sm:grid-cols-2 gap-x-12 gap-y-9">
                <div>
                    <dt class="text-sm font-medium text-ink-faint">Официальный сайт</dt>
                    <dd class="mt-3">
                        ${university.website
                            ? `<a href="${escAttr(university.website)}" target="_blank" rel="noopener noreferrer"
                                  class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Официальный сайт университета</a>`
                            : '<span class="text-ink-soft">не указан</span>'}
                    </dd>
                </div>
                <div>
                    <dt class="text-sm font-medium text-ink-faint">Правил льгот</dt>
                    <dd class="mt-2 text-base font-semibold">${total}</dd>
                </div>
            </dl>
        </section>

        ${isAdmin ? `
        <section class="mt-12">
            <button type="button" id="uni-edit" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Редактировать университет</button>
        </section>` : ''}

        <section class="mt-20 md:mt-28" aria-labelledby="uni-benefits-title">
            <p class="${UI.eyebrow}">Льготы</p>
            <h2 id="uni-benefits-title" class="mt-5 text-3xl md:text-4xl font-extrabold tracking-tight leading-[1.08]">
                За какие олимпиады вуз даёт льготы
            </h2>
            <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">
                Правила указывает сам университет и подтверждает документом.
                Непроверенные правила помечены предупреждением «Не проверено Papaya».
            </p>
            <form id="uni-benefits-filter" class="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_16rem_12rem_auto]" role="search">
                <div>
                    <label for="uni-benefit-search" class="sr-only">Поиск по олимпиаде или профилю</label>
                    <input id="uni-benefit-search" name="search" type="search" class="${UI.input}"
                           placeholder="Олимпиада или профиль">
                </div>
                <div>
                    <label for="uni-benefit-type" class="sr-only">Тип льготы</label>
                    <select id="uni-benefit-type" name="benefit_type" class="${UI.input}">
                        <option value="">Все типы льгот</option>
                        <option value="BVI">БВИ</option>
                        <option value="EGE_100">100 баллов ЕГЭ</option>
                        <option value="DVI_100">100 баллов ДВИ</option>
                        <option value="OTHER">Другая льгота</option>
                    </select>
                </div>
                <div>
                    <label for="uni-benefit-level" class="sr-only">Уровень РСОШ</label>
                    <select id="uni-benefit-level" name="level" class="${UI.input}">
                        <option value="">Любой уровень</option>
                        <option value="1">Уровень 1</option>
                        <option value="2">Уровень 2</option>
                        <option value="3">Уровень 3</option>
                    </select>
                </div>
                <button type="submit" class="${UI.btn} ${UI.btnSecondary} shrink-0">Показать</button>
            </form>
            <p id="uni-benefits-count" class="mt-5 text-sm text-ink-faint" aria-live="polite">Найдено: ${total}</p>
            <div id="uni-benefits-list" class="mt-6 space-y-4">
                ${benefitCardsHtml(benefits)}
            </div>
            <div id="uni-benefits-more" class="mt-6"></div>
        </section>

        <section class="mt-12" aria-labelledby="uni-programs-title">
            <p class="${UI.eyebrow}">Программы</p>
            <h2 id="uni-programs-title" class="mt-5 text-2xl font-extrabold tracking-tight">Образовательные программы</h2>
            <div class="mt-6">
                ${programs.length
                    ? `<div class="grid gap-4 sm:grid-cols-2">${programs.map(p => `
                        <div class="bg-mist rounded px-5 py-4">
                            <p class="font-semibold text-ink leading-snug">${escHtml(p.name)}${p.code ? ` <span class="text-ink-faint font-normal">· ${escHtml(p.code)}</span>` : ''}</p>
                            ${p.description ? `<p class="mt-2 text-sm text-ink-soft leading-relaxed">${escHtml(p.description)}</p>` : ''}
                        </div>`).join('')}</div>`
                    : '<span class="text-sm text-ink-soft">Не указаны</span>'}
            </div>
        </section>
    </article>`;

    const editBtn = document.getElementById('uni-edit');
    if (editBtn) {
        editBtn.addEventListener('click', () =>
            openUniversityFormModal(university, () => renderUniversity(universityId)));
    }

    bindUniversityBenefitsFilter(universityId);
}

/** Карточки публичных правил льгот: опубликованные, включая непроверенные. */
function benefitCardsHtml(rules) {
    if (!rules.length) {
        return emptyHtml('Правила льгот не опубликованы',
            'Данные появятся, когда представитель университета добавит правило и опубликует его.');
    }
    return rules.map(item => {
        const result = benefitResultText(item);
        const ege = benefitEgeLine(item);
        const olympiadLabel = item.olympiad_name || 'Олимпиада';
        const context = [
            item.season_label ? `сезон ${item.season_label}` : '',
            item.profile_name
                ? `${item.profile_name}${item.profile_rsosh_level ? ` · уровень РСОШ ${item.profile_rsosh_level}` : ''}`
                : '',
        ].filter(Boolean).join(' · ');
        return `
        <article class="${UI.card} px-8 py-6">
            <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div class="min-w-0">
                    <p class="font-bold text-ink leading-snug">
                        ${escHtml(benefitTypeLabel(item.benefit_type))}${result ? ` · ${escHtml(result)}` : ''}
                    </p>
                    <p class="mt-2 text-sm text-ink-soft">
                        <a href="#/olympiads/${escAttr(item.olympiad_id)}"
                           class="underline decoration-line hover:decoration-brand">${escHtml(olympiadLabel)}</a>
                    </p>
                    ${context ? `<p class="mt-1 text-sm text-ink-soft">${escHtml(context)}</p>` : ''}
                    ${ege ? `<p class="mt-2 text-sm text-ink-soft">${escHtml(ege)}</p>` : ''}
                    ${item.doc && item.doc.name
                        ? `<p class="mt-3 text-xs text-ink-faint">Документ: ${
                            item.doc.source_url
                                ? `<a href="${escAttr(item.doc.source_url)}" target="_blank" rel="noopener noreferrer"
                                       class="underline">${escHtml(item.doc.name)}</a>`
                                : escHtml(item.doc.name)
                        }</p>`
                        : ''}
                </div>
                <div class="shrink-0 flex flex-wrap gap-2">
                    ${benefitStatusBadge(item.verification_status)}
                    ${item.needs_review ? `<span class="${UI.badge} ${UI.badgeDanger}">Требует уточнения</span>` : ''}
                </div>
            </div>
        </article>`;
    }).join('');
}

async function bindUniversityBenefitsFilter(universityId) {
    const form = document.getElementById('uni-benefits-filter');
    const list = document.getElementById('uni-benefits-list');
    const count = document.getElementById('uni-benefits-count');
    if (!form || !list) return;

    form.addEventListener('submit', async e => {
        e.preventDefault();
        const params = {
            benefit_type: (document.getElementById('uni-benefit-type') || {}).value || '',
            level: (document.getElementById('uni-benefit-level') || {}).value || '',
            search: ((document.getElementById('uni-benefit-search') || {}).value || '').trim(),
            limit: 200,
        };

        list.innerHTML = loadingHtml('Ищем правила…');
        const res = await api.listUniversityBenefits(universityId, params);
        if (!res.ok) {
            list.innerHTML = alertHtml(errorText(res), 'error');
            return;
        }
        const rules = (res.data && res.data.rules) || [];
        if (count) {
            count.textContent = `Найдено: ${res.data.total != null ? res.data.total : rules.length}`;
        }
        list.innerHTML = benefitCardsHtml(rules);
    });
}
