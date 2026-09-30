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
    'newImport', 'runImport', 'previewImport', 'confirmImport', 'rejectImport',
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
        grant: () => api.grantAdmin(id),
        demote: () => api.demoteAdmin(id),
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
        previewImport: () => showImportPreview(id),
        confirmImport: () => confirmImportAction(id),
        rejectImport: () => rejectImportAction(id),
    };

    const messages = {
        ban: 'Пользователь заблокирован',
        unban: 'Пользователь разблокирован',
        grant: 'Назначена роль администратора',
        demote: 'Роль администратора снята',
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
    // - администратору привязка не мешает, но она нужна, чтобы demote вернул
    //   его в представители, а не в обычные пользователи. Поэтому при
    //   назначении ADMIN не обнуляем то, что уже выбрано.
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
                <div class="flex items-center gap-5 flex-1 min-w-0">
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
                <div class="flex flex-col sm:flex-row sm:items-center gap-3 shrink-0 xl:justify-end">
                    <label class="sr-only" for="role-${escAttr(u.id)}">Роль: ${escHtml(u.email)}</label>
                    <select id="role-${escAttr(u.id)}" data-role-for="${escAttr(u.id)}" class="${UI.input} !w-auto !py-2 text-sm">
                        ${Object.keys(ROLE_LABELS).map(role =>
                            `<option value="${role}" ${u.role === role ? 'selected' : ''}>${ROLE_LABELS[role]}</option>`).join('')}
                    </select>
                    <label class="sr-only" for="university-${escAttr(u.id)}">Университет: ${escHtml(u.email)}</label>
                    <select id="university-${escAttr(u.id)}" data-university-for="${escAttr(u.id)}"
                            class="${UI.input} !w-auto !py-2 text-sm"
                            ${u.role === 'EDITOR' ? '' : 'disabled title="Университет назначается представителю"'}>
                        <option value="">Без университета</option>
                        ${universityOptions}
                    </select>
                    <button type="button" data-act="saveRole" data-id="${escAttr(u.id)}" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}"
                            ${isLastAdmin ? lockedAttrs : ''}>
                        Сохранить роль
                    </button>
                    <button type="button" data-act="${u.role === 'ADMIN' ? 'demote' : 'grant'}" data-id="${escAttr(u.id)}"
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
                    <button data-act="previewImport" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Результат</button>
                </div>
            </div>
            <div class="mt-6 flex flex-wrap gap-3">
                <a href="${escAttr(api.docFileUrl(item.id))}" target="_blank" rel="noopener noreferrer" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Скачать документ</a>
                <button data-act="confirmImport" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Подтвердить импорт</button>
                <button data-act="rejectImport" data-id="${escAttr(item.id)}" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}">Отклонить</button>
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

async function rejectImportAction(id) {
    const res = await api.rejectImport(id);
    if (res.ok) {
        showToast('Результаты импорта отклонены', 'success');
        await loadAdminTab('imports');
        return;
    }
    showToast(errorText(res), 'error');
}

async function confirmImportAction(id) {
    const res = await api.confirmImport(id, { skip: [], archive_missing: true });
    if (!res.ok) {
        showToast(errorText(res), 'error');
        return;
    }
    const result = res.data.result || {};
    showToast(
        `Импорт применён: создано ${(result.created || []).length}, обновлено ${(result.updated || []).length}, в архив ${(result.archived || []).length}`,
        'success', 6000);
    await loadAdminTab('imports');
}

async function showImportPreview(id) {
    const body = `<div id="modal-alert"></div><div id="preview-body">${loadingHtml('Готовим preview…')}</div>
        <div class="flex flex-wrap justify-end gap-3 mt-10">
            <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Закрыть</button>
        </div>`;
    const { overlay, close } = openModal('Результат импорта РСОШ', body, { wide: true });
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    const target = overlay.querySelector('#preview-body');
    const res = await api.importPreview(id);
    if (!res.ok) {
        target.innerHTML = alertHtml(errorText(res), 'error');
        return;
    }

    const data = res.data;
    const imp = data.import || {};
    const candidates = data.candidates || [];
    const pages = data.pages || [];

    const pagesHtml = pages.length ? `
    <div class="mb-8">
        <p class="${UI.eyebrow}">Страницы</p>
        <ul class="mt-4 space-y-2 text-sm text-ink-soft">
            ${pages.map(p => `<li>стр. ${p.page}: ${escHtml(p.method)}, таблиц ${p.tables}, строк ${p.rows}, уверенность ${p.confidence}${p.orientation ? `, поворот ${p.orientation}°` : ''}</li>`).join('')}
        </ul>
    </div>` : '';

    const warningsHtml = (imp.warnings || []).length ? `
    <div class="mb-8">${alertHtml((imp.warnings || []).join(' · '), 'error')}</div>` : '';

    const rowsHtml = candidates.length
        ? `<div class="space-y-3">${candidates.map(c => `
            <div class="${UI.card} px-6 py-5">
                <div class="flex flex-wrap items-center gap-3">
                    ${c.action === 'create'
                        ? `<span class="${UI.badge} ${UI.badgeSuccess}">Новая</span>`
                        : `<span class="${UI.badge} ${UI.badgeNeutral}">Объединить</span>`}
                    ${c.confidence === 'review' ? `<span class="${UI.badge} ${UI.badgeDanger}">Нужна проверка</span>` : ''}
                    ${c.page ? `<span class="text-xs text-ink-faint">стр. ${c.page}</span>` : ''}
                </div>
                <p class="mt-3 font-semibold text-ink leading-snug">${escHtml(c.name)}</p>
                ${c.issues && c.issues.length ? `<p class="mt-2 text-sm text-ink-soft">${escHtml(c.issues.join(' · '))}</p>` : ''}
            </div>`).join('')}</div>`
        : `<p class="py-12 text-center text-ink-soft">Кандидатов нет</p>`;

    target.innerHTML = `
    <p class="text-sm text-ink-soft mb-8">
        Состояние: ${escHtml(IMPORT_STATE_LABELS[imp.state] || imp.state || '—')}.
        В каталог ничего не записано: запись произойдёт только после подтверждения.
    </p>
    ${imp.error ? alertHtml(imp.error, 'error') : ''}
    ${warningsHtml}
    ${pagesHtml}
    <p class="${UI.eyebrow}">Кандидаты (${candidates.length})</p>
    <div class="mt-6">${rowsHtml}</div>`;
}
