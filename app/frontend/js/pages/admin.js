/* ==========================================================================
 * pages/admin.js — панель администратора.
 * Страницы для API-маршрутов /admin/*: /admin/users, /admin/events,
 * ban/unban, grant/demote, archive.
 * Доступ: только пользователи с ролью ADMIN (проверка на входе).
 * Разделение блоков: только «воздух» (space-y-6) и тени elev-1.
 * Монохром: активная вкладка — чёрная, статусные бейджи — ч/б.
 * ========================================================================== */

let adminTab = 'users';

function renderAdmin() {
    const page = document.getElementById('page');

    /* Охрана доступа: без роли ADMIN показываем заглушку */
    if (!store.isAdmin()) {
        page.innerHTML = `
        <div class="max-w-narrow mx-auto py-24 md:py-32 text-center">
            <div class="mx-auto w-16 h-16 rounded bg-mist flex items-center justify-center mb-10" aria-hidden="true">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#FF7F11" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="4" y="11" width="16" height="10"></rect>
                    <path d="M8 11V7a4 4 0 0 1 8 0v4"></path>
                </svg>
            </div>
            <h1 class="text-3xl md:text-4xl font-extrabold tracking-tight">Доступ ограничен</h1>
            <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-md mx-auto">Этот раздел доступен только администраторам платформы.</p>
            <a href="#/" class="${UI.btn} ${UI.btnPrimary} mt-10">На главную</a>
        </div>`;
        return;
    }

    page.innerHTML = `
    <section class="pt-4 pb-16 md:pb-20">
        <p class="${UI.eyebrow}">Администрирование</p>
        <h1 class="mt-4 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">Панель администратора</h1>
        <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">Управление пользователями и событиями: роли, блокировки, архив.</p>
    </section>

    <!-- Сегментированные вкладки: активная — чёрная подложка, без границ -->
    <div class="flex sm:inline-flex flex-wrap gap-2 bg-mist rounded p-2 mb-12" role="tablist" aria-label="Разделы администрирования">
        <button id="admin-tab-users" role="tab" aria-selected="true" class="flex-1 sm:flex-none sm:min-w-[10rem] px-6 py-3 rounded text-sm font-semibold bg-ink text-white shadow-elev-1 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">Пользователи</button>
        <button id="admin-tab-events" role="tab" aria-selected="false" class="flex-1 sm:flex-none sm:min-w-[10rem] px-6 py-3 rounded text-sm font-semibold text-ink-soft hover:text-ink transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">События</button>
    </div>

    <section id="admin-content" aria-live="polite">${loadingHtml()}</section>`;

    document.getElementById('admin-tab-users').addEventListener('click', () => selectAdminTab('users'));
    document.getElementById('admin-tab-events').addEventListener('click', () => selectAdminTab('events'));

    /* Делегирование действий (бан, роли, архив) на контейнере списка */
    document.getElementById('admin-content').addEventListener('click', async e => {
        const btn = e.target.closest('[data-act]');
        if (!btn || btn.disabled) return;
        btn.disabled = true;

        const { act, id } = btn.dataset;
        const calls = {
            ban: () => api.banUser(id),
            unban: () => api.unbanUser(id),
            grant: () => api.grantAdmin(id),
            demote: () => api.demoteAdmin(id),
            archive: () => api.archiveEvent(id),
        };
        const messages = {
            ban: 'Пользователь заблокирован',
            unban: 'Пользователь разблокирован',
            grant: 'Назначена роль администратора',
            demote: 'Роль администратора снята',
            archive: 'Событие перенесено в архив',
        };
        try {
            const res = await calls[act]();
            if (res.ok) { showToast(messages[act], 'success'); await loadAdminTab(adminTab); return; }
            showToast(errorText(res), 'error');
        } catch {
            showToast('Сетевая ошибка', 'error');
        }
        btn.disabled = false;
    });

    selectAdminTab('users');
}

function selectAdminTab(tab) {
    adminTab = tab;
    const usersBtn = document.getElementById('admin-tab-users');
    const eventsBtn = document.getElementById('admin-tab-events');
    if (!usersBtn || !eventsBtn) return;

    const base = 'flex-1 sm:flex-none sm:min-w-[10rem] px-6 py-3 rounded text-sm font-semibold transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60';
    usersBtn.className = tab === 'users' ? `${base} bg-ink text-white shadow-elev-1` : `${base} text-ink-soft hover:text-ink`;
    eventsBtn.className = tab === 'events' ? `${base} bg-ink text-white shadow-elev-1` : `${base} text-ink-soft hover:text-ink`;
    usersBtn.setAttribute('aria-selected', String(tab === 'users'));
    eventsBtn.setAttribute('aria-selected', String(tab === 'events'));

    loadAdminTab(tab);
}

async function loadAdminTab(tab) {
    const box = document.getElementById('admin-content');
    if (!box) return;
    box.innerHTML = loadingHtml();

    let res;
    try {
        res = tab === 'users' ? await api.adminUsers() : await api.adminEvents();
    } catch {
        res = { ok: false };
    }
    if (!res.ok || !res.data) {
        box.innerHTML = alertHtml(errorText(res), 'error');
        return;
    }
    box.innerHTML = tab === 'users'
        ? usersListHtml(res.data.users || [])
        : eventsListHtml(res.data.events || []);
}

/* Список пользователей: строки-карточки, разделённые только отступами */
function usersListHtml(users) {
    if (!users.length) return `<p class="py-24 text-center text-lg text-ink-soft">Пользователи не найдены</p>`;

    const selfId = store.user ? store.user.id : null;

    return `<p class="text-sm text-ink-faint mb-6">Всего: ${users.length}</p>
    <div class="space-y-6">
        ${users.map(u => {
            const initials = (((u.name || '?')[0] || '?') + ((u.surname || '')[0] || '')).toUpperCase();
            const isSelf = u.id === selfId;
            const roleBadge = u.role === 'ADMIN'
                ? `<span class="${UI.badge} ${UI.badgeAdmin}">Администратор</span>`
                : `<span class="${UI.badge} ${UI.badgeNeutral}">${escHtml(u.role || 'USER')}</span>`;
            const statusBadge = u.isActive
                ? `<span class="${UI.badge} ${UI.badgeSuccess}"><span class="w-2 h-2 rounded-full bg-ink/60" aria-hidden="true"></span>Активен</span>`
                : `<span class="${UI.badge} ${UI.badgeDanger}">Заблокирован</span>`;

            return `
            <div class="${UI.card} px-8 py-7 flex flex-col xl:flex-row xl:items-center gap-6">
                <div class="flex items-center gap-5 flex-1 min-w-0">
                    <div class="w-12 h-12 rounded bg-ember text-ink font-bold flex items-center justify-center shrink-0" aria-hidden="true">${escHtml(initials)}</div>
                    <div class="min-w-0">
                        <p class="font-bold text-ink truncate">${escHtml(u.name)} ${escHtml(u.surname)}${isSelf ? ' <span class="text-ink-faint font-medium">(вы)</span>' : ''}</p>
                        <p class="text-sm text-ink-soft truncate">${escHtml(u.email)}</p>
                    </div>
                </div>
                <div class="flex items-center gap-3 flex-wrap shrink-0">
                    ${roleBadge}
                    ${statusBadge}
                </div>
                <div class="flex items-center gap-2 flex-wrap xl:justify-end shrink-0">
                    ${u.role === 'ADMIN'
                        ? `<button data-act="demote" data-id="${escAttr(u.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}" ${isSelf ? 'disabled title="Нельзя снять роль у себя"' : ''}>Снять администратора</button>`
                        : `<button data-act="grant" data-id="${escAttr(u.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Назначить администратором</button>`}
                    ${u.isActive
                        ? `<button data-act="ban" data-id="${escAttr(u.id)}" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}" ${isSelf ? 'disabled title="Нельзя заблокировать себя"' : ''}>Заблокировать</button>`
                        : `<button data-act="unban" data-id="${escAttr(u.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Разблокировать</button>`}
                </div>
            </div>`;
        }).join('')}
    </div>`;
}

/* Список событий: такой же принцип — карточки и «воздух» вместо линий */
function eventsListHtml(events) {
    if (!events.length) return `<p class="py-24 text-center text-lg text-ink-soft">Событий пока нет</p>`;

    return `<p class="text-sm text-ink-faint mb-6">Всего: ${events.length}</p>
    <div class="space-y-6">
        ${events.map(ev => {
            const active = ev.isActive !== false;
            const statusBadge = active
                ? `<span class="${UI.badge} ${UI.badgeSuccess}"><span class="w-2 h-2 rounded-full bg-ink/60" aria-hidden="true"></span>Активно</span>`
                : `<span class="${UI.badge} ${UI.badgeNeutral}">Архив</span>`;

            return `
            <div class="${UI.card} px-8 py-7 flex flex-col lg:flex-row lg:items-center gap-6">
                <div class="flex-1 min-w-0">
                    <p class="font-bold text-ink truncate">${escHtml(ev.name)}</p>
                    <p class="mt-2 text-sm text-ink-soft">Создано ${formatDate(ev.createdAt)}</p>
                </div>
                <div class="flex items-center gap-3 flex-wrap shrink-0">
                    ${statusBadge}
                    <a href="#/event/${ev.id}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Открыть</a>
                    ${active ? `<button data-act="archive" data-id="${escAttr(ev.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">В архив</button>` : ''}
                </div>
            </div>`;
        }).join('')}
    </div>`;
}