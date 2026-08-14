/* ==========================================================================
 * pages/users.js — страницы маршрутов:
 *   #/users      → GET /api/v1/user/users
 *   #/users/{id} → GET /api/v1/user/{id}
 * ========================================================================== */

async function renderUsers() {
    const page = document.getElementById('page');
    if (!store.user) { navigate('#/auth'); return; }
    page.innerHTML = loadingHtml();

    let res;
    try { res = await api.getUsers(); } catch { res = { ok: false }; }

    if (!res.ok || !res.data || !res.data.user_id) { navigate('#/auth'); return; }

    store.setUser(userFromDashboard(res.data));
    renderHeader();
    drawUsers(res.data.users || []);
}

function drawUsers(users) {
    const page = document.getElementById('page');

    let listHtml;
    if (!users.length) {
        listHtml = `<p class="py-24 text-center text-lg text-ink-soft">Пользователи не найдены</p>`;
    } else {
        listHtml = `<div class="grid gap-8 md:grid-cols-2 xl:grid-cols-3">` + users.map(u => {
            const initials = (((u.name || '?')[0] || '?') + ((u.surname || '')[0] || '')).toUpperCase();
            const roleBadge = u.role === 'ADMIN'
                ? `<span class="${UI.badge} ${UI.badgeAdmin}">Администратор</span>`
                : `<span class="${UI.badge} ${UI.badgeNeutral}">${escHtml(u.role || 'USER')}</span>`;
            const activeBadge = u.isActive
                ? `<span class="${UI.badge} ${UI.badgeSuccess}"><span class="w-2 h-2 rounded-full bg-ink/60" aria-hidden="true"></span>Активен</span>`
                : `<span class="${UI.badge} ${UI.badgeDanger}">Заблокирован</span>`;

            return `
            <a href="#/users/${u.id}"
               class="group block bg-white shadow-elev-1 hover:shadow-elev-2 hover:-translate-y-1 transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">
                <div class="p-8">
                    <div class="flex items-center gap-5">
                        <div class="w-12 h-12 rounded bg-ember text-ink font-bold flex items-center justify-center shrink-0" aria-hidden="true">${escHtml(initials)}</div>
                        <div class="min-w-0">
                            <h2 class="font-bold text-ink truncate">${escHtml(u.name)} ${escHtml(u.surname)}</h2>
                            <p class="text-sm text-ink-soft truncate">${escHtml(u.email)}</p>
                        </div>
                    </div>
                    <div class="mt-7 flex items-center gap-3 flex-wrap">
                        ${roleBadge}
                        ${activeBadge}
                    </div>
                    <p class="mt-7 text-sm font-semibold text-ink group-hover:text-black transition-colors">Открыть профиль →</p>
                </div>
            </a>`;
        }).join('') + '</div>';
    }

    page.innerHTML = `
    <section class="pt-4 pb-16 md:pb-20">
        <div class="max-w-2xl">
            <p class="${UI.eyebrow}">Люди</p>
            <h1 class="mt-4 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">Пользователи</h1>
            <p class="mt-6 text-lg text-ink-soft leading-relaxed">Участники платформы. Откройте карточку, чтобы увидеть подробности профиля.</p>
        </div>
    </section>

    <section aria-label="Список пользователей">${listHtml}</section>`;
}

async function renderUserPublic(userId) {
    const page = document.getElementById('page');
    if (!store.user) { navigate('#/auth'); return; }
    page.innerHTML = loadingHtml();

    let res;
    try { res = await api.getUser(userId); } catch { res = { ok: false }; }

    if (!res.ok || !res.data) {
        page.innerHTML = `
        <div class="max-w-narrow mx-auto py-24 text-center">
            <h1 class="text-3xl font-extrabold tracking-tight">Пользователь не найден</h1>
            <p class="mt-5 text-lg text-ink-soft leading-relaxed">Возможно, профиль был удалён или ссылка неверна.</p>
            <a href="#/users" class="${UI.btn} ${UI.btnSecondary} mt-10">К списку пользователей</a>
        </div>`;
        return;
    }

    const u = res.data;
    const isSelf = store.user && String(store.user.id) === String(u.id);

    page.innerHTML = (isSelf
        ? `<div class="max-w-narrow mx-auto">${alertHtml('Это ваш профиль — редактировать его можно на странице «Профиль».', 'success')}</div>`
        : '') + userProfileHtml(u, { editable: false });
}