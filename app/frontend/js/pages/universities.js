/* ==========================================================================
 * pages/universities.js — каталог университетов и страница университета.
 *
 *   #/universities        → GET /api/v1/universities
 *   #/universities/{id}   → GET /api/v1/universities/{id}
 *                          GET /api/v1/universities/{id}/olympiads
 *
 * Страница университета — главный экран продукта: основная информация
 * плюс список олимпиад, дающих БВИ.
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
        <h1 class="mt-4 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">Университеты</h1>
        <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Откройте университет и посмотрите, какие олимпиады дают поступление без
            вступительных испытаний.
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
        ? `<p class="text-sm text-ink-faint mb-6">Найдено: ${items.length}</p>
           <div class="grid gap-8 sm:grid-cols-2 xl:grid-cols-3">${items.map(universityCardHtml).join('')}</div>`
        : emptyHtml('Университеты не найдены',
                    'Попробуйте другое название: каталог ищет по полному названию, аббревиатуре и описанию.',
                    '<a href="#/universities" class="' + UI.btn + ' ' + UI.btnSecondary + '">Сбросить поиск</a>');
}

async function renderUniversity(universityId) {
    const page = document.getElementById('page');
    if (!universityId) { renderNotFound(); return; }
    page.innerHTML = loadingHtml('Открываем университет…');

    const [uniRes, olyRes] = await Promise.all([
        api.getUniversity(universityId),
        api.getUniversityOlympiads(universityId),
    ]);

    if (!uniRes.ok || !uniRes.data) {
        page.innerHTML = emptyHtml('Университет не найден',
            'Возможно, он был удалён или ссылка неверна.',
            '<a href="#/universities" class="' + UI.btn + ' ' + UI.btnSecondary + '">К каталогу университетов</a>');
        return;
    }

    const university = uniRes.data;
    const olympiads = (olyRes.ok && olyRes.data && olyRes.data.olympiads) || [];
    const isAdmin = store.isAdmin();

    const olympiadsHtml = olympiads.length
        ? `<div class="grid gap-8 md:grid-cols-2">` + olympiads.map(bviOlympiadCardHtml).join('') + `</div>`
        : emptyHtml('Пока нет олимпиад с БВИ',
            'Когда университет подтвердит перечень олимпиад РСОШ, они появятся здесь.');

    page.innerHTML = `
    <article class="pb-16 md:pb-24">
        <a href="#/universities" class="inline-flex items-center gap-2 text-ink-soft font-semibold hover:text-ink transition-colors rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">
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
            <h1 class="mt-6 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">${escHtml(university.short_name || university.name)}</h1>
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
                    <dd class="mt-2">
                        ${university.website
                            ? `<a href="${escAttr(university.website)}" target="_blank" rel="noopener noreferrer" class="text-ink font-semibold underline underline-offset-4">${escHtml(university.website)}</a>`
                            : '<span class="text-ink-soft">не указан</span>'}
                    </dd>
                </div>
                <div>
                    <dt class="text-sm font-medium text-ink-faint">Олимпиад с БВИ</dt>
                    <dd class="mt-2 text-base font-semibold">${olympiads.length}</dd>
                </div>
                <div>
                    <dt class="text-sm font-medium text-ink-faint">Обновлено</dt>
                    <dd class="mt-2 text-base">${formatDate(university.updatedAt)}</dd>
                </div>
            </dl>
        </section>

        ${isAdmin ? `
        <section class="mt-12">
            <button type="button" id="uni-edit" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Редактировать университет</button>
        </section>` : ''}

        <section class="mt-20 md:mt-28" aria-labelledby="uni-bvi-title">
            <p class="${UI.eyebrow}">Главное для поступления</p>
            <h2 id="uni-bvi-title" class="mt-5 text-3xl md:text-4xl font-extrabold tracking-tight leading-[1.08]">
                Олимпиады, дающие БВИ
            </h2>
            <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">
                Поступление без вступительных испытаний за дипломы этих олимпиад.
            </p>
            <div class="mt-12">${olympiadsHtml}</div>
        </section>
    </article>`;

    const editBtn = document.getElementById('uni-edit');
    if (editBtn) {
        editBtn.addEventListener('click', () =>
            openUniversityFormModal(university, () => renderUniversity(universityId)));
    }
}

function bviOlympiadCardHtml(olympiad) {
    return `
    <a href="#/olympiads/${escAttr(olympiad.id)}"
       class="group block bg-white shadow-elev-1 hover:shadow-elev-2 hover:-translate-y-1 transition-all duration-200 p-8 focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">
        ${cardImageHtml(olympiad)}
        <div class="flex items-center gap-3 flex-wrap">
            <span class="${UI.badge} ${UI.badgeSuccess}">
                <span class="w-2 h-2 rounded-full bg-ink/60" aria-hidden="true"></span>БВИ
            </span>
            ${olympiad.status === 'ARCHIVED' ? olympiadStatusBadge(olympiad.status) : ''}
        </div>
        <h3 class="mt-5 text-lg font-bold tracking-tight leading-snug">${escHtml(olympiad.name)}</h3>
        <p class="mt-3 text-sm text-ink-soft leading-relaxed line-clamp-2">${escHtml(olympiad.description || '')}</p>
        <p class="mt-6 text-sm font-semibold text-ink group-hover:text-black transition-colors">Открыть олимпиаду →</p>
    </a>`;
}
