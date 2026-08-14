/* ==========================================================================
 * pages/myevents.js — «Мои события» (GET /api/v1/events/dashboard/my_events).
 * Карточки: белые поверхности elev-1, разделение — space-y-6.
 * ========================================================================== */

async function renderMyEvents() {
    const page = document.getElementById('page');
    if (!store.user) { navigate('#/auth'); return; }
    page.innerHTML = loadingHtml();

    let res;
    try { res = await api.getMyEvents(); } catch { res = { ok: false }; }
    if (!res.ok || !res.data || !res.data.user_id) { navigate('#/auth'); return; }

    store.setUser(userFromDashboard(res.data));
    store.setMyEvents(res.data.events);
    renderHeader();
    drawMyEvents();
}

function drawMyEvents() {
    const page = document.getElementById('page');
    const events = store.myEvents;
    const canEdit = store.canManageEvents();

    const listHtml = events.length
        ? `<div class="space-y-6">` + events.map(ev => `
            <div class="${UI.card} p-8 md:p-10 flex flex-col md:flex-row md:items-center gap-6">
                <div class="flex-1 min-w-0">
                    <h2 class="text-xl font-bold tracking-tight leading-snug truncate">${escHtml(ev.name)}</h2>
                    <div class="mt-3 flex items-center gap-3 flex-wrap">
                        <p class="text-sm text-ink-soft">Обновлено ${formatDate(ev.updatedAt)}</p>
                        ${ev.isActive === false ? `<span class="${UI.badge} ${UI.badgeNeutral}">В архиве</span>` : ''}
                    </div>
                </div>
                <div class="flex flex-wrap gap-3 shrink-0">
                    <a href="#/event/${ev.id}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Открыть</a>
                    ${canEdit ? `<button data-edit="${escAttr(ev.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Редактировать</button>` : ''}
                </div>
            </div>`).join('') + '</div>'
        : `
        <div class="py-24 text-center max-w-md mx-auto">
            <h2 class="text-2xl font-bold tracking-tight">У вас пока нет событий</h2>
            <p class="mt-4 text-ink-soft leading-relaxed">События, у которых вы указаны как владелец, появятся здесь.</p>
            <div class="flex flex-wrap justify-center gap-3 mt-10">
                <a href="#/" class="${UI.btn} ${UI.btnSecondary}">Смотреть каталог</a>
            </div>
        </div>`;

    page.innerHTML = `
    <section class="pt-4 pb-16 md:pb-20">
        <div class="max-w-2xl">
            <p class="${UI.eyebrow}">Управление</p>
            <h1 class="mt-4 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">Мои события</h1>
            <p class="mt-6 text-lg text-ink-soft leading-relaxed">События, владельцем которых вы являетесь.</p>
        </div>
    </section>
    <section aria-label="Мои события">${listHtml}</section>`;

    page.querySelectorAll('[data-edit]').forEach(btn =>
        btn.addEventListener('click', () => {
            const ev = store.myEvents.find(e => e.id === btn.dataset.edit);
            if (ev) openEditEventModal(ev, renderMyEvents);
        }));
}