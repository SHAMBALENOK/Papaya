/* ==========================================================================
 * pages/admin.js — панель администратора.
 * Страницы: #/admin и #/admin/users → GET /admin/users
 *           #/admin/events          → GET /admin/events
 *           #/admin/imports         → дашборд RSOSH-импортов
 * Действия: ban, unban, grant, demote, archive, imp-confirm, imp-reject.
 * ========================================================================== */

let adminTab = 'users';

function renderAdmin(initialTab) {
    const page = document.getElementById('page');
    adminTab = initialTab === 'events' ? 'events' : initialTab === 'imports' ? 'imports' : 'users';

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
        <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">Управление пользователями, событиями и подтверждение RSOSH-импортов.</p>
    </section>

    <div class="flex sm:inline-flex flex-wrap gap-2 bg-mist rounded p-2 mb-12" role="tablist" aria-label="Разделы администрирования">
        <a href="#/admin/users" id="admin-tab-users" role="tab" aria-selected="true" class="flex-1 sm:flex-none sm:min-w-[10rem] text-center px-6 py-3 rounded text-sm font-semibold bg-ink text-white shadow-elev-1 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">Пользователи</a>
        <a href="#/admin/events" id="admin-tab-events" role="tab" aria-selected="false" class="flex-1 sm:flex-none sm:min-w-[10rem] text-center px-6 py-3 rounded text-sm font-semibold text-ink-soft hover:text-ink transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">События</a>
        <a href="#/admin/imports" id="admin-tab-imports" role="tab" aria-selected="false" class="flex-1 sm:flex-none sm:min-w-[10rem] text-center px-6 py-3 rounded text-sm font-semibold text-ink-soft hover:text-ink transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">Импорты</a>
    </div>

    <section id="admin-content" aria-live="polite">${loadingHtml()}</section>`;

    document.getElementById('admin-content').addEventListener('click', async e => {
        const btn = e.target.closest('[data-act]');
        if (!btn || btn.disabled) return;
        btn.disabled = true;

        const impAct = btn.dataset.act;
        if (impAct === 'imp-confirm' || impAct === 'imp-reject') {
            if (impAct === 'imp-confirm') {
                const next = Number(btn.dataset.next || 0);
                if (!window.confirm(`Подтвердить импорт и создать ${next} новых олимпиад?`)) { btn.disabled = false; return; }
            } else if (!window.confirm('Отклонить импорт? Ничего создано не будет.')) {
                btn.disabled = false;
                return;
            }
            const res = await (impAct === 'imp-confirm'
                ? api.confirmImport(btn.dataset.id)
                : api.rejectImport(btn.dataset.id)).catch(() => null);
            if (res && res.ok) {
                showToast(impAct === 'imp-confirm' ? 'Импорт подтверждён и применён' : 'Импорт отклонён', 'success');
                await loadAdminTab(adminTab);
                return;
            }
            showToast(res ? errorText(res) : 'Сетевая ошибка', 'error');
            btn.disabled = false;
            return;
        }

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

    paintAdminTabs(adminTab);
    loadAdminTab(adminTab);
}

function paintAdminTabs(tab) {
    const usersBtn = document.getElementById('admin-tab-users');
    const eventsBtn = document.getElementById('admin-tab-events');
    const importsBtn = document.getElementById('admin-tab-imports');
    if (!usersBtn || !eventsBtn || !importsBtn) return;

    const base = 'flex-1 sm:flex-none sm:min-w-[10rem] text-center px-6 py-3 rounded text-sm font-semibold transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60';
    usersBtn.className = tab === 'users' ? `${base} bg-ink text-white shadow-elev-1` : `${base} text-ink-soft hover:text-ink`;
    eventsBtn.className = tab === 'events' ? `${base} bg-ink text-white shadow-elev-1` : `${base} text-ink-soft hover:text-ink`;
    importsBtn.className = tab === 'imports' ? `${base} bg-ink text-white shadow-elev-1` : `${base} text-ink-soft hover:text-ink`;
    usersBtn.setAttribute('aria-selected', String(tab === 'users'));
    eventsBtn.setAttribute('aria-selected', String(tab === 'events'));
    importsBtn.setAttribute('aria-selected', String(tab === 'imports'));
}

async function loadAdminTab(tab) {
    const box = document.getElementById('admin-content');
    if (!box) return;
    box.innerHTML = loadingHtml();

    if (tab === 'imports') {
        await loadImportManager();
        return;
    }

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

function importStateBadge(state) {
    const map = {
        processing: [UI.badgeNeutral, 'Обработка…', 'Импорт выполняется в фоне'],
        review: [UI.badgeDanger, 'Ожидают подтверждения', 'Нужно решение админа'],
        approved: [UI.badgeSuccess, 'Подтверждён', 'Импорт применён'],
        rejected: [UI.badgeNeutral, 'Отклонён', 'Импорт отклонён'],
        failed: [UI.badgeDanger, 'Ошибка', 'Произошла ошибка обработки'],
    };
    const [cls, label, title] = map[state] || [UI.badgeNeutral, state || '—', ''];
    return `<span class="${UI.badge} ${cls}" title="${escAttr(title)}">${escHtml(label)}</span>`;
}

async function loadImportManager() {
    const box = document.getElementById('admin-content');
    if (!box) return;

    let orgs = { ok: true, data: [] };
    let oly = { ok: true, data: [] };
    let docs = { ok: true, data: [] };
    let imports = { ok: true, data: [] };
    try {
        [orgs, oly, docs, imports] = await Promise.all([
            api.getOrganizations().catch(() => orgs),
            api.getOlympiads().catch(() => oly),
            api.getDocs().catch(() => docs),
            api.getImports().catch(() => imports),
        ]);
    } catch {
        box.innerHTML = alertHtml('Сетевая ошибка', 'error');
        return;
    }

    const orgList = Array.isArray(orgs.data) ? orgs.data : [];
    const olyList = Array.isArray(oly.data) ? oly.data : [];
    const docList = Array.isArray(docs.data) ? docs.data : [];
    const importsList = Array.isArray(imports.data) ? imports.data : [];
    const pending = importsList.filter(i => i.state === 'review').length;

    const cards = [
        { label: 'Организации', value: orgList.length, href: '#/organizations' },
        { label: 'Олимпиады', value: olyList.length, href: '#/olympiads' },
        { label: 'Документы', value: docList.length, href: '#/docs' },
        { label: 'Ждут подтверждения', value: pending, href: '#/admin/imports', accent: pending > 0 },
    ];

    box.innerHTML = `
    <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-10">
        ${cards.map(c => `
            <a href="${c.href}" class="${UI.card} px-6 py-5 block">
                <p class="text-3xl font-extrabold ${c.accent ? 'text-ember' : ''}">${c.value}</p>
                <p class="mt-1 text-sm text-ink-soft">${escHtml(c.label)}</p>
            </a>`).join('')}
    </div>
    ${importsListHtml(importsList)}`;
}

function importsListHtml(imports) {
    if (!imports.length) {
        return `<p class="py-24 text-center text-lg text-ink-soft">RSOSH-импортов пока нет.<br>
            <span class="text-sm">Загрузите документ типа RSOSH_LIST, затем запустите импорт со страницы этого документа.</span></p>`;
    }

    return `
    <div class="${UI.card} p-6 md:p-8">
        <div class="flex flex-wrap items-center justify-between gap-3 mb-6">
            <h2 class="text-xl font-bold">Импорты RSOSH</h2>
            <a href="#/docs" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Документы</a>
        </div>
        <div class="overflow-x-auto">
            <table class="w-full min-w-[880px] text-left">
                <thead>
                    <tr class="text-xs text-ink-soft uppercase">
                        <th class="py-2 pr-3">Документ</th>
                        <th class="py-2 pr-3">Статус</th>
                        <th class="py-2 pr-3">Сводка</th>
                        <th class="py-2 pr-3">Запущен</th>
                        <th class="py-2">Действия</th>
                    </tr>
                </thead>
                <tbody>
                    ${imports.map(imp => {
                        const s = imp.summary || {};
                        const parts = [];
                        if (s.new) parts.push(`новых ${s.new}`);
                        if (s.merge) parts.push(`объединить ${s.merge}`);
                        if (s.review) parts.push(`на проверку ${s.review}`);
                        if (!parts.length) parts.push(`кандидатов ${s.total}`);
                        const canReview = imp.state === 'review';
                        const errorHtml = imp.error
                            ? `<p class="mt-1 text-xs text-crimson break-all" title="${escAttr(imp.error)}">${escHtml(String(imp.error).slice(0, 120))}</p>` : '';
                        return `
                        <tr class="border-t border-mist align-top">
                            <td class="py-4 pr-3 min-w-0">
                                <a href="#/imports/${imp.import_id}" class="font-medium text-ink hover:text-ember">${escHtml(imp.doc_name || 'Без названия')}</a>
                                <p class="text-xs text-ink-faint mt-1 break-all">${escHtml(imp.import_id)}</p>
                                ${errorHtml}
                            </td>
                            <td class="py-4 pr-3 whitespace-nowrap">${importStateBadge(imp.state)}</td>
                            <td class="py-4 pr-3 text-sm text-ink-soft whitespace-nowrap">${escHtml(parts.join(' · '))}</td>
                            <td class="py-4 pr-3 text-sm whitespace-nowrap">${formatDate(imp.started_at)}</td>
                            <td class="py-4 whitespace-nowrap">
                                <div class="flex items-center gap-2">
                                    <a href="#/imports/${imp.import_id}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Открыть</a>
                                    ${canReview ? `
                                    <button data-act="imp-confirm" data-id="${escAttr(imp.import_id)}" data-next="${s.new || 0}" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Подтвердить</button>
                                    <button data-act="imp-reject" data-id="${escAttr(imp.import_id)}" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}">Отклонить</button>` : ''}
                                </div>
                            </td>
                        </tr>`;
                    }).join('')}
                </tbody>
            </table>
        </div>
    </div>`;
}

function usersListHtml(users) {
    if (!users.length) return `<p class="py-24 text-center text-lg text-ink-soft">Пользователи не найдены</p>`;

    const selfId = store.user ? store.user.id : null;

    return `<p class="text-sm text-ink-faint mb-6">Всего: ${users.length}</p>
    <div class="space-y-6">
        ${users.map(u => {
            const initials = (((u.name || '?')[0] || '?') + ((u.surname || '')[0] || '')).toUpperCase();
            const isSelf = String(u.id) === String(selfId);
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