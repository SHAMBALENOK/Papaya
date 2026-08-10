/* ==========================================================================
 * pages/dashboard.js — каталог олимпиад (главный экран).
 * Действия (PDF, добавить, обновить) вынесены в FAB «+» (см. app.js).
 * ========================================================================== */

const FALLBACK_IMG = 'https://placehold.co/640x360/EBF2FA/427AA1?text=Papaya';

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
        <p class="mt-5 text-lg text-ink/60 leading-relaxed">Каталог временно недоступен. Проверьте подключение к серверу и попробуйте ещё раз.</p>
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

    let listHtml;
    if (!events.length) {
        listHtml = `
        <div class="py-24 md:py-32 text-center max-w-md mx-auto">
            <div class="mx-auto w-16 h-16 rounded bg-tint flex items-center justify-center mb-10" aria-hidden="true">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#679436" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="4" width="18" height="17" rx="1"></rect>
                    <path d="M3 9h18M8 2v4M16 2v4"></path>
                </svg>
            </div>
            <h2 class="text-2xl font-bold tracking-tight">Событий пока нет</h2>
            <p class="mt-4 text-ink/60 leading-relaxed">Загляните позже — мы обязательно добавим что-нибудь интересное. Или добавьте первое событие через кнопку «+».</p>
            <button id="btn-add-first" class="${UI.btn} ${UI.btnPrimary} mt-10">Добавить первое событие</button>
        </div>`;
    } else {
        listHtml = `<div class="grid gap-8 md:grid-cols-2 xl:grid-cols-3">` + events.map(ev => {
            const img = ev.preview_picture || FALLBACK_IMG;
            const archived = ev.isActive === false;
            return `
            <a href="#/event/${ev.id}"
               class="group block bg-white rounded overflow-hidden shadow-elev-1 hover:shadow-elev-2 hover:-translate-y-1 transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary">
                <div class="h-48 bg-tint overflow-hidden">
                    <img class="w-full h-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
                         src="${escAttr(img)}" alt="${escAttr(ev.name)}" loading="lazy"
                         onerror="this.onerror=null;this.src='${FALLBACK_IMG}'">
                </div>
                <div class="p-8">
                    ${archived ? `<span class="${UI.badge} ${UI.badgeNeutral} mb-4">Архив</span>` : ''}
                    <h2 class="text-xl font-bold tracking-tight leading-snug text-ink">${escHtml(ev.name)}</h2>
                    <p class="mt-3 text-ink/60 leading-relaxed line-clamp-3">${escHtml(ev.disc || 'Описание отсутствует.')}</p>
                    <p class="mt-7 text-sm font-semibold text-navy group-hover:text-primary transition-colors">Подробнее</p>
                </div>
            </a>`;
        }).join('') + '</div>';
    }

    page.innerHTML = `
    <section class="pt-4 pb-14 md:pb-16">
        <div class="max-w-2xl">
            <p class="${UI.eyebrow}">Каталог</p>
            <h1 class="mt-4 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">Актуальные олимпиады</h1>
            <p class="mt-6 text-lg text-ink/60 leading-relaxed">
                Всероссийские и региональные мероприятия для школьников.
                Откройте карточку, чтобы узнать подробности.
            </p>
        </div>
    </section>

    <section aria-label="Список олимпиад">${listHtml}</section>`;

    const first = document.getElementById('btn-add-first');
    if (first) first.addEventListener('click', () => openAddEventModal(async () => {
        try { await loadDashboardData(); } catch { /* остаются текущие данные */ }
        drawDashboard();
    }));
}