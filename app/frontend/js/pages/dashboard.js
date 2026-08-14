/* ==========================================================================
 * pages/dashboard.js — каталог олимпиад (GET /events/dashboard).
 *
 * Поля ответа: user_id, user_name, user_surname, user_email, user_role, events[].
 * Метрики — подсчёт по массиву events, не выдуманные значения.
 * ========================================================================== */

const FALLBACK_IMG = 'https://placehold.co/640x360/C6BFA9/1A1A1A?text=Papaya';

async function loadDashboardData() {
    const res = await api.getDashboard();
    if (res.ok && res.data && res.data.user_id) {
        store.setUser(userFromDashboard(res.data));
        store.setEvents(res.data.events);
        renderHeader();
        return true;
    }
    return false;
}

async function renderDashboard() {
    const page = document.getElementById('page');
    page.innerHTML = loadingHtml();

    let ok = false;
    try { ok = await loadDashboardData(); }
    catch (err) { console.error('[dashboard] ошибка загрузки:', err); }

    if (ok) { drawDashboard(); return; }

    page.innerHTML = `
    <div class="max-w-narrow mx-auto py-24 text-center">
        <h1 class="text-3xl font-extrabold tracking-tight">Не удалось загрузить данные</h1>
        <p class="mt-5 text-lg text-ink-soft leading-relaxed">Каталог временно недоступен. Проверьте подключение к серверу и попробуйте ещё раз.</p>
        <div class="flex flex-wrap justify-center gap-3 mt-10">
            <button id="dash-retry" class="${UI.btn} ${UI.btnPrimary}">Повторить</button>
            <button id="dash-logout" class="${UI.btn} ${UI.btnGhost}">Выйти</button>
        </div>
    </div>`;
    document.getElementById('dash-retry').addEventListener('click', renderDashboard);
    document.getElementById('dash-logout').addEventListener('click', logout);
}

function drawDashboard() {
    const page = document.getElementById('page');
    const events = store.events;

    const total = events.length;
    const active = events.filter(ev => ev.isActive !== false).length;
    const archived = total - active;
    const role = (store.user && store.user.role) || '—';

    const stats = [
        { label: 'Событий в каталоге', value: total },
        { label: 'Активных', value: active },
        { label: 'В архиве', value: archived },
        { label: 'Ваша роль', value: escHtml(role) },
    ];

    const statsHtml = `
    <div class="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        ${stats.map(s => `
        <div class="bg-white shadow-elev-1 p-8">
            <p class="text-xs font-semibold text-ink-soft uppercase tracking-[0.14em]">${escHtml(s.label)}</p>
            <p class="mt-4 text-4xl font-extrabold tracking-tight text-ink">${s.value}</p>
        </div>`).join('')}
    </div>`;

    let listHtml;
    if (!events.length) {
        listHtml = `
        <div class="py-24 md:py-32 text-center max-w-md mx-auto">
            <div class="mx-auto w-16 h-16 rounded bg-mist flex items-center justify-center mb-10" aria-hidden="true">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#FF7F11" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="4" width="18" height="17"></rect>
                    <path d="M3 9h18M8 2v4M16 2v4"></path>
                </svg>
            </div>
            <h2 class="text-2xl font-bold tracking-tight">Событий пока нет</h2>
            <p class="mt-4 text-ink-soft leading-relaxed">Загляните позже — каталог пуст. Если у вас есть права EDITOR или ADMIN, добавьте событие через кнопку «+».</p>
        </div>`;
    } else {
        listHtml = `<div class="grid gap-8 md:grid-cols-2 xl:grid-cols-3">` + events.map(ev => {
            const img = ev.preview_picture || FALLBACK_IMG;
            const archivedEv = ev.isActive === false;
            return `
            <a href="#/event/${ev.id}"
               class="group block bg-white shadow-elev-1 hover:shadow-elev-2 hover:-translate-y-1 transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">
                <div class="h-48 bg-mist overflow-hidden">
                    <img class="w-full h-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
                         src="${escAttr(img)}" alt="${escAttr(ev.name)}" loading="lazy"
                         onerror="this.onerror=null;this.src='${FALLBACK_IMG}'">
                </div>
                <div class="p-8">
                    ${archivedEv ? `<span class="${UI.badge} ${UI.badgeNeutral} mb-4">Архив</span>` : ''}
                    <h2 class="text-xl font-bold tracking-tight leading-snug text-ink">${escHtml(ev.name)}</h2>
                    <p class="mt-3 text-ink-soft leading-relaxed line-clamp-3">${escHtml(ev.disc || 'Описание отсутствует.')}</p>
                    <p class="mt-7 text-sm font-semibold text-ink group-hover:text-black transition-colors">Подробнее →</p>
                </div>
            </a>`;
        }).join('') + '</div>';
    }

    page.innerHTML = `
    <section class="pt-4 pb-16 md:pb-20">
        <div class="max-w-2xl">
            <p class="${UI.eyebrow}">Каталог</p>
            <h1 class="mt-4 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">Актуальные олимпиады</h1>
            <p class="mt-6 text-lg text-ink-soft leading-relaxed">
                Всероссийские и региональные мероприятия для школьников.
                Откройте карточку, чтобы узнать подробности.
            </p>
        </div>
    </section>

    <section class="pb-16 md:pb-20" aria-label="Сводка">${statsHtml}</section>

    <section aria-label="Список олимпиад">${listHtml}</section>`;
}