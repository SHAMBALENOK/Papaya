/* ==========================================================================
 * pages/olympiads.js — каталог олимпиад и страница олимпиады.
 *
 *   #/olympiads          → GET /api/v1/olympiads
 *   #/olympiads/{id}     → GET /api/v1/olympiads/{id}
 *                          GET /api/v1/olympiads/{id}/universities
 *
 * Страница олимпиады завершает сценарий: описание, официальный сайт,
 * источник информации и обратная связь — вузы, дающие БВИ.
 * ========================================================================== */

async function renderOlympiads() {
    const page = document.getElementById('page');
    page.innerHTML = `
    <section class="pt-4 pb-16 md:pb-20">
        <p class="${UI.eyebrow}">Каталог</p>
        <h1 class="mt-4 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">Олимпиады</h1>
        <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Единый каталог олимпиад перечня РСОШ. На странице олимпиады видно,
            какие университеты дают за неё БВИ.
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
        ? `<p class="text-sm text-ink-faint mb-6">Найдено: ${items.length}</p>
           <div class="grid gap-8 sm:grid-cols-2 xl:grid-cols-3">${items.map(olympiadCardHtml).join('')}</div>`
        : emptyHtml('Олимпиады не найдены',
                    'Попробуйте другое название: каталог ищет по названию и описанию.',
                    '<a href="#/olympiads" class="' + UI.btn + ' ' + UI.btnSecondary + '">Сбросить поиск</a>');
}

async function renderOlympiad(olympiadId) {
    const page = document.getElementById('page');
    if (!olympiadId) { renderNotFound(); return; }
    page.innerHTML = loadingHtml('Открываем олимпиаду…');

    const [olyRes, uniRes, srcRes] = await Promise.all([
        api.getOlympiad(olympiadId),
        api.getOlympiadUniversities(olympiadId),
        // Источник публичный и необязательный: его отсутствие — не ошибка
        // страницы, поэтому гасим неудачу вместо того, чтобы ломать рендер.
        api.getOlympiadSource(olympiadId).catch(() => ({ ok: false })),
    ]);

    if (!olyRes.ok || !olyRes.data) {
        page.innerHTML = emptyHtml('Олимпиада не найдена',
            'Возможно, она была удалена или ссылка неверна.',
            '<a href="#/olympiads" class="' + UI.btn + ' ' + UI.btnSecondary + '">К каталогу олимпиад</a>');
        return;
    }

    const olympiad = olyRes.data;
    const universities = (uniRes.ok && uniRes.data && uniRes.data.universities) || [];
    const source = (srcRes.ok && srcRes.data) || null;
    const isAdmin = store.isAdmin();
    const isArchived = olympiad.status === 'ARCHIVED';

    // Актуальные и исторические связи — разные блоки. У архивной олимпиады
    // историческими являются все оставшиеся связи: университеты учитывали её
    // для БВИ, пока она была в перечне РСОШ. Выбрасывать их нельзя — это
    // стёрло бы историю, но и подписывать их «БВИ» значило бы обещать льготу,
    // которой сейчас нет.
    const currentUniversities = universities.filter(
        item => !(isArchived || isHistoricalBvi(item)));
    const historicalUniversities = universities.filter(
        item => isArchived || isHistoricalBvi(item));

    function universityLinkHtml(university, historical) {
        const badge = historical
            ? `<span class="${UI.badge} ${UI.badgeNeutral}">Историческая связь</span>`
            : `<span class="${UI.badge} ${UI.badgeSuccess}">
                   <span class="w-2 h-2 rounded-full bg-ink/60" aria-hidden="true"></span>БВИ
               </span>`;
        return `
        <a href="#/universities/${escAttr(university.id)}"
           class="group block bg-white shadow-elev-1 hover:shadow-elev-2 hover:-translate-y-1 transition-all duration-200 p-8 focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">
            ${badge}
            ${entityTitleHtml(university)}
            <p class="mt-6 text-sm font-semibold text-ink group-hover:text-black transition-colors">Открыть →</p>
        </a>`;
    }

    const universitiesHtml = currentUniversities.length
        ? `<div class="grid gap-8 sm:grid-cols-2 xl:grid-cols-3">`
            + currentUniversities.map(item => universityLinkHtml(item, false)).join('')
            + `</div>`
        : emptyHtml('Университеты с БВИ пока не указаны',
                    'Представители университетов заявляют такие связи, администратор подтверждает их.');

    const historicalHtml = historicalUniversities.length
        ? `<div class="mt-14 pt-10 border-t border-mist">
               <h3 class="${UI.eyebrow}">Исторические связи</h3>
               <p class="mt-4 text-sm text-ink-soft leading-relaxed max-w-2xl">
                   ${isArchived
                       ? 'Олимпиада не входит в актуальный перечень РСОШ. Университеты учитывали её для БВИ раньше — связи сохранены как история.'
                       : 'Ранее подтверждённые связи, которые сейчас не действуют.'}
               </p>
               <div class="mt-8 grid gap-6 sm:grid-cols-2 xl:grid-cols-3 opacity-70">
                   ${historicalUniversities.map(item => universityLinkHtml(item, true)).join('')}
               </div>
           </div>`
        : '';

    page.innerHTML = `
    <article class="max-w-narrow mx-auto pb-16 md:pb-24">
        <a href="#/olympiads" class="inline-flex items-center gap-2 text-ink-soft font-semibold hover:text-ink transition-colors rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">
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
            <h1 class="mt-6 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">${escHtml(olympiad.name)}</h1>
        </header>

        ${isArchived ? `
        <div class="mt-8">${alertHtml(archivedOlympiadNotice(), 'error')}</div>` : ''}

        ${olympiad.description ? `
        <section class="mt-14">
            <h2 class="${UI.eyebrow}">Описание</h2>
            <p class="mt-6 text-lg text-ink leading-[1.8] whitespace-pre-wrap">${escHtml(olympiad.description)}</p>
        </section>` : ''}

        <section class="mt-14">
            <h2 class="${UI.eyebrow}">Куда идти</h2>
            <div class="mt-8">
                ${olympiad.official_url
                    ? `<a href="${escAttr(olympiad.official_url)}" target="_blank" rel="noopener noreferrer"
                          class="${UI.btn} ${UI.btnPrimary}">Официальный сайт олимпиады</a>`
                    : `<p class="text-ink-soft leading-relaxed">Официальный сайт олимпиады пока не указан в каталоге.</p>`}
            </div>
        </section>

        ${sourceBlockHtml(source)}

        ${isAdmin ? `
        <section class="mt-12">
            <button type="button" id="oly-edit" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Редактировать олимпиаду</button>
        </section>` : ''}

        <section class="mt-20 md:mt-28">
            <h2 class="${UI.eyebrow}">БВИ</h2>
            <h3 class="mt-5 text-3xl font-extrabold tracking-tight leading-[1.1]">Университеты, учитывающие олимпиаду для БВИ</h3>
            <p class="mt-6 text-lg text-ink-soft leading-relaxed">
                Эти университеты засчитывают диплом олимпиады для поступления без
                вступительных испытаний. В других университетах условия
                устанавливает сам вуз.
            </p>
            <div class="mt-12">${universitiesHtml}</div>
            ${historicalHtml}
        </section>
    </article>`;

    const editBtn = document.getElementById('oly-edit');
    if (editBtn) {
        editBtn.addEventListener('click', () =>
            openOlympiadFormModal(olympiad, () => renderOlympiad(olympiadId)));
    }
}


/** Текст архивной олимпиады для публичной страницы.
 *
 * Формулировка намеренно не называет причину архива. В публичном API её нет
 * (значения `RSOSH_ABSENT` и `MANUAL` — технические enumы, пользователю они
 * ничего не объясняют), а обе причины означают одно и то же для посетителя:
 * олимпиады сейчас нет в актуальном каталоге, но её история сохранена.
 * Точную причину видит администратор в панели.
 */
function archivedOlympiadNotice() {
    return 'Олимпиада не входит в актуальный каталог Papaya. '
         + 'Информация об олимпиаде, официальный сайт и ранее подтверждённые '
         + 'связи с университетами сохранены.';
}

/** Блок «Откуда взялась информация».
 *
 * Источник важен для доверия к каталогу: пользователь должен видеть, что данные
 * пришли из перечня РСОШ или что запись завели вручную. Ответ приходит всегда
 * для существующей олимпиады, поэтому блок показывается всегда — скрывать его
 * значило бы прятать факт ручного ввода.
 */
function sourceBlockHtml(source) {
    const title = (source && source.title) || '';
    const url = (source && source.source_url) || '';

    const linkHtml = url
        ? `<p class="mt-3 text-sm">
               <a href="${escAttr(url)}" target="_blank" rel="noopener noreferrer"
                  class="text-ink font-semibold underline underline-offset-4">Открыть источник</a>
           </p>`
        : '';

    return `
        <section class="mt-14">
            <h2 class="${UI.eyebrow}">Откуда взялась информация</h2>
            <p class="mt-4 text-base font-semibold">${escHtml(title || 'Источник не указан')}</p>
            ${linkHtml}
        </section>`;
}
