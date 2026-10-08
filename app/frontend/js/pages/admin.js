/* ==========================================================================
 * pages/admin.js — панель администратора Papaya.
 *
 *   #/admin/users       пользователи: роли, блокировки, привязка к университету
 *   #/admin/olympiads   каталог олимпиад: правка, архив, ручное создание
 *   #/admin/universities каталог университетов
 *   #/admin/bvi         заявки университетов на связи БВИ
 *   #/admin/imports     документы РСОШ: загрузка, импорт, preview, подтверждение
 * ========================================================================== */

const ADMIN_TABS = [
    { key: 'users', label: 'Пользователи', href: '#/admin/users' },
    { key: 'olympiads', label: 'Олимпиады', href: '#/admin/olympiads' },
    { key: 'universities', label: 'Университеты', href: '#/admin/universities' },
    { key: 'bvi', label: 'Заявки БВИ', href: '#/admin/bvi' },
    { key: 'imports', label: 'Импорт РСОШ', href: '#/admin/imports' },
];

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
        users: async () => (await api.adminUsers()).data.users || [],
        olympiads: async () => (await api.adminOlympiads()).data.olympiads || [],
        universities: async () => (await api.listUniversities()).data.universities || [],
        bvi: async () => (await api.adminBviLinks()).data.links || [],
        imports: async () => (await api.listImports()).data.imports || [],
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
        box.innerHTML = adminUsersHtml(data, universities.data.universities || []);
        return;
    }

    const renderers = {
        olympiads: adminOlympiadsHtml,
        universities: adminUniversitiesHtml,
        bvi: adminBviHtml,
        imports: adminImportsHtml,
    };
    box.innerHTML = renderers[tab](data);
}

/* Действия, которые открывают модалку или сами показывают результат. */
const ADMIN_SIDE_EFFECT_ACTIONS = new Set([
    'newUniversity', 'editUniversity', 'newOlympiad', 'editOlympiad',
    'newImport', 'runImport', 'previewImport',
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
        toggleAdmin: () => toggleAdminRole(id),
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
    };

    const messages = {
        ban: 'Пользователь заблокирован',
        unban: 'Пользователь разблокирован',
        toggleAdmin: 'Роль администратора изменена',
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

/**
 * Быстрые кнопки «Сделать админом» / «Снять админа».
 *
 * Отдельных маршрутов для этого в API нет и не должно быть: роль меняется
 * только через `/admin/role/{user_id}`, вместе с привязкой к университету.
 * Кнопка лишь подставляет целевую роль в тот же запрос.
 *
 * Куда попадает человек после снятия ADMIN, выводится из уже выбранного в
 * строке университета, а не из отдельной таблицы на клиенте: университет
 * выбирается только для EDITOR (см. handleAdminChange), поэтому «привязан =
 * EDITOR» уже следует из состояния формы. Инвариант проверяет сервер — если
 * подстановка окажется неверной, придёт 400, а не повреждённые права.
 */
async function toggleAdminRole(userId) {
    const roleSelect = document.querySelector(`[data-role-for="${CSS.escape(userId)}"]`);
    const universitySelect = document.querySelector(`[data-university-for="${CSS.escape(userId)}"]`);
    if (!roleSelect || !universitySelect) return;

    const isAdmin = roleSelect.value === 'ADMIN';
    const universityId = universitySelect.value || null;
    const role = isAdmin ? (universityId ? 'EDITOR' : 'USER') : 'ADMIN';
    const targetUniversity = role === 'USER' ? null : universityId;

    const res = await api.setUserRole(userId, role, targetUniversity);
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

function adminUsersHtml(users, universities) {
    if (!users.length) return emptyHtml('Пользователей нет', 'Зарегистрируйте первого пользователя.');
    const selfId = store.user ? store.user.id : null;
    // Активных администраторов может быть один: последнего нельзя понизить или
    // заблокировать — иначе зайти в панель будет некому. Сервер проверяет это
    // правило (ошибка 409), здесь кнопки просто не предлагают действие.
    const activeAdmins = users.filter(item => item.role === 'ADMIN' && item.isActive).length;

    return `<p class="text-sm text-ink-faint mb-6">Всего: ${users.length}</p>
    <div class="space-y-6">
        ${users.map(u => {
            const isSelf = String(u.id) === String(selfId);
            const isLastAdmin = u.role === 'ADMIN' && u.isActive && activeAdmins === 1;
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
                    <select id="role-${escAttr(u.id)}" data-role-for="${escAttr(u.id)}" class="${UI.input} sm:!w-auto sm:max-w-[11rem] !py-2 text-sm">
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
                    <button type="button" data-act="toggleAdmin" data-id="${escAttr(u.id)}"
                            class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}"
                            ${u.role === 'ADMIN' ? lockedAttrs : ''}>
                        ${u.role === 'ADMIN' ? 'Снять админа' : 'Сделать админом'}
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

/* -------------------------------- Олимпиады -------------------------------- */

function adminOlympiadsHtml(olympiads) {
    if (!olympiads.length) {
        return emptyHtml('Каталог олимпиад пуст',
            'Добавьте олимпиаду вручную или импортируйте документ РСОШ.',
            `<button data-act="newOlympiad" class="${UI.btn} ${UI.btnPrimary}">Создать олимпиаду</button>`);
    }
    return `
    <div class="flex flex-wrap items-center justify-between gap-6 mb-10">
        <p class="text-sm text-ink-faint">Всего: ${olympiads.length}</p>
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

/* --------------------------------- БВИ ------------------------------------ */

function adminBviHtml(links) {
    if (!links.length) {
        return emptyHtml('Заявок нет', 'Представители университетов ещё не заявляли связи БВИ.');
    }
    return `<p class="text-sm text-ink-faint mb-6">Заявок и подтверждённых связей: ${links.length}</p>
    <div class="space-y-6">
        ${links.map(link => `
        <div class="${UI.card} px-8 py-7 flex flex-col lg:flex-row lg:items-center gap-6">
            <div class="flex-1 min-w-0">
                <p class="font-bold text-ink leading-snug">${escHtml(link.university_name || 'Университет')}</p>
                <p class="mt-2 text-ink-soft">${escHtml(link.olympiad_name || 'Олимпиада')}</p>
            </div>
            <div class="flex items-center gap-3 flex-wrap shrink-0">
                ${bviStatusBadge(link.status)}
                ${link.status === 'CONFIRMED'
                    ? `<button data-act="rejectBvi" data-university="${escAttr(link.university_id)}" data-id="${escAttr(link.olympiad_id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Удалить связь</button>
                       <button data-act="revokeBvi" data-university="${escAttr(link.university_id)}" data-id="${escAttr(link.olympiad_id)}" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}">Отозвать подтверждение</button>`
                    : `<button data-act="rejectBvi" data-university="${escAttr(link.university_id)}" data-id="${escAttr(link.olympiad_id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Отклонить</button>
                       <button data-act="confirmBvi" data-university="${escAttr(link.university_id)}" data-id="${escAttr(link.olympiad_id)}" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Подтвердить</button>`}
            </div>
        </div>`).join('')}
    </div>`;
}

/* ------------------------------ Импорт РСОШ ------------------------------- */

const IMPORT_STATE_LABELS = {
    processing: 'Обрабатывается…',
    review: 'Готов к подтверждению',
    approved: 'Применён',
    rejected: 'Отклонён',
    failed: 'Ошибка',
};

function adminImportsHtml(imports) {
    return `
    <div class="flex flex-wrap items-center justify-between gap-6 mb-10">
        <p class="text-sm text-ink-faint">Документов РСОШ: ${imports.length}</p>
        <button data-act="newImport" class="${UI.btn} ${UI.btnPrimary}">Загрузить документ РСОШ</button>
    </div>
    ${imports.length ? `<div class="space-y-6">${imports.map(item => {
        const state = item.state || '—';
        const summary = item.summary || {};
        return `
        <div class="${UI.card} px-8 py-7">
            <div class="flex flex-col lg:flex-row lg:items-center gap-6">
                <div class="flex-1 min-w-0">
                    <p class="font-bold text-ink leading-snug">${escHtml(item.name)}</p>
                    <p class="mt-2 text-sm text-ink-soft">
                        Статус документа: ${escHtml(item.status)} ·
                        ${escHtml(IMPORT_STATE_LABELS[state] || state)}
                        ${summary.total ? ` · найдено: ${summary.total} (новых: ${summary.new || 0}, объединений: ${summary.merge || 0}, на проверку: ${summary.review || 0})` : ''}
                    </p>
                    ${item.error ? `<p class="mt-3 text-sm text-crimson">${escHtml(item.error)}</p>` : ''}
                </div>
                <div class="flex flex-wrap gap-3 shrink-0">
                    <button data-act="runImport" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Запустить импорт</button>
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
            `<button data-act="newImport" class="${UI.btn} ${UI.btnPrimary}">Загрузить документ</button>`)}`;
}

function openUploadModal() {
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
    const { overlay, close } = openModal('Документ РСОШ', body);
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
            </div>`;
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
        for (const c of candidates) {
            if (!confirmedKeys.has(c.name_norm) || excluded.has(c.name_norm)) continue;
            if (merges[c.name_norm] || (c.action === 'merge' && c.matched_olympiad_id)) merged++;
            else fresh++;
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
        const { overlay, close } = openModal('Редактирование олимпиады', body, { size: 'lg' });
        overlay.querySelector('[data-ri-close]').addEventListener('click', close);
        overlay.querySelector('[data-ri-save]').addEventListener('click', () => {
            applyCandidateEdit(overlay, key);
            close();
            refresh();
        });
        overlay.querySelector('#ri-edit-form').addEventListener('submit', e => {
            e.preventDefault();
            applyCandidateEdit(overlay, key);
            close();
            confirmedKeys.add(key);
            excluded.delete(key);
            refresh();
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
                <p class="text-ink-soft">Каталог не изменён. Запустите импорт заново, чтобы вернуть результаты на проверку.</p>
            </div>`;
        }
        if (state === 'failed') {
            return `<div class="rounded bg-sand/50 px-6 py-4 mb-8 text-sm leading-relaxed" role="status">
                <p class="font-semibold text-ink mb-1">Импорт завершился ошибкой</p>
                <p class="text-ink-soft">Каталог не изменён. Запустите импорт заново — обработка начинается с начала.</p>
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
        const s = stats();
        const stat = (label, value) => `
        <div class="bg-white rounded px-5 py-4 shadow-elev-1">
            <p class="${UI.eyebrow} mb-1">${escHtml(label)}</p>
            <p class="text-3xl font-extrabold tabular-nums">${value}</p>
        </div>`;
        return `
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            ${stat('Распознано', s.total)}
            ${stat('Объединено', s.merged)}
            ${stat('Новых', s.fresh)}
            ${stat('Малодостоверных', s.lowConf)}
        </div>`;
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
            : `<div class="mt-4">${emptyHtml('Результатов нет', 'Для этого прогона кандидаты не сохранены.')}</div>`}`}`;
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

        if (act === 'confirm') { confirmedKeys.add(key); excluded.delete(key); refresh(); }
        else if (act === 'unconfirm') { confirmedKeys.delete(key); refresh(); }
        else if (act === 'delete') { confirmedKeys.delete(key); excluded.add(key); refresh(); }
        else if (act === 'edit') { openCandidateEdit(key); }
        else if (act === 'confirmAll') { confirmAll(); refresh(); }
        else if (act === 'sort-order') { sortMode = 'order'; refresh(); }
        else if (act === 'sort-confidence') { sortMode = 'confidence'; refresh(); }
        else if (act === 'apply') { void doApply(); }
        else if (act === 'reject') { void doReject(); }
    });

    container.addEventListener('input', e => {
        const input = e.target.closest('[data-ri="search"]');
        if (input) {
            query = input.value;
            refreshLists();
        }
    });
}
