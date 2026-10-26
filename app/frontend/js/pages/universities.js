/* ==========================================================================
 * pages/universities.js — каталог университетов и страница университета.
 *
 *   #/universities        → GET /api/v1/universities
 *   #/universities/{id}   → GET /api/v1/universities/{id}
 *                          GET /api/v1/universities/{id}/olympiads
 *
 * Страница университета — главный экран продукта: основная информация
 * плюс олимпиады с вложенными правилами льгот (БВИ, 100 баллов и т. д.)
 * и комбинируемые фильтры по виду льготы, предмету, программе и сезону.
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

    // Фильтры льгот живут в состоянии страницы: смена фильтра перезапрашивает
    // список, но не перерисовывает всю страницу целиком.
    const filterState = { benefitType: '', subject: '', programId: '', seasonId: '' };

    const [uniRes, olyRes, programsRes, facetsRes] = await Promise.all([
        api.getUniversity(universityId),
        api.getUniversityOlympiads(universityId),
        api.listUniversityPrograms(universityId),
        api.benefitRuleFacets(universityId).catch(() => ({ ok: false })),
    ]);

    if (!uniRes.ok || !uniRes.data) {
        page.innerHTML = emptyHtml('Университет не найден',
            'Возможно, он был удалён или ссылка неверна.',
            '<a href="#/universities" class="' + UI.btn + ' ' + UI.btnSecondary + '">К каталогу университетов</a>');
        return;
    }

    const university = uniRes.data;
    const all = (olyRes.ok && olyRes.data && olyRes.data.olympiads) || [];
    const total = (olyRes.ok && olyRes.data && olyRes.data.total) || all.length;
    const isAdmin = store.isAdmin();
    const canManage = isAdmin
        || (store.isUniversityRep() && String(store.user.university_id) === String(universityId));
    const programs = (programsRes.ok && programsRes.data && programsRes.data.programs) || [];
    const facets = (facetsRes.ok && facetsRes.data) || null;

    // Действующие и исторические правила — разные ответы на разные вопросы.
    // «Какие олимпиады дают льготу здесь сейчас?» — только про действующие;
    // архивные показываются отдельно и не входят в счётчик.
    const current = all.filter(item => !isHistoricalRule(item));
    const historical = all.filter(isHistoricalRule);
    const rulesCount = current.reduce((sum, item) => sum + ((item.rules || []).length), 0);

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

        ${programs.length ? `
        <section class="mt-12">
            <h2 class="${UI.eyebrow}">Образовательные программы</h2>
            <p class="mt-4 text-sm text-ink-soft leading-relaxed max-w-2xl">
                Направления подготовки, на которые университет распространяет свои льготы.
            </p>
            <ul class="mt-6 flex flex-wrap gap-2">
                ${programs.map(item => `<li class="${UI.badge} ${UI.badgeNeutral}">${escHtml(item.name)}</li>`).join('')}
            </ul>
        </section>` : ''}

        <section class="mt-12">
            <h2 class="${UI.eyebrow}">Информация</h2>
            <dl class="mt-8 grid sm:grid-cols-3 gap-x-12 gap-y-9">
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
                    <dt class="text-sm font-medium text-ink-faint">Олимпиад с льготами сейчас</dt>
                    <dd class="mt-2 text-base font-semibold">${current.length}</dd>
                </div>
                <div>
                    <dt class="text-sm font-medium text-ink-faint">Действующих правил</dt>
                    <dd class="mt-2 text-base font-semibold">${rulesCount}</dd>
                </div>
            </dl>
        </section>

        ${(isAdmin || canManage) ? `
        <section class="mt-12 flex flex-wrap gap-3">
            ${isAdmin ? `<button type="button" id="uni-edit" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Редактировать университет</button>` : ''}
            <a href="${isAdmin ? '#/admin/benefit-rules' : '#/my-university'}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Управлять правилами льгот</a>
        </section>` : ''}

        <section class="mt-20 md:mt-28" aria-labelledby="uni-benefits-title">
            <p class="${UI.eyebrow}">Главное для поступления</p>
            <h2 id="uni-benefits-title" class="mt-5 text-3xl md:text-4xl font-extrabold tracking-tight leading-[1.08]">
                Олимпиады, за которые университет даёт льготы
            </h2>
            <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">
                Под каждой олимпиадой — правила: вид льготы, сезон, профиль, требуемый
                результат и программы. Условия устанавливает сам университет; отметка
                «Проверено Papaya» означает, что модератор сверил правило с документом.
            </p>
            ${benefitFiltersHtml(filterState, facets, { prefix: 'uni' })}
            <p class="mt-6 text-sm text-ink-faint" id="uni-benefits-count">Показано олимпиад: ${current.length} из ${total}</p>
            <div class="mt-8" id="uni-benefits-list">${universityOlympiadsListHtml(current, false)}</div>
            <div id="uni-benefits-history">${universityHistoricalHtml(historical)}</div>
        </section>
    </article>`;

    const editBtn = document.getElementById('uni-edit');
    if (editBtn) {
        editBtn.addEventListener('click', () =>
            openUniversityFormModal(university, () => renderUniversity(universityId)));
    }

    // Фильтры применяются к списку правил: перезапрашиваем данные и меняем
    // только блок списка, чтобы не терять позицию и заголовок страницы.
    const listBox = document.getElementById('uni-benefits-list');
    const historyBox = document.getElementById('uni-benefits-history');
    const countBox = document.getElementById('uni-benefits-count');
    bindBenefitFilters('uni', filterState, async state => {
        if (!listBox) return;
        const filtered = Object.values(state).some(Boolean);
        listBox.innerHTML = loadingHtml('Применяем фильтр…');
        const res = await api.getUniversityOlympiads(universityId, state);
        if (!res.ok) {
            listBox.innerHTML = alertHtml(errorText(res), 'error');
            return;
        }
        const items = (res.data && res.data.olympiads) || [];
        const visible = items.filter(item => !isHistoricalRule(item));
        listBox.innerHTML = universityOlympiadsListHtml(visible, filtered);
        if (historyBox) historyBox.innerHTML = universityHistoricalHtml(items.filter(isHistoricalRule));
        // Счётчик считаем по тем же данным, что и список: иначе после
        // фильтрации он продолжал бы показывать число без фильтра.
        if (countBox) {
            const newTotal = (res.data && res.data.total) || visible.length;
            countBox.textContent = `Показано олимпиад: ${visible.length} из ${newTotal}`;
        }
    });
}

/** Список олимпиад с вложенными правилами или пустое состояние. */
function universityOlympiadsListHtml(items, filtered) {
    if (items.length) {
        return `<div class="grid gap-8 md:grid-cols-2">${items.map(olympiadWithRulesCardHtml).join('')}</div>`;
    }
    return filtered
        ? emptyHtml('По этому фильтру ничего не найдено',
                    'Смягчите условия: снимите фильтр по виду льготы, предмету, программе или сезону.')
        : emptyHtml('Пока нет опубликованных правил',
            'Правила появляются здесь, когда представитель университета публикует их '
            + 'в своём кабинете. Перечень олимпиад приходит из РСОШ.');
}

/** Исторический блок — визуально второстепенный и только при наличии. */
function universityHistoricalHtml(historical) {
    if (!historical.length) return '';
    return `<div class="mt-14 pt-10 border-t border-mist">
        <h2 class="${UI.eyebrow}">Исторические правила</h2>
        <p class="mt-4 text-sm text-ink-soft leading-relaxed max-w-2xl">
            Олимпиады, которые университет учитывал раньше. Сейчас их нет в
            актуальном перечне РСОШ, поэтому правила сохранены как история и
            не считаются действующими.
        </p>
        <div class="mt-8 grid gap-6 md:grid-cols-2 opacity-70">
            ${historical.map(olympiadWithRulesCardHtml).join('')}
        </div>
    </div>`;
}
