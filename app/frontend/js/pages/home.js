/* ==========================================================================
 * pages/home.js — главная страница Papaya.
 *
 * Главная объясняет продукт и сразу даёт главный инструмент: поиск
 * университета. Сценарий сервиса — «найди университет → узнай олимпиады
 * с БВИ → открой олимпиаду → перейди на её сайт», поэтому главная не
 * является административной панелью и не перегружена статистикой.
 * ========================================================================== */

function renderHome() {
    const page = document.getElementById('page');

    page.innerHTML = `
    <section class="pb-16 md:pb-24" aria-labelledby="home-title">
        <p class="${UI.eyebrow}">Олимпиады и поступление</p>
        <h1 id="home-title" class="mt-6 text-4xl md:text-6xl font-black tracking-tight leading-[1.05] max-w-4xl">
            Какие олимпиады дают <span class="text-ember">БВИ</span> в нужном мне университете?
        </h1>
        <p class="mt-8 text-lg md:text-xl text-ink-soft leading-relaxed max-w-2xl">
            Papaya помогает узнать, какие олимпиады дают поступление без вступительных
            испытаний в конкретных университетах. Найдите университет — и увидите
            олимпиады, которые он принимает.
        </p>

        <form id="home-search" class="mt-12 max-w-2xl" role="search">
            <label for="home-search-input" class="sr-only">Поиск университета или олимпиады</label>
            <div class="flex flex-col sm:flex-row gap-3">
                <input id="home-search-input" name="q" type="search" autocomplete="off"
                       class="${UI.input} flex-1" placeholder="Например: МФТИ, ИТМО, Ломоносов…">
                <button type="submit" class="${UI.btn} ${UI.btnPrimary} shrink-0">Найти</button>
            </div>
            <p class="mt-4 text-sm text-ink-soft">Ищет по университетам и олимпиадам одновременно.</p>
        </form>
    </section>

    <section class="grid gap-8 md:grid-cols-3 pb-16 md:pb-24" aria-label="Как это работает">
        <article class="${UI.card} p-8">
            <p class="text-sm font-extrabold text-ember">01</p>
            <h2 class="mt-6 text-xl font-bold tracking-tight">Найдите университет</h2>
            <p class="mt-4 text-ink-soft leading-relaxed">
                Каталог университетов с поиском по названию и краткому названию.
            </p>
        </article>
        <article class="${UI.card} p-8">
            <p class="text-sm font-extrabold text-ember">02</p>
            <h2 class="mt-6 text-xl font-bold tracking-tight">Посмотрите олимпиады с БВИ</h2>
            <p class="mt-4 text-ink-soft leading-relaxed">
                На странице университета — список олимпиад, дающих поступление без испытаний.
            </p>
        </article>
        <article class="${UI.card} p-8">
            <p class="text-sm font-extrabold text-ember">03</p>
            <h2 class="mt-6 text-xl font-bold tracking-tight">Откройте сайт олимпиады</h2>
            <p class="mt-4 text-ink-soft leading-relaxed">
                В карточке олимпиады — описание, официальный сайт и список вузов с БВИ.
            </p>
        </article>
    </section>

    <section id="home-catalog" aria-live="polite" class="pb-16 md:pb-24">
        ${loadingHtml('Загружаем каталоги…')}
    </section>`;

    document.getElementById('home-search').addEventListener('submit', e => {
        e.preventDefault();
        const value = document.getElementById('home-search-input').value.trim();
        store.setSearchQuery(value);
        navigate(value ? `#/search?q=${encodeURIComponent(value)}` : '#/search');
    });

    loadHomeCatalog();
}

async function loadHomeCatalog() {
    const box = document.getElementById('home-catalog');
    if (!box) return;

    const [universities, olympiads] = await Promise.all([
        api.listUniversities().catch(() => ({ ok: false })),
        api.listOlympiads().catch(() => ({ ok: false })),
    ]);

    const universitiesData = universities.ok ? universities.data.universities || [] : [];
    const olympiadsData = olympiads.ok ? olympiads.data.olympiads || [] : [];

    const universitiesHtml = universitiesData.length
        ? `<div class="grid gap-8 sm:grid-cols-2 xl:grid-cols-3">` +
          universitiesData.slice(0, 6).map(universityCardHtml).join('') +
          `</div>
           <p class="mt-8"><a href="#/universities" class="${UI.btn} ${UI.btnGhost}">Все университеты →</a></p>`
        : emptyHtml('Каталог университетов пока пуст',
                    'Университеты заводит администратор Papaya. Связь с олимпиадами '
                    + 'представитель университета подтверждает сам — после этого олимпиады '
                    + 'дают БВИ.');

    const olympiadsHtml = olympiadsData.length
        ? `<div class="grid gap-8 sm:grid-cols-2 xl:grid-cols-3">` +
          olympiadsData.slice(0, 6).map(olympiadCardHtml).join('') +
          `</div>
           <p class="mt-8"><a href="#/olympiads" class="${UI.btn} ${UI.btnGhost}">Все олимпиады →</a></p>`
        : emptyHtml('Каталог олимпиад пока пуст',
                    'Перечень олимпиад загружает администратор из документов РСОШ.');

    box.innerHTML = `
    <div class="mb-16 md:mb-24">
        <p class="${UI.eyebrow}">Каталог БВИ университетов</p>
        <h2 class="mt-5 text-3xl md:text-4xl font-extrabold tracking-tight leading-[1.08]">Университеты</h2>
        <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Главный раздел Papaya: университет и олимпиады, которые дают поступающим
            право на зачисление без экзаменов. Откройте университет, чтобы увидеть его
            подтверждённый перечень.
        </p>
        <div class="mt-12">${universitiesHtml}</div>
    </div>
    <div>
        <p class="${UI.eyebrow}">Перечень олимпиад РСОШ</p>
        <h2 class="mt-5 text-3xl md:text-4xl font-extrabold tracking-tight leading-[1.08]">Олимпиады</h2>
        <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Единый каталог олимпиад: одна запись на олимпиаду, независимо от года
            проведения. Каталог наполняется импортом документов РСОШ.
        </p>
        <div class="mt-12">${olympiadsHtml}</div>
    </div>`;
}

function universityCardHtml(university) {
    return `
    <a href="#/universities/${escAttr(university.id)}"
       class="group block bg-white shadow-elev-1 hover:shadow-elev-2 hover:-translate-y-1 transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">
        <div class="p-8">
            ${cardImageHtml(university)}
            ${entityTitleHtml(university)}
            <p class="mt-3 text-sm text-ink-soft leading-relaxed line-clamp-3">${escHtml(university.description || '')}</p>
            <p class="mt-7 text-sm font-semibold text-ink group-hover:text-black transition-colors">Олимпиады с БВИ →</p>
        </div>
    </a>`;
}

function olympiadCardHtml(olympiad) {
    return `
    <a href="#/olympiads/${escAttr(olympiad.id)}"
       class="group block bg-white shadow-elev-1 hover:shadow-elev-2 hover:-translate-y-1 transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">
        <div class="p-8">
            ${cardImageHtml(olympiad)}
            <div class="flex items-center gap-3 flex-wrap">${olympiadStatusBadge(olympiad.status)}</div>
            <h3 class="mt-5 text-lg font-bold tracking-tight leading-snug">${escHtml(olympiad.name)}</h3>
            <p class="mt-3 text-sm text-ink-soft leading-relaxed line-clamp-3">${escHtml(olympiad.description || '')}</p>
            <p class="mt-7 text-sm font-semibold text-ink group-hover:text-black transition-colors">Подробнее →</p>
        </div>
    </a>`;
}

/** Картинка для карточки каталога.
 *
 * У сущности две картинки: маленькое превью для карточек и большая для
 * страницы. Если превью не задано, показываем большую — каталог не должен
 * выглядеть пустым из-за не заполненного необязательного поля.
 */
function cardImageHtml(entity) {
    const src = entity.preview_image || entity.image;
    if (!src) return '';
    return `
            <div class="mb-6 bg-mist">
                <img src="${escAttr(src)}" alt="${escAttr(entity.name)}"
                     class="w-full h-32 object-cover"
                     onerror="this.onerror=null;this.parentElement.style.display='none'">
            </div>`;
}

/** Заголовок карточки: полное название и краткое — оба, если они разные.
 *
 * Раньше карточка показывала только краткое название, из-за чего
 * «НИУ ВШЭ — Школа экономики» выглядело как случайный набор слов.
 */
function entityTitleHtml(entity) {
    const name = escHtml(entity.name || '');
    const shortName = escHtml(entity.short_name || '');
    if (!shortName || shortName === name) {
        return `<h3 class="text-xl font-bold tracking-tight leading-snug">${name}</h3>`;
    }
    return `
            <h3 class="text-xl font-bold tracking-tight leading-snug">${name}</h3>
            <p class="mt-1 text-sm font-semibold text-ink-soft">${shortName}</p>`;
}
