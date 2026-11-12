/* ==========================================================================
 * pages/home.js — главная страница Papaya.
 *
 * Точка входа в сервис: объясняет продукт, даёт быстрый поиск и показывает
 * существующие каталоги. Сценарий — «найди университет → узнай олимпиады
 * с БВИ → открой олимпиаду → перейди на её сайт», поэтому главная не
 * дублирует административную панель и не показывает выдуманную статистику.
 * ========================================================================== */

function renderHome() {
    const page = document.getElementById('page');

    page.innerHTML = `
    <section class="pt-2 pb-12 md:pb-16" aria-labelledby="home-title">
        <div class="grid gap-10 lg:grid-cols-[1.15fr_0.85fr] lg:gap-16 items-start">
            <div>
                <p class="${UI.eyebrow}">Олимпиады и поступление</p>
                <h1 id="home-title" class="mt-5 text-4xl md:text-5xl xl:text-6xl font-black tracking-tight leading-[1.06] max-w-3xl">
                    Какие олимпиады дают <span class="text-brand">БВИ</span> в нужном мне университете?
                </h1>
                <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">
                    Papaya помогает найти олимпиаду и понять, какие преимущества она даёт
                    при поступлении в конкретный университет: БВИ, 100 баллов или другую
                    льготу. Источники и подтверждённые правила — рядом с записью.
                </p>
                <div class="mt-8 flex flex-wrap gap-3">
                    <a href="#/search" class="${UI.btn} ${UI.btnPrimary}">Найти олимпиаду</a>
                    <a href="#/universities" class="${UI.btn} ${UI.btnSecondary}">Выбрать университет</a>
                </div>
                <p class="mt-4 text-sm text-ink-faint">
                    Каталоги открыты без регистрации. Вход нужен для управления каталогом
                    и БВИ своего университета.
                </p>
            </div>

            <aside class="rounded-2xl bg-brand-soft p-6 md:p-7" aria-label="Что показывает Papaya">
                <p class="text-sm font-semibold text-brand-strong">Что показывает Papaya</p>
                <ul class="mt-4 space-y-3 text-sm text-ink-soft leading-relaxed">
                    <li class="flex items-start gap-3">
                        <span class="mt-1.5 h-2 w-2 rounded-full bg-brand shrink-0" aria-hidden="true"></span>
                        Олимпиады из перечня РСОШ и их официальные сайты.
                    </li>
                    <li class="flex items-start gap-3">
                        <span class="mt-1.5 h-2 w-2 rounded-full bg-leaf shrink-0" aria-hidden="true"></span>
                        Университеты, которые засчитывают олимпиаду для БВИ.
                    </li>
                    <li class="flex items-start gap-3">
                        <span class="mt-1.5 h-2 w-2 rounded-full bg-lime2 shrink-0" aria-hidden="true"></span>
                        Проверенные льготы с документом-основанием.
                    </li>
                </ul>
                <a href="#/benefits" class="mt-5 inline-flex items-center gap-1 text-sm font-semibold text-brand-strong hover:text-brand rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60">
                    Смотреть каталог льгот →
                </a>
            </aside>
        </div>
    </section>

    <section class="py-10 md:py-12 border-t border-line" aria-labelledby="home-features-title">
        <div class="flex flex-wrap items-end justify-between gap-4">
            <div>
                <p class="${UI.eyebrow}">Возможности</p>
                <h2 id="home-features-title" class="mt-3 text-2xl md:text-3xl font-extrabold tracking-tight">Что можно сделать</h2>
            </div>
            <a href="#/search" class="text-sm font-semibold text-brand-strong hover:text-brand rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60">Открыть поиск →</a>
        </div>

        <div class="mt-8 grid gap-x-10 gap-y-8 sm:grid-cols-2">
            <div class="border-t-2 border-brand pt-4">
                <h3 class="text-base font-bold tracking-tight">Найти олимпиаду</h3>
                <p class="mt-2 text-sm text-ink-soft leading-relaxed">
                    Поиск по названию и описанию сразу по олимпиадам и университетам.
                </p>
            </div>
            <div class="border-t-2 border-leaf pt-4">
                <h3 class="text-base font-bold tracking-tight">Посмотреть университеты</h3>
                <p class="mt-2 text-sm text-ink-soft leading-relaxed">
                    На странице олимпиады видно, какие вузы засчитывают её для БВИ.
                </p>
            </div>
            <div class="border-t-2 border-lime pt-4">
                <h3 class="text-base font-bold tracking-tight">Узнать условия льготы</h3>
                <p class="mt-2 text-sm text-ink-soft leading-relaxed">
                    Проверенные правила: БВИ, 100 баллов или другой результат за диплом.
                </p>
            </div>
            <div class="border-t-2 border-lemon2 pt-4">
                <h3 class="text-base font-bold tracking-tight">Сравнить университеты</h3>
                <p class="mt-2 text-sm text-ink-soft leading-relaxed">
                    Откройте несколько вузов и сверьте их перечни олимпиад и льгот.
                </p>
            </div>
        </div>
    </section>

    <section class="py-10 md:py-12 border-t border-line" aria-labelledby="home-search-title">
        <div class="grid gap-6 lg:grid-cols-[0.9fr_1.1fr] lg:gap-12 items-center">
            <div>
                <p class="${UI.eyebrow}">Быстрый старт</p>
                <h2 id="home-search-title" class="mt-3 text-2xl md:text-3xl font-extrabold tracking-tight">С чего начать</h2>
                <p class="mt-3 text-ink-soft leading-relaxed max-w-md">
                    Введите университет или олимпиаду — Papaya покажет подходящие записи.
                    Или начните с каталога.
                </p>
            </div>
            <div class="rounded-xl bg-mist p-5 md:p-6">
                <form id="home-search" role="search">
                    <label for="home-search-input" class="sr-only">Поиск университета или олимпиады</label>
                    <div class="flex flex-col sm:flex-row gap-3">
                        <input id="home-search-input" name="q" type="search" autocomplete="off"
                               class="${UI.input} flex-1 bg-white" placeholder="Например: МФТИ, ИТМО, «Высшая проба»…">
                        <button type="submit" class="${UI.btn} ${UI.btnPrimary} shrink-0">Найти</button>
                    </div>
                </form>
                <div class="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm font-semibold">
                    <a href="#/olympiads" class="text-brand-strong hover:text-brand rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60">Каталог олимпиад →</a>
                    <a href="#/universities" class="text-brand-strong hover:text-brand rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60">Каталог университетов →</a>
                </div>
            </div>
        </div>
    </section>

    <section id="home-catalog" aria-live="polite" class="pt-10 md:pt-12 border-t border-line">
        ${loadingHtml('Загружаем каталоги…')}
    </section>

    <section class="mt-12 md:mt-16 pt-10 border-t border-line grid gap-6 lg:grid-cols-[0.9fr_1.1fr] lg:gap-12" aria-labelledby="home-about-title">
        <div>
            <p class="${UI.eyebrow}">О Papaya</p>
            <h2 id="home-about-title" class="mt-3 text-2xl md:text-3xl font-extrabold tracking-tight">Зачем нужен сервис</h2>
        </div>
        <div class="space-y-4 text-ink-soft leading-relaxed max-w-2xl">
            <p>
                Условия приёма разбросаны по перечням РСОШ и приказам университетов.
                Сверить их вручную долго, а ошибка стоит дорого.
            </p>
            <p>
                Papaya собирает олимпиады и связи с вузами в одном каталоге, показывает
                документ-источник и отмечает льготы, которые проверил администратор.
                Сервис не заменяет правила приёма: окончательное решение принимает вуз.
            </p>
        </div>
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
        ? `<div class="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">` +
          universitiesData.slice(0, 6).map(universityCardHtml).join('') +
          `</div>
           <p class="mt-6"><a href="#/universities" class="${UI.btn} ${UI.btnGhost}">Все университеты →</a></p>`
        : emptyHtml('Каталог университетов пока пуст',
                    'Университеты заводит администратор Papaya. Связь с олимпиадами '
                    + 'запрашивает представитель университета, а подтверждает модератор '
                    + 'Papaya — после этого в каталоге появляются олимпиады этого вуза.');

    const olympiadsHtml = olympiadsData.length
        ? `<div class="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">` +
          olympiadsData.slice(0, 6).map(olympiadCardHtml).join('') +
          `</div>
           <p class="mt-6"><a href="#/olympiads" class="${UI.btn} ${UI.btnGhost}">Все олимпиады →</a></p>`
        : emptyHtml('Каталог олимпиад пока пуст',
                    'Перечень олимпиад загружает администратор из документов РСОШ.');

    box.innerHTML = `
    <div class="mb-12 md:mb-16">
        <p class="${UI.eyebrow}">Каталог БВИ университетов</p>
        <div class="mt-3 flex flex-wrap items-end justify-between gap-4">
            <h2 class="text-2xl md:text-3xl font-extrabold tracking-tight leading-[1.1]">Университеты</h2>
            <a href="#/universities" class="text-sm font-semibold text-brand-strong hover:text-brand rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60">Все университеты →</a>
        </div>
        <p class="mt-3 text-ink-soft leading-relaxed max-w-2xl">
            Откройте университет, чтобы увидеть олимпиады, за которые он даёт
            поступление без вступительных испытаний.
        </p>
        <div class="mt-8">${universitiesHtml}</div>
    </div>
    <div>
        <p class="${UI.eyebrow}">Перечень олимпиад РСОШ</p>
        <div class="mt-3 flex flex-wrap items-end justify-between gap-4">
            <h2 class="text-2xl md:text-3xl font-extrabold tracking-tight leading-[1.1]">Олимпиады</h2>
            <a href="#/olympiads" class="text-sm font-semibold text-brand-strong hover:text-brand rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60">Все олимпиады →</a>
        </div>
        <p class="mt-3 text-ink-soft leading-relaxed max-w-2xl">
            Одна запись на олимпиаду, независимо от года проведения. Каталог
            наполняется импортом документов РСОШ.
        </p>
        <div class="mt-8">${olympiadsHtml}</div>
    </div>`;
}

/** Историческая ли связь БВИ.
 *
 * Единственное место, где это решается во фронтенде: раздел актуальных и
 * исторических связей на страницах университета и олимпиады обязан считать
 * одинаково, иначе одна страница покажет олимпиаду как действующую льготу,
 * а другая — как историю.
 *
 * Проверяются оба признака: сервер отдаёт `is_historical` (унаследовано от
 * олимпиады), а на всякий случай и её собственный статус. `is_archived` —
 * дублирование того же факта, поэтому в проверке не участвует.
 */
function isHistoricalBvi(item) {
    return Boolean(item.is_historical) || item.status === 'ARCHIVED';
}


function universityCardHtml(university) {
    return `
    <a href="#/universities/${escAttr(university.id)}"
       class="group block bg-white rounded-lg border border-line shadow-elev-1 hover:shadow-elev-2 hover:-translate-y-0.5 hover:border-brand/30 transition-[transform,box-shadow,border-color] duration-200 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60">
        <div class="p-5 md:p-6">
            ${cardImageHtml(university)}
            ${entityTitleHtml(university)}
            <p class="mt-2 text-sm text-ink-soft leading-relaxed line-clamp-3">${escHtml(university.description || '')}</p>
            <p class="mt-5 text-sm font-semibold text-brand-strong group-hover:text-brand">Олимпиады с БВИ →</p>
        </div>
    </a>`;
}

function olympiadCardHtml(olympiad) {
    return `
    <a href="#/olympiads/${escAttr(olympiad.id)}"
       class="group block bg-white rounded-lg border border-line shadow-elev-1 hover:shadow-elev-2 hover:-translate-y-0.5 hover:border-brand/30 transition-[transform,box-shadow,border-color] duration-200 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60">
        <div class="p-5 md:p-6">
            ${cardImageHtml(olympiad)}
            <div class="flex items-center gap-3 flex-wrap">${olympiadStatusBadge(olympiad.status)}</div>
            <h3 class="mt-4 text-lg font-bold tracking-tight leading-snug">${escHtml(olympiad.name)}</h3>
            <p class="mt-2 text-sm text-ink-soft leading-relaxed line-clamp-3">${escHtml(olympiad.description || '')}</p>
            <p class="mt-5 text-sm font-semibold text-brand-strong group-hover:text-brand">Подробнее →</p>
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
            <div class="mb-4 overflow-hidden rounded-md bg-mist">
                <img src="${escAttr(src)}" alt="${escAttr(entity.name)}"
                     width="640" height="320" loading="lazy" decoding="async"
                     class="w-full h-36 object-cover"
                     onerror="this.onerror=null;this.parentElement.style.display='none'">
            </div>`;
}

/** Заголовок карточки: краткое название, под ним — полное.
 *
 * Краткое название идёт первым намеренно: карточка отвечает на вопрос «это
 * МФТИ или Ломоносов?», а полное название нужное как уточнение. Обратный
 * порядок заставлял читать «Московский физико-технический институт» раньше,
 * чем «МФТИ». Полное название не прячется — оно всегда под кратким.
 */
function entityTitleHtml(entity) {
    const name = escHtml(entity.name || '');
    const shortName = escHtml(entity.short_name || '');
    if (!shortName || shortName === name) {
        return `<h3 class="text-xl font-bold tracking-tight leading-snug">${name}</h3>`;
    }
    return `
            <h3 class="text-xl font-bold tracking-tight leading-snug">${shortName}</h3>
            <p class="mt-0.5 text-sm text-ink-soft leading-snug break-words">${name}</p>`;
}
