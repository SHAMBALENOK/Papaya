/* ==========================================================================
 * pages/admin.js — панель администратора Papaya.
 *
 *   #/admin/users       пользователи: роли, блокировки, привязка к университету
 *   #/admin/olympiads   каталог олимпиад: правка, архив, ручное создание
 *   #/admin/universities каталог университетов
 *   #/admin/requests    запросы представителей на отсутствующие сущности
 *   #/admin/imports     документы РСОШ: загрузка, импорт, preview, подтверждение
 * ========================================================================== */

/* Группы администрирования: верхний уровень — смысловые блоки, внутри —
   подразделы. Ключи вкладок и маршруты не меняются, поэтому старые прямые
   ссылки (`#/admin/seasons`, `#/admin/benefits` и т.д.) продолжают работать. */
const ADMIN_GROUPS = [
    {
        key: 'dashboard', label: 'Сводка',
        tabs: [{ key: 'dashboard', label: 'Сводка' }],
    },
    {
        key: 'users', label: 'Пользователи',
        tabs: [
            { key: 'users', label: 'Пользователи' },
            { key: 'adminapps', label: 'Заявки администраторов' },
        ],
    },
    {
        key: 'olympiads', label: 'Олимпиады',
        tabs: [
            { key: 'olympiads', label: 'Олимпиады' },
            { key: 'seasons', label: 'Сезоны' },
            { key: 'requests', label: 'Запросы в каталог' },
        ],
    },
    {
        key: 'universities', label: 'Университеты',
        tabs: [
            { key: 'universities', label: 'Университеты' },
            { key: 'benefits', label: 'Льготы' },
            { key: 'programs', label: 'Программы' },
            { key: 'repapps', label: 'Заявки представителей' },
        ],
    },
    {
        key: 'data', label: 'Данные',
        tabs: [
            { key: 'docs', label: 'Документы' },
            { key: 'imports', label: 'Импорт РСОШ' },
        ],
    },
    {
        key: 'audit', label: 'Аудит',
        tabs: [{ key: 'audit', label: 'Аудит' }],
    },
];

const ADMIN_TABS = ADMIN_GROUPS.flatMap(group =>
    group.tabs.map(tab => ({ ...tab, href: `#/admin/${tab.key}` })));
const ADMIN_TAB_KEYS = new Set(ADMIN_TABS.map(tab => tab.key));

/** Размер страницы списков пользователей и олимпиад. */
const ADMIN_LIST_PAGE_SIZE = 50;

/** Состояние постраничных списков панели: строки, всего и активный поиск. */
let adminUsersState = { users: [], total: 0, search: '', universities: [] };
let adminOlympiadsState = { olympiads: [], total: 0, search: '' };
let adminBenefitsState = {
    rules: [], total: 0, status: '', search: '', needsReview: false,
    universities: [], olympiads: [],
};
let adminSeasonsState = { seasons: [], total: 0, olympiads: [] };
let adminProgramsState = { programs: [], total: 0, universities: [] };
let adminDocsState = { docs: [], total: 0, search: '', type: '', status: '' };
let adminRequestsState = { requests: [], total: 0, status: '' };
let adminAuditState = { logs: [], total: 0, entityType: '', action: '', updatedAt: null };
let adminRepAppsStatus = '';
let adminAdminAppsStatus = '';

function renderAdmin(initialTab) {
    const page = document.getElementById('page');
    if (!store.isAdmin()) {
        renderForbidden('Администрирование Papaya', 'Этот раздел доступен только администратору платформы.');
        return;
    }
    const tab = ADMIN_TAB_KEYS.has(initialTab) ? initialTab : 'users';
    const activeGroup = ADMIN_GROUPS.find(group =>
        group.tabs.some(item => item.key === tab)) || ADMIN_GROUPS[1];
    const groupNav = ADMIN_GROUPS.map(group => {
        const active = group.key === activeGroup.key;
        const href = `#/admin/${group.tabs[0].key}`;
        return `<a href="${href}"
                   class="px-4 py-2.5 rounded text-sm font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand ${
                       active
                           ? 'bg-white text-brand-strong shadow-elev-1'
                           : 'text-ink-soft hover:text-ink hover:bg-white'
                   }" aria-current="${active ? 'page' : 'false'}">${group.label}</a>`;
    }).join('');
    const subNav = activeGroup.tabs.length > 1
        ? `<nav class="flex flex-wrap gap-1.5 mb-12" aria-label="Подразделы: ${activeGroup.label}">
               ${activeGroup.tabs.map(item => {
                   const active = item.key === tab;
                   return `<a href="#/admin/${item.key}"
                              class="px-3.5 py-2 rounded text-sm font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand ${
                                  active
                                      ? 'bg-brand text-white'
                                      : 'text-ink-soft hover:text-ink hover:bg-mist'
                              }" aria-current="${active ? 'page' : 'false'}">${item.label}</a>`;
               }).join('')}
           </nav>`
        : '<div class="mb-12"></div>';

    page.innerHTML = `
    <section class="pt-2 pb-10 md:pb-12">
        <p class="${UI.eyebrow}">Администрирование</p>
        <h1 class="mt-3 text-3xl md:text-4xl font-extrabold tracking-tight leading-[1.1]">Панель администратора</h1>
        <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Каталог олимпиад и университетов, модерация правил льгот, запросы
            представителей и импорт документов РСОШ.
        </p>
    </section>

    <nav class="flex flex-wrap gap-1 bg-mist rounded p-2 mb-4" aria-label="Разделы администрирования">
        ${groupNav}
    </nav>
    ${subNav}

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
        dashboard: async () => (await api.adminStats()).data || {},
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
        adminapps: async () => {
            const res = await api.listAdminApplications(adminAdminAppsStatus || undefined);
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
        universities: async () => (await api.adminUniversities({ include_archived: true })).data.universities || [],
        benefits: async () => {
            const [res, universities, olympiads] = await Promise.all([
                api.adminBenefits({ limit: ADMIN_LIST_PAGE_SIZE, offset: 0 }),
                api.adminUniversities({ include_archived: true, limit: 200 }).catch(() => ({ data: {} })),
                api.adminOlympiads({ limit: 200 }).catch(() => ({ data: {} })),
            ]);
            const rules = res.data.rules || [];
            adminBenefitsState = {
                rules,
                total: res.data.total != null ? res.data.total : rules.length,
                status: '',
                search: '',
                needsReview: false,
                universities: (universities.data && universities.data.universities) || [],
                olympiads: (olympiads.data && olympiads.data.olympiads) || [],
            };
            return rules;
        },
        seasons: async () => {
            const [res, olympiads] = await Promise.all([
                api.adminSeasons({ include_archived: true }),
                api.adminOlympiads({ limit: 200 }).catch(() => ({ data: {} })),
            ]);
            const seasons = res.data.seasons || [];
            adminSeasonsState = {
                seasons,
                total: res.data.total != null ? res.data.total : seasons.length,
                olympiads: (olympiads.data && olympiads.data.olympiads) || [],
            };
            return seasons;
        },
        programs: async () => {
            const [res, universities] = await Promise.all([
                api.adminPrograms({ include_archived: true }),
                api.adminUniversities({ include_archived: true, limit: 200 }).catch(() => ({ data: {} })),
            ]);
            const programs = res.data.programs || [];
            adminProgramsState = {
                programs,
                total: res.data.total != null ? res.data.total : programs.length,
                universities: (universities.data && universities.data.universities) || [],
            };
            return programs;
        },
        docs: async () => {
            const res = await api.adminDocs({ limit: ADMIN_LIST_PAGE_SIZE, offset: 0 });
            const docs = res.data.docs || [];
            adminDocsState = {
                docs,
                total: res.data.total != null ? res.data.total : docs.length,
                search: '',
                type: '',
                status: '',
            };
            return docs;
        },
        requests: async () => {
            const res = await api.adminEntityRequests({ limit: ADMIN_LIST_PAGE_SIZE, offset: 0 });
            const requests = res.data.requests || [];
            adminRequestsState = {
                requests,
                total: res.data.total != null ? res.data.total : requests.length,
                status: '',
            };
            return requests;
        },
        imports: async () => {
            // Документы РСОШ — рабочая вкладка; журнал прогонов идёт отдельной
            // секцией: он отвечает на вопрос «что и когда запускали».
            const [docs, jobs] = await Promise.all([
                api.listImports().catch(() => ({ data: {} })),
                api.adminImportJobs({ limit: 20 }).catch(() => ({ data: {} })),
            ]);
            return {
                docs: (docs.data && docs.data.imports) || [],
                jobs: (jobs.data && jobs.data.imports) || [],
            };
        },
        repapps: async () => (await api.listRepresentativeApplications(adminRepAppsStatus || undefined)).data.applications || [],
        audit: async () => {
            const res = await api.listAudit({ limit: 50, offset: 0 });
            const logs = res.data.logs || [];
            adminAuditState = {
                logs,
                total: res.data.total != null ? res.data.total : logs.length,
                entityType: '',
                action: '',
                updatedAt: new Date(),
            };
            return logs;
        },
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
        dashboard: () => adminDashboardHtml(data),
        adminapps: () => adminAdminAppsHtml(data),
        benefits: () => adminBenefitsHtml(),
        olympiads: () => adminOlympiadsHtml(),
        universities: () => adminUniversitiesHtml(data),
        seasons: () => adminSeasonsHtml(),
        programs: () => adminProgramsHtml(),
        docs: () => adminDocsHtml(),
        requests: () => adminRequestsHtml(),
        imports: () => adminImportsHtml(data),
        repapps: () => adminRepAppsHtml(data),
        audit: () => adminAuditHtml(data),
    };
    box.innerHTML = renderers[tab]();
    // Аудит обновляется сам, пока вкладка открыта: иначе действие,
    // выполненное в соседней вкладке, выглядело бы потерянным до перезагрузки.
    if (window.adminAuditTimer) clearInterval(window.adminAuditTimer);
    if (tab === 'audit') {
        // 5 секунд — компромисс: новое действие появляется почти сразу, но
        // скрытая вкладка не тратит запросы впустую.
        window.adminAuditTimer = setInterval(() => {
            if (document.visibilityState !== 'visible') return;
            if (currentAdminTab() !== 'audit') return;
            if (document.getElementById('admin-audit-entity')) filterAudit();
        }, 5000);
    }
}

/* Действия, которые открывают модалку или сами показывают результат. */
const ADMIN_SIDE_EFFECT_ACTIONS = new Set([
    'newUniversity', 'editUniversity', 'newOlympiad', 'editOlympiad',
    'newImport', 'runImport', 'previewImport',
    'pauseImport', 'resumeImport',
    'newSeason', 'editSeason', 'seasonProfiles',
    'newBenefit', 'editBenefit',
    'newProgram', 'editProgram',
    'searchBenefits', 'loadMoreBenefits',
    'loadMoreUsers', 'searchUsers', 'loadMoreOlympiads', 'searchOlympiads',
    'searchDocs', 'loadMoreDocs', 'importJobRecords',
    'searchRequests', 'loadMoreRequests',
    'loadMoreAudit',
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

    if (act === 'rejectBenefit') {
        btn.disabled = false;
        openRejectBenefitModal(id, () => reloadAdmin());
        return;
    }

    if (act === 'rejectRepApp') {
        btn.disabled = false;
        openRejectRepAppModal(id, () => reloadAdmin());
        return;
    }

    if (act === 'rejectAdminApp') {
        btn.disabled = false;
        openRejectAdminAppModal(id, () => reloadAdmin());
        return;
    }

    if (act === 'refreshAdminApps') {
        btn.disabled = false;
        await loadAdminTab('adminapps');
        return;
    }

    if (act === 'rejectRequest') {
        btn.disabled = false;
        openRejectRequestModal(id, () => reloadAdmin());
        return;
    }

    if (act === 'newBenefit') {
        btn.disabled = false;
        openBenefitFormModal(null, null, [], () => reloadAdmin(), { admin: true });
        return;
    }

    if (act === 'editBenefit') {
        btn.disabled = false;
        const rule = adminBenefitsState.rules.find(item => String(item.id) === String(id)) || null;
        openBenefitFormModal(null, rule, [], () => reloadAdmin(), { admin: true });
        return;
    }

    if (act === 'refreshAudit') {
        btn.disabled = true;
        await filterAudit();
        return;
    }

    const calls = {
        ban: () => api.banUser(id),
        unban: () => api.unbanUser(id),
        archive: () => api.archiveOlympiad(id, true),
        restore: () => api.archiveOlympiad(id, false),
        approveRequest: () => api.approveEntityRequest(id),
        newUniversity: () => openUniversityFormModal(null, () => reloadAdmin()),
        editUniversity: () => editUniversityAction(id),
        archiveUniversity: () => api.archiveUniversity(id, true),
        restoreUniversity: () => api.archiveUniversity(id, false),
        archiveProgram: () => api.archiveProgram(id, true),
        restoreProgram: () => api.archiveProgram(id, false),
        archiveSeason: () => api.archiveSeason(id, true),
        restoreSeason: () => api.archiveSeason(id, false),
        newSeason: () => openSeasonFormModal(null, () => reloadAdmin()),
        editSeason: () => openSeasonFormModal(
            adminSeasonsState.seasons.find(item => String(item.id) === String(id)) || null,
            () => reloadAdmin()
        ),
        seasonProfiles: () => openSeasonProfilesModal(id),
        newProgram: () => openAdminProgramFormModal(null, () => reloadAdmin()),
        editProgram: () => openAdminProgramFormModal(
            adminProgramsState.programs.find(item => String(item.id) === String(id)) || null,
            () => reloadAdmin()
        ),
        verifyBenefit: () => api.verifyBenefit(id),
        newOlympiad: () => openOlympiadFormModal(null, () => reloadAdmin()),
        editOlympiad: () => editOlympiadAction(id),
        newImport: () => openUploadModal(),
        runImport: () => runImportAction(id, btn),
        previewImport: () => navigate(`#/admin/imports/${id}`),
        pauseImport: () => pauseImportAction(id, btn),
        resumeImport: () => resumeImportAction(id, btn),
        loadMoreUsers: () => loadMoreUsers(),
        searchUsers: () => searchUsers(),
        loadMoreOlympiads: () => loadMoreOlympiads(),
        searchOlympiads: () => searchOlympiads(),
        searchBenefits: () => searchBenefits(),
        loadMoreBenefits: () => loadMoreBenefits(),
        searchDocs: () => searchDocs(),
        loadMoreDocs: () => loadMoreDocs(),
        searchRequests: () => searchRequests(),
        loadMoreRequests: () => loadMoreRequests(),
        importJobRecords: () => openImportJobModal(id),
        loadMoreAudit: () => loadMoreAudit(),
        approveRepApp: () => api.reviewRepresentativeApplication(id, { status: 'approved' }),
        approveAdminApp: () => api.approveAdminApplication(id),
    };

    const messages = {
        ban: 'Пользователь заблокирован',
        unban: 'Пользователь разблокирован',
        archive: 'Олимпиада исключена из актуального каталога',
        restore: 'Олимпиада возвращена в актуальный каталог',
        approveRequest: 'Запрос одобрен, сущность создана',
        archiveUniversity: 'Университет архивирован',
        restoreUniversity: 'Университет возвращён из архива',
        archiveProgram: 'Программа архивирована',
        restoreProgram: 'Программа возвращена из архива',
        archiveSeason: 'Сезон архивирован',
        restoreSeason: 'Сезон возвращён из архива',
        verifyBenefit: 'Правило льготы подтверждено',
        rejectBenefit: 'Правило льготы отклонено',
        approveAdminApp: 'Заявка одобрена, роль администратора выдана',
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

    /* Смена статуса в фильтре льгот сразу перезапрашивает список: иначе
       выбранный фильтр выглядел бы применённым, но ничего не менял. */
    if (e.target.closest('[data-benefit-status]')) {
        searchBenefits();
        return;
    }

    if (e.target.closest('[data-repapp-status]')) {
        filterRepApps();
    }

    if (e.target.closest('[data-adminapp-status]')) {
        filterAdminApps();
    }

    if (e.target.closest('[data-doc-filter]')) {
        searchDocs();
        return;
    }

    if (e.target.closest('[data-audit-filter]')) {
        filterAudit();
    }
}

function currentAdminTab() {
    return (routePath() || '/admin/users').split('/admin/')[1] || 'users';
}

async function reloadAdmin() {
    const tab = currentAdminTab();
    await loadAdminTab(ADMIN_TAB_KEYS.has(tab) ? tab : 'users');
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
                    <div class="w-12 h-12 rounded bg-brand-soft text-brand-strong font-bold flex items-center justify-center shrink-0" aria-hidden="true">${escHtml(userInitials(u))}</div>
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
                ${item.is_archived ? `<div class="mt-3"><span class="${UI.badge} ${UI.badgeNeutral}">В архиве</span></div>` : ''}
            </div>
            <div class="flex items-center gap-3 flex-wrap shrink-0">
                <a href="#/universities/${escAttr(item.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Открыть</a>
                <button data-act="editUniversity" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Правка</button>
                ${item.is_archived
                    ? `<button data-act="restoreUniversity" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Вернуть</button>`
                    : `<button data-act="archiveUniversity" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}">В архив</button>`}
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

/* ------------------------- Запросы в каталог ------------------------------ */

const ENTITY_REQUEST_TYPE_LABELS = {
    OLYMPIAD: 'Олимпиада',
    SEASON: 'Сезон',
    PROFILE: 'Профиль',
    UNIVERSITY: 'Новый университет',
};

const ENTITY_REQUEST_STATUS_LABELS = {
    pending: 'На рассмотрении',
    approved: 'Одобрен',
    rejected: 'Отклонён',
};

function entityRequestStatusBadge(status) {
    if (status === 'approved') {
        return `<span class="${UI.badge} ${UI.badgeSuccess}">Одобрен</span>`;
    }
    if (status === 'rejected') {
        return `<span class="${UI.badge} ${UI.badgeDanger}">Отклонён</span>`;
    }
    return `<span class="${UI.badge} ${UI.badgePending}">На рассмотрении</span>`;
}

/** Строка очереди: что просят, кто просит, к чему привязано и действия. */
function adminRequestRowHtml(request) {
    const typeLabel = ENTITY_REQUEST_TYPE_LABELS[request.entity_type] || request.entity_type;
    const status = request.status || 'pending';
    const payload = request.payload || {};
    const details = [];
    if (request.parent_id) details.push(`родитель: ${escHtml(String(request.parent_id))}`);
    if (payload.rsosh_level) details.push(`уровень РСОШ: ${escHtml(String(payload.rsosh_level))}`);
    if (payload.organizer) details.push(`организатор: ${escHtml(String(payload.organizer))}`);
    if (payload.official_url) details.push(`сайт: ${escHtml(String(payload.official_url))}`);
    if (payload.short_name) details.push(`кратко: ${escHtml(String(payload.short_name))}`);
    if (payload.website) details.push(`сайт: ${escHtml(String(payload.website))}`);
    if (payload.contact_email) details.push(`почта для связи: ${escHtml(String(payload.contact_email))}`);
    if (payload.become_representative) details.push('хочет стать представителем вуза');

    return `<div class="${UI.card} px-8 py-6">
        <div class="flex flex-col lg:flex-row lg:items-start justify-between gap-5">
            <div class="flex-1 min-w-0">
                <p class="text-xs font-semibold uppercase tracking-wide text-ink-faint">${escHtml(typeLabel)}</p>
                <p class="mt-2 font-bold text-ink leading-snug">${escHtml(request.name || '—')}</p>
                ${request.description ? `<p class="mt-2 text-sm text-ink-soft leading-relaxed">${escHtml(request.description)}</p>` : ''}
                ${payload.representative_justification ? `<p class="mt-2 text-sm text-ink leading-relaxed whitespace-pre-wrap">Почему хочет быть представителем: ${escHtml(payload.representative_justification)}</p>` : ''}
                ${details.length ? `<p class="mt-2 text-xs text-ink-faint">${details.join(' · ')}</p>` : ''}
                ${attachmentLinksHtml(request.attachments, 'Документы заявителя')}
                ${status === 'rejected' && request.rejection_reason
                    ? `<p class="mt-3 text-sm text-danger">Причина отказа: ${escHtml(request.rejection_reason)}</p>`
                    : ''}
                ${status === 'approved' && request.created_entity_id
                    ? `<p class="mt-3 text-sm text-ink-soft">Создана запись: ${escHtml(String(request.created_entity_id))}</p>`
                    : ''}
            </div>
            <div class="shrink-0 flex flex-wrap lg:flex-col items-start gap-2">
                ${entityRequestStatusBadge(status)}
                ${status === 'pending' ? `
                    <button type="button" data-act="approveRequest" data-id="${escAttr(request.id)}"
                            class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Одобрить и создать</button>
                    <button type="button" data-act="rejectRequest" data-id="${escAttr(request.id)}"
                            class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Отклонить</button>` : ''}
            </div>
        </div>
    </div>`;
}

function adminRequestsHtml() {
    const { requests, total, status } = adminRequestsState;
    const filter = `
    <div class="flex flex-wrap items-end justify-between gap-4 mb-8">
        <form class="flex flex-wrap items-end gap-3" onsubmit="return false;">
            <div>
                <label class="block text-xs font-semibold text-ink-faint mb-1" for="admin-requests-status">Статус</label>
                <select id="admin-requests-status" class="${UI.input}" data-request-status>
                    ${[
                        { value: '', label: 'Все запросы' },
                        { value: 'pending', label: 'На рассмотрении' },
                        { value: 'approved', label: 'Одобренные' },
                        { value: 'rejected', label: 'Отклонённые' },
                    ].map(opt => `<option value="${opt.value}"${opt.value === status ? ' selected' : ''}>${opt.label}</option>`).join('')}
                </select>
            </div>
            <button type="button" data-act="searchRequests" class="${UI.btn} ${UI.btnSecondary}">Показать</button>
        </form>
        <p class="text-sm text-ink-faint">Всего: ${total}</p>
    </div>`;

    if (!requests.length) {
        return filter + emptyHtml('Запросов нет',
            'Представители университетов пока не просили добавить олимпиаду, сезон или профиль.');
    }

    return filter + `<div class="space-y-4">${requests.map(adminRequestRowHtml).join('')}</div>
    ${requests.length < total
        ? `<div class="mt-8 text-center"><button type="button" data-act="loadMoreRequests"
                class="${UI.btn} ${UI.btnSecondary}">Показать ещё</button></div>`
        : ''}`;
}

async function searchRequests() {
    const select = document.querySelector('[data-request-status]');
    const status = select ? select.value : '';
    try {
        const res = await api.adminEntityRequests({
            limit: ADMIN_LIST_PAGE_SIZE,
            offset: 0,
            status: status || undefined,
        });
        if (!res.ok) { showToast(errorText(res), 'error'); return; }
        adminRequestsState = {
            requests: res.data.requests || [],
            total: res.data.total != null ? res.data.total : 0,
            status,
        };
        renderRequestsBox();
    } catch {
        showToast('Сетевая ошибка', 'error');
    }
}

async function loadMoreRequests() {
    try {
        const res = await api.adminEntityRequests({
            limit: ADMIN_LIST_PAGE_SIZE,
            offset: adminRequestsState.requests.length,
            status: adminRequestsState.status || undefined,
        });
        if (!res.ok) { showToast(errorText(res), 'error'); return; }
        const batch = res.data.requests || [];
        adminRequestsState.requests = adminRequestsState.requests.concat(batch);
        if (res.data.total != null) adminRequestsState.total = res.data.total;
        renderRequestsBox();
    } catch {
        showToast('Сетевая ошибка', 'error');
    }
}

function renderRequestsBox() {
    const box = document.getElementById('admin-content');
    if (box) box.innerHTML = adminRequestsHtml();
}

/** Отказ требует непустой причины: администратор объясняет, чего не хватает. */
function openRejectRequestModal(id, onDone) {
    const overlay = openModal('Отклонить запрос', `
        <p class="text-sm text-ink-soft leading-relaxed">
            Опишите, почему запрос отклонён. Причина сохранится в истории и будет
            видна представителю университета.
        </p>
        ${textareaField({ id: 'request-reject-reason', name: 'reason', label: 'Причина отказа', rows: 3, required: true })}
        <div class="mt-6 flex flex-wrap gap-3">
            <button type="button" id="request-reject-submit" class="${UI.btn} ${UI.btnDanger}">Отклонить запрос</button>
            <button type="button" class="${UI.btn} ${UI.btnGhost}" data-close-modal>Отмена</button>
        </div>`);

    const submit = overlay.querySelector('#request-reject-submit');
    submit.addEventListener('click', async () => {
        const reason = (overlay.querySelector('#request-reject-reason').value || '').trim();
        if (!reason) {
            showModalError(overlay, { data: { detail: 'Причина отказа обязательна' } });
            return;
        }
        submit.disabled = true;
        try {
            const res = await api.rejectEntityRequest(id, reason);
            if (!res.ok) { showModalError(overlay, res); submit.disabled = false; return; }
            overlay.remove();
            showToast('Запрос отклонён', 'success');
            if (onDone) await onDone();
        } catch {
            showModalError(overlay, { data: { detail: 'Сетевая ошибка' } });
            submit.disabled = false;
        }
    });
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

function adminImportsHtml(data) {
    const imports = Array.isArray(data) ? data : (data.docs || []);
    const jobs = Array.isArray(data) ? [] : (data.jobs || []);
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
                        ${summary.mode === 'official_list'
                            ? ` · официальный перечень: строк ${summary.rows || 0}, олимпиад ${summary.olympiads || 0}, новых ${summary.create || 0}, в каталоге ${summary.use || 0}`
                            : (summary.total ? ` · найдено: ${summary.total} (новых: ${summary.new || 0}, объединений: ${summary.merge || 0}, на проверку: ${summary.review || 0})` : '')}
                    </p>
                    ${item.error ? `<p class="mt-3 text-sm text-danger">${escHtml(item.error)}</p>` : ''}
                </div>
                <div class="flex flex-wrap gap-3 shrink-0">
                    ${state === 'rejected' ? '' : `<button data-act="runImport" data-id="${escAttr(item.id)}" ${state === 'paused' || state === 'processing' ? 'disabled' : ''} class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Запустить импорт</button>`}
                    ${state === 'paused' ? `<button data-act="resumeImport" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Возобновить</button>` : ''}
                    ${state === 'processing' ? `<button data-act="pauseImport" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Приостановить</button>` : ''}
                    <button data-act="previewImport" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Открыть результаты</button>
                </div>
            </div>
            <div class="mt-6 flex flex-wrap gap-3">
                <a href="${escAttr(api.docFileUrl(item.id))}" target="_blank" rel="noopener noreferrer" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Скачать документ</a>
            </div>
        </div>`;
    }).join('')}</div>`
        : emptyHtml('Документов РСОШ нет',
            'Загрузите официальный документ РСОШ (PDF, XLSX, PNG/JPG) — импорт покажет preview до записи в каталог.',
            `<button data-act="newImport" class="${UI.btn} ${UI.btnPrimary}">Загрузить документ</button>`)}
    ${importJobsHtml(jobs)}`;
}

/** Журнал прогонов импорта: кто, когда и чем закончилось. */
function importJobsHtml(jobs) {
    if (!jobs.length) return '';
    return `
    <section class="mt-20" aria-labelledby="import-jobs-title">
        <h2 id="import-jobs-title" class="text-2xl font-extrabold tracking-tight">История импортов</h2>
        <p class="mt-3 text-sm text-ink-soft">Журнал запусков: переживает перезапись состояния документа.</p>
        <div class="mt-6 space-y-3">
            ${jobs.map(job => {
                const summary = job.summary || {};
                const status = job.status || 'PROCESSING';
                const statusClass = status === 'FAILED'
                    ? UI.badgeDanger
                    : (status === 'PROCESSING' ? UI.badgePending : UI.badgeNeutral);
                return `
                <div class="${UI.card} px-6 py-5 flex flex-col lg:flex-row lg:items-center gap-4">
                    <div class="flex-1 min-w-0">
                        <div class="flex flex-wrap items-center gap-3">
                            <span class="${UI.badge} ${statusClass}">${escHtml(status)}</span>
                            <span class="text-sm text-ink-soft">${escHtml(job.kind || 'RSOSH')}</span>
                        </div>
                        <p class="mt-2 text-sm text-ink-soft">
                            Начат: ${escHtml(formatDate(job.started_at))}
                            ${job.finished_at ? ` · завершён: ${escHtml(formatDate(job.finished_at))}` : ''}
                        </p>
                        ${summary.total != null
                            ? `<p class="mt-1 text-sm text-ink-soft">Записей: ${summary.total}, новых: ${summary.new || 0}, объединений: ${summary.merge || 0}, на проверку: ${summary.review || 0}</p>`
                            : ''}
                        ${job.error ? `<p class="mt-1 text-sm text-danger">${escHtml(job.error)}</p>` : ''}
                    </div>
                    <button type="button" data-act="importJobRecords" data-id="${escAttr(job.id)}"
                            class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall} shrink-0">Показать записи</button>
                </div>`;
            }).join('')}
        </div>
    </section>`;
}

/** Построчные результаты прогона импорта. */
async function openImportJobModal(jobId) {
    const res = await api.adminImportJob(jobId);
    if (!res.ok) { showToast(errorText(res), 'error'); return; }
    const job = res.data || {};
    const records = job.records || [];
    const body = `
        <div class="space-y-4">
            <p class="text-sm text-ink-soft">
                Прогон от ${escHtml(formatDate(job.started_at))} · ${escHtml(job.status || '—')}
                ${job.error ? ` · <span class="text-danger">${escHtml(job.error)}</span>` : ''}
            </p>
            ${records.length
                ? `<div class="space-y-2">${records.map(item => `
                    <div class="rounded bg-mist px-5 py-4">
                        <p class="font-semibold text-ink leading-snug">${escHtml(item.name || 'Запись')}</p>
                        <p class="mt-1 text-sm text-ink-soft">
                            ${escHtml(item.action || '—')} · ${escHtml(item.status || '—')}
                        </p>
                    </div>`).join('')}</div>`
                : '<p class="text-sm text-ink-soft">Построчных записей у этого прогона нет.</p>'}
        </div>
        <div class="flex flex-wrap justify-end gap-3 mt-10">
            <button type="button" data-close class="${UI.btn} ${UI.btnGhost}">Закрыть</button>
        </div>`;
    const { overlay, close } = openModal('Записи импорта', body, { wide: true });
    overlay.querySelector('[data-close]').addEventListener('click', close);
}

function openUploadModal() {
    let dirty = false;
    const body = `
        <div id="modal-alert"></div>
        <form id="upload-form">
            <div class="${UI.field}">
                <label for="upload-file" class="${UI.label}">Файл документа РСОШ <span class="text-danger" aria-hidden="true">*</span></label>
                <input id="upload-file" name="file" type="file" accept=".pdf,.xlsx,.png,.jpg,.jpeg" required
                       class="block w-full cursor-pointer text-sm text-ink-soft file:mr-4 file:rounded file:px-5 file:py-2.5 file:text-sm file:font-semibold file:bg-brand file:text-white hover:file:bg-brand-strong">
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
    <div class="mb-8 rounded bg-mist px-6 py-4 text-sm leading-relaxed" role="status">
        <p class="font-semibold text-ink mb-2">Замечания при чтении документа</p>
        <ul class="space-y-1.5 text-ink-soft">
            ${warnings.map(w => `
            <li class="flex items-start gap-2">
                <span class="w-1.5 h-1.5 rounded-full bg-brand shrink-0 mt-1.5" aria-hidden="true"></span>
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
        class="fixed bottom-8 right-8 z-40 inline-flex items-center gap-2 rounded bg-brand text-white px-6 py-4 text-sm font-semibold shadow-elev-2 hover:bg-brand-strong transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand">
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

/* ---------------------- Официальный перечень РСОШ ------------------------- */

const PLAN_MATCH_LABELS = {
    create: 'Новая олимпиада',
    use: 'Есть в каталоге',
    review: 'Нужно выбрать',
    skip: 'Пропустить',
};

const PLAN_LEVEL_LABELS = [
    { value: '', label: '—' },
    { value: '1', label: 'I' },
    { value: '2', label: 'II' },
    { value: '3', label: 'III' },
];

const HISTORY_ACTION_LABELS = {
    olympiad_created: 'Олимпиада создана',
    olympiad_restored: 'Олимпиада возвращена из архива',
    olympiad_renamed: 'Олимпиада переименована',
    olympiad_absent: 'Олимпиада отсутствует в перечне',
    season_created: 'Создан сезон',
    season_restored: 'Сезон возвращён из архива',
    profile_created: 'Создан профиль',
    profile_absent: 'Профиль отсутствует в перечне',
    profile_level_changed: 'Изменён уровень профиля',
};

function planActionBadge(action) {
    const tones = {
        create: 'bg-brand/10 text-brand-strong',
        use: 'bg-mist text-ink-soft',
        review: 'bg-amber-100 text-amber-800',
        skip: 'bg-danger/10 text-danger',
    };
    const tone = tones[action] || 'bg-mist text-ink-soft';
    return `<span class="inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold ${tone}">${escHtml(PLAN_MATCH_LABELS[action] || action || '—')}</span>`;
}

function planMatchOptions(item) {
    const match = item.match || {};
    const current = match.olympiad_id || '';
    const candidates = (match.candidates || []).slice();
    const options = [
        `<option value="create" ${match.action === 'create' ? 'selected' : ''}>Создать новую</option>`,
        `<option value="skip" ${match.action === 'skip' ? 'selected' : ''}>Пропустить</option>`,
    ];
    // Пока совпадение не выбрано, «Создать новую» нельзя показывать выбранной:
    // иначе сохранение формы молча превратит спорную строку в новую запись.
    if (match.action === 'review') {
        options.unshift(
            '<option value="" selected disabled>— нужно выбрать —</option>'
        );
    }
    for (const candidate of candidates) {
        options.push(
            `<option value="use:${escAttr(candidate.olympiad_id)}" ${match.action === 'use' && current === candidate.olympiad_id ? 'selected' : ''}>В каталоге: ${escHtml(candidate.name)} (${Math.round((candidate.score || 0) * 100)}%)</option>`
        );
    }
    if (match.action === 'use' && current && !candidates.some(c => c.olympiad_id === current)) {
        options.push(
            `<option value="use:${escAttr(current)}" selected>Текущая запись каталога</option>`
        );
    }
    return options.join('');
}

function planOlympiadHtml(item, index) {
    const match = item.match || {};
    const action = match.action || 'create';
    const profiles = item.profiles || [];
    const createCount = profiles.filter(p => (p.match || {}).action === 'create').length;
    const updateCount = profiles.filter(p => (p.match || {}).action === 'update').length;
    const rows = profiles.map(profile => {
        const pmatch = profile.match || {};
        const level = profile.level || '';
        const skipped = pmatch.action === 'skip';
        return `
        <tr class="${skipped ? 'opacity-50' : ''}" data-profile data-olympiad="${escAttr(item.name_norm)}" data-row="${escAttr(String(profile.source_row))}">
            <td class="px-2 py-1 align-top">
                <input class="${UI.input} !py-1 text-sm w-full" data-field="profile-name"
                       value="${escAttr(profile.name || '')}" aria-label="Название профиля">
            </td>
            <td class="px-2 py-1 align-top w-24">
                <select class="${UI.input} !py-1 text-sm" data-field="profile-level" aria-label="Уровень профиля">
                    ${PLAN_LEVEL_LABELS.map(o => `<option value="${o.value}" ${o.value === level ? 'selected' : ''}>${o.label}</option>`).join('')}
                </select>
                ${profile.previous_level ? `<p class="mt-1 text-xs text-ink-faint">было ${escHtml(PLAN_LEVEL_LABELS.find(o => o.value === profile.previous_level)?.label || profile.previous_level)}</p>` : ''}
            </td>
            <td class="px-2 py-1 align-top w-20 text-center">
                <input type="checkbox" data-field="profile-skip" ${skipped ? 'checked' : ''} aria-label="Пропустить профиль">
            </td>
            <td class="px-2 py-1 align-top text-xs text-ink-faint">
                стр. ${escHtml(String(profile.page || '—'))}
                ${(profile.issues || []).length ? `<span class="block text-danger">${escHtml(profile.issues[0])}</span>` : ''}
            </td>
        </tr>`;
    }).join('');

    return `
    <details class="${UI.card} px-4 py-3" data-olympiad="${escAttr(item.name_norm)}" ${(item.issues || []).length || action === 'review' ? 'open' : ''}>
        <summary class="cursor-pointer flex flex-wrap items-center gap-3">
            <span class="font-semibold text-ink">${escHtml(item.number ? `№ ${item.number} · ` : '')}${escHtml(item.name)}</span>
            ${planActionBadge(action)}
            <span class="text-xs text-ink-faint">
                профилей: ${profiles.length}${createCount ? ` · новых: ${createCount}` : ''}${updateCount ? ` · изменится: ${updateCount}` : ''}
            </span>
        </summary>
        <div class="mt-4 grid gap-3 md:grid-cols-2">
            <label class="block">
                <span class="text-xs text-ink-faint">Название</span>
                <input class="${UI.input} !py-1 text-sm w-full" data-field="olympiad-name"
                       value="${escAttr(item.name)}" aria-label="Название олимпиады">
            </label>
            <label class="block">
                <span class="text-xs text-ink-faint">Сопоставление с каталогом</span>
                <select class="${UI.input} !py-1 text-sm w-full" data-field="olympiad-match" aria-label="Сопоставление с каталогом">
                    ${planMatchOptions(item)}
                </select>
            </label>
            <label class="block md:col-span-2">
                <span class="text-xs text-ink-faint">Организатор</span>
                <textarea class="${UI.input} !py-1 text-sm w-full" rows="2" data-field="olympiad-organizer" aria-label="Организатор">${escHtml(item.organizer || '')}</textarea>
            </label>
        </div>
        ${(item.issues || []).length ? `<ul class="mt-3 text-xs text-danger list-disc pl-5 space-y-1">${item.issues.map(issue => `<li>${escHtml(issue)}</li>`).join('')}</ul>` : ''}
        <div class="mt-4 overflow-x-auto">
            <table class="w-full text-sm">
                <thead>
                    <tr class="text-left text-xs text-ink-faint">
                        <th class="px-2 py-1 font-semibold">Профиль</th>
                        <th class="px-2 py-1 font-semibold">Уровень</th>
                        <th class="px-2 py-1 font-semibold text-center">Пропуск</th>
                        <th class="px-2 py-1 font-semibold">Источник</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
    </details>`;
}

function planSummaryHtml(plan) {
    const summary = plan.summary || {};
    const chips = [
        ['Строк', summary.profiles],
        ['Олимпиад', summary.olympiads],
        ['Новых', summary.create],
        ['В каталоге', summary.use],
        ['На проверку', summary.review],
        ['Новых профилей', summary.profiles_create],
        ['Отсутствуют', summary.missing],
    ].filter(([, value]) => value !== undefined && value !== null && value !== 0);
    return chips.map(([label, value]) => `
        <span class="inline-flex items-baseline gap-1 rounded bg-mist px-3 py-1 text-sm">
            <span class="text-ink-faint">${escHtml(label)}:</span>
            <span class="font-semibold text-ink">${escHtml(String(value))}</span>
        </span>`).join('');
}

function planIssuesHtml(plan) {
    const warnings = plan.warnings || [];
    const errors = plan.errors || [];
    if (!warnings.length && !errors.length) return '';
    return `
    <div class="space-y-3">
        ${errors.length ? `<div class="rounded border border-danger/30 bg-danger/5 px-5 py-4">
            <p class="font-semibold text-danger mb-2">Нужно исправить до применения</p>
            <ul class="text-sm text-ink space-y-1 list-disc pl-5">${errors.map(e => `<li>${escHtml(e)}</li>`).join('')}</ul>
        </div>` : ''}
        ${warnings.length ? `<div class="rounded bg-mist px-5 py-4">
            <p class="font-semibold text-ink mb-2">Предупреждения</p>
            <ul class="text-sm text-ink-soft space-y-1 list-disc pl-5">${warnings.map(w => `<li>${escHtml(w)}</li>`).join('')}</ul>
        </div>` : ''}
    </div>`;
}

function planMissingHtml(plan) {
    const missing = plan.missing || [];
    if (!missing.length) return '';
    return `
    <section class="${UI.card} px-6 py-5">
        <h2 class="text-lg font-extrabold">Нет в документе</h2>
        <p class="mt-2 text-sm text-ink-soft leading-relaxed">
            Эти олимпиады есть в каталоге за ${escHtml(plan.season_label || 'этот сезон')}, но не найдены в перечне.
            При применении их можно пометить отсутствующими: профили потеряют уровень,
            а олимпиады уйдут в архив. Записи не удаляются.
        </p>
        <ul class="mt-3 text-sm space-y-1">${missing.map(item => `<li>${escHtml(item.name)}</li>`).join('')}</ul>
        <label class="mt-4 inline-flex items-center gap-2 text-sm">
            <input type="checkbox" id="apply-missing" ${plan.missing_allowed ? '' : 'disabled'}>
            <span>Зафиксировать отсутствие при применении</span>
        </label>
        ${plan.missing_allowed ? '' : `<p class="mt-2 text-xs text-danger">Перечень прочитан не полностью: фиксировать отсутствие нельзя.</p>`}
    </section>`;
}

async function renderOfficialList(importId, imp) {
    const page = document.getElementById('page');
    const planRes = await api.importPlan(importId);
    if (!planRes.ok) {
        page.innerHTML = `
        <div class="max-w-content mx-auto pt-4 pb-12">
            ${alertHtml(errorText(planRes), 'error')}
            <a href="#/admin/imports" class="${UI.btn} ${UI.btnGhost}">К списку импортов</a>
        </div>`;
        return;
    }
    const plan = planRes.data.plan;
    const applied = Boolean(imp.applied_at) || imp.state === 'approved';
    const state = { tab: 'plan', offset: 0, search: '', sheet: 'list', table: null, history: null };

    function headerHtml() {
        return `
        <a href="#/admin/imports" class="text-sm text-ink-soft hover:text-ink">← К списку импортов</a>
        <div class="mt-4 flex flex-wrap items-start justify-between gap-4">
            <div>
                <h1 class="text-3xl font-extrabold tracking-tight">Официальный перечень</h1>
                <p class="mt-2 text-sm text-ink-soft">
                    ${escHtml(plan.title || 'Перечень олимпиад школьников')}
                    ${plan.season_label ? ` · учебный год: ${escHtml(plan.season_label)}` : ''}
                    · ${escHtml(IMPORT_STATE_LABELS[imp.state] || imp.state || '')}
                </p>
            </div>
            <div class="flex flex-wrap gap-2">
                <a href="${api.docFileUrl(importId)}" target="_blank" rel="noopener" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">PDF</a>
                ${imp.table && imp.table.doc_id ? `<a href="${api.docFileUrl(imp.table.doc_id)}" target="_blank" rel="noopener" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">XLSX</a>` : ''}
                ${imp.html && imp.html.doc_id ? `<a href="${api.docFileUrl(imp.html.doc_id)}" target="_blank" rel="noopener" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">HTML-таблица</a>` : ''}
            </div>
        </div>
        <div class="mt-5 flex flex-wrap gap-2">${planSummaryHtml(plan)}</div>`;
    }

    function tabsHtml() {
        const tabs = [
            ['plan', 'План импорта'],
            ['table', 'Таблица'],
            ['history', 'История'],
        ];
        return `<div class="mt-8 flex gap-2 border-b border-ink/10">
            ${tabs.map(([key, label]) => `<button type="button" data-tab="${key}"
                class="px-4 py-2 text-sm font-semibold ${state.tab === key ? 'text-brand-strong border-b-2 border-brand' : 'text-ink-soft hover:text-ink'}">${escHtml(label)}</button>`).join('')}
        </div>`;
    }

    function planHtml() {
        return `
        <div class="mt-6 space-y-4">
            ${planIssuesHtml(plan)}
            ${(plan.olympiads || []).map(planOlympiadHtml).join('')}
            ${planMissingHtml(plan)}
        </div>
        ${applied ? '' : `<div class="sticky bottom-4 mt-8 flex flex-wrap items-center justify-end gap-3 rounded bg-white shadow-elev-2 px-5 py-4">
            <button type="button" data-list-act="savePlan" class="${UI.btn} ${UI.btnSecondary}">Сохранить правки</button>
            <button type="button" data-list-act="applyPlan" ${(plan.errors || []).length ? 'disabled' : ''} class="${UI.btn} ${UI.btnPrimary}">Применить импорт</button>
        </div>`}`;
    }

    function tableHtml() {
        const table = state.table;
        if (!table) return `<div class="mt-6">${loadingHtml('Загружаем таблицу…')}</div>`;
        const rows = table.rows || [];
        return `
        <div class="mt-6 flex flex-wrap items-end gap-3">
            <label class="text-sm">
                <span class="sr-only">Лист</span>
                <select id="table-sheet" class="${UI.input} !py-2 text-sm">
                    <option value="list" ${state.sheet === 'list' ? 'selected' : ''}>Перечень</option>
                    <option value="summary" ${state.sheet === 'summary' ? 'selected' : ''}>Сводка</option>
                </select>
            </label>
            <label class="text-sm flex-1 min-w-48">
                <span class="sr-only">Поиск по таблице</span>
                <input id="table-search" type="search" value="${escAttr(state.search)}" placeholder="Поиск по таблице" class="${UI.input} !py-2 text-sm w-full">
            </label>
            <button type="button" data-list-act="tableSearch" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Найти</button>
        </div>
        <p class="mt-3 text-sm text-ink-faint">
            ${escHtml(table.title || '')} · показано ${rows.length} из ${table.total}
        </p>
        <div class="mt-3 overflow-x-auto">
            <table class="w-full text-sm">
                <thead><tr class="bg-brand text-white">${(table.headers || []).map(h => `<th class="px-2 py-2 text-left font-semibold">${escHtml(h)}</th>`).join('')}</tr></thead>
                <tbody>${rows.map(row => `<tr class="border-b border-ink/5">${row.map((cell, i) => `<td class="px-2 py-1 align-top ${i === 0 || i === row.length - 1 ? 'text-center whitespace-nowrap' : ''}">${escHtml(String(cell ?? '')).replace(/\n/g, '<br>')}</td>`).join('')}</tr>`).join('')}</tbody>
            </table>
        </div>
        <div class="mt-4 flex items-center justify-between gap-3">
            <button type="button" data-list-act="tablePrev" ${state.offset <= 0 ? 'disabled' : ''} class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Назад</button>
            <span class="text-sm text-ink-faint">${state.offset + 1}–${Math.min(state.offset + (table.limit || 50), table.total)} из ${table.total}</span>
            <button type="button" data-list-act="tableNext" ${state.offset + (table.limit || 50) >= table.total ? 'disabled' : ''} class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Вперёд</button>
        </div>`;
    }

    function historyHtml() {
        const history = state.history;
        if (!history) return `<div class="mt-6">${loadingHtml('Загружаем историю…')}</div>`;
        if (!history.length) {
            return `<p class="mt-6 text-sm text-ink-soft">Изменений пока нет: импорт ещё не применён.</p>`;
        }
        return `<ul class="mt-6 space-y-2">${history.map(entry => `
            <li class="${UI.card} px-5 py-3 text-sm">
                <span class="font-semibold">${escHtml(HISTORY_ACTION_LABELS[entry.action] || entry.action)}</span>
                ${entry.name ? ` · ${escHtml(entry.name)}` : ''}
                ${entry.profile ? ` · профиль «${escHtml(entry.profile)}»` : ''}
                ${entry.previous_level || entry.level ? ` · уровень ${escHtml(entry.previous_level || '—')} → ${escHtml(entry.level || '—')}` : ''}
                <span class="block mt-1 text-xs text-ink-faint">${escHtml(entry.at || '')}</span>
            </li>`).join('')}</ul>`;
    }

    function render() {
        page.innerHTML = `
        <section class="pt-4 pb-24 max-w-content mx-auto">
            ${headerHtml()}
            ${tabsHtml()}
            ${state.tab === 'plan' ? planHtml() : state.tab === 'table' ? tableHtml() : historyHtml()}
        </section>`;
        bind();
    }

    function bind() {
        page.querySelectorAll('[data-tab]').forEach(button => {
            button.addEventListener('click', () => {
                state.tab = button.dataset.tab;
                render();
                if (state.tab === 'table' && !state.table) loadTable();
                if (state.tab === 'history' && !state.history) loadHistory();
            });
        });
        page.querySelectorAll('[data-list-act]').forEach(button => {
            button.addEventListener('click', () => {
                const action = button.dataset.listAct;
                if (action === 'savePlan') savePlan();
                if (action === 'applyPlan') applyPlan();
                if (action === 'tableSearch') {
                    state.search = (document.getElementById('table-search') || {}).value || '';
                    state.offset = 0;
                    loadTable();
                }
                if (action === 'tablePrev') {
                    state.offset = Math.max(0, state.offset - 50);
                    loadTable();
                }
                if (action === 'tableNext') {
                    state.offset += 50;
                    loadTable();
                }
            });
        });
        const sheet = document.getElementById('table-sheet');
        if (sheet) sheet.addEventListener('change', () => {
            state.sheet = sheet.value;
            state.offset = 0;
            loadTable();
        });
    }

    async function loadTable() {
        const res = await api.importTable(importId, {
            sheet: state.sheet,
            offset: state.offset,
            search: state.search,
            limit: 50,
        });
        if (!res.ok) { showToast(errorText(res), 'error'); return; }
        state.table = res.data;
        render();
    }

    async function loadHistory() {
        const res = await api.importHistory(importId);
        if (!res.ok) { showToast(errorText(res), 'error'); return; }
        state.history = res.data.history || [];
        render();
    }

    function collectPlan() {
        const olympiads = [];
        const profiles = [];
        page.querySelectorAll('[data-olympiad]').forEach(card => {
            if (!card.querySelector('[data-field="olympiad-name"]')) return;
            const norm = card.dataset.olympiad;
            const matchValue = card.querySelector('[data-field="olympiad-match"]').value;
            const change = {
                name_norm: norm,
                name: card.querySelector('[data-field="olympiad-name"]').value.trim(),
                organizer: card.querySelector('[data-field="olympiad-organizer"]').value.trim(),
            };
            if (matchValue.startsWith('use:')) {
                change.action = 'use';
                change.olympiad_id = matchValue.slice(4);
            } else if (matchValue) {
                change.action = matchValue;
            }
            // Пустое значение — «нужно выбрать»: действие не отправляется, и
            // сервер оставляет строку в состоянии review (применить нельзя).
            olympiads.push(change);
        });
        page.querySelectorAll('[data-profile]').forEach(row => {
            const skip = row.querySelector('[data-field="profile-skip"]').checked;
            profiles.push({
                olympiad: row.dataset.olympiad,
                source_row: Number(row.dataset.row),
                name: row.querySelector('[data-field="profile-name"]').value.trim(),
                level: row.querySelector('[data-field="profile-level"]').value,
                action: skip ? 'skip' : undefined,
            });
        });
        return { olympiads, profiles };
    }

    async function savePlan() {
        const button = page.querySelector('[data-list-act="savePlan"]');
        if (button) button.disabled = true;
        try {
            const res = await api.updateImportPlan(importId, collectPlan());
            if (!res.ok) { showToast(errorText(res), 'error'); return; }
            showToast('План сохранён', 'success');
            await renderOfficialList(importId, (res.data.import) || imp);
            return;
        } finally {
            if (button) button.disabled = false;
        }
    }

    async function applyPlan() {
        const missingBox = document.getElementById('apply-missing');
        const markMissing = Boolean(missingBox && missingBox.checked);
        const ok = window.confirm(
            'Применить перечень к каталогу? Олимпиады и профили будут созданы или обновлены, '
            + 'а документ получит статус «Применён». Повторно применить этот же перечень нельзя.'
        );
        if (!ok) return;
        const button = page.querySelector('[data-list-act="applyPlan"]');
        if (button) button.disabled = true;
        try {
            // Правки из формы уходят до применения: план на сервере — это то,
            // что действительно попадёт в каталог.
            const saved = await api.updateImportPlan(importId, collectPlan());
            if (!saved.ok) { showToast(errorText(saved), 'error'); return; }
            const res = await api.applyImportPlan(importId, { mark_missing: markMissing });
            if (!res.ok) { showToast(errorText(res), 'error'); return; }
            const result = res.data.result || {};
            showToast(
                `Применено: создано ${result.created || 0}, использовано ${result.used || 0}, профилей ${result.profiles_created || 0}`,
                'success'
            );
            await renderImportReview(importId);
        } finally {
            if (button) button.disabled = false;
        }
    }

    render();
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
        // Официальный перечень проверяется не карточками кандидатов, а планом
        // импорта: у него своя страница с таблицей, сопоставлением и сезоном.
        if ((data.import || {}).mode === 'official_list') {
            await renderOfficialList(importId, data.import || {});
            return;
        }
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
                <div class="rounded bg-mist px-6 py-4 mt-6 mb-8 text-sm leading-relaxed" role="status">
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
            <div class="${UI.card} px-6 py-5 ${confirmed ? 'ring-1 ring-brand/25' : ''}">
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
            return `<div class="rounded bg-success-soft px-6 py-4 mb-8 text-sm leading-relaxed" role="status">
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
            return `<div class="rounded bg-mist px-6 py-4 mb-8 text-sm leading-relaxed" role="status">
                <p class="font-semibold text-ink mb-1">Импорт завершился ошибкой</p>
                <p class="text-ink-soft">Каталог не изменён. Запустите импорт заново — обработка начинается с начала.</p>
            </div>`;
        }
        if (state === 'paused') {
            const stage = IMPORT_PROGRESS_LABELS[(imp.progress || {}).stage] || '';
            return `<div class="rounded bg-mist px-6 py-4 mb-8 text-sm leading-relaxed" role="status">
                <p class="font-semibold text-ink mb-1">Импорт приостановлен</p>
                <p class="text-ink-soft">Обработка остановлена${stage ? ` на этапе «${escHtml(stage)}»` : ''}. Возобновить её можно кнопкой «Возобновить» в списке импортов: если документ уже распознан, повторного чтения не будет.</p>
            </div>`;
        }
        return `<div class="rounded bg-mist px-6 py-4 mb-8 text-sm leading-relaxed" role="status">
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
        <div class="rounded bg-success-soft border border-line px-6 py-6">
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

/* --------------------------- Сводка и новые разделы ------------------------ */

function adminDashboardHtml(stats) {
    const cards = [
        ['Пользователи', stats.users, `${stats.users_active || 0} активных`],
        ['Университеты', stats.universities, `${stats.universities_archived || 0} в архиве`],
        ['Олимпиады', stats.olympiads, `${stats.olympiads_archived || 0} в архиве`],
        ['Правила льгот', stats.benefits, `опубликовано: ${stats.benefits_published || 0}`],
        ['Документы', stats.docs, ''],
        ['Заявки представителей', stats.representative_applications_pending, 'ожидают рассмотрения'],
    ];
    const status = stats.benefits_by_status || {};
    return `
    <div class="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        ${cards.map(([label, value, note]) => `
        <div class="${UI.card} px-8 py-7">
            <p class="text-sm font-semibold text-ink-soft">${escHtml(label)}</p>
            <p class="mt-3 text-3xl font-extrabold tracking-tight">${value != null ? value : 0}</p>
            ${note ? `<p class="mt-2 text-xs text-ink-faint">${escHtml(note)}</p>` : ''}
        </div>`).join('')}
    </div>
    <div class="${UI.card} px-8 py-7 mt-6">
        <p class="font-bold text-ink">Модерация льгот</p>
        <div class="mt-4 flex flex-wrap gap-3 text-sm">
            <span class="${UI.badge} ${UI.badgePending}">Не проверено: ${status.unverified || 0}</span>
            <span class="${UI.badge} ${UI.badgeSuccess}">Проверено: ${status.verified || 0}</span>
            <span class="${UI.badge} ${UI.badgeDanger}">Отклонено: ${status.rejected || 0}</span>
        </div>
    </div>`;
}

function adminEntityName(items, id, fallback = '—') {
    const item = (items || []).find(x => String(x.id) === String(id));
    if (!item) return fallback;
    return item.short_name || item.name || item.season_label || fallback;
}

function adminBenefitsHtml() {
    const rules = adminBenefitsState.rules;
    const total = adminBenefitsState.total > rules.length ? adminBenefitsState.total : rules.length;
    const statusOptions = [
        { value: '', label: 'Все статусы' },
        { value: 'unverified', label: 'Не проверено' },
        { value: 'verified', label: 'Проверено' },
        { value: 'rejected', label: 'Отклонено' },
    ];
    const toolbar = `
    <div class="flex flex-wrap items-end justify-between gap-4 mb-8">
        <form class="flex flex-wrap items-end gap-3" onsubmit="return false;">
            <label class="sr-only" for="admin-benefits-search">Поиск по льготам</label>
            <input id="admin-benefits-search" type="search" value="${escAttr(adminBenefitsState.search)}"
                   placeholder="Олимпиада, вуз, профиль, сезон"
                   class="${UI.input} sm:!w-72 !py-2 text-sm">
            <label class="sr-only" for="admin-benefits-status">Статус проверки</label>
            <select id="admin-benefits-status" data-benefit-status class="${UI.input} sm:!w-56 !py-2 text-sm">
                ${statusOptions.map(o => `<option value="${escAttr(o.value)}" ${o.value === adminBenefitsState.status ? 'selected' : ''}>${escHtml(o.label)}</option>`).join('')}
            </select>
            <label class="inline-flex items-center gap-2 text-sm text-ink-soft pb-2">
                <input type="checkbox" data-benefit-needs-review class="w-4 h-4"
                       ${adminBenefitsState.needsReview ? 'checked' : ''}>
                Только требующие уточнения
            </label>
            <button type="button" data-act="searchBenefits" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Найти</button>
        </form>
        <div class="flex items-center gap-3">
            <p class="text-sm text-ink-faint">Показано ${rules.length} из ${total}</p>
            ${rules.length < total
                ? `<button type="button" data-act="loadMoreBenefits" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Показать ещё</button>`
                : ''}
            <button type="button" data-act="newBenefit" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Добавить правило</button>
        </div>
    </div>`;

    if (!rules.length) {
        return toolbar + (adminBenefitsState.search || adminBenefitsState.status || adminBenefitsState.needsReview
            ? emptyHtml('Ничего не найдено', 'По этим условиям правил льгот нет.')
            : emptyHtml('Правил льгот нет',
                'Представители добавляют правила в своём кабинете, администратор — здесь.',
                `<button data-act="newBenefit" class="${UI.btn} ${UI.btnPrimary}">Добавить правило</button>`));
    }

    return toolbar + `
    <div class="space-y-4">
        ${rules.map(item => {
            const university = adminEntityName(adminBenefitsState.universities, item.university_id, 'университет не найден');
            const olympiad = adminEntityName(adminBenefitsState.olympiads, item.olympiad_id, 'олимпиада не найдена');
            const canVerify = !!item.doc_id;
            const typeLabel = benefitTypeLabel(item.benefit_type);
            const result = benefitResultText(item);
            const context = [
                item.season_label ? `сезон ${item.season_label}` : '',
                item.profile_name
                    ? `${item.profile_name}${item.profile_rsosh_level ? ` · уровень РСОШ ${item.profile_rsosh_level}` : ''}`
                    : '',
            ].filter(Boolean).join(' · ');
            const ege = benefitEgeLine(item);
            return `
        <div class="${UI.card} px-8 py-6 flex flex-col lg:flex-row lg:items-start gap-5">
            <div class="flex-1 min-w-0">
                <p class="font-bold text-ink leading-snug">
                    ${escHtml(typeLabel || 'Правило льготы')}${result ? ` · ${escHtml(result)}` : ''}
                </p>
                <p class="mt-2 text-sm text-ink-soft">${escHtml(university)} · ${escHtml(olympiad)}</p>
                ${context ? `<p class="mt-2 text-sm text-ink-soft">${escHtml(context)}</p>` : '<p class="mt-2 text-sm text-danger">Сезон и профиль не указаны</p>'}
                ${ege ? `<p class="mt-2 text-sm text-ink-soft">${escHtml(ege)}</p>` : ''}
                <p class="mt-3 text-xs text-ink-faint flex flex-wrap items-center gap-x-4 gap-y-2">
                    ${item.doc_id
                        ? `<a href="${api.docFileUrl(item.doc_id)}" target="_blank" rel="noopener" class="underline">${escHtml((item.doc && item.doc.name) || 'Документ-основание')}</a>`
                        : '<span class="text-danger">Документ-основание не приложен</span>'}
                    ${item.ege_requirement
                        ? '<span>Требование ЕГЭ заполнено</span>'
                        : '<span>Без требования ЕГЭ</span>'}
                </p>
                ${item.rejection_reason ? `<p class="mt-2 text-xs text-ink-faint">Причина отклонения: ${escHtml(item.rejection_reason)}</p>` : ''}
            </div>
            <div class="flex items-center gap-3 flex-wrap shrink-0">
                ${benefitStatusBadge(item.verification_status)}
                ${item.needs_review
                    ? `<span class="${UI.badge} ${UI.badgeDanger}">Требует уточнения</span>` : ''}
                <button data-act="editBenefit" data-id="${escAttr(item.id)}"
                        class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Изменить</button>
                ${item.verification_status !== 'verified'
                    ? `<button data-act="verifyBenefit" data-id="${escAttr(item.id)}"
                               class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}"
                               ${canVerify ? '' : 'disabled title="Для подтверждения нужен документ-основание университета"'}>Подтвердить</button>` : ''}
                ${item.verification_status !== 'rejected'
                    ? `<button data-act="rejectBenefit" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}">Отклонить</button>` : ''}
            </div>
        </div>`;
        }).join('')}
    </div>`;
}

function adminSeasonsHtml() {
    const seasons = adminSeasonsState.seasons;
    const total = adminSeasonsState.total > seasons.length ? adminSeasonsState.total : seasons.length;
    if (!seasons.length) {
        return emptyHtml('Сезонов нет',
            'Сезон добавляется в окне правки олимпиады: откройте олимпиаду в '
            + 'каталоге и добавьте метку года. Профили и уровни задаются внутри сезона.',
            `<a href="#/admin/olympiads" class="${UI.btn} ${UI.btnPrimary}">Открыть олимпиады</a>`);
    }
    return `
    <div class="flex flex-wrap items-center justify-between gap-6 mb-10">
        <p class="text-sm text-ink-faint">Сезонов: ${total}</p>
        <a href="#/admin/olympiads" class="${UI.btn} ${UI.btnSecondary}">Добавить через олимпиаду</a>
    </div>
    <div class="space-y-4">${seasons.map(item => {
        const olympiad = adminEntityName(adminSeasonsState.olympiads, item.olympiad_id, 'олимпиада не найдена');
        return `
        <div class="${UI.card} px-8 py-6 flex flex-col lg:flex-row lg:items-center gap-5">
            <div class="flex-1 min-w-0">
                <p class="font-bold text-ink">${escHtml(item.season_label)}</p>
                <p class="mt-2 text-sm text-ink-soft">${escHtml(olympiad)}</p>
                ${item.source_doc_id
                    ? `<p class="mt-2 text-xs text-ink-faint">Документ РСОШ: ${escHtml(String(item.source_doc_id))}</p>`
                    : ''}
                ${item.is_archived ? `<div class="mt-2"><span class="${UI.badge} ${UI.badgeNeutral}">В архиве</span></div>` : ''}
            </div>
            <div class="flex items-center gap-3 flex-wrap shrink-0">
                <button data-act="seasonProfiles" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Профили</button>
                <button data-act="editSeason" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Правка</button>
                ${item.is_archived
                    ? `<button data-act="restoreSeason" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Вернуть</button>`
                    : `<button data-act="archiveSeason" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}">В архив</button>`}
            </div>
        </div>`;
    }).join('')}</div>`;
}

function adminProgramsHtml() {
    const programs = adminProgramsState.programs;
    const total = adminProgramsState.total > programs.length ? adminProgramsState.total : programs.length;
    if (!programs.length) {
        return emptyHtml('Программ нет',
            'Программа — самостоятельная запись справочника вуза: направление '
            + 'подготовки, код и описание. Создайте первую программу.',
            `<button data-act="newProgram" class="${UI.btn} ${UI.btnPrimary}">Создать программу</button>`);
    }
    return `
    <div class="flex flex-wrap items-center justify-between gap-6 mb-10">
        <p class="text-sm text-ink-faint">Программ: ${total}</p>
        <button data-act="newProgram" class="${UI.btn} ${UI.btnPrimary}">Создать программу</button>
    </div>
    <div class="space-y-4">${programs.map(item => {
        const university = adminEntityName(adminProgramsState.universities, item.university_id, 'университет не найден');
        return `
        <div class="${UI.card} px-8 py-6 flex flex-col lg:flex-row lg:items-center gap-5">
            <div class="flex-1 min-w-0">
                <p class="font-bold text-ink">${escHtml(item.name)}</p>
                <p class="mt-2 text-sm text-ink-soft">${escHtml(university)}${item.code ? ` · ${escHtml(item.code)}` : ''}</p>
                ${item.description ? `<p class="mt-2 text-sm text-ink-soft">${escHtml(item.description)}</p>` : ''}
                ${item.is_archived ? `<div class="mt-2"><span class="${UI.badge} ${UI.badgeNeutral}">В архиве</span></div>` : ''}
            </div>
            <div class="flex items-center gap-3 flex-wrap shrink-0">
                <button data-act="editProgram" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Правка</button>
                ${item.is_archived
                    ? `<button data-act="restoreProgram" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Вернуть</button>`
                    : `<button data-act="archiveProgram" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}">В архив</button>`}
            </div>
        </div>`;
    }).join('')}</div>`;
}

/** Перерисовать содержимое вкладки после локального обновления состояния. */
function renderAdminContent(html) {
    const box = document.getElementById('admin-content');
    if (box) box.innerHTML = html;
}

const ADMIN_DOC_STATUS_LABELS = {
    UPLOADED: 'Загружен',
    PROCESSING: 'Обрабатывается',
    PROCESSED: 'Обработан',
    NEEDS_REVIEW: 'Требует проверки',
    FAILED: 'Ошибка',
    REJECTED: 'Отклонён',
};

function adminDocsHtml() {
    const { docs, total, search, type, status } = adminDocsState;
    const docTypes = [
        { value: '', label: 'Все типы' },
        { value: 'RSOSH_LIST', label: 'Перечень РСОШ' },
        { value: 'UNIVERSITY_ORDER', label: 'Приказ университета' },
        { value: 'OTHER', label: 'Другой документ' },
        { value: 'RSOSH_TABLE', label: 'Таблица перечня (XLSX)' },
        { value: 'RSOSH_HTML', label: 'Таблица перечня (HTML)' },
    ];
    const statuses = [
        { value: '', label: 'Все статусы' },
        ...Object.entries(ADMIN_DOC_STATUS_LABELS).map(([value, label]) => ({ value, label })),
    ];
    const shown = docs.length;
    const more = shown < total;

    const filter = `
    <div class="flex flex-wrap items-end justify-between gap-4 mb-8">
        <form class="flex flex-wrap items-end gap-3" onsubmit="return false;">
            <label class="sr-only" for="admin-docs-search">Поиск документа</label>
            <input id="admin-docs-search" type="search" value="${escAttr(search || '')}"
                   placeholder="Название документа" class="${UI.input} sm:!w-72 !py-2 text-sm">
            <label class="sr-only" for="admin-docs-type">Тип документа</label>
            <select id="admin-docs-type" data-doc-filter class="${UI.input} sm:!w-56 !py-2 text-sm">
                ${docTypes.map(o => `<option value="${escAttr(o.value)}" ${o.value === type ? 'selected' : ''}>${escHtml(o.label)}</option>`).join('')}
            </select>
            <label class="sr-only" for="admin-docs-status">Статус документа</label>
            <select id="admin-docs-status" data-doc-filter class="${UI.input} sm:!w-52 !py-2 text-sm">
                ${statuses.map(o => `<option value="${escAttr(o.value)}" ${o.value === status ? 'selected' : ''}>${escHtml(o.label)}</option>`).join('')}
            </select>
            <button type="button" data-act="searchDocs" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Найти</button>
        </form>
        <div class="flex items-center gap-3">
            <p class="text-sm text-ink-faint">Показано ${shown} из ${total}</p>
            ${more ? `<button type="button" data-act="loadMoreDocs" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Показать ещё</button>` : ''}
        </div>
    </div>`;

    if (!docs.length) {
        return filter + (search || type || status
            ? emptyHtml('Документов не найдено', 'Измените запрос или сбросьте фильтры.')
            : emptyHtml('Документов нет', 'Документы загружают администратор и представители вузов.'));
    }
    return filter + `<div class="space-y-4">${docs.map(item => {
        const meta = item.metadata || {};
        const rsosh = meta.rsosh || {};
        const plan = rsosh.plan || {};
        const season = rsosh.season_label || plan.season_label || '';
        const author = rsosh.author || item.uploaded_by || '';
        const created = item.createdAt ? new Date(item.createdAt).toLocaleDateString('ru-RU') : '';
        const isHtml = item.type === 'RSOSH_HTML';
        return `
        <div class="${UI.card} px-8 py-6 flex flex-col lg:flex-row lg:items-center gap-5">
            <div class="flex-1 min-w-0">
                <p class="font-bold text-ink">${escHtml(item.name)}</p>
                <p class="mt-2 text-sm text-ink-soft">
                    ${escHtml(docTypeLabel(item.type))} ·
                    ${escHtml(ADMIN_DOC_STATUS_LABELS[item.status] || item.status)}
                    ${season ? ` · учебный год: ${escHtml(season)}` : ''}
                </p>
                <p class="mt-1 text-xs text-ink-faint">
                    ${item.university_id ? 'Документ университета' : 'Общий источник'}
                    ${created ? ` · загружен ${escHtml(created)}` : ''}
                    ${author ? ` · автор: ${escHtml(String(author).slice(0, 8))}` : ''}
                </p>
            </div>
            <div class="shrink-0 flex flex-wrap gap-2">
                ${isHtml ? `<a href="${api.docFileUrl(item.id)}" target="_blank" rel="noopener" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Открыть таблицу</a>` : ''}
                <a href="${api.docFileUrl(item.id)}" target="_blank" rel="noopener" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Скачать</a>
            </div>
        </div>`;
    }).join('')}</div>`;
}

async function searchDocs() {
    const input = document.getElementById('admin-docs-search');
    const typeSelect = document.getElementById('admin-docs-type');
    const statusSelect = document.getElementById('admin-docs-status');
    const search = (input ? input.value : '').trim();
    const type = typeSelect ? typeSelect.value : '';
    const status = statusSelect ? statusSelect.value : '';
    try {
        const res = await api.adminDocs({
            limit: ADMIN_LIST_PAGE_SIZE,
            offset: 0,
            search: search || undefined,
            type: type || undefined,
            status: status || undefined,
        });
        if (!res.ok) { showToast(errorText(res), 'error'); return; }
        const docs = res.data.docs || [];
        adminDocsState = {
            docs,
            total: res.data.total != null ? res.data.total : docs.length,
            search,
            type,
            status,
        };
        renderAdminContent(adminDocsHtml());
    } catch {
        showToast('Не удалось загрузить документы', 'error');
    }
}

async function loadMoreDocs() {
    try {
        const res = await api.adminDocs({
            limit: ADMIN_LIST_PAGE_SIZE,
            offset: adminDocsState.docs.length,
            search: adminDocsState.search || undefined,
            type: adminDocsState.type || undefined,
            status: adminDocsState.status || undefined,
        });
        if (!res.ok) { showToast(errorText(res), 'error'); return; }
        const docs = res.data.docs || [];
        adminDocsState.docs = adminDocsState.docs.concat(docs);
        if (res.data.total != null) adminDocsState.total = res.data.total;
        renderAdminContent(adminDocsHtml());
    } catch {
        showToast('Не удалось загрузить документы', 'error');
    }
}

/* --------------------------- Льготы: фильтры и модерация --------------------------- */

function renderBenefitsBox() {
    const box = document.getElementById('admin-content');
    if (box) box.innerHTML = adminBenefitsHtml();
}

async function searchBenefits() {
    const input = document.getElementById('admin-benefits-search');
    const statusSelect = document.querySelector('[data-benefit-status]');
    const needsReviewBox = document.querySelector('[data-benefit-needs-review]');
    const search = (input ? input.value : '').trim();
    const status = statusSelect ? statusSelect.value : '';
    const needsReview = !!(needsReviewBox && needsReviewBox.checked);
    try {
        const res = await api.adminBenefits({
            limit: ADMIN_LIST_PAGE_SIZE,
            offset: 0,
            search: search || undefined,
            verification_status: status || undefined,
            needs_review: needsReview || undefined,
        });
        if (!res.ok) {
            showToast(errorText(res), 'error');
            return;
        }
        const rules = res.data.rules || [];
        adminBenefitsState.rules = rules;
        adminBenefitsState.total = res.data.total != null ? res.data.total : rules.length;
        adminBenefitsState.search = search;
        adminBenefitsState.status = status;
        adminBenefitsState.needsReview = needsReview;
        renderBenefitsBox();
    } catch {
        showToast('Не удалось загрузить правила льгот', 'error');
    }
}

async function loadMoreBenefits() {
    try {
        const res = await api.adminBenefits({
            limit: ADMIN_LIST_PAGE_SIZE,
            offset: adminBenefitsState.rules.length,
            search: adminBenefitsState.search || undefined,
            verification_status: adminBenefitsState.status || undefined,
            needs_review: adminBenefitsState.needsReview || undefined,
        });
        if (!res.ok) {
            showToast(errorText(res), 'error');
            return;
        }
        adminBenefitsState.rules = adminBenefitsState.rules.concat(res.data.rules || []);
        if (res.data.total != null) adminBenefitsState.total = res.data.total;
        renderBenefitsBox();
    } catch {
        showToast('Не удалось загрузить правила льгот', 'error');
    }
}

function openRejectBenefitModal(id, onDone) {
    let dirty = false;
    const body = `
        <div id="modal-alert"></div>
        <form id="reject-benefit-form">
            ${textareaField({
                id: 'reject-benefit-reason',
                name: 'reason',
                label: 'Причина отклонения',
                rows: 3,
                placeholder: 'Например: условие не подтверждено документом университета',
            })}
            <div class="flex flex-wrap justify-end gap-3 mt-8">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnDanger}">Отклонить</button>
            </div>
        </form>`;
    const { overlay, close } = openModal('Отклонить правило льготы', body, {
        isDirty: () => dirty,
    });
    ['input', 'change'].forEach(ev => overlay.addEventListener(ev, () => { dirty = true; }));
    overlay.querySelector('[data-cancel]').addEventListener('click', close);
    overlay.querySelector('#reject-benefit-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const reason = (fd.get('reason') || '').trim();
        const btn = e.target.querySelector('button[type="submit"]');
        if (!reason) {
            showModalError(overlay, { data: { detail: 'Укажите причину отклонения' } });
            return;
        }
        btn.disabled = true;
        try {
            const res = await api.rejectBenefit(id, { reason });
            if (res.ok) {
                dirty = false;
                close();
                showToast('Правило льготы отклонено', 'success');
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

/* ----------------------------- Сезоны и профили ----------------------------- */

async function openSeasonFormModal(season, onDone) {
    const isEdit = !!season;
    const olympiads = adminSeasonsState.olympiads.slice();
    if (!isEdit && !olympiads.length) {
        showToast('Сначала создайте олимпиаду в каталоге', 'error');
        return;
    }
    if (isEdit && season.olympiad_id && !olympiads.some(item => String(item.id) === String(season.olympiad_id))) {
        olympiads.unshift({ id: season.olympiad_id, name: 'Текущая олимпиада (нет в актуальном списке)' });
    }

    let docs = [];
    try {
        const docsRes = await api.adminDocs({ limit: 200 });
        docs = (docsRes.data && docsRes.data.docs) || [];
    } catch {
        docs = [];
    }
    if (isEdit && season.source_doc_id && !docs.some(item => String(item.id) === String(season.source_doc_id))) {
        docs.unshift({ id: season.source_doc_id, name: 'Текущий документ (нет в списке)' });
    }

    let dirty = false;
    const olympiadOptions = [{ value: '', label: 'Выберите олимпиаду' }]
        .concat(olympiads.map(item => ({ value: item.id, label: item.name })));
    const docOptions = [{ value: '', label: 'Без документа-основания' }]
        .concat(docs.map(item => ({ value: item.id, label: item.name })));
    const seasonYears = academicYearOptions();
    if (isEdit && season.season_label && !seasonYears.includes(season.season_label)) {
        seasonYears.unshift(season.season_label);
    }
    const seasonYearOptions = seasonYears.map(label => ({ value: label, label }));

    const body = `
        <div id="modal-alert"></div>
        <form id="season-form">
            ${isEdit
                ? `<p class="mb-6 text-sm text-ink-soft">Олимпиада: <span class="font-semibold text-ink">${escHtml(adminEntityName(olympiads, season.olympiad_id, 'не найдена'))}</span></p>`
                : selectField({
                    id: 'season-olympiad',
                    name: 'olympiad_id',
                    label: 'Олимпиада',
                    options: olympiadOptions,
                    value: season ? season.olympiad_id : '',
                })}
            ${selectField({
                id: 'season-label',
                name: 'season_label',
                label: 'Учебный год',
                options: seasonYearOptions,
                value: (season || {}).season_label || seasonYearOptions[0].value,
            })}
            <p class="mt-2 mb-4 text-sm text-ink-soft">
                Учебный год начинается в августе: 2026/2027 — с сентября 2026 по август 2027.
                Уровень РСОШ указывается у профиля сезона: у одной олимпиады
                в одном сезоне бывает несколько профилей с разными уровнями.
            </p>
            ${selectField({
                id: 'season-source',
                name: 'source_doc_id',
                label: 'Документ РСОШ (необязательно)',
                options: docOptions,
                value: (season || {}).source_doc_id || '',
            })}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">${isEdit ? 'Сохранить' : 'Создать сезон'}</button>
            </div>
        </form>`;
    const { overlay, close } = openModal(
        isEdit ? 'Редактирование сезона' : 'Новый сезон',
        body,
        { wide: true, isDirty: () => dirty }
    );
    ['input', 'change'].forEach(ev => overlay.addEventListener(ev, () => { dirty = true; }));
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    overlay.querySelector('#season-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const btn = e.target.querySelector('button[type="submit"]');
        const seasonLabel = (fd.get('season_label') || '').trim();
        if (!seasonLabel) {
            showModalError(overlay, { data: { detail: 'Укажите метку сезона' } });
            return;
        }
        const payload = {
            season_label: seasonLabel,
            source_doc_id: (fd.get('source_doc_id') || '') || null,
        };
        const olympiadId = isEdit ? season.olympiad_id : fd.get('olympiad_id');
        if (!olympiadId) {
            showModalError(overlay, { data: { detail: 'Выберите олимпиаду' } });
            return;
        }
        btn.disabled = true;
        try {
            const res = isEdit
                ? await api.updateSeason(season.id, { ...payload, version: season.version })
                : await api.createSeason(olympiadId, payload);
            if (res.ok) {
                dirty = false;
                close();
                showToast(isEdit ? 'Сезон обновлён' : 'Сезон создан', 'success');
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

async function openSeasonProfilesModal(seasonId, onChange) {
    const season = adminSeasonsState.seasons.find(item => String(item.id) === String(seasonId));
    const title = season ? `Профили сезона «${season.season_label}»` : 'Профили сезона';
    const body = `
        <div id="season-profiles-list">${loadingHtml('Загружаем профили…')}</div>
        <div class="mt-10 pt-8 border-t border-mist">
            <h3 id="profile-form-title" class="text-lg font-bold tracking-tight">Новый профиль</h3>
            <form id="profile-form" class="mt-6">
                <div id="modal-alert"></div>
                <input type="hidden" name="profile_id" value="">
                ${inputField({ id: 'profile-name', name: 'name', label: 'Название профиля', required: true, placeholder: 'Математика' })}
                ${selectField({
                    id: 'profile-level',
                    name: 'rsosh_level',
                    label: 'Уровень РСОШ',
                    options: [
                        { value: '', label: 'Не указан' },
                        { value: '1', label: 'Уровень 1' },
                        { value: '2', label: 'Уровень 2' },
                        { value: '3', label: 'Уровень 3' },
                    ],
                    value: '',
                })}
                ${textareaField({ id: 'profile-description', name: 'description', label: 'Описание', rows: 2 })}
                <div class="flex flex-wrap justify-end gap-3">
                    <button type="button" data-profile-reset class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Сбросить</button>
                    <button type="submit" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Добавить профиль</button>
                </div>
            </form>
        </div>`;
    const { overlay, close } = openModal(title, body, { wide: true });

    let profiles = [];
    const form = overlay.querySelector('#profile-form');
    const submitBtn = form.querySelector('button[type="submit"]');
    const titleEl = overlay.querySelector('#profile-form-title');
    let editing = null;

    function resetForm() {
        editing = null;
        form.reset();
        form.querySelector('[name="profile_id"]').value = '';
        submitBtn.textContent = 'Добавить профиль';
        titleEl.textContent = 'Новый профиль';
    }

    overlay.querySelector('[data-profile-reset]').addEventListener('click', resetForm);

    async function refreshProfiles() {
        const box = overlay.querySelector('#season-profiles-list');
        if (!box) return;
        const res = await api.listProfiles(seasonId);
        if (!res.ok) {
            box.innerHTML = alertHtml(errorText(res), 'error');
            return;
        }
        profiles = (res.data && res.data.profiles) || [];
        if (!profiles.length) {
            box.innerHTML = '<p class="text-sm text-ink-soft">Профилей пока нет. Профиль — это название и уровень РСОШ, причём уровень принадлежит конкретному сезону.</p>';
            return;
        }
        box.innerHTML = `<div class="space-y-3">${profiles.map(item => `
            <div class="bg-mist rounded px-5 py-4 flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div class="min-w-0">
                    <p class="font-semibold text-ink">${escHtml(item.name)}</p>
                    <p class="mt-1 text-sm text-ink-soft">${item.rsosh_level ? `Уровень РСОШ: ${escHtml(item.rsosh_level)}` : 'Уровень РСОШ не указан'}</p>
                    ${item.description ? `<p class="mt-1 text-sm text-ink-soft">${escHtml(item.description)}</p>` : ''}
                </div>
                <div class="flex items-center gap-2 shrink-0">
                    <button type="button" data-profile-edit="${escAttr(item.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Изменить</button>
                    <button type="button" data-profile-delete="${escAttr(item.id)}" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}">Удалить</button>
                </div>
            </div>`).join('')}</div>`;

        box.querySelectorAll('[data-profile-edit]').forEach(btn => {
            btn.addEventListener('click', () => {
                const item = profiles.find(p => String(p.id) === btn.dataset.profileEdit);
                if (!item) return;
                editing = item;
                form.querySelector('[name="profile_id"]').value = item.id;
                form.querySelector('[name="name"]').value = item.name || '';
                form.querySelector('[name="rsosh_level"]').value = item.rsosh_level || '';
                form.querySelector('[name="description"]').value = item.description || '';
                submitBtn.textContent = 'Сохранить профиль';
                titleEl.textContent = `Профиль «${item.name}»`;
                form.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            });
        });
        box.querySelectorAll('[data-profile-delete]').forEach(btn => {
            btn.addEventListener('click', async () => {
                const item = profiles.find(p => String(p.id) === btn.dataset.profileDelete);
                if (!item) return;
                if (!window.confirm(`Удалить профиль «${item.name}»?\n\nПравила, привязанные к нему, останутся и будут отмечены как требующие уточнения.`)) return;
                btn.disabled = true;
                const res = await api.deleteProfile(item.id);
                if (!res.ok) {
                    showModalError(overlay, res);
                    btn.disabled = false;
                    return;
                }
                if (editing && String(editing.id) === String(item.id)) resetForm();
                showToast('Профиль удалён', 'success');
                await refreshProfiles();
                if (onChange) onChange();
            });
        });
    }

    form.addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(form);
        const name = (fd.get('name') || '').trim();
        if (!name) {
            showModalError(overlay, { data: { detail: 'Укажите название профиля' } });
            return;
        }
        const payload = {
            name,
            rsosh_level: (fd.get('rsosh_level') || '').trim() || null,
            description: (fd.get('description') || '').trim() || null,
        };
        submitBtn.disabled = true;
        try {
            const wasEdit = !!editing;
            const res = editing
                ? await api.updateProfile(editing.id, { ...payload, version: editing.version })
                : await api.createProfile(seasonId, payload);
            if (res.ok) {
                resetForm();
                showToast(wasEdit ? 'Профиль обновлён' : 'Профиль добавлен', 'success');
                await refreshProfiles();
                if (onChange) onChange();
            } else {
                showModalError(overlay, res);
            }
        } catch {
            showModalError(overlay, { data: { detail: 'Сетевая ошибка' } });
        }
        submitBtn.disabled = false;
    });

    await refreshProfiles();
}

/* -------------------------------- Программы -------------------------------- */

async function openAdminProgramFormModal(program, onDone) {
    const isEdit = !!program;
    const universities = adminProgramsState.universities.slice();
    if (!isEdit && !universities.length) {
        showToast('Сначала создайте университет', 'error');
        return;
    }
    if (isEdit && program.university_id && !universities.some(item => String(item.id) === String(program.university_id))) {
        universities.unshift({ id: program.university_id, name: 'Текущий университет (нет в списке)' });
    }
    let dirty = false;
    const options = [{ value: '', label: 'Выберите университет' }]
        .concat(universities.map(item => ({ value: item.id, label: item.short_name || item.name })));
    const body = `
        <div id="modal-alert"></div>
        <form id="program-form">
            ${isEdit
                ? `<p class="mb-6 text-sm text-ink-soft">Университет: <span class="font-semibold text-ink">${escHtml(adminEntityName(universities, program.university_id, 'не найден'))}</span></p>`
                : selectField({
                    id: 'program-university',
                    name: 'university_id',
                    label: 'Университет',
                    options,
                    value: '',
                })}
            ${inputField({
                id: 'program-name',
                name: 'name',
                label: 'Название программы',
                required: true,
                value: (program || {}).name || '',
                placeholder: 'Прикладная математика и информатика',
            })}
            ${inputField({
                id: 'program-code',
                name: 'code',
                label: 'Код направления',
                value: (program || {}).code || '',
                placeholder: '01.03.02',
            })}
            ${textareaField({
                id: 'program-description',
                name: 'description',
                label: 'Описание',
                value: (program || {}).description || '',
                rows: 3,
            })}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">${isEdit ? 'Сохранить' : 'Создать программу'}</button>
            </div>
        </form>`;
    const { overlay, close } = openModal(
        isEdit ? 'Редактирование программы' : 'Новая программа',
        body,
        { wide: true, isDirty: () => dirty }
    );
    ['input', 'change'].forEach(ev => overlay.addEventListener(ev, () => { dirty = true; }));
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    overlay.querySelector('#program-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const btn = e.target.querySelector('button[type="submit"]');
        const name = (fd.get('name') || '').trim();
        const universityId = isEdit ? program.university_id : (fd.get('university_id') || '');
        if (!name) {
            showModalError(overlay, { data: { detail: 'Укажите название программы' } });
            return;
        }
        if (!universityId) {
            showModalError(overlay, { data: { detail: 'Выберите университет' } });
            return;
        }
        const payload = {
            name,
            code: (fd.get('code') || '').trim() || null,
            description: (fd.get('description') || '').trim() || null,
        };
        btn.disabled = true;
        try {
            const res = isEdit
                ? await api.updateProgram(program.id, { ...payload, version: program.version })
                : await api.createProgram(universityId, payload);
            if (res.ok) {
                dirty = false;
                close();
                showToast(isEdit ? 'Программа обновлена' : 'Программа создана', 'success');
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
