/* ==========================================================================
 * pages/admin.js — панель администратора Papaya.
 *
 *   #/admin/users       пользователи: роли, блокировки, привязка к университету
 *   #/admin/olympiads   каталог олимпиад: правка, архив, ручное создание
 *   #/admin/universities каталог университетов
 *   #/admin/bvi         заявки университетов на связи БВИ
 *   #/admin/imports     документы РСОШ: загрузка, импорт, preview, подтверждение
 *   #/admin/orders      приказы университетов: загрузка, импорт, preview, подтверждение
 * ========================================================================== */

const ADMIN_TABS = [
    { key: 'users', label: 'Пользователи', href: '#/admin/users' },
    { key: 'applications', label: 'Заявки вузов', href: '#/admin/applications' },
    { key: 'olympiads', label: 'Олимпиады', href: '#/admin/olympiads' },
    { key: 'universities', label: 'Университеты', href: '#/admin/universities' },
    { key: 'bvi', label: 'Заявки БВИ', href: '#/admin/bvi' },
    { key: 'imports', label: 'Импорт РСОШ', href: '#/admin/imports' },
    { key: 'orders', label: 'Приказы вузов', href: '#/admin/orders' },
];

/** Размер страницы при выгрузке очереди БВИ: список качается постранично. */
const BVI_PAGE_SIZE = 50;

/** Размер страницы списков пользователей и олимпиад. */
const ADMIN_LIST_PAGE_SIZE = 50;

/** Текущее состояние постраничной очереди БВИ (загруженные строки и всего). */
let bviState = { links: [], total: 0 };

/** Состояние постраничных списков панели: строки, всего и активный поиск. */
let adminUsersState = { users: [], total: 0, search: '', universities: [] };
let adminOlympiadsState = { olympiads: [], total: 0, search: '' };

function renderAdmin(initialTab) {
    const page = document.getElementById('page');
    if (!store.isAdmin()) {
        renderForbidden('Администрирование Papaya', 'Этот раздел доступен только администратору платформы.');
        return;
    }
    const tab = ADMIN_TABS.some(item => item.key === initialTab) ? initialTab : 'users';

    page.innerHTML = `
    <section class="pt-4 pb-12 md:pb-16">
        <p class="${UI.eyebrow}">Администрирование</p>
        <h1 class="mt-4 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">Панель администратора</h1>
        <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Каталог олимпиад и университетов, модерация связей БВИ и импорт документов РСОШ.
        </p>
    </section>

    <div class="flex flex-wrap gap-2 bg-mist rounded p-2 mb-12" role="tablist" aria-label="Разделы администрирования">
        ${ADMIN_TABS.map(item => `
        <a href="${item.href}" data-admin-tab="${item.key}" role="tab" aria-selected="${item.key === tab}"
           class="admin-tab flex-1 sm:flex-none sm:min-w-[11rem] text-center px-6 py-3 rounded text-sm font-semibold transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60 ${
               item.key === tab ? 'bg-ink text-white shadow-elev-1' : 'text-ink-soft hover:text-ink'
           }">${item.label}</a>`).join('')}
    </div>

    <section id="admin-content" aria-live="polite">${loadingHtml()}</section>`;

    document.getElementById('admin-content').addEventListener('click', handleAdminClick);
    document.getElementById('admin-content').addEventListener('change', handleAdminChange);
    loadAdminTab(tab);
}

async function loadAdminTab(tab) {
    const box = document.getElementById('admin-content');
    if (!box) return;
    box.innerHTML = loadingHtml();

    const loaders = {
        users: async () => {
            // Первая страница списка: остальные догружаются кнопкой «Показать ещё».
            const res = await api.adminUsers({ limit: ADMIN_LIST_PAGE_SIZE, offset: 0 });
            const users = res.data.users || [];
            adminUsersState = {
                users,
                total: res.data.total != null ? res.data.total : users.length,
                search: '',
                universities: [],
            };
            return users;
        },
        applications: async () => {
            // Очередь заявок представителей: по умолчанию — ожидающие решения.
            const res = await api.listApplications('PENDING');
            return (res.data && res.data.applications) || [];
        },
        olympiads: async () => {
            const res = await api.adminOlympiads({ limit: ADMIN_LIST_PAGE_SIZE, offset: 0 });
            const olympiads = res.data.olympiads || [];
            adminOlympiadsState = {
                olympiads,
                total: res.data.total != null ? res.data.total : olympiads.length,
                search: '',
            };
            return olympiads;
        },
        universities: async () => (await api.listUniversities()).data.universities || [],
        bvi: async () => {
            // Группировка по университетам возможна только по всему списку:
            // порционная выдача разрезала бы один вуз между страницами.
            const links = await fetchAllBviLinks();
            bviState = { links, total: links.length };
            return links;
        },
        imports: async () => (await api.listImports()).data.imports || [],
        orders: async () => (await api.listUniversityImports()).data.imports || [],
    };

    let data;
    try {
        data = await loaders[tab]();
    } catch (err) {
        box.innerHTML = alertHtml('Не удалось загрузить данные', 'error');
        return;
    }

    if (tab === 'users') {
        // Список университетов нужен для выпадающих списков привязки.
        const universities = await api.listUniversities().catch(() => ({ data: { universities: [] } }));
        adminUsersState.universities = universities.data.universities || [];
        box.innerHTML = adminUsersHtml();
        return;
    }

    const renderers = {
        applications: () => adminApplicationsHtml(data),
        olympiads: () => adminOlympiadsHtml(),
        universities: () => adminUniversitiesHtml(data),
        bvi: () => adminBviHtml(data),
        imports: () => adminImportsHtml(data),
        orders: () => adminOrdersHtml(data),
    };
    box.innerHTML = renderers[tab]();
}

/* Действия, которые открывают модалку или сами показывают результат. */
const ADMIN_SIDE_EFFECT_ACTIONS = new Set([
    'newUniversity', 'editUniversity', 'newOlympiad', 'editOlympiad',
    'newImport', 'runImport', 'previewImport', 'confirmAllBvi',
    'pauseImport', 'resumeImport',
    'newOrder', 'runOrderImport', 'previewOrderImport',
    'pauseOrderImport', 'resumeOrderImport',
    'loadMoreUsers', 'searchUsers', 'loadMoreOlympiads', 'searchOlympiads',
    'decideApplication', 'editBenefitRule', 'setDocAvailability', 'editSeasons',
]);

async function handleAdminClick(e) {
    const btn = e.target.closest('[data-act]');
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    const { act, id } = btn.dataset;

    if (act === 'saveRole') {
        btn.disabled = false;
        await saveUserRole(id, btn);
        return;
    }

    const calls = {
        ban: () => api.banUser(id),
        unban: () => api.unbanUser(id),
        archive: () => api.archiveOlympiad(id, true),
        restore: () => api.archiveOlympiad(id, false),
        confirmBvi: () => api.moderateBvi(btn.dataset.university, id, 'confirm'),
        rejectBvi: () => api.moderateBvi(btn.dataset.university, id, 'reject'),
        revokeBvi: () => api.moderateBvi(btn.dataset.university, id, 'revoke'),
        newUniversity: () => openUniversityFormModal(null, () => reloadAdmin()),
        editUniversity: () => editUniversityAction(id),
        newOlympiad: () => openOlympiadFormModal(null, () => reloadAdmin()),
        editOlympiad: () => editOlympiadAction(id),
        newImport: () => openUploadModal(),
        runImport: () => runImportAction(id, btn),
        previewImport: () => navigate(`#/admin/imports/${id}`),
        confirmAllBvi: () => confirmAllBviLinks(btn.dataset.university),
        pauseImport: () => pauseImportAction(id, btn),
        resumeImport: () => resumeImportAction(id, btn),
        newOrder: () => openOrderUploadModal(),
        runOrderImport: () => runOrderImportAction(id, btn),
        previewOrderImport: () => navigate(`#/admin/orders/${id}`),
        pauseOrderImport: () => pauseOrderImportAction(id, btn),
        resumeOrderImport: () => resumeOrderImportAction(id, btn),
        loadMoreUsers: () => loadMoreUsers(),
        searchUsers: () => searchUsers(),
        loadMoreOlympiads: () => loadMoreOlympiads(),
        searchOlympiads: () => searchOlympiads(),
        decideApplication: () => openApplicationDecisionModal(id),
        editSeasons: () => openSeasonsModal(id, btn.dataset.olympiadName || ''),
        editBenefitRule: () => openBenefitRuleModal(
            btn.dataset.university, id, btn.dataset.olympiadName || ''),
        setDocAvailability: () => setDocAvailabilityAction(id, btn.dataset.availability),
    };

    const messages = {
        ban: 'Пользователь заблокирован',
        unban: 'Пользователь разблокирован',
        archive: 'Олимпиада исключена из актуального каталога',
        restore: 'Олимпиада возвращена в актуальный каталог',
        confirmBvi: 'Связь БВИ подтверждена',
        rejectBvi: 'Заявка отклонена, связь удалена',
        revokeBvi: 'Подтверждение отозвано, связь удалена',
    };

    const call = calls[act];
    if (!call) { btn.disabled = false; return; }

    if (ADMIN_SIDE_EFFECT_ACTIONS.has(act)) {
        btn.disabled = false;
        try {
            await call();
        } catch {
            showToast('Сетевая ошибка', 'error');
        }
        return;
    }

    try {
        const res = await call();
        if (res.ok) {
            if (messages[act]) showToast(messages[act], 'success');
            await reloadAdmin();
            return;
        }
        showToast(errorText(res), 'error');
    } catch {
        showToast('Сетевая ошибка', 'error');
    }
    btn.disabled = false;
}

/**
 * Подтверждение выдачи прав администратора.
 *
 * Выдача ADMIN — необратимо широкое действие (полный доступ к каталогу и
 * управлению ролями), поэтому запрашивается явное согласие. Это именно
 * подстраховка интерфейса, а не граница безопасности: настоящие правила
 * (роль меняет только администратор, последнего админа понизить нельзя, свою
 * роль менять нельзя) проверяет сервер.
 */
function confirmGrantAdmin(target) {
    const who = target ? ` пользователю ${target}` : '';
    return window.confirm(
        `Выдать права администратора Papaya${who}?\n\n`
        + 'Администратор видит и меняет весь каталог и управляет ролями других '
        + 'пользователей.'
    );
}

/**
 * Сохранить роль пользователя вместе с привязкой к университету.
 *
 * Роль и университет уходят одним запросом: представителем нельзя стать без
 * вуза, а обычному пользователю нельзя привязать вуз «просто так».
 */
async function saveUserRole(userId, btn) {
    const roleSelect = document.querySelector(`[data-role-for="${CSS.escape(userId)}"]`);
    const universitySelect = document.querySelector(`[data-university-for="${CSS.escape(userId)}"]`);
    if (!roleSelect || !universitySelect) return;

    const role = roleSelect.value;
    // Что уходит в запрос, зависит от роли, и это не «как сложилось»:
    //
    // - обычный пользователь не привязывается ни к какому вузу — при снятии
    //   роли представителя привязку нужно очистить, иначе сервер отклонит
    //   запрос (а «просто молча» оставить её нельзя);
    // - администратору привязка не мешает, поэтому при назначении ADMIN не
    //   обнуляем то, что уже выбрано: снятие роли ниже само выбирает, кем
    //   человек станет дальше.
    const universityId = role === 'USER' ? null : (universitySelect.value || null);

    if (role === 'EDITOR' && !universityId) {
        showToast('Выберите университет, который представляет пользователь', 'error');
        return;
    }

    // Повышение до администратора подтверждается только при реальной смене
    // роли, а не при повторном сохранении уже выбранной.
    const wasAdmin = roleSelect.dataset.currentRole === 'ADMIN';
    if (role === 'ADMIN' && !wasAdmin && !confirmGrantAdmin('')) {
        return;
    }

    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Сохраняем…';
    const res = await api.setUserRole(userId, role, universityId);
    btn.disabled = false;
    btn.textContent = originalText;

    if (res.ok) {
        showToast(`Роль обновлена: ${ROLE_LABELS[res.data.role] || res.data.role}`, 'success');
        await reloadAdmin();
        return;
    }
    showToast(errorText(res), 'error');
}

async function handleAdminChange(e) {
    /* Университет доступен для выбора только когда роль — представитель:
       иначе привязка была бы молчаливым способом выдать права. */
    const roleSelect = e.target.closest('[data-role-for]');
    if (roleSelect) {
        const userId = roleSelect.dataset.roleFor;
        const universitySelect = document.querySelector(`[data-university-for="${CSS.escape(userId)}"]`);
        if (universitySelect) universitySelect.disabled = roleSelect.value !== 'EDITOR';
        return;
    }
}

function currentAdminTab() {
    return (routePath() || '/admin/users').split('/admin/')[1] || 'users';
}

async function reloadAdmin() {
    const tab = currentAdminTab();
    await loadAdminTab(ADMIN_TABS.some(item => item.key === tab) ? tab : 'users');
}

/* ------------------------------- Пользователи ------------------------------ */

const ROLE_LABELS = {
    USER: 'Школьник',
    EDITOR: 'Представитель университета',
    ADMIN: 'Администратор Papaya',
};

function roleBadge(role) {
    if (role === 'ADMIN') return `<span class="${UI.badge} ${UI.badgeAdmin}">Администратор</span>`;
    if (role === 'EDITOR') return `<span class="${UI.badge} ${UI.badgeNeutral}">Представитель</span>`;
    return `<span class="${UI.badge} ${UI.badgeNeutral}">Школьник</span>`;
}

/** Панель поиска и постраничной выдачи, общая для списков пользователей и олимпиад. */
function adminListToolbarHtml({ searchId, searchAct, moreAct, shown, total, placeholder }) {
    const more = shown < total;
    return `<div class="flex flex-wrap items-end justify-between gap-4 mb-8">
        <form class="flex flex-wrap items-end gap-3" onsubmit="return false;">
            <label class="sr-only" for="${searchId}">Поиск</label>
            <input id="${searchId}" type="search" placeholder="${escAttr(placeholder)}"
                   class="${UI.input} sm:!w-72 !py-2 text-sm">
            <button type="button" data-act="${searchAct}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Найти</button>
        </form>
        <div class="flex items-center gap-3">
            <p class="text-sm text-ink-faint">Показано ${shown} из ${total}</p>
            ${more ? `<button type="button" data-act="${moreAct}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Показать ещё</button>` : ''}
        </div>
    </div>`;
}

function adminUsersHtml() {
    const users = adminUsersState.users;
    const universities = adminUsersState.universities;
    const total = adminUsersState.total > users.length ? adminUsersState.total : users.length;
    const toolbar = adminListToolbarHtml({
        searchId: 'admin-users-search',
        searchAct: 'searchUsers',
        moreAct: 'loadMoreUsers',
        shown: users.length,
        total,
        placeholder: 'Имя, фамилия или email',
    });
    if (!users.length) {
        return toolbar + (adminUsersState.search
            ? emptyHtml('Никого не найдено', 'По этому запросу пользователей нет.')
            : emptyHtml('Пользователей нет', 'Зарегистрируйте первого пользователя.'));
    }
    const selfId = store.user ? store.user.id : null;
    // Активных администраторов может быть один: последнего нельзя понизить или
    // заблокировать — иначе зайти в панель будет некому. Сервер проверяет это
    // правило (ошибка 409), здесь кнопки просто не предлагают действие. Но
    // выводим блокировку только когда список загружен целиком: по одной
    // странице нельзя утверждать, что администратор последний.
    const listComplete = adminUsersState.total <= users.length;
    const activeAdmins = users.filter(item => item.role === 'ADMIN' && item.isActive).length;

    return `${toolbar}
    <div class="space-y-6">
        ${users.map(u => {
            const isSelf = String(u.id) === String(selfId);
            const isLastAdmin = listComplete && u.role === 'ADMIN' && u.isActive && activeAdmins === 1;
            // Кнопки без действующего обоснования не показываем: показывать
            // «сделать нельзя» и получать ошибку — хуже, чем объяснить сразу.
            const lockedReason = isSelf
                ? 'Нельзя менять роль у себя'
                : (isLastAdmin ? 'Последний активный администратор' : '');
            const lockedAttrs = lockedReason ? `disabled title="${escAttr(lockedReason)}"` : '';
            const universityOptions = universities.map(item =>
                `<option value="${escAttr(item.id)}" ${String(u.university_id) === String(item.id) ? 'selected' : ''}>${escHtml(item.short_name || item.name)}</option>`).join('');
            return `
            <div class="${UI.card} px-8 py-7 flex flex-col xl:flex-row xl:items-center gap-6">
                <div class="flex items-center gap-5 flex-1 min-w-[16rem]">
                    <div class="w-12 h-12 rounded bg-ember text-ink font-bold flex items-center justify-center shrink-0" aria-hidden="true">${escHtml(userInitials(u))}</div>
                    <div class="min-w-0">
                        <p class="font-bold text-ink truncate">${escHtml(u.name)} ${escHtml(u.surname)}${isSelf ? ' <span class="text-ink-faint font-medium">(вы)</span>' : ''}</p>
                        <p class="text-sm text-ink-soft truncate">${escHtml(u.email)}</p>
                        <div class="mt-3 flex items-center gap-3 flex-wrap">
                            ${roleBadge(u.role)}
                            ${u.university_id ? `<span class="text-sm text-ink-soft">представляет: ${escHtml(universityLabel(universities, u.university_id))}</span>` : ''}
                            ${u.isActive
                                ? `<span class="${UI.badge} ${UI.badgeSuccess}">Активен</span>`
                                : `<span class="${UI.badge} ${UI.badgeDanger}">Заблокирован</span>`}
                        </div>
                    </div>
                </div>
                <div class="flex flex-col sm:flex-row sm:items-center gap-3 sm:flex-wrap xl:justify-end">
                    <label class="sr-only" for="role-${escAttr(u.id)}">Роль: ${escHtml(u.email)}</label>
                    <select id="role-${escAttr(u.id)}" data-role-for="${escAttr(u.id)}" data-current-role="${escAttr(u.role)}" class="${UI.input} sm:!w-auto sm:max-w-[11rem] !py-2 text-sm">
                        ${Object.keys(ROLE_LABELS).map(role =>
                            `<option value="${role}" ${u.role === role ? 'selected' : ''}>${ROLE_LABELS[role]}</option>`).join('')}
                    </select>
                    <label class="sr-only" for="university-${escAttr(u.id)}">Университет: ${escHtml(u.email)}</label>
                    <select id="university-${escAttr(u.id)}" data-university-for="${escAttr(u.id)}"
                            class="${UI.input} sm:!w-auto sm:max-w-[15rem] !py-2 text-sm"
                            ${u.role === 'EDITOR' ? '' : 'disabled title="Университет назначается представителю"'}>
                        <option value="">Без университета</option>
                        ${universityOptions}
                    </select>
                    <button type="button" data-act="saveRole" data-id="${escAttr(u.id)}" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}"
                            ${isLastAdmin ? lockedAttrs : ''}>
                        Сохранить роль
                    </button>
                    <button type="button" data-act="${u.isActive ? 'ban' : 'unban'}" data-id="${escAttr(u.id)}"
                            class="${UI.btn} ${u.isActive ? UI.btnDanger : UI.btnSecondary} ${UI.btnSmall}"
                            ${u.isActive ? lockedAttrs : ''}>
                        ${u.isActive ? 'Заблокировать' : 'Разблокировать'}
                    </button>
                </div>
            </div>`;
        }).join('')}
    </div>`;
}

function universityLabel(universities, universityId) {
    const match = universities.find(item => String(item.id) === String(universityId));
    return match ? (match.short_name || match.name) : 'университет';
}

/** Перерисовать только контейнер пользователей (после догрузки или поиска). */
function renderUsersBox() {
    const box = document.getElementById('admin-content');
    if (box) box.innerHTML = adminUsersHtml();
}

async function loadMoreUsers() {
    try {
        const res = await api.adminUsers({
            limit: ADMIN_LIST_PAGE_SIZE,
            offset: adminUsersState.users.length,
            search: adminUsersState.search || undefined,
        });
        adminUsersState.users = adminUsersState.users.concat(res.data.users || []);
        if (res.data.total != null) adminUsersState.total = res.data.total;
        renderUsersBox();
    } catch (err) {
        showToast('Не удалось загрузить пользователей', 'error');
    }
}

async function searchUsers() {
    const input = document.getElementById('admin-users-search');
    const search = (input ? input.value : '').trim();
    try {
        const res = await api.adminUsers({ limit: ADMIN_LIST_PAGE_SIZE, offset: 0, search: search || undefined });
        const users = res.data.users || [];
        adminUsersState.users = users;
        adminUsersState.total = res.data.total != null ? res.data.total : users.length;
        adminUsersState.search = search;
        renderUsersBox();
    } catch (err) {
        showToast('Не удалось выполнить поиск', 'error');
    }
}

/* -------------------------------- Олимпиады -------------------------------- */

function adminOlympiadsHtml() {
    const olympiads = adminOlympiadsState.olympiads;
    const total = adminOlympiadsState.total > olympiads.length ? adminOlympiadsState.total : olympiads.length;
    const toolbar = adminListToolbarHtml({
        searchId: 'admin-olympiads-search',
        searchAct: 'searchOlympiads',
        moreAct: 'loadMoreOlympiads',
        shown: olympiads.length,
        total,
        placeholder: 'Название олимпиады',
    });
    if (!olympiads.length) {
        if (adminOlympiadsState.search) {
            return toolbar + emptyHtml('Ничего не найдено', 'По этому запросу олимпиад нет.');
        }
        return emptyHtml('Каталог олимпиад пуст',
            'Добавьте олимпиаду вручную или импортируйте документ РСОШ.',
            `<button data-act="newOlympiad" class="${UI.btn} ${UI.btnPrimary}">Создать олимпиаду</button>`);
    }
    return `${toolbar}
    <div class="flex flex-wrap items-center justify-between gap-6 mb-10">
        <p class="text-sm text-ink-faint">Всего: ${total}</p>
        <button data-act="newOlympiad" class="${UI.btn} ${UI.btnPrimary}">Создать олимпиаду</button>
    </div>
    <div class="space-y-6">
        ${olympiads.map(item => `
        <div class="${UI.card} px-8 py-7 flex flex-col lg:flex-row lg:items-center gap-6">
            <div class="flex-1 min-w-0">
                <p class="font-bold text-ink leading-snug">${escHtml(item.name)}</p>
                <p class="mt-2 text-sm text-ink-soft">Обновлена ${formatDate(item.updatedAt)}${item.source_doc_id ? ' · из документа РСОШ' : ' · вручную'}</p>
                ${item.status === 'ARCHIVED' ? `<p class="mt-2 text-sm text-ink-soft">${escHtml(archiveReasonText(item.archive_reason))}</p>` : ''}
            </div>
            <div class="flex items-center gap-3 flex-wrap shrink-0">
                ${olympiadStatusBadge(item.status)}
                <a href="#/olympiads/${escAttr(item.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Открыть</a>
                <button data-act="editOlympiad" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Правка</button>
                <button data-act="editSeasons" data-id="${escAttr(item.id)}" data-olympiad-name="${escAttr(item.name)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Сезоны</button>
                ${item.status === 'ARCHIVED'
                    ? (item.archive_reason === 'RSOSH_ABSENT'
                        // Вернуть из архива «нет в перечне РСОШ» вручную нельзя:
                        // кнопка была бы без действия, поэтому её не показываем.
                        ? `<span class="${UI.badge} ${UI.badgeNeutral}">Вернётся при импорте РСОШ</span>`
                        : `<button data-act="restore" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Вернуть</button>`)
                    : `<button data-act="archive" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">В архив</button>`}
            </div>
        </div>`).join('')}
    </div>`;
}

/** Перерисовать только контейнер олимпиад (после догрузки или поиска). */
function renderOlympiadsBox() {
    const box = document.getElementById('admin-content');
    if (box) box.innerHTML = adminOlympiadsHtml();
}

async function loadMoreOlympiads() {
    try {
        const res = await api.adminOlympiads({
            limit: ADMIN_LIST_PAGE_SIZE,
            offset: adminOlympiadsState.olympiads.length,
            search: adminOlympiadsState.search || undefined,
        });
        adminOlympiadsState.olympiads = adminOlympiadsState.olympiads.concat(res.data.olympiads || []);
        if (res.data.total != null) adminOlympiadsState.total = res.data.total;
        renderOlympiadsBox();
    } catch (err) {
        showToast('Не удалось загрузить олимпиады', 'error');
    }
}

async function searchOlympiads() {
    const input = document.getElementById('admin-olympiads-search');
    const search = (input ? input.value : '').trim();
    try {
        const res = await api.adminOlympiads({ limit: ADMIN_LIST_PAGE_SIZE, offset: 0, search: search || undefined });
        const olympiads = res.data.olympiads || [];
        adminOlympiadsState.olympiads = olympiads;
        adminOlympiadsState.total = res.data.total != null ? res.data.total : olympiads.length;
        adminOlympiadsState.search = search;
        renderOlympiadsBox();
    } catch (err) {
        showToast('Не удалось выполнить поиск', 'error');
    }
}

/* ------------------------------ Университеты ------------------------------- */

function adminUniversitiesHtml(universities) {
    if (!universities.length) {
        return emptyHtml('Каталог университетов пуст',
            'Университеты заводятся вручную администратором.',
            `<button data-act="newUniversity" class="${UI.btn} ${UI.btnPrimary}">Создать университет</button>`);
    }
    return `
    <div class="flex flex-wrap items-center justify-between gap-6 mb-10">
        <p class="text-sm text-ink-faint">Всего: ${universities.length}</p>
        <button data-act="newUniversity" class="${UI.btn} ${UI.btnPrimary}">Создать университет</button>
    </div>
    <div class="space-y-6">
        ${universities.map(item => `
        <div class="${UI.card} px-8 py-7 flex flex-col lg:flex-row lg:items-center gap-6">
            <div class="flex-1 min-w-0">
                <p class="font-bold text-ink leading-snug">${escHtml(item.short_name || item.name)}</p>
                <p class="mt-2 text-sm text-ink-soft">${escHtml(item.short_name ? item.name : '')}${item.website ? `${item.short_name ? ' · ' : ''}` + escHtml(item.website) : ''}</p>
            </div>
            <div class="flex items-center gap-3 flex-wrap shrink-0">
                <a href="#/universities/${escAttr(item.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Открыть</a>
                <button data-act="editUniversity" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Правка</button>
            </div>
        </div>`).join('')}
    </div>`;
}

async function editUniversityAction(id) {
    const res = await api.getUniversity(id);
    if (!res.ok) { showToast(errorText(res), 'error'); return; }
    openUniversityFormModal(res.data, () => reloadAdmin());
}

async function editOlympiadAction(id) {
    const res = await api.getOlympiad(id);
    if (!res.ok) { showToast(errorText(res), 'error'); return; }
    openOlympiadFormModal(res.data, () => reloadAdmin());
}

/* ------------------------------ Заявки вузов ------------------------------- */

/**
 * Очередь заявок на роль представителя вуза (ТЗ §3.4).
 *
 * Администратор решает по человеку и вузу, поэтому в строке видно, кто
 * подал заявку и от какого университета, а не только идентификаторы.
 */
function adminApplicationsHtml(applications) {
    if (!applications.length) {
        return emptyHtml('Заявок нет', 'Заявок на роль представителя, ожидающих решения, сейчас нет.');
    }
    const rows = applications.map(app => `
        <div class="${UI.card} px-8 py-6">
            <div class="flex flex-col lg:flex-row lg:items-start gap-6">
                <div class="flex-1 min-w-0">
                    <p class="font-bold text-ink leading-snug">
                        ${escHtml(app.applicant_name || 'Заявитель')}
                    </p>
                    <p class="mt-2 text-sm text-ink-soft">
                        ${escHtml(app.applicant_email || '')}
                        ${app.applicant_email && app.university_name ? ' · ' : ''}
                        ${escHtml(app.university_name || '')}
                    </p>
                    ${app.motivation
                        ? `<p class="mt-4 text-base text-ink leading-relaxed">${escHtml(app.motivation)}</p>`
                        : ''}
                    <p class="mt-3 text-sm text-ink-faint">Подана: ${formatDate(app.createdAt)}</p>
                </div>
                <div class="flex flex-wrap gap-3 shrink-0">
                    <button data-act="decideApplication" data-id="${escAttr(app.id)}"
                            data-decision="APPROVED"
                            class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Одобрить</button>
                    <button data-act="decideApplication" data-id="${escAttr(app.id)}"
                            data-decision="REJECTED"
                            class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Отклонить</button>
                </div>
            </div>
        </div>`).join('');

    return `
    <div class="flex flex-wrap items-center justify-between gap-4 mb-6">
        <p class="text-sm text-ink-faint">Ожидают решения: ${applications.length}</p>
    </div>
    <div class="space-y-4">${rows}</div>`;
}

/**
 * Решение по заявке с обязательным пояснением при отклонении.
 *
 * Отказ без причины бесполезен заявителю: он не понимает, что исправлять.
 * Поэтому при отклонении пояснение спрашивается, а при одобрении — можно
 * оставить пустым.
 */
function openApplicationDecisionModal(applicationId) {
    const body = `
        <div id="modal-alert"></div>
        <form id="application-decision-form">
            ${textareaField({
                id: 'decision-note', name: 'note', rows: 3,
                label: 'Пояснение (обязательно при отклонении)',
                placeholder: 'Например: не подтверждено письмо от приёмной комиссии',
            })}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" data-decision="REJECTED" class="${UI.btn} ${UI.btnSecondary}">Отклонить</button>
                <button type="submit" data-decision="APPROVED" class="${UI.btn} ${UI.btnPrimary}">Одобрить</button>
            </div>
        </form>`;
    const { overlay, close } = openModal('Решение по заявке', body);
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    overlay.querySelector('#application-decision-form').addEventListener('submit', async e => {
        e.preventDefault();
        const decision = e.submitter ? e.submitter.dataset.decision : 'APPROVED';
        const note = overlay.querySelector('#decision-note').value.trim();
        if (decision === 'REJECTED' && !note) {
            showModalError(overlay, {
                data: { detail: 'Укажите причину отклонения: без неё заявитель не поймёт, что исправлять' },
            });
            return;
        }
        const res = await api.decideApplication(applicationId, { decision, note: note || null });
        if (res.ok) {
            close();
            showToast(decision === 'APPROVED' ? 'Заявка одобрена' : 'Заявка отклонена', 'success');
            await reloadAdmin();
            return;
        }
        showModalError(overlay, res);
    });
}

/* -------------------------- Сезоны и профили олимпиады ---------------------- */

/**
 * Сезоны олимпиады и профили (ТЗ §4.2, §4.4).
 *
 * Сезон — год с его состоянием, датами и уровнем РСОШ; профиль — предметная
 * номенклатура сезона. Условия олимпиады меняются год от года, поэтому они и
 * хранятся по сезонам, а не приписываются олимпиаде навсегда.
 */
async function openSeasonsModal(olympiadId, olympiadName) {
    const res = await api.listOlympiadSeasons(olympiadId).catch(() => ({ ok: false }));
    const seasons = (res.ok && res.data && res.data.seasons) || [];

    const body = `
        <div id="modal-alert"></div>
        <div id="seasons-list">${seasonsModalListHtml(seasons)}</div>
        <form id="season-create-form" class="mt-10 pt-8 border-t border-mist">
            <h3 class="${UI.eyebrow}">Добавить или обновить сезон</h3>
            <div class="mt-6 grid sm:grid-cols-2 gap-x-4">
                ${inputField({ id: 'season-year', name: 'year', label: 'Год', type: 'number', required: true, value: String(new Date().getFullYear()) })}
                ${selectField({ id: 'season-state', name: 'state', label: 'Состояние', value: 'unknown', options: [
                    { value: 'unknown', label: 'Неизвестно' },
                    { value: 'upcoming', label: 'Сезон ещё не начался' },
                    { value: 'active', label: 'Сезон идёт' },
                    { value: 'completed', label: 'Сезон завершён' },
                ]})}
            </div>
            <div class="grid sm:grid-cols-2 gap-x-4">
                ${inputField({ id: 'season-rsoh', name: 'rsoh_level', label: 'Уровень РСОШ', value: '', placeholder: 'например: 1' })}
                ${inputField({ id: 'season-registration-start', name: 'registration_start', label: 'Начало регистрации', type: 'date', value: '' })}
            </div>
            <div class="grid sm:grid-cols-2 gap-x-4">
                ${inputField({ id: 'season-registration-end', name: 'registration_end', label: 'Конец регистрации', type: 'date', value: '' })}
                ${inputField({ id: 'season-start-date', name: 'start_date', label: 'Начало туров', type: 'date', value: '' })}
            </div>
            ${inputField({ id: 'season-end-date', name: 'end_date', label: 'Конец туров', type: 'date', value: '' })}
            ${inputField({ id: 'season-source-url', name: 'source_url', label: 'Ссылка на условия', type: 'url', value: '' })}
            ${textareaField({ id: 'season-description', name: 'description', rows: 2, label: 'Описание сезона', value: '' })}
            <div class="flex flex-wrap justify-end gap-3 mt-8">
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Сохранить сезон</button>
            </div>
        </form>`;

    const { overlay, close } = openModal(`Сезоны: ${olympiadName || 'олимпиада'}`, body, { wide: true });

    overlay.querySelector('#season-create-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const year = Number(fd.get('year'));
        if (!year) return;
        const dates = {};
        ['registration_start', 'registration_end', 'start_date', 'end_date'].forEach(key => {
            const value = fd.get(key);
            if (value) dates[key] = value;
        });
        const payload = {
            year,
            state: fd.get('state'),
            rsoh_level: fd.get('rsoh_level') || null,
            description: fd.get('description') || null,
            source_url: fd.get('source_url') || null,
            dates: Object.keys(dates).length ? dates : null,
        };
        const saved = await api.upsertOlympiadSeason(olympiadId, year, payload);
        if (saved.ok) {
            close();
            showToast('Сезон сохранён', 'success');
            return;
        }
        showModalError(overlay, saved);
    });

    // Архивирование сезона и добавление профиля — по кнопкам в списке.
    overlay.addEventListener('click', async e => {
        const archiveBtn = e.target.closest('[data-archive-season]');
        if (archiveBtn) {
            archiveBtn.disabled = true;
            const archived = await api.archiveOlympiadSeason(
                olympiadId, archiveBtn.dataset.archiveSeason);
            if (archived.ok) {
                close();
                showToast('Сезон закрыт', 'success');
            } else {
                showToast(errorText(archived), 'error');
                archiveBtn.disabled = false;
            }
            return;
        }
        const profileBtn = e.target.closest('[data-add-profile]');
        if (profileBtn) {
            // Форма профиля раскрывается на месте: отдельный вопрос профиля
            // не должен уводить администратора в системный диалог, где нельзя
            // указать предмет и ошибиться без возможности вернуться.
            const form = overlay.querySelector(
                `[data-profile-form="${profileBtn.dataset.addProfile}"]`);
            if (form) form.classList.toggle('hidden');
            return;
        }
    });

    overlay.addEventListener('submit', async e => {
        const form = e.target.closest('[data-profile-form]');
        if (!form) return;
        e.preventDefault();
        const fd = new FormData(form);
        const name = (fd.get('name') || '').trim();
        if (!name) return;
        const subject = (fd.get('subject') || '').trim();
        const added = await api.addOlympiadSeasonProfile(
            olympiadId, form.dataset.profileForm, { name, subject: subject || null });
        if (added.ok) {
            close();
            showToast('Профиль добавлен', 'success');
            return;
        }
        showModalError(overlay, added);
    });
}

/** Список сезонов внутри модалки. */
function seasonsModalListHtml(seasons) {
    if (!seasons.length) {
        return `<p class="text-ink-soft leading-relaxed">
            Сезонов пока нет. Условия олимпиады хранятся по сезонам, поэтому
            добавьте год с датами — иначе посетитель увидит «даты не опубликованы».
        </p>`;
    }
    const rows = seasons.map(season => `
        <div class="rounded bg-mist px-5 py-4">
            <div class="flex flex-wrap items-center gap-3">
                <span class="text-lg font-bold">${escHtml(String(season.year))}</span>
                <span class="${UI.badge} ${UI.badgeNeutral}">${escHtml(seasonStateLabel(season.state))}</span>
                ${season.rsoh_level
                    ? `<span class="${UI.badge} ${UI.badgePending}">Уровень РСОШ: ${escHtml(season.rsoh_level)}</span>`
                    : ''}
            </div>
            <p class="mt-3 text-sm text-ink-soft">${escHtml(seasonDatesText(season.dates))}</p>
            ${seasonProfilesAdminHtml(season.profiles)}
            <div class="mt-4 flex flex-wrap gap-3">
                <button type="button" data-add-profile="${escAttr(season.id)}"
                        class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Добавить профиль</button>
                ${season.state === 'completed'
                    ? ''
                    : `<button type="button" data-archive-season="${escAttr(season.id)}"
                              class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Закрыть сезон</button>`}
            </div>
            <form class="hidden mt-4 flex flex-wrap items-end gap-3" data-profile-form="${escAttr(season.id)}">
                <div class="flex-1 min-w-[12rem]">
                    <label for="profile-name-${escAttr(season.id)}" class="${UI.label}">Название профиля</label>
                    <input id="profile-name-${escAttr(season.id)}" name="name" type="text" class="${UI.input}"
                           placeholder="например: Математика">
                </div>
                <div class="flex-1 min-w-[12rem]">
                    <label for="profile-subject-${escAttr(season.id)}" class="${UI.label}">Предмет</label>
                    <input id="profile-subject-${escAttr(season.id)}" name="subject" type="text" class="${UI.input}"
                           placeholder="необязательно">
                </div>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Сохранить профиль</button>
            </form>
        </div>`).join('');
    return `<div class="space-y-4">${rows}</div>`;
}

/** Уже заведённые профили сезона — списком под датами. */
function seasonProfilesAdminHtml(profiles) {
    if (!profiles || !profiles.length) return '';
    const items = profiles.map(profile => `
        <li class="flex flex-wrap items-baseline gap-2 text-sm">
            <span class="font-semibold text-ink">${escHtml(profile.name)}</span>
            ${profile.subject
                ? `<span class="text-ink-soft">${escHtml(profile.subject)}</span>`
                : ''}
        </li>`).join('');
    return `
        <ul class="mt-3 space-y-1">${items}</ul>`;
}

/* --------------------------------- БВИ ------------------------------------ */
/** Скачать всю очередь БВИ постранично: группировка по вузам требует полного списка. */
async function fetchAllBviLinks() {
    const all = [];
    let total = Infinity;
    while (all.length < total) {
        const res = await api.adminBviLinks(null, { limit: BVI_PAGE_SIZE, offset: all.length });
        if (!res.ok) throw new Error(errorText(res));
        const batch = res.data.links || [];
        all.push(...batch);
        total = res.data.total != null ? res.data.total : all.length;
        if (!batch.length) break;
    }
    return all;
}

/** Сгруппировать связи по университету и разложить на заявки и подтверждённые. */
function groupBviLinksByUniversity(links) {
    const groups = new Map();
    for (const link of links) {
        const key = String(link.university_id || 'unknown');
        if (!groups.has(key)) {
            groups.set(key, {
                university_id: link.university_id,
                university_name: link.university_name || 'Университет',
                pending: [],
                confirmed: [],
            });
        }
        const group = groups.get(key);
        if (link.status === 'CONFIRMED') group.confirmed.push(link);
        else group.pending.push(link);
    }
    return [...groups.values()];
}

/** Одна связь внутри группы: олимпиада и действия по её статусу. */
function bviLinkRowHtml(link) {
    return `<div class="rounded bg-mist px-5 py-4 flex flex-col lg:flex-row lg:items-center gap-4">
        <div class="flex-1 min-w-0">
            <p class="text-ink leading-snug">${escHtml(link.olympiad_name || 'Олимпиада')}</p>
            ${link.olympiad_status === 'ARCHIVED' ? '<p class="mt-1 text-xs text-ink-faint">Олимпиада в архиве</p>' : ''}
            ${link.status === 'CONFIRMED' && link.benefit_type
                ? `<p class="mt-1 text-xs text-ink-faint">Льгота: ${escHtml(benefitTypeLabel(link.benefit_type))}</p>`
                : ''}
        </div>
        <div class="flex items-center gap-3 flex-wrap shrink-0">
            ${bviStatusBadge(link.status)}
            ${link.status === 'CONFIRMED'
                ? `<button data-act="revokeBvi" data-university="${escAttr(link.university_id)}" data-id="${escAttr(link.olympiad_id)}" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}">Отозвать подтверждение</button>
                   <button data-act="editBenefitRule" data-university="${escAttr(link.university_id)}" data-id="${escAttr(link.olympiad_id)}" data-olympiad-name="${escAttr(link.olympiad_name || '')}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Правило льготы</button>`
                : `<button data-act="rejectBvi" data-university="${escAttr(link.university_id)}" data-id="${escAttr(link.olympiad_id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Отклонить</button>
                   <button data-act="confirmBvi" data-university="${escAttr(link.university_id)}" data-id="${escAttr(link.olympiad_id)}" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Подтвердить</button>`}
        </div>
    </div>`;
}

/** Раскрывающийся раздел одного университета: заявки и подтверждённые отдельно. */
function bviUniversityGroupHtml(group) {
    const pendingCount = group.pending.length;
    const confirmedCount = group.confirmed.length;
    const open = pendingCount > 0 ? ' open' : '';
    const badge = (cls, text) => `<span class="${UI.badge} ${cls}">${text}</span>`;
    return `<details class="${UI.card} px-8 py-6"${open}>
        <summary class="flex flex-wrap items-center justify-between gap-4 cursor-pointer list-none [&::-webkit-details-marker]:hidden">
            <span class="font-bold text-ink leading-snug">${escHtml(group.university_name)}</span>
            <span class="flex flex-wrap items-center gap-3 text-sm">
                ${pendingCount ? badge(UI.badgePending, `Ждут подтверждения: ${pendingCount}`) : ''}
                ${confirmedCount ? badge(UI.badgeSuccess, `Подтверждено: ${confirmedCount}`) : ''}
            </span>
        </summary>
        <div class="mt-6 space-y-8">
            ${pendingCount ? `<div>
                <div class="flex flex-wrap items-center justify-between gap-4 mb-4">
                    <p class="text-sm font-semibold text-ink-soft">Ожидают подтверждения · ${pendingCount}</p>
                    <button type="button" data-act="confirmAllBvi" data-university="${escAttr(group.university_id)}" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Подтвердить все</button>
                </div>
                <div class="space-y-3">${group.pending.map(bviLinkRowHtml).join('')}</div>
            </div>` : ''}
            ${confirmedCount ? `<div>
                <p class="text-sm font-semibold text-ink-soft mb-4">Подтверждённые · ${confirmedCount}</p>
                <div class="space-y-3">${group.confirmed.map(bviLinkRowHtml).join('')}</div>
            </div>` : ''}
        </div>
    </details>`;
}

function adminBviHtml(links) {
    if (!links.length) {
        return emptyHtml('Заявок нет', 'Представители университетов ещё не заявляли связи БВИ.');
    }
    const groups = groupBviLinksByUniversity(links);
    return `<div class="flex flex-wrap items-center justify-between gap-4 mb-6">
        <p class="text-sm text-ink-faint">Университетов: ${groups.length} · связей: ${links.length}</p>
    </div>
    <div class="space-y-4">
        ${groups.map(bviUniversityGroupHtml).join('')}
    </div>`;
}

/** Подтвердить разом все ожидающие заявки одного университета. */
async function confirmAllBviLinks(universityId) {
    const pending = bviState.links.filter(
        link => String(link.university_id) === String(universityId) && link.status !== 'CONFIRMED'
    );
    if (!pending.length) return;
    let confirmed = 0;
    let failed = 0;
    for (const link of pending) {
        try {
            const res = await api.moderateBvi(link.university_id, link.olympiad_id, 'confirm');
            if (res.ok) confirmed += 1; else failed += 1;
        } catch {
            failed += 1;
        }
    }
    if (confirmed) {
        showToast(confirmed === 1 ? 'Связь БВИ подтверждена' : `Подтверждено связей: ${confirmed}`, 'success');
    }
    if (failed) showToast(`Не удалось подтвердить: ${failed}`, 'error');
    await reloadAdmin();
}

/* -------------------------- Правила льгот и версии ------------------------- */

/**
 * Правка правила льготы и его история (ТЗ §4.3, §8).
 *
 * Модалка показывает две вещи: форму текущего правила и список версий с
 * откатом. Откат — не «отмена правки», а новая версия с прежним содержимым,
 * поэтому в истории остаётся видно, что откат был.
 */
async function openBenefitRuleModal(universityId, olympiadId, olympiadName) {
    const [rulesRes, versionsRes] = await Promise.all([
        // include_pending: правило заполняется и до подтверждения связи —
        // иначе у заявки, ждущей модерации, условия было бы негде указать.
        api.listBenefitRules(universityId, { include_pending: true }),
        api.benefitRuleVersions(universityId, olympiadId).catch(() => ({ ok: false })),
    ]);
    const rules = (rulesRes.ok && rulesRes.data && rulesRes.data.rules) || [];
    const rule = rules.find(item => String(item.olympiad_id) === String(olympiadId)) || {};
    const versions = (versionsRes.ok && versionsRes.data && versionsRes.data.versions) || [];

    const body = `
        <div id="modal-alert"></div>
        <form id="benefit-rule-form">
            ${selectField({
                id: 'rule-benefit-type', name: 'benefit_type', label: 'Вид льготы',
                value: rule.benefit_type || 'BVI',
                options: [
                    { value: 'BVI', label: 'БВИ' },
                    { value: 'EGE_100', label: '100 баллов ЕГЭ' },
                    { value: 'DVI_100', label: '100 баллов ДВИ' },
                    { value: 'OTHER', label: 'Иная льгота' },
                ],
            })}
            ${inputField({
                id: 'rule-result-requirement', name: 'result_requirement',
                label: 'Требуемый результат', value: rule.result_requirement || '',
                placeholder: 'например: диплом победителя',
            })}
            ${inputField({
                id: 'rule-subject', name: 'subject', label: 'Предмет',
                value: rule.subject || '', placeholder: 'например: Математика',
            })}
            ${inputField({
                id: 'rule-programs', name: 'programs', label: 'Образовательные программы (через запятую)',
                value: (rule.programs || []).join(', '),
            })}
            ${textareaField({
                id: 'rule-extra', name: 'extra_requirements', rows: 2,
                label: 'Дополнительные условия', value: rule.extra_requirements || '',
            })}
            ${inputField({
                id: 'rule-source-url', name: 'source_url', type: 'url', label: 'Ссылка на источник',
                value: rule.source_url || '', placeholder: 'https://…',
            })}
            ${inputField({
                id: 'rule-valid-until', name: 'valid_until', type: 'date',
                label: 'Действует до (дата)',
                value: (rule.valid_until || '').slice(0, 10),
            })}
            ${selectField({
                id: 'rule-verification', name: 'verification_status', label: 'Проверка Papaya',
                value: rule.verification_status || 'unverified',
                options: [
                    { value: 'unverified', label: 'Не проверено' },
                    { value: 'verified', label: 'Проверено' },
                    { value: 'rejected', label: 'Проверка не пройдена' },
                ],
            })}
            ${inputField({
                id: 'rule-reason', name: 'reason', label: 'Почему изменено (попадёт в историю)',
                value: '', placeholder: 'например: сверено с приказом вуза за 2026 год',
            })}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Сохранить</button>
            </div>
        </form>
        <section class="mt-12">
            <h3 class="${UI.eyebrow}">История версий</h3>
            ${benefitVersionsHtml(versions)}
        </section>`;

    const { overlay, close } = openModal(
        `Правило льготы: ${olympiadName || 'олимпиада'}`, body, { wide: true });
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    overlay.querySelector('#benefit-rule-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const programs = String(fd.get('programs') || '')
            .split(',')
            .map(part => part.trim())
            .filter(Boolean);
        const payload = {
            benefit_type: fd.get('benefit_type'),
            result_requirement: fd.get('result_requirement') || null,
            subject: fd.get('subject') || null,
            programs,
            extra_requirements: fd.get('extra_requirements') || null,
            source_url: fd.get('source_url') || null,
            valid_until: fd.get('valid_until') || null,
            verification_status: fd.get('verification_status'),
            reason: fd.get('reason') || null,
        };
        const res = await api.updateBenefitRule(universityId, olympiadId, payload);
        if (res.ok) {
            close();
            showToast('Правило льготы сохранено', 'success');
            await reloadAdmin();
            return;
        }
        showModalError(overlay, res);
    });

    // Откат версии: подтверждаем, потому что он меняет публичное правило.
    overlay.addEventListener('click', async e => {
        const btn = e.target.closest('[data-rollback]');
        if (!btn) return;
        const version = btn.dataset.rollback;
        if (!window.confirm(`Откатить правило к версии ${version}?`)) return;
        btn.disabled = true;
        const res = await api.rollbackBenefitRule(universityId, olympiadId, version);
        if (res.ok) {
            close();
            showToast('Правило откатано', 'success');
            await reloadAdmin();
            return;
        }
        btn.disabled = false;
        showToast(errorText(res), 'error');
    });
}

/** Список версий правила: номер, кто и когда изменил, и кнопка отката. */
function benefitVersionsHtml(versions) {
    if (!versions.length) {
        return `<p class="mt-4 text-sm text-ink-soft">История пуста: правило ещё не менялось.</p>`;
    }
    const rows = versions.slice().reverse().map(version => `
        <li class="rounded bg-mist px-5 py-4">
            <div class="flex flex-wrap items-center gap-3">
                <span class="text-sm font-bold">Версия ${escHtml(String(version.version))}</span>
                ${version.is_rollback ? `<span class="${UI.badge} ${UI.badgeNeutral}">Откат</span>` : ''}
                <span class="text-sm text-ink-soft">${formatDate(version.changed_at)}</span>
                <button type="button" data-rollback="${escAttr(String(version.version))}"
                        class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall} ml-auto">Откатить</button>
            </div>
            ${version.reason
                ? `<p class="mt-2 text-sm text-ink-soft">${escHtml(version.reason)}</p>`
                : ''}
        </li>`).join('');
    return `<ul class="mt-4 space-y-3">${rows}</ul>`;
}

/* ------------------------------ Импорт РСОШ ------------------------------- */

const IMPORT_STATE_LABELS = {
    processing: 'Обрабатывается…',
    paused: 'Приостановлен',
    review: 'Готов к подтверждению',
    approved: 'Применён',
    rejected: 'Отклонён',
    failed: 'Ошибка',
};

/* Этап обработки — понятный человеку текст вместо машинного ``stage``. */
const IMPORT_PROGRESS_LABELS = {
    starting: 'подготовка',
    extracting: 'чтение документа',
    matching: 'сопоставление с каталогом',
    resuming: 'возобновление',
    done: 'завершено',
    failed: 'ошибка',
};

function importProgressText(item) {
    const stage = (item.progress || {}).stage;
    return stage ? (IMPORT_PROGRESS_LABELS[stage] || stage) : '';
}

function adminImportsHtml(imports) {
    return `
    <div class="flex flex-wrap items-center justify-between gap-6 mb-10">
        <p class="text-sm text-ink-faint">Документов РСОШ: ${imports.length}</p>
        <button data-act="newImport" class="${UI.btn} ${UI.btnPrimary}">Загрузить документ РСОШ</button>
    </div>
    ${imports.length ? `<div class="space-y-6">${imports.map(item => {
        const state = item.state || '—';
        const summary = item.summary || {};
        const stage = importProgressText(item);
        return `
        <div class="${UI.card} px-8 py-7">
            <div class="flex flex-col lg:flex-row lg:items-center gap-6">
                <div class="flex-1 min-w-0">
                    <p class="font-bold text-ink leading-snug">${escHtml(item.name)}</p>
                    <p class="mt-2 text-sm text-ink-soft">
                        Статус документа: ${escHtml(item.status)} ·
                        ${escHtml(IMPORT_STATE_LABELS[state] || state)}
                        ${state === 'processing' && stage ? ` · этап: ${escHtml(stage)}` : ''}
                        ${summary.total ? ` · найдено: ${summary.total} (новых: ${summary.new || 0}, объединений: ${summary.merge || 0}, на проверку: ${summary.review || 0})` : ''}
                    </p>
                    ${item.error ? `<p class="mt-3 text-sm text-crimson">${escHtml(item.error)}</p>` : ''}
                </div>
                <div class="flex flex-wrap gap-3 shrink-0">
                    ${state === 'rejected' ? '' : `<button data-act="runImport" data-id="${escAttr(item.id)}" ${state === 'paused' || state === 'processing' ? 'disabled' : ''} class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Запустить импорт</button>`}
                    ${state === 'paused' ? `<button data-act="resumeImport" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Возобновить</button>` : ''}
                    ${state === 'processing' ? `<button data-act="pauseImport" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Приостановить</button>` : ''}
                    <button data-act="previewImport" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Открыть результаты</button>
                </div>
            </div>
            <div class="mt-6 flex flex-wrap gap-3 items-center">
                <a href="${escAttr(api.docFileUrl(item.id))}" target="_blank" rel="noopener noreferrer" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Скачать документ</a>
                ${docAvailabilityHtml(item)}
            </div>
        </div>`;
    }).join('')}</div>`
        : emptyHtml('Документов РСОШ нет',
            'Загрузите официальный документ РСОШ (PDF, XLSX, PNG/JPG) — импорт покажет preview до записи в каталог.',
            `<button data-act="newImport" class="${UI.btn} ${UI.btnPrimary}">Загрузить документ</button>`)}`;
}

/**
 * Доступность документа-источника (ТЗ §7.3).
 *
 * Показывает состояние источника отдельно от состояния импорта: документ мог
 * обработаться успешно, а ссылка на него — протухнуть. Поэтому состояние
 * выбирается вручную, а не выводится из результата импорта.
 */
function docAvailabilityHtml(item) {
    const current = item.availability || 'unknown';
    const labels = {
        unknown: 'Не проверялось',
        ok: 'Доступен',
        broken: 'Недоступен',
    };
    const buttons = Object.keys(labels).map(value => `
        <button type="button" data-act="setDocAvailability" data-id="${escAttr(item.id)}"
                data-availability="${value}"
                class="${UI.btn} ${current === value ? UI.btnPrimary : UI.btnGhost} ${UI.btnSmall}">
            ${escHtml(labels[value])}
        </button>`).join('');
    return `<span class="flex flex-wrap gap-2 items-center" role="group" aria-label="Доступность источника">
        <span class="text-sm text-ink-faint">Источник:</span>${buttons}
    </span>`;
}

/** Сохранить доступность документа-источника. */
async function setDocAvailabilityAction(id, availability) {
    const res = await api.setDocAvailability(id, availability);
    if (res.ok) {
        showToast('Доступность источника сохранена', 'success');
        await reloadAdmin();
        return;
    }
    showToast(errorText(res), 'error');
}

function openUploadModal() {
    let dirty = false;
    const body = `
        <div id="modal-alert"></div>
        <form id="upload-form">
            <div class="${UI.field}">
                <label for="upload-file" class="${UI.label}">Файл документа РСОШ <span class="text-crimson" aria-hidden="true">*</span></label>
                <input id="upload-file" name="file" type="file" accept=".pdf,.xlsx,.png,.jpg,.jpeg" required
                       class="block w-full cursor-pointer text-sm text-ink-soft file:mr-4 file:rounded file:px-5 file:py-2.5 file:text-sm file:font-semibold file:bg-ink file:text-white hover:file:bg-ink-deep">
                <p class="mt-2 text-sm text-ink-soft leading-relaxed">
                    Поддерживаются PDF, XLSX и изображения PNG/JPG/JPEG. Сканы и повёрнутые
                    страницы распознаются через OCR.
                </p>
            </div>
            ${inputField({ id: 'upload-name', name: 'name', label: 'Название документа', placeholder: 'Перечень олимпиад РСОШ 2026' })}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Загрузить и импортировать</button>
            </div>
        </form>`;
    const { overlay, close } = openModal('Документ РСОШ', body, { isDirty: () => dirty });
    ['input', 'change'].forEach(ev => overlay.addEventListener(ev, () => { dirty = true; }));
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    overlay.querySelector('#upload-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const btn = e.target.querySelector('button[type="submit"]');
        btn.disabled = true;
        btn.textContent = 'Загружаем…';
        const upload = await api.uploadDoc(fd);
        if (!upload.ok) {
            showModalError(overlay, upload);
            btn.disabled = false;
            btn.textContent = 'Загрузить и импортировать';
            return;
        }
        dirty = false;
        close();
        showToast('Документ загружен, запускаем импорт', 'success');
        const started = await api.startRsoshImport(upload.data.id);
        if (!started.ok) {
            showToast(errorText(started), 'error');
        } else {
            showToast('Импорт запущен: откройте «Результат» для проверки', 'success');
        }
        await loadAdminTab('imports');
    });
}

async function runImportAction(id, btn) {
    if (btn) { btn.textContent = 'Запускаем…'; }
    const res = await api.startRsoshImport(id);
    if (res.ok) {
        const state = res.data.state || '';
        showToast(state === 'review'
            ? 'Импорт готов к проверке'
            : 'Импорт запущен', 'success');
        await loadAdminTab('imports');
        return;
    }
    showToast(errorText(res), 'error');
    await loadAdminTab('imports');
}

async function pauseImportAction(id, btn) {
    if (btn) { btn.textContent = 'Останавливаем…'; }
    const res = await api.pauseImport(id);
    if (res.ok) {
        // ``paused`` — обработка уже остановлена; ``processing`` — запрос
        // принят, остановка произойдёт на ближайшей границе этапа.
        showToast(res.data.state === 'paused'
            ? 'Импорт приостановлен'
            : 'Запрошена остановка импорта', 'success');
        await loadAdminTab('imports');
        return;
    }
    showToast(errorText(res), 'error');
    await loadAdminTab('imports');
}

async function resumeImportAction(id, btn) {
    if (btn) { btn.textContent = 'Возобновляем…'; }
    const res = await api.resumeImport(id);
    if (res.ok) {
        showToast(res.data.state === 'review'
            ? 'Импорт возобновлён и готов к проверке'
            : 'Импорт возобновлён', 'success');
        await loadAdminTab('imports');
        return;
    }
    showToast(errorText(res), 'error');
    await loadAdminTab('imports');
}

/* ---------------------------- Приказы вузов ------------------------------- */
/* Импорт приказа отличается от перечня РСОШ по существу: приказ не создаёт
   олимпиад. Он лишь заводит заявки БВИ (PENDING) на уже существующие
   олимпиады каталога, а подтверждает их модератор. Поэтому в меню приказа нет
   ни правки названий, ни объединений — только связывание строк. */

function adminOrdersHtml(imports) {
    return `
    <div class="flex flex-wrap items-center justify-between gap-6 mb-10">
        <p class="text-sm text-ink-faint">Приказов вузов: ${imports.length}</p>
        <button data-act="newOrder" class="${UI.btn} ${UI.btnPrimary}">Загрузить приказ вуза</button>
    </div>
    ${imports.length ? `<div class="space-y-6">${imports.map(item => {
        const state = item.state || '—';
        const summary = item.summary || {};
        const stage = importProgressText(item);
        const uni = (item.university || {}).name;
        return `
        <div class="${UI.card} px-8 py-7">
            <div class="flex flex-col lg:flex-row lg:items-center gap-6">
                <div class="flex-1 min-w-0">
                    <p class="font-bold text-ink leading-snug">${escHtml(item.name)}</p>
                    <p class="mt-2 text-sm text-ink-soft">
                        ${uni ? `Вуз: ${escHtml(uni)} · ` : ''}
                        Статус документа: ${escHtml(item.status)} ·
                        ${escHtml(IMPORT_STATE_LABELS[state] || state)}
                        ${state === 'processing' && stage ? ` · этап: ${escHtml(stage)}` : ''}
                        ${summary.total ? ` · строк: ${summary.total} (сопоставлено: ${summary.matched || 0}, вручную: ${summary.unmatched || 0})` : ''}
                    </p>
                    ${item.error ? `<p class="mt-3 text-sm text-crimson">${escHtml(item.error)}</p>` : ''}
                </div>
                <div class="flex flex-wrap gap-3 shrink-0">
                    ${state === 'rejected' || state === 'approved' ? '' : `<button data-act="runOrderImport" data-id="${escAttr(item.id)}" ${state === 'paused' || state === 'processing' ? 'disabled' : ''} class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Запустить импорт</button>`}
                    ${state === 'paused' ? `<button data-act="resumeOrderImport" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Возобновить</button>` : ''}
                    ${state === 'processing' ? `<button data-act="pauseOrderImport" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Приостановить</button>` : ''}
                    <button data-act="previewOrderImport" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Открыть результаты</button>
                </div>
            </div>
            <div class="mt-6 flex flex-wrap gap-3 items-center">
                <a href="${escAttr(api.docFileUrl(item.id))}" target="_blank" rel="noopener noreferrer" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Скачать документ</a>
                ${docAvailabilityHtml(item)}
            </div>
        </div>`;
    }).join('')}</div>`
        : emptyHtml('Приказов вузов нет',
            'Загрузите приказ университета (PDF, XLSX, PNG/JPG) — импорт покажет строки и распознанный вуз до записи заявок.',
            `<button data-act="newOrder" class="${UI.btn} ${UI.btnPrimary}">Загрузить приказ</button>`)}`;
}

function openOrderUploadModal() {
    let dirty = false;
    const body = `
        <div id="modal-alert"></div>
        <form id="order-upload-form">
            <div class="${UI.field}">
                <label for="order-file" class="${UI.label}">Файл приказа вуза <span class="text-crimson" aria-hidden="true">*</span></label>
                <input id="order-file" name="file" type="file" accept=".pdf,.xlsx,.png,.jpg,.jpeg" required
                       class="block w-full cursor-pointer text-sm text-ink-soft file:mr-4 file:rounded file:px-5 file:py-2.5 file:text-sm file:font-semibold file:bg-ink file:text-white hover:file:bg-ink-deep">
                <p class="mt-2 text-sm text-ink-soft leading-relaxed">
                    Приказ сопоставляется с уже существующим каталогом олимпиад.
                    Новые олимпиады не создаются: при подтверждении появятся только
                    заявки БВИ на подтверждение модератором.
                </p>
            </div>
            ${inputField({ id: 'order-name', name: 'name', label: 'Название документа', placeholder: 'Приказ ИТМО о БВИ 2026' })}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Загрузить и импортировать</button>
            </div>
        </form>`;
    const { overlay, close } = openModal('Приказ вуза', body, { isDirty: () => dirty });
    ['input', 'change'].forEach(ev => overlay.addEventListener(ev, () => { dirty = true; }));
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    overlay.querySelector('#order-upload-form').addEventListener('submit', async e => {
        e.preventDefault();
        // Университетский тип документа обязателен: иначе импорт отклонит файл.
        const fd = new FormData(e.target);
        fd.set('type', 'UNIVERSITY_ORDER');
        const btn = e.target.querySelector('button[type="submit"]');
        btn.disabled = true;
        btn.textContent = 'Загружаем…';
        const upload = await api.uploadDoc(fd);
        if (!upload.ok) {
            showModalError(overlay, upload);
            btn.disabled = false;
            btn.textContent = 'Загрузить и импортировать';
            return;
        }
        dirty = false;
        close();
        showToast('Документ загружен, запускаем импорт', 'success');
        const started = await api.startUniversityImport(upload.data.id);
        if (!started.ok) {
            showToast(errorText(started), 'error');
        } else {
            showToast('Импорт запущен: откройте «Результаты» для проверки', 'success');
        }
        await loadAdminTab('orders');
    });
}

async function runOrderImportAction(id, btn) {
    if (btn) { btn.textContent = 'Запускаем…'; }
    const res = await api.startUniversityImport(id);
    if (res.ok) {
        showToast(res.data.state === 'review'
            ? 'Приказ готов к проверке'
            : 'Импорт приказа запущен', 'success');
        await loadAdminTab('orders');
        return;
    }
    showToast(errorText(res), 'error');
    await loadAdminTab('orders');
}

async function pauseOrderImportAction(id, btn) {
    if (btn) { btn.textContent = 'Останавливаем…'; }
    const res = await api.pauseUniversityImport(id);
    if (res.ok) {
        showToast(res.data.state === 'paused'
            ? 'Импорт приказа приостановлен'
            : 'Запрошена остановка импорта', 'success');
        await loadAdminTab('orders');
        return;
    }
    showToast(errorText(res), 'error');
    await loadAdminTab('orders');
}

async function resumeOrderImportAction(id, btn) {
    if (btn) { btn.textContent = 'Возобновляем…'; }
    const res = await api.resumeUniversityImport(id);
    if (res.ok) {
        showToast(res.data.state === 'review'
            ? 'Импорт приказа возобновлён и готов к проверке'
            : 'Импорт приказа возобновлён', 'success');
        await loadAdminTab('orders');
        return;
    }
    showToast(errorText(res), 'error');
    await loadAdminTab('orders');
}

/** Объяснить отказ по устаревшему перечню — без предложения «применить всё равно». */
function showOutdatedImportNotice(reason) {
    const body = `
    <div class="space-y-5 text-ink-soft leading-relaxed">
        <p>${escHtml(reason)}</p>
        <p>Актуальный каталог определяется последним подтверждённым перечнем
           РСОШ, поэтому вернуть его к предыдущей редакции нельзя. Загрузите
           актуальный перечень и подтвердите его — олимпиады, исчезнувшие из
           нового перечня, попадут в архив, а исторические связи сохранятся.</p>
    </div>
    <div class="flex flex-wrap justify-end gap-3 mt-10">
        <button type="button" data-close class="${UI.btn} ${UI.btnGhost}">Понятно</button>
    </div>`;
    const { overlay, close } = openModal('Перечень не применён', body);
    overlay.querySelector('[data-close]').addEventListener('click', close);
}

/** Предупреждения разбора — информационный блок, а не «ошибка». */
function importNoticesHtml(warnings) {
    if (!warnings || !warnings.length) return '';
    return `
    <div class="mb-8 rounded bg-sand/50 px-6 py-4 text-sm leading-relaxed" role="status">
        <p class="font-semibold text-ink mb-2">Замечания при чтении документа</p>
        <ul class="space-y-1.5 text-ink-soft">
            ${warnings.map(w => `
            <li class="flex items-start gap-2">
                <span class="w-1.5 h-1.5 rounded-full bg-ember shrink-0 mt-1.5" aria-hidden="true"></span>
                <span>${escHtml(w)}</span>
            </li>`).join('')}
        </ul>
    </div>`;
}

/* Плавающая кнопка «Добавить олимпиаду» в меню документа РСОШ. Показывается,
   пока прогон не подтверждён и не отклонён: пока перечень не применён,
   администратор может дополнить его вручную. */
function importFabHtml(state) {
    if (!['processing', 'paused', 'review'].includes(state)) return '';
    return `<button type="button" data-ri="addManualCandidate"
        class="fixed bottom-8 right-8 z-40 inline-flex items-center gap-2 rounded bg-ink text-white px-6 py-4 text-sm font-semibold shadow-elev-2 hover:bg-ink-deep transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">
        <span aria-hidden="true" class="text-lg leading-none">+</span> Добавить олимпиаду
    </button>`;
}

function openAddImportCandidateModal(importId, onDone) {
    let dirty = false;
    const body = `
        <div id="modal-alert"></div>
        <form id="import-candidate-form">
            ${inputField({ id: 'ic-name', name: 'name', label: 'Название олимпиады', required: true, placeholder: 'Например: Олимпиада школьников «Ломоносов»' })}
            ${textareaField({ id: 'ic-desc', name: 'description', label: 'Описание', value: '' })}
            <p class="mt-4 text-sm text-ink-soft leading-relaxed">
                Олимпиада добавится в этот документ и создастся при подтверждении
                импорта. Её источником станет сам документ РСОШ.
            </p>
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Добавить олимпиаду</button>
            </div>
        </form>`;
    const { overlay, close } = openModal('Новая олимпиада в документе', body, { isDirty: () => dirty });
    ['input', 'change'].forEach(ev => overlay.addEventListener(ev, () => { dirty = true; }));
    overlay.querySelector('[data-cancel]').addEventListener('click', close);
    overlay.querySelector('#import-candidate-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const payload = {
            name: (fd.get('name') || '').trim(),
            description: (fd.get('description') || '').trim() || null,
        };
        if (!payload.name) {
            showModalError(overlay, { data: { detail: 'Укажите название олимпиады' } });
            return;
        }
        const btn = e.target.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
            const res = await api.addImportCandidate(importId, payload);
            if (res.ok) {
                dirty = false;
                close();
                showToast('Олимпиада добавлена в документ', 'success');
                if (onDone) onDone();
                return;
            }
            showModalError(overlay, res);
        } catch {
            showModalError(overlay, { data: { detail: 'Сетевая ошибка' } });
        }
        btn.disabled = false;
    });
}

async function renderImportReview(importId) {
    const page = document.getElementById('page');
    page.innerHTML = `<section class="pt-4 pb-32">${loadingHtml('Загружаем результаты импорта…')}</section>`;

    let data = null;
    const olympiadMap = new Map();
    let preview = null;
    try {
        preview = await api.importPreview(importId);
        if (!preview.ok) throw new Error(errorText(preview));
        data = preview.data;
        const list = await api.adminOlympiads();
        if (list.ok) {
            for (const o of (list.data.olympiads || [])) olympiadMap.set(o.id, o);
        }
    } catch (err) {
        if (preview && preview.status === 409) {
            // Preview для документа в обработке отдаёт 409 — это не ошибка, а
            // состояние «ещё нет результатов». Показываем баннер вместо падения.
            page.innerHTML = `
            <div class="max-w-content mx-auto pt-4 pb-12">
                <a href="#/admin/imports" class="text-sm text-ink-soft hover:text-ink">← К списку импортов</a>
                <div class="rounded bg-sand/50 px-6 py-4 mt-6 mb-8 text-sm leading-relaxed" role="status">
                    <p class="font-semibold text-ink mb-1">Импорт ещё обрабатывается</p>
                    <p class="text-ink-soft">Результаты появятся, когда обработка завершится. Обновите страницу позже.</p>
                </div>
                <a href="#/admin/imports" class="${UI.btn} ${UI.btnGhost}">К списку импортов</a>
            </div>
            ${importFabHtml('processing')}`;
            const fab = page.querySelector('[data-ri="addManualCandidate"]');
            if (fab) {
                fab.addEventListener('click', () =>
                    openAddImportCandidateModal(importId, () => renderImportReview(importId)));
            }
            return;
        }
        page.innerHTML = `
        <div class="max-w-content mx-auto pt-4 pb-12">
            ${alertHtml(String((err && err.message) || err), 'error')}
            <a href="#/admin/imports" class="${UI.btn} ${UI.btnGhost}">К списку импортов</a>
        </div>`;
        return;
    }

    const imp = data.import || {};
    const candidates = (data.candidates || []).slice();
    const warnings = imp.warnings || [];
    const state = imp.state || '';
    const reviewable = state === 'review';

    // «Порядок в документе» — по страницам и строкам: для порядковых номеров и
    // сортировки «по порядку».
    const docOrder = candidates.slice().sort(
        (a, b) => (a.page || 0) - (b.page || 0) || (a.row || 0) - (b.row || 0)
    );
    const ordinal = new Map(docOrder.map((c, i) => [c.name_norm, i + 1]));

    // Сценарий администратора: что подтверждено, что удалено, какие правки
    // названий/описаний/объединений сделаны.
    const excluded = new Set();      // удалённые строки: не применяются и не архивируются
    const confirmedKeys = new Set(); // подтверждённые кандидаты (по исходному name_norm)
    const edits = {};                // name_norm -> {name, description}
    const merges = {};               // name_norm -> id олимпиады для объединения
    let sortMode = 'order';          // order | confidence
    let query = '';

    // Сохранённый ранее выбор восстанавливается: подтверждённые/снятые строки
    // и правки переживают перезагрузку страницы (их хранит сам прогон).
    const storedSelection = data.selection || null;
    if (reviewable && storedSelection) {
        const skip = new Set(storedSelection.skip || []);
        for (const c of candidates) {
            if (!skip.has(c.name_norm)) confirmedKeys.add(c.name_norm);
        }
        const rename = storedSelection.rename || {};
        const descriptions = storedSelection.descriptions || {};
        const editedKeys = new Set([...Object.keys(rename), ...Object.keys(descriptions)]);
        for (const key of editedKeys) {
            edits[key] = {
                name: rename[key] || '',
                description: descriptions[key] || '',
            };
        }
        Object.assign(merges, storedSelection.merge || {});
    }

    const container = document.createElement('div');
    page.innerHTML = '';
    page.appendChild(container);

    function reviewed(c) { return !!c && c.confidence === 'review'; }
    function candidateById(key) { return candidates.find(c => c.name_norm === key) || null; }

    function confirmedCount() {
        return [...confirmedKeys].filter(key => !excluded.has(key)).length;
    }

    function unconfirmedTotal() {
        return candidates.filter(c => !confirmedKeys.has(c.name_norm) && !excluded.has(c.name_norm)).length;
    }

    function stats() {
        const lowConf = candidates.filter(c => reviewed(c)).length;
        let merged = 0;
        let fresh = 0;
        if (reviewable) {
            for (const c of candidates) {
                if (!confirmedKeys.has(c.name_norm) || excluded.has(c.name_norm)) continue;
                if (merges[c.name_norm] || (c.action === 'merge' && c.matched_olympiad_id)) merged++;
                else fresh++;
            }
        } else {
            // Для завершённых прогонов выбора уже нет (confirmedKeys пуст),
            // поэтому план читается из самих кандидатов, а не из подтверждений.
            for (const c of candidates) {
                if (c.action === 'merge' && c.matched_olympiad_id) merged++;
                else if (c.action === 'create') fresh++;
            }
        }
        return { total: candidates.length, merged, fresh, lowConf };
    }

    function matchesQuery(c) {
        if (!query) return true;
        const q = query.toLowerCase();
        return (c.name || '').toLowerCase().includes(q)
            || (c.description || '').toLowerCase().includes(q)
            || (c.issues || []).some(i => i.toLowerCase().includes(q));
    }

    function sortCandidates(list) {
        const orderPos = new Map(docOrder.map((c, i) => [c.name_norm, i]));
        return list.slice().sort((a, b) => {
            if (sortMode === 'confidence') {
                const ra = reviewed(a) ? 0 : 1;
                const rb = reviewed(b) ? 0 : 1;
                if (ra !== rb) return ra - rb;
                const sa = a.match_score || 0;
                const sb = b.match_score || 0;
                if (sa !== sb) return sa - sb;
            }
            return (orderPos.get(a.name_norm) ?? 9999) - (orderPos.get(b.name_norm) ?? 9999);
        });
    }

    function mergedNoteFor(c) {
        const key = c.name_norm;
        const mergedId = merges[key] || (c.action === 'merge' ? c.matched_olympiad_id : '');
        if (!mergedId || !olympiadMap.has(mergedId)) return '';
        return `<p class="mt-2 text-sm text-ink-soft">Объединится с: <span class="font-medium text-ink">${escHtml(olympiadMap.get(mergedId).name)}</span></p>`;
    }

    function issuesHtml(c) {
        if (!c.issues || !c.issues.length) return '';
        return `<p class="mt-2 text-sm text-ink-soft">${escHtml(c.issues.join(' · '))}</p>`;
    }

    function candidateCardHtml(c, confirmed) {
        const key = c.name_norm;
        const edit = edits[key] || {};
        const name = (edit.name || c.name || '').trim();
        const actionBadge = c.action === 'create'
            ? `<span class="${UI.badge} ${UI.badgeSuccess}">Новая</span>`
            : `<span class="${UI.badge} ${UI.badgeNeutral}">Объединение</span>`;
        const reviewBadge = reviewed(c)
            ? `<span class="${UI.badge} ${UI.badgeDanger}">Малодостоверная</span>`
            : `<span class="${UI.badge} ${UI.badgeSuccess}">Распознана</span>`;
        const confirmedBadge = confirmed
            ? `<span class="${UI.badge} ${UI.badgePending}">Подтверждена</span>` : '';
        const page = c.page ? `стр. ${c.page}` : '—';
        const ord = ordinal.get(key);
        return `
            <div class="${UI.card} px-6 py-5 ${confirmed ? 'border-2 border-sage' : ''}">
                <div class="flex flex-wrap items-start justify-between gap-4">
                    <div class="flex-1 min-w-0">
                        <div class="flex flex-wrap items-center gap-2.5">
                            ${actionBadge}${reviewBadge}${confirmedBadge}
                            <span class="text-xs text-ink-faint">${escHtml(page)} · № ${ord || '—'}</span>
                        </div>
                        <p class="mt-2.5 font-semibold text-ink leading-snug break-words">${escHtml(name)}</p>
                        ${mergedNoteFor(c)}
                        ${issuesHtml(c)}
                    </div>
                    <div class="flex flex-wrap gap-2 shrink-0">
                        ${confirmed
                            ? `<button type="button" data-ri="unconfirm" data-key="${escAttr(key)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Отменить подтверждение</button>`
                            : `<button type="button" data-ri="edit" data-key="${escAttr(key)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Изменить</button>
                               <button type="button" data-ri="delete" data-key="${escAttr(key)}" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}">Удалить</button>
                               <button type="button" data-ri="confirm" data-key="${escAttr(key)}" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Подтвердить</button>`}
                    </div>
                </div>
            </div>`;
    }

    function readonlyCandidateCardHtml(c) {
        const actionBadge = c.action === 'create'
            ? `<span class="${UI.badge} ${UI.badgeSuccess}">Новая</span>`
            : `<span class="${UI.badge} ${UI.badgeNeutral}">Объединение</span>`;
        const reviewBadge = reviewed(c)
            ? `<span class="${UI.badge} ${UI.badgeDanger}">Малодостоверная</span>`
            : `<span class="${UI.badge} ${UI.badgeSuccess}">Распознана</span>`;
        const page = c.page ? `стр. ${c.page}` : '—';
        const ord = ordinal.get(c.name_norm);
        return `
            <div class="${UI.card} px-6 py-5">
                <div class="flex flex-wrap items-start justify-between gap-4">
                    <div class="flex-1 min-w-0">
                        <div class="flex flex-wrap items-center gap-2.5">
                            ${actionBadge}${reviewBadge}
                            <span class="text-xs text-ink-faint">${escHtml(page)} · № ${ord || '—'}</span>
                        </div>
                        <p class="mt-2.5 font-semibold text-ink leading-snug break-words">${escHtml(c.name || '')}</p>
                        ${mergedNoteFor(c)}
                        ${issuesHtml(c)}
                    </div>
                </div>
            </div>`;
    }

    function mergeSelectHtml(selectedId) {
        const options = olympiadMap.size
            ? [...olympiadMap.values()]
                .map(o => `<option value="${escAttr(o.id)}" ${selectedId === o.id ? 'selected' : ''}>${escHtml(o.name)}</option>`)
                .join('')
            : '<option value="" disabled>— список олимпиад недоступен —</option>';
        return `
        <div class="${UI.field}">
            <label for="ri-merge" class="${UI.label}">Объединить с существующей олимпиадой в каталоге</label>
            <select id="ri-merge" name="merge" class="${UI.input}">
                <option value="">— не объединять, создать/обновить свою —</option>
                ${options}
            </select>
            <p class="mt-2 text-sm text-ink-soft leading-relaxed">
                При объединении данные выбранной олимпиады обновятся из перечня, дубликат создан не будет.
            </p>
        </div>`;
    }

    function applyCandidateEdit(overlay, key) {
        const fd = new FormData(overlay.querySelector('#ri-edit-form'));
        const name = (fd.get('name') || '').trim();
        const description = (fd.get('description') || '').trim();
        const mergedId = (fd.get('merge') || '').trim();
        if (name) edits[key] = { name, description };
        if (mergedId) merges[key] = mergedId; else delete merges[key];
    }

    function openCandidateEdit(key) {
        const c = candidateById(key);
        if (!c) return;
        let dirty = false;
        const currentEdit = edits[key] || {};
        const name = currentEdit.name || c.name || '';
        const description = typeof currentEdit.description === 'string' ? currentEdit.description : (c.description || '');
        const selectedMerge = merges[key] || (c.action === 'merge' ? c.matched_olympiad_id : '');
        const body = `
        <div id="modal-alert"></div>
        <form id="ri-edit-form">
            ${inputField({ id: 'ri-name', name: 'name', label: 'Название олимпиады', required: true, value: name })}
            ${textareaField({ id: 'ri-desc', name: 'description', label: 'Описание', value: description })}
            ${mergeSelectHtml(selectedMerge)}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-ri-close class="${UI.btn} ${UI.btnGhost}">Отменить</button>
                <button type="button" data-ri-save class="${UI.btn} ${UI.btnSecondary}">Сохранить</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Подтвердить</button>
            </div>
        </form>`;
        const { overlay, close } = openModal('Редактирование олимпиады', body, { size: 'lg', isDirty: () => dirty });
        ['input', 'change'].forEach(ev => overlay.addEventListener(ev, () => { dirty = true; }));
        // Явная «Отмена» — это осознанный отказ от правок, поэтому она закрывает
        // без дополнительного вопроса. Спрашивать нужно только про неявные пути:
        // Escape, крестик, клик по подложке.
        overlay.querySelector('[data-ri-close]').addEventListener('click', () => { dirty = false; close(); });
        overlay.querySelector('[data-ri-save]').addEventListener('click', () => {
            applyCandidateEdit(overlay, key);
            dirty = false;
            close();
            refresh();
            persistSelection();
        });
        overlay.querySelector('#ri-edit-form').addEventListener('submit', e => {
            e.preventDefault();
            applyCandidateEdit(overlay, key);
            dirty = false;
            close();
            confirmedKeys.add(key);
            excluded.delete(key);
            refresh();
            persistSelection();
        });
    }

    function stateBannerHtml() {
        if (reviewable) return '';
        if (state === 'approved') {
            const cr = imp.confirm || {};
            const created = (cr.created || []).length;
            const updated = (cr.updated || []).length;
            const archived = (cr.archived || []).length;
            return `<div class="rounded bg-sage/30 px-6 py-4 mb-8 text-sm leading-relaxed" role="status">
                <p class="font-semibold text-ink mb-1">Импорт уже применён</p>
                <p class="text-ink-soft">Создано: ${created}, обновлено: ${updated}, в архив: ${archived}.
                   Изменить исполнение можно только через загрузку актуального перечня.</p>
            </div>`;
        }
        if (state === 'rejected') {
            return `<div class="rounded bg-mist px-6 py-4 mb-8 text-sm leading-relaxed" role="status">
                <p class="font-semibold text-ink mb-1">Результаты импорта отклонены</p>
                <p class="text-ink-soft">Каталог не изменён. Отклонённый прогон перезапустить нельзя: загрузите документ заново, чтобы провести новый импорт.</p>
            </div>`;
        }
        if (state === 'failed') {
            return `<div class="rounded bg-sand/50 px-6 py-4 mb-8 text-sm leading-relaxed" role="status">
                <p class="font-semibold text-ink mb-1">Импорт завершился ошибкой</p>
                <p class="text-ink-soft">Каталог не изменён. Запустите импорт заново — обработка начинается с начала.</p>
            </div>`;
        }
        if (state === 'paused') {
            const stage = IMPORT_PROGRESS_LABELS[(imp.progress || {}).stage] || '';
            return `<div class="rounded bg-sand/50 px-6 py-4 mb-8 text-sm leading-relaxed" role="status">
                <p class="font-semibold text-ink mb-1">Импорт приостановлен</p>
                <p class="text-ink-soft">Обработка остановлена${stage ? ` на этапе «${escHtml(stage)}»` : ''}. Возобновить её можно кнопкой «Возобновить» в списке импортов: если документ уже распознан, повторного чтения не будет.</p>
            </div>`;
        }
        return `<div class="rounded bg-sand/50 px-6 py-4 mb-8 text-sm leading-relaxed" role="status">
            <p class="font-semibold text-ink mb-1">Импорт ещё обрабатывается</p>
            <p class="text-ink-soft">Результаты появятся, когда обработка завершится. Обновите страницу позже.</p>
        </div>`;
    }

    function actionsHtml() {
        const selected = confirmedCount();
        const unconfirmed = unconfirmedTotal();
        return `
        <div class="flex flex-wrap items-center justify-between gap-4 mb-8">
            <p class="text-sm text-ink-soft leading-relaxed">
                К применению: <span class="font-semibold text-ink">${selected}</span>
                <span class="text-ink-faint"> · неподтверждено: ${unconfirmed}</span>
            </p>
            <button type="button" data-ri="confirmAll" class="${UI.btn} ${UI.btnSecondary}" ${!reviewable || unconfirmed === 0 ? 'disabled' : ''}>
                Подтвердить все
            </button>
        </div>`;
    }

    function statsHtml() {
        const stat = (label, value) => `
        <div class="bg-white rounded px-5 py-4 shadow-elev-1">
            <p class="${UI.eyebrow} mb-1">${escHtml(label)}</p>
            <p class="text-3xl font-extrabold tabular-nums">${value}</p>
        </div>`;
        const grid = (cards) => `
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            ${cards}
        </div>`;
        if (state === 'failed') return '';
        if (state === 'approved') {
            // Счётчики применённого читаются из факта подтверждения
            // (imp.confirm): кандидаты approved-прогона — прошлый план, а
            // знают применённое только результаты confirm. Read-only: после
            // применения изменить их уже нельзя.
            const cr = imp.confirm || {};
            const len = (v) => (Array.isArray(v) ? v.length : 0);
            return grid(`
            ${stat('Создано', len(cr.created))}
            ${stat('Обновлено', len(cr.updated))}
            ${stat('В архив', len(cr.archived))}
            ${stat('Пропущено', len(cr.skipped))}`);
        }
        const s = stats();
        return grid(`
            ${stat('Распознано', s.total)}
            ${stat('Объединено', s.merged)}
            ${stat('Новых', s.fresh)}
            ${stat('Малодостоверных', s.lowConf)}`);
    }

    function searchCountsHtml() {
        if (!query) return '';
        const un = candidates.filter(c => !confirmedKeys.has(c.name_norm) && !excluded.has(c.name_norm)).filter(matchesQuery).length;
        const co = candidates.filter(c => confirmedKeys.has(c.name_norm) && !excluded.has(c.name_norm)).filter(matchesQuery).length;
        return `<p class="text-sm text-ink-faint mt-3">Совпадений: неподтверждённые — <span class="font-semibold text-ink">${un}</span>, подтверждённые — <span class="font-semibold text-ink">${co}</span></p>`;
    }

    function searchHtml() {
        const sortBtn = (act, label, active) =>
            `<button type="button" data-ri="${act}" class="${UI.btn} ${UI.btnSmall} ${active ? UI.btnPrimary : UI.btnGhost}">${label}</button>`;
        return `
        <div class="flex flex-col gap-3 mb-5">
            <div class="flex flex-wrap items-center gap-3">
                <div class="flex-1 min-w-64">
                    <input data-ri="search" type="search" value="${escAttr(query)}"
                           placeholder="Поиск по названию и замечаниям…"
                           class="${UI.input} !py-2.5 text-sm" aria-label="Поиск по олимпиадам">
                </div>
                <div class="flex flex-wrap gap-2 shrink-0">
                    ${sortBtn('sort-order', 'По порядку', sortMode === 'order')}
                    ${sortBtn('sort-confidence', 'По достоверности', sortMode === 'confidence')}
                </div>
            </div>
            <div id="ri-search-counts">${searchCountsHtml()}</div>
        </div>`;
    }

    function unconfirmedBodyHtml() {
        const cands = candidates.filter(c => !confirmedKeys.has(c.name_norm) && !excluded.has(c.name_norm)).filter(matchesQuery);
        const cards = sortCandidates(cands)
            .map(c => candidateCardHtml(c, false));
        const count = cands.length;
        return `
            <div class="flex items-center justify-between gap-3">
                <p class="${UI.eyebrow} mb-0">Неподтверждённые (${count})</p>
            </div>
            ${cards.length
                ? `<div class="space-y-3 mt-4">${cards.join('')}</div>`
                : `<div class="mt-4">${emptyHtml(
                    query ? 'Ничего не найдено' : 'Всё подтверждено',
                    query ? 'Измените поисковый запрос.' : 'Осталось нажать «Подтвердить импорт».'
                )}</div>`}`;
    }

    function confirmedBodyHtml() {
        const cands = candidates.filter(c => confirmedKeys.has(c.name_norm) && !excluded.has(c.name_norm)).filter(matchesQuery);
        const cards = sortCandidates(cands)
            .map(c => candidateCardHtml(c, true));
        const count = cands.length;
        return `
        <div class="rounded bg-sage/25 border border-sage px-6 py-6">
            <div class="flex items-center justify-between gap-3">
                <p class="${UI.eyebrow} mb-0">Подтверждённые (${count})</p>
            </div>
            ${cards.length
                ? `<div class="space-y-3 mt-4">${cards.join('')}</div>`
                : `<div class="mt-4">${emptyHtml(
                    query ? 'Ничего не найдено' : 'Пока ничего не подтверждено',
                    query ? 'Измените поисковый запрос.' : 'Подтверждайте олимпиады из списка выше.'
                )}</div>`}
        </div>`;
    }

    function staticHtml() {
        return `
        <a href="#/admin/imports" class="text-sm text-ink-soft hover:text-ink">← К списку импортов</a>
        <div class="flex flex-wrap items-start justify-between gap-6 mt-4 mb-8">
            <div class="flex-1 min-w-0">
                <p class="${UI.eyebrow} mb-2">Импорт РСОШ</p>
                <h1 class="text-2xl md:text-3xl font-extrabold tracking-tight break-words">${escHtml(imp.name || 'Документ РСОШ')}</h1>
                <p class="mt-2 text-sm text-ink-soft">
                    Состояние: <span class="font-semibold text-ink">${escHtml(IMPORT_STATE_LABELS[state] || state || '—')}</span>
                    ${imp.status ? ` · статус документа: ${escHtml(imp.status)}` : ''}
                </p>
            </div>
            <div class="flex flex-wrap gap-3 shrink-0">
                <a href="${escAttr(api.docFileUrl(importId))}" target="_blank" rel="noopener noreferrer" class="${UI.btn} ${UI.btnGhost}">Скачать документ</a>
                <button type="button" data-ri="reject" class="${UI.btn} ${UI.btnDanger}" ${!reviewable ? 'disabled' : ''}>Отклонить</button>
                <button type="button" data-ri="apply" class="${UI.btn} ${UI.btnPrimary}" ${!reviewable || confirmedCount() === 0 ? 'disabled' : ''}>Подтвердить импорт</button>
            </div>
        </div>
        ${stateBannerHtml()}
        ${imp.error ? alertHtml(imp.error, 'error') : ''}
    ${reviewable ? `
        <p class="text-sm text-ink-faint mb-8 leading-relaxed">
            В каталог ничего не записано, пока вы не нажмёте «Подтвердить импорт». Удалённая
            строка не создаётся и не архивируется; подтверждённая олимпиада создаётся
            или обновляется вместе с её данными из перечня.
        </p>
        ${importNoticesHtml(warnings)}
        ${actionsHtml()}
        ${statsHtml()}
        ${searchHtml()}
        <div id="ri-unconfirmed">${unconfirmedBodyHtml()}</div>
        <div id="ri-confirmed" class="mt-10">${confirmedBodyHtml()}</div>` : `
        ${importNoticesHtml(warnings)}
        ${statsHtml()}
        <p class="${UI.eyebrow} mb-2 mt-10">Результаты импорта</p>
        ${candidates.length
            ? `<div class="space-y-3 mt-4">${candidates.map(c => readonlyCandidateCardHtml(c)).join('')}</div>`
            : `<div class="mt-4">${emptyHtml('Результатов нет', 'Для этого прогона кандидаты не сохранены.')}</div>`}`}
        ${importFabHtml(state)}`;
    }

    function refresh() {
        container.innerHTML = staticHtml();
    }

    function refreshLists() {
        const countsEl = container.querySelector('#ri-search-counts');
        if (countsEl) countsEl.innerHTML = searchCountsHtml();
        const un = container.querySelector('#ri-unconfirmed');
        if (un) un.innerHTML = unconfirmedBodyHtml();
        const co = container.querySelector('#ri-confirmed');
        if (co) co.innerHTML = confirmedBodyHtml();
    }

    function confirmAll() {
        for (const c of candidates) {
            if (!excluded.has(c.name_norm)) confirmedKeys.add(c.name_norm);
        }
    }

    function buildPayload() {
        const skip = [];
        const rename = {};
        const descriptions = {};
        const merge = {};
        for (const c of candidates) {
            const key = c.name_norm;
            if (!confirmedKeys.has(key)) skip.push(key);
            const edit = edits[key];
            if (edit) {
                if (edit.name && edit.name !== c.name) rename[key] = edit.name;
                const orig = c.description || '';
                if (typeof edit.description === 'string' && edit.description.trim() !== orig.trim()) {
                    descriptions[key] = edit.description.trim();
                }
            }
            if (merges[key]) merge[key] = merges[key];
        }
        return {
            skip,
            rename,
            descriptions,
            merge,
            archive_missing: true,
        };
    }

    // Сохранение выбора на сервере (без спешки): хранится вместе с прогоном,
    // поэтому перезагрузка страницы не теряет решения администратора.
    let saveTimer = null;
    function persistSelection() {
        if (!reviewable) return;
        clearTimeout(saveTimer);
        saveTimer = setTimeout(() => {
            void api.saveImportSelection(importId, buildPayload());
        }, 400);
    }

    async function doApply() {
        const btn = container.querySelector('[data-ri="apply"]');
        if (btn) { btn.disabled = true; btn.textContent = 'Применяем…'; }
        const payload = buildPayload();
        const res = await api.confirmImport(importId, payload);
        if (!res.ok) {
            if (btn) { btn.disabled = false; btn.textContent = 'Подтвердить импорт'; }
            if (res.status === 409) {
                // Каталог уже соответствует более новому перечню либо этот
                // перечень уже применён (см. showOutdatedImportNotice).
                showOutdatedImportNotice(errorText(res));
                return;
            }
            showToast(errorText(res), 'error');
            return;
        }
        const result = res.data.result || {};
        showToast(
            `Импорт применён: создано ${(result.created || []).length}, обновлено ${(result.updated || []).length}, в архив ${(result.archived || []).length}`,
            'success', 6000);
        if (result.archive_skipped_reason) {
            showToast(`Архивирование пропущено: ${result.archive_skipped_reason}`, 'error', 10000);
        }
        navigate('#/admin/imports');
    }

    async function doReject() {
        const btn = container.querySelector('[data-ri="reject"]');
        if (btn) { btn.disabled = true; btn.textContent = 'Отклоняем…'; }
        const res = await api.rejectImport(importId);
        if (btn) { btn.disabled = false; btn.textContent = 'Отклонить'; }
        if (!res.ok) {
            showToast(errorText(res), 'error');
            return;
        }
        showToast('Результаты импорта отклонены', 'success');
        navigate('#/admin/imports');
    }

    refresh();

    container.addEventListener('click', e => {
        const btn = e.target.closest('[data-ri]');
        if (!btn || btn.disabled) return;
        const act = btn.dataset.ri;
        const key = btn.dataset.key;

        if (act === 'confirm') { confirmedKeys.add(key); excluded.delete(key); refresh(); persistSelection(); }
        else if (act === 'unconfirm') { confirmedKeys.delete(key); refresh(); persistSelection(); }
        else if (act === 'delete') { confirmedKeys.delete(key); excluded.add(key); refresh(); persistSelection(); }
        else if (act === 'edit') { openCandidateEdit(key); }
        else if (act === 'confirmAll') { confirmAll(); refresh(); persistSelection(); }
        else if (act === 'sort-order') { sortMode = 'order'; refresh(); }
        else if (act === 'sort-confidence') { sortMode = 'confidence'; refresh(); }
        else if (act === 'apply') { void doApply(); }
        else if (act === 'reject') { void doReject(); }
        else if (act === 'addManualCandidate') {
            openAddImportCandidateModal(importId, () => renderImportReview(importId));
        }
    });

    container.addEventListener('input', e => {
        const input = e.target.closest('[data-ri="search"]');
        if (input) {
            query = input.value;
            refreshLists();
        }
    });
}

/* ------------------- Просмотр и подтверждение приказа --------------------- */

/**
 * Меню приказа университета.
 *
 * Отличия от меню перечня РСОШ принципиальные, а не косметические. Приказ не
 * создаёт олимпиад: строки либо находят пару в каталоге, либо остаются
 * несопоставленными и связываются вручную. Поэтому здесь нет правки названий
 * и объединений, а есть только выбор: связать (и с чем) или пропустить.
 * Подтверждение заводит заявки БВИ (PENDING) — их отдельно проверяет модератор.
 */
async function renderUniversityReview(importId) {
    const page = document.getElementById('page');
    page.innerHTML = `<section class="pt-4 pb-32">${loadingHtml('Загружаем приказ…')}</section>`;

    let data = null;
    let preview = null;
    const olympiadMap = new Map();
    const universities = [];
    try {
        preview = await api.universityImportPreview(importId);
        if (!preview.ok) throw new Error(errorText(preview));
        data = preview.data;
        const [list, unis] = await Promise.all([
            api.adminOlympiads(),
            api.listUniversities(),
        ]);
        if (list.ok) for (const o of (list.data.olympiads || [])) olympiadMap.set(o.id, o);
        if (unis.ok) universities.push(...(unis.data.universities || []));
    } catch (err) {
        if (preview && preview.status === 409) {
            page.innerHTML = `
            <div class="max-w-content mx-auto pt-4 pb-12">
                <a href="#/admin/orders" class="text-sm text-ink-soft hover:text-ink">← К списку приказов</a>
                <div class="rounded bg-sand/50 px-6 py-4 mt-6 mb-8 text-sm leading-relaxed" role="status">
                    <p class="font-semibold text-ink mb-1">Импорт ещё обрабатывается</p>
                    <p class="text-ink-soft">Строки приказа появятся, когда обработка завершится. Обновите страницу позже.</p>
                </div>
                <a href="#/admin/orders" class="${UI.btn} ${UI.btnGhost}">К списку приказов</a>
            </div>`;
            return;
        }
        page.innerHTML = `
        <div class="max-w-content mx-auto pt-4 pb-12">
            ${alertHtml(String((err && err.message) || err), 'error')}
            <a href="#/admin/orders" class="${UI.btn} ${UI.btnGhost}">К списку приказов</a>
        </div>`;
        return;
    }

    const container = page.querySelector('section') || page;
    const imp = data.import || {};
    const candidates = (data.candidates || []).slice();
    const recognized = data.university || {};
    const warnings = imp.warnings || [];
    const state = imp.state || '';
    const reviewable = state === 'review';

    // Решения администратора. Ключ строки — её нормализованное название, как и
    // в ответе сервера: так выбор переживает и сохранение, и перезагрузку.
    const skip = new Set((data.selection || {}).skip || []);
    const links = Object.assign({}, (data.selection || {}).links || {});
    let universityId = (data.selection || {}).university_id
        || recognized.id || '';

    // Сохранённые по умолчанию сопоставленные строки не входят в skip.
    for (const c of candidates) {
        if (!c.olympiad_id) continue;
        if (skip.has(c.name_norm)) continue;
        if (!links[c.name_norm]) links[c.name_norm] = c.olympiad_id;
    }

    let query = '';
    let linkedOnly = false;

    const olympiadOptions = (selected) => {
        const options = [...olympiadMap.values()]
            .sort((a, b) => a.name.localeCompare(b.name, 'ru'));
        return `<option value="">— не выбрана —</option>`
            + options.map(o => `<option value="${escAttr(o.id)}" ${o.id === selected ? 'selected' : ''}>${escHtml(o.name)}</option>`).join('');
    };

    function effectiveLink(c) {
        return links[c.name_norm] || '';
    }

    function rowHtml(c) {
        const chosen = effectiveLink(c);
        const skipped = skip.has(c.name_norm);
        const matched = !!c.olympiad_id;
        const meta = c.meta || {};
        const badge = matched
            ? `<span class="inline-flex items-center rounded bg-sage/30 text-ink px-2 py-0.5 text-xs font-semibold">сопоставлено · ${(c.match_score != null ? Number(c.match_score).toFixed(2) : '—')}</span>`
            : `<span class="inline-flex items-center rounded bg-sand/60 text-ink px-2 py-0.5 text-xs font-semibold">вручную</span>`;
        return `
        <div class="${UI.card} px-6 py-5 ${skipped ? 'opacity-60' : ''}">
            <div class="flex flex-col lg:flex-row lg:items-start gap-4">
                <div class="flex-1 min-w-0">
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="font-semibold text-ink">${escHtml(c.olympiad_name || c.name || '')}</span>
                        ${badge}
                    </div>
                    <p class="mt-2 text-sm text-ink-soft">
                        ${meta.direction ? `Направление: ${escHtml(meta.direction)} · ` : ''}
                        ${meta.profile ? `Профиль: ${escHtml(meta.profile)} · ` : ''}
                        ${meta.level ? `Уровень: ${escHtml(meta.level)} · ` : ''}
                        ${meta.diploma ? `Диплом: ${escHtml(meta.diploma)}` : ''}
                    </p>
                    ${reviewable ? `
                    <label class="mt-3 inline-flex items-center gap-2 text-sm text-ink-soft">
                        <input type="checkbox" data-ri="skip" data-key="${escAttr(c.name_norm)}" ${skipped ? 'checked' : ''}
                               class="rounded border-ink-faint">
                        Пропустить строку
                    </label>` : ''}
                </div>
                <div class="lg:w-96 shrink-0">
                    ${reviewable
                        ? `<label class="block text-xs font-semibold text-ink-faint mb-1">Связать с олимпиадой каталога</label>
                           <select data-ri="link" data-key="${escAttr(c.name_norm)}" ${skipped ? 'disabled' : ''}
                                   class="${UI.input} !py-2 text-sm w-full">${olympiadOptions(chosen)}</select>`
                        : `<p class="text-sm text-ink-soft">${chosen ? escHtml((olympiadMap.get(chosen) || {}).name || chosen) : '—'}</p>`}
                </div>
            </div>
        </div>`;
    }

    function matchesQuery(c) {
        if (!query) return true;
        const q = query.toLowerCase();
        const meta = c.meta || {};
        return (c.olympiad_name || '').toLowerCase().includes(q)
            || (c.name || '').toLowerCase().includes(q)
            || (meta.direction || '').toLowerCase().includes(q)
            || (meta.profile || '').toLowerCase().includes(q);
    }

    function visibleRows() {
        return candidates.filter(matchesQuery).filter(c => !linkedOnly || effectiveLink(c));
    }

    function counts() {
        const total = candidates.length;
        let linked = 0;
        for (const c of candidates) if (effectiveLink(c) && !skip.has(c.name_norm)) linked += 1;
        return { total, linked, unmatched: total - linked };
    }

    function refresh() {
        const c = counts();
        const rows = visibleRows().map(rowHtml).join('');
        const uniName = recognized.name || '';
        container.innerHTML = `
        <a href="#/admin/orders" class="text-sm text-ink-soft hover:text-ink">← К списку приказов</a>
        <div class="flex flex-wrap items-start justify-between gap-6 mt-4 mb-8">
            <div>
                <h1 class="text-3xl md:text-4xl font-extrabold tracking-tight">${escHtml(imp.name || 'Приказ вуза')}</h1>
                <p class="mt-3 text-sm text-ink-soft">
                    Состояние: <span class="font-semibold text-ink">${escHtml(IMPORT_STATE_LABELS[state] || state || '—')}</span>
                    · строк: ${c.total} · связано: ${c.linked} · без пары: ${c.unmatched}
                </p>
            </div>
            <div class="flex flex-wrap gap-3">
                <a href="${escAttr(api.docFileUrl(importId))}" target="_blank" rel="noopener noreferrer" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Скачать документ</a>
                ${reviewable ? `
                <button data-ri="apply" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Подтвердить импорт</button>
                <button data-ri="reject" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Отклонить</button>` : ''}
            </div>
        </div>

        <div class="rounded bg-mist/60 px-6 py-5 mb-8">
            <p class="${UI.eyebrow} mb-2">Вуз из шапки документа</p>
            ${reviewable ? `
            <select data-ri="university" class="${UI.input} !py-2.5 text-sm max-w-lg">
                <option value="">— вуз не распознан, выберите вручную —</option>
                ${universities.map(u => `<option value="${escAttr(u.id)}" ${u.id === universityId ? 'selected' : ''}>${escHtml(u.name)}</option>`).join('')}
            </select>` : `
            <p class="text-ink">${uniName ? escHtml(uniName) : '— вуз не распознан —'}</p>`}
            ${!universityId ? `<p class="mt-2 text-sm text-crimson">Без вуза подтвердить импорт нельзя: выберите университет.</p>` : ''}
        </div>

        ${importNoticesHtml(warnings)}

        <div class="flex flex-wrap items-center gap-3 mb-6">
            <div class="flex-1 min-w-64">
                <input data-ri="search" type="search" value="${escAttr(query)}"
                       placeholder="Поиск по названию, направлению, профилю…"
                       class="${UI.input} !py-2.5 text-sm" aria-label="Поиск по строкам приказа">
            </div>
            <label class="inline-flex items-center gap-2 text-sm text-ink-soft">
                <input type="checkbox" data-ri="linkedOnly" ${linkedOnly ? 'checked' : ''} class="rounded border-ink-faint">
                Только связанные
            </label>
        </div>

        ${rows
            ? `<div class="space-y-3">${rows}</div>`
            : emptyHtml(query ? 'Ничего не найдено' : 'Строк нет',
                query ? 'Измените поисковый запрос.' : 'Документ не дал ни одной строки приказа.')}`;
    }

    function buildPayload() {
        const skipList = [];
        const linkMap = {};
        for (const c of candidates) {
            if (skip.has(c.name_norm)) { skipList.push(c.name_norm); continue; }
            const chosen = effectiveLink(c);
            if (chosen) linkMap[c.name_norm] = chosen;
        }
        return { skip: skipList, links: linkMap, university_id: universityId || null };
    }

    let saveTimer = null;
    function persistSelection() {
        if (!reviewable) return;
        clearTimeout(saveTimer);
        saveTimer = setTimeout(() => {
            void api.saveUniversitySelection(importId, buildPayload());
        }, 400);
    }

    async function doApply() {
        if (!universityId) { showToast('Выберите вуз', 'error'); return; }
        const btn = container.querySelector('[data-ri="apply"]');
        if (btn) { btn.disabled = true; btn.textContent = 'Применяем…'; }
        const res = await api.confirmUniversityImport(importId, buildPayload());
        if (!res.ok) {
            if (btn) { btn.disabled = false; btn.textContent = 'Подтвердить импорт'; }
            showToast(errorText(res), 'error');
            return;
        }
        const result = res.data.result || {};
        showToast(
            `Импорт применён: связей создано ${result.linked || 0}, обновлено ${result.updated || 0}, без пары ${result.unmatched || 0}`,
            'success', 6000);
        navigate('#/admin/orders');
    }

    async function doReject() {
        const btn = container.querySelector('[data-ri="reject"]');
        if (btn) { btn.disabled = true; btn.textContent = 'Отклоняем…'; }
        const res = await api.rejectUniversityImport(importId);
        if (btn) { btn.disabled = false; btn.textContent = 'Отклонить'; }
        if (!res.ok) { showToast(errorText(res), 'error'); return; }
        showToast('Результаты импорта отклонены', 'success');
        navigate('#/admin/orders');
    }

    refresh();

    container.addEventListener('change', e => {
        const el = e.target.closest('[data-ri]');
        if (!el) return;
        const act = el.dataset.ri;
        const key = el.dataset.key;
        if (act === 'skip') {
            if (el.checked) { skip.add(key); delete links[key]; }
            else skip.delete(key);
            refresh(); persistSelection();
        } else if (act === 'link') {
            if (el.value) { links[key] = el.value; skip.delete(key); }
            else delete links[key];
            refresh(); persistSelection();
        } else if (act === 'university') {
            universityId = el.value;
            refresh(); persistSelection();
        } else if (act === 'linkedOnly') {
            linkedOnly = el.checked;
            refresh();
        }
    });

    container.addEventListener('click', e => {
        const btn = e.target.closest('[data-ri]');
        if (!btn || btn.disabled) return;
        if (btn.dataset.ri === 'apply') { void doApply(); }
        else if (btn.dataset.ri === 'reject') { void doReject(); }
    });

    container.addEventListener('input', e => {
        const input = e.target.closest('[data-ri="search"]');
        if (input) {
            query = input.value;
            refresh();
            const again = container.querySelector('[data-ri="search"]');
            if (again) { again.focus(); again.setSelectionRange(query.length, query.length); }
        }
    });
}
