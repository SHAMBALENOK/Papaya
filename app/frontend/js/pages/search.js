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
    <section class="pt-4 pb-12 md:pb-16">
        <p class="${UI.eyebrow}">Поиск</p>
        <h1 class="mt-4 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">Найти</h1>
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

    if (!universities.length && !olympiads.length) {
        box.innerHTML = emptyHtml('Ничего не нашлось', `По запросу «${query}» нет ни университетов, ни олимпиад.`);
        return;
    }

    box.innerHTML = `
    ${universities.length ? `
    <div class="mb-16">
        <p class="${UI.eyebrow}">Университеты (${universities.length})</p>
        <div class="mt-8 grid gap-8 sm:grid-cols-2 xl:grid-cols-3">${universities.map(universityCardHtml).join('')}</div>
    </div>` : ''}
    ${olympiads.length ? `
    <div>
        <p class="${UI.eyebrow}">Олимпиады (${olympiads.length})</p>
        <div class="mt-8 grid gap-8 sm:grid-cols-2 xl:grid-cols-3">${olympiads.map(olympiadCardHtml).join('')}</div>
    </div>` : ''}`;
}
