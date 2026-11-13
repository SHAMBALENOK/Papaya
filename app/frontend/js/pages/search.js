/* ==========================================================================
 * pages/search.js — результаты поиска по университетам и олимпиадам.
 *
 *   #/search?q=…  → GET /api/v1/search?q=…
 *
 * Поиск отдаёт оба типа сущностей сразу: школьник не обязан знать, в каком
 * разделе искать — «Высшая проба» может быть и олимпиадой, и вузом.
 * ========================================================================== */

async function renderSearch(query) {
    const page = document.getElementById('page');
    store.setSearchQuery(query);

    page.innerHTML = `
    <section class="pt-2 pb-10 md:pb-12">
        <p class="${UI.eyebrow}">Поиск</p>
        <h1 class="mt-3 text-3xl md:text-4xl font-extrabold tracking-tight leading-[1.1]">Найти</h1>
        <form id="search-form" class="mt-10 max-w-2xl" role="search">
            <label for="search-input" class="sr-only">Поисковый запрос</label>
            <div class="flex flex-col sm:flex-row gap-3">
                <input id="search-input" name="q" type="search" autocomplete="off" value="${escAttr(query)}"
                       class="${UI.input} flex-1" placeholder="Университет или олимпиада">
                <button type="submit" class="${UI.btn} ${UI.btnPrimary} shrink-0">Найти</button>
            </div>
        </form>
    </section>
    <section id="search-results" aria-live="polite">${loadingHtml('Ищем…')}</section>`;

    document.getElementById('search-form').addEventListener('submit', e => {
        e.preventDefault();
        const value = document.getElementById('search-input').value.trim();
        store.setSearchQuery(value);
        navigate(value ? `#/search?q=${encodeURIComponent(value)}` : '#/search');
    });

    const box = document.getElementById('search-results');
    if (!query) {
        box.innerHTML = emptyHtml('Введите запрос', 'Например: МФТИ, ИТМО или название олимпиады.');
        return;
    }

    const res = await api.search(query);
    if (!res.ok) {
        box.innerHTML = alertHtml(errorText(res), 'error');
        return;
    }

    const universities = res.data.universities || [];
    const olympiads = res.data.olympiads || [];
    const programs = res.data.programs || [];

    if (!universities.length && !olympiads.length && !programs.length) {
        box.innerHTML = emptyHtml('Ничего не нашлось', `По запросу «${query}» нет ни университетов, ни олимпиад, ни программ.`);
        return;
    }

    box.innerHTML = `
    ${universities.length ? `
    <div class="mb-16">
        <h2 class="${UI.eyebrow}">Университеты (${universities.length})</h2>
        <div class="mt-8 grid gap-8 sm:grid-cols-2 xl:grid-cols-3">${universities.map(universityCardHtml).join('')}</div>
    </div>` : ''}
    ${olympiads.length ? `
    <div class="${programs.length ? 'mb-16' : ''}">
        <h2 class="${UI.eyebrow}">Олимпиады (${olympiads.length})</h2>
        <div class="mt-8 grid gap-8 sm:grid-cols-2 xl:grid-cols-3">${olympiads.map(olympiadCardHtml).join('')}</div>
    </div>` : ''}
    ${programs.length ? `
    <div>
        <h2 class="${UI.eyebrow}">Образовательные программы (${programs.length})</h2>
        <div class="mt-8 grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
            ${programs.map(item => `
                <a href="#/universities/${escAttr(item.university_id)}"
                   class="block min-w-0 bg-white rounded-lg border border-line shadow-elev-1 hover:shadow-elev-2 hover:-translate-y-0.5 hover:border-brand/30 transition-[transform,box-shadow,border-color] duration-200 ease-out p-6 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand">
                    <p class="font-bold text-ink leading-snug wrap-anywhere">${escHtml(item.name)}</p>
                    ${item.code ? `<p class="mt-2 text-sm text-ink-soft">Код: ${escHtml(item.code)}</p>` : ''}
                    <p class="mt-4 text-sm font-semibold text-brand-strong">Открыть университет →</p>
                </a>`).join('')}
        </div>
    </div>` : ''}`;
}
