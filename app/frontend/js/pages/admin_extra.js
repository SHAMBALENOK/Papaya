const REP_APP_STATUS_LABELS = {
    pending: 'На рассмотрении',
    approved: 'Одобрена',
    rejected: 'Отклонена',
};

function repAppStatusBadge(status) {
    if (status === 'approved') {
        return `<span class="${UI.badge} ${UI.badgeSuccess}">Одобрена</span>`;
    }
    if (status === 'rejected') {
        return `<span class="${UI.badge} ${UI.badgeDanger}">Отклонена</span>`;
    }
    return `<span class="${UI.badge} ${UI.badgePending}">На рассмотрении</span>`;
}

function adminRepAppsHtml(items) {
    const statuses = [
        { value: '', label: 'Все заявки' },
        { value: 'pending', label: 'На рассмотрении' },
        { value: 'approved', label: 'Одобренные' },
        { value: 'rejected', label: 'Отклонённые' },
    ];
    const filter = `
    <div class="flex flex-wrap items-end justify-between gap-4 mb-8">
        <form class="flex flex-wrap items-end gap-3" onsubmit="return false;">
            <label class="sr-only" for="admin-repapps-status">Статус заявки</label>
            <select id="admin-repapps-status" data-repapp-status class="${UI.input} sm:!w-64 !py-2 text-sm">
                ${statuses.map(o => `<option value="${escAttr(o.value)}" ${o.value === adminRepAppsStatus ? 'selected' : ''}>${escHtml(o.label)}</option>`).join('')}
            </select>
        </form>
        <p class="text-sm text-ink-faint">Заявок: ${items.length}</p>
    </div>`;

    if (!items.length) {
        return filter + (adminRepAppsStatus
            ? emptyHtml('Заявок с таким статусом нет', 'Выберите другой статус или покажите все заявки.')
            : emptyHtml('Заявок нет',
                'Пользователь может подать заявку из своего профиля, выбрав университет.'));
    }

    return filter + `
    <div class="space-y-4">
        ${items.map(a => `
            <article class="${UI.card} px-8 py-6">
                <div class="flex flex-col lg:flex-row lg:items-start justify-between gap-5">
                    <div class="min-w-0 flex-1">
                        <div class="flex flex-wrap items-center gap-3">
                            <p class="font-bold text-ink">${escHtml(a.user_name || 'Пользователь')}</p>
                            ${repAppStatusBadge(a.status)}
                        </div>
                        <p class="mt-2 text-sm text-ink-soft">${escHtml(a.user_email || 'email не указан')}</p>
                        <p class="mt-1 text-sm text-ink-soft">Университет: ${escHtml(a.university_name || 'не найден')}</p>
                        <p class="mt-1 text-xs text-ink-faint">Подана: ${formatDate(a.createdAt)}${a.reviewed_at ? ` · рассмотрена: ${formatDate(a.reviewed_at)}` : ''}</p>
                        ${a.justification ? `<p class="mt-3 text-sm text-ink leading-relaxed whitespace-pre-wrap">${escHtml(a.justification)}</p>` : ''}
                        ${attachmentLinksHtml(a.attachments, 'Документы заявителя')}
                        ${a.rejection_reason ? `<p class="mt-3 text-sm text-ink-soft">Причина отклонения: ${escHtml(a.rejection_reason)}</p>` : ''}
                    </div>
                    ${a.status === 'pending' ? `
                    <div class="flex flex-wrap gap-2 shrink-0">
                        <button class="admin-action ${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}" data-act="approveRepApp" data-id="${escAttr(a.id)}">Одобрить</button>
                        <button class="admin-action ${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}" data-act="rejectRepApp" data-id="${escAttr(a.id)}">Отклонить</button>
                    </div>` : ''}
                </div>
            </article>`).join('')}
    </div>`;
}

async function filterRepApps() {
    const select = document.querySelector('[data-repapp-status]');
    adminRepAppsStatus = select ? select.value : '';
    await loadAdminTab('repapps');
}

function openRejectRepAppModal(id, onDone) {
    let dirty = false;
    const body = `
        <div id="modal-alert"></div>
        <form id="reject-repapp-form">
            ${textareaField({
                id: 'reject-repapp-reason',
                name: 'reason',
                label: 'Причина отклонения',
                rows: 3,
                placeholder: 'Например: не удалось подтвердить, что пользователь представляет университет',
            })}
            <div class="flex flex-wrap justify-end gap-3 mt-8">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnDanger}">Отклонить заявку</button>
            </div>
        </form>`;
    const { overlay, close } = openModal('Отклонить заявку представителя', body, {
        isDirty: () => dirty,
    });
    ['input', 'change'].forEach(ev => overlay.addEventListener(ev, () => { dirty = true; }));
    overlay.querySelector('[data-cancel]').addEventListener('click', close);
    overlay.querySelector('#reject-repapp-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const btn = e.target.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
            const res = await api.reviewRepresentativeApplication(id, {
                status: 'rejected',
                rejection_reason: (fd.get('reason') || '').trim() || null,
            });
            if (res.ok) {
                dirty = false;
                close();
                showToast('Заявка отклонена', 'success');
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

const AUDIT_ENTITY_TYPES = [
    { value: 'benefit_rule', label: 'Правила льгот' },
    { value: 'university', label: 'Университеты' },
    { value: 'olympiad', label: 'Олимпиады' },
    { value: 'olympiad_season', label: 'Сезоны' },
    { value: 'season_profile', label: 'Профили сезонов' },
    { value: 'program', label: 'Программы' },
    { value: 'university_program', label: 'Программы' },
    { value: 'entity_request', label: 'Запросы в каталог' },
    { value: 'doc', label: 'Документы' },
    { value: 'import', label: 'Импорт' },
    { value: 'representative_application', label: 'Заявки представителей' },
    { value: 'user', label: 'Пользователи' },
];

const AUDIT_ACTIONS = [
    { value: 'create', label: 'Создание' },
    { value: 'update', label: 'Правка' },
    { value: 'delete', label: 'Удаление' },
    { value: 'verify', label: 'Подтверждение' },
    { value: 'reject', label: 'Отклонение' },
    { value: 'approve', label: 'Одобрение' },
    { value: 'status_change', label: 'Смена статуса' },
    { value: 'rollback', label: 'Откат версии' },
    { value: 'archive', label: 'Архив' },
    { value: 'restore', label: 'Возврат из архива' },
    { value: 'upload', label: 'Загрузка' },
    { value: 'start', label: 'Запуск импорта' },
    { value: 'confirm', label: 'Подтверждение импорта' },
    { value: 'review', label: 'Рассмотрение заявки' },
    { value: 'bulk_create', label: 'Массовое создание' },
    { value: 'role_change', label: 'Смена роли' },
    { value: 'ban', label: 'Блокировка' },
    { value: 'unban', label: 'Разблокировка' },
];

const AUDIT_ENTITY_LABELS = Object.fromEntries(
    AUDIT_ENTITY_TYPES.map(item => [item.value, item.label])
);
const AUDIT_ACTION_LABELS = Object.fromEntries(
    AUDIT_ACTIONS.map(item => [item.value, item.label])
);

function auditEntityLabel(type) {
    return AUDIT_ENTITY_LABELS[type] || type || 'Объект';
}

function auditActionLabel(action) {
    return AUDIT_ACTION_LABELS[action] || action || 'Действие';
}

/** Название объекта из снимка аудита — вместо голого UUID. */
function auditEntityName(log) {
    const after = log.after || {};
    const before = log.before || {};
    return after.name || after.short_name || after.season_label
        || after.university_name || after.profile_name
        || before.name || before.short_name || before.season_label
        || '';
}

function auditDetails(log) {
    const after = log.after || {};
    if (log.action === 'bulk_create') {
        const profiles = (after.profiles || []).join(', ');
        return [
            after.season_label ? `сезон ${after.season_label}` : '',
            after.created != null ? `создано ${after.created}` : '',
            after.skipped != null ? `пропущено ${after.skipped}` : '',
            profiles ? `профили: ${profiles}` : '',
        ].filter(Boolean).join(' · ');
    }
    if (log.action === 'role_change') {
        const oldRole = (log.before || {}).role || '—';
        const newRole = after.role || '—';
        return `роль: ${oldRole} → ${newRole}`;
    }
    return '';
}


function adminAuditHtml() {
    const { logs, total, entityType, action } = adminAuditState;
    const more = logs.length < total;
    const filter = `
    <div class="flex flex-wrap items-end justify-between gap-4 mb-8">
        <form class="flex flex-wrap items-end gap-3" onsubmit="return false;">
            <label class="sr-only" for="admin-audit-entity">Тип сущности</label>
            <select id="admin-audit-entity" data-audit-filter class="${UI.input} sm:!w-56 !py-2 text-sm">
                <option value="">Все сущности</option>
                ${AUDIT_ENTITY_TYPES.map(o => `<option value="${escAttr(o.value)}" ${o.value === entityType ? 'selected' : ''}>${escHtml(o.label)}</option>`).join('')}
            </select>
            <label class="sr-only" for="admin-audit-action">Действие</label>
            <select id="admin-audit-action" data-audit-filter class="${UI.input} sm:!w-56 !py-2 text-sm">
                <option value="">Все действия</option>
                ${AUDIT_ACTIONS.map(o => `<option value="${escAttr(o.value)}" ${o.value === action ? 'selected' : ''}>${escHtml(o.label)}</option>`).join('')}
            </select>
        </form>
        <div class="flex items-center gap-3">
            <p class="text-sm text-ink-faint">Показано ${logs.length} из ${total}</p>
            <button type="button" data-act="refreshAudit" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Обновить</button>
            ${more ? `<button type="button" data-act="loadMoreAudit" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Показать ещё</button>` : ''}
        </div>
    </div>`;

    if (!logs.length) {
        return filter + ((entityType || action)
            ? emptyHtml('Записей не найдено', 'Измените фильтры или покажите все действия.')
            : emptyHtml('Записей нет', 'Действия появятся после изменений.'));
    }

    return filter + `<div class="space-y-4">
        ${logs.map(l => {
            const name = auditEntityName(l);
            const details = auditDetails(l);
            const actor = l.user_name || l.user_email || l.user_id || 'система';
            return `
            <article class="${UI.card} px-7 py-5">
                <p class="font-semibold text-ink">
                    ${escHtml(auditActionLabel(l.action))} · ${escHtml(auditEntityLabel(l.entity_type))}${name ? ` — ${escHtml(name)}` : ''}
                </p>
                <p class="mt-1 text-sm text-ink-soft">
                    ${escHtml(formatDateTime(l.createdAt))} · ${escHtml(actor)}
                </p>
                ${details ? `<p class="mt-1 text-sm text-ink-soft">${escHtml(details)}</p>` : ''}
                ${l.entity_id ? `<p class="mt-1 text-xs text-ink-faint break-all">${escHtml(l.entity_id)}</p>` : ''}
            </article>`;
        }).join('')}
    </div>`;
}

function auditFilterParams(extra) {
    return {
        ...extra,
        entity_type: adminAuditState.entityType || undefined,
        action: adminAuditState.action || undefined,
    };
}

async function filterAudit() {
    const entity = document.getElementById('admin-audit-entity');
    const action = document.getElementById('admin-audit-action');
    adminAuditState.entityType = entity ? entity.value : '';
    adminAuditState.action = action ? action.value : '';
    try {
        const res = await api.listAudit(auditFilterParams({ limit: 50, offset: 0 }));
        if (!res.ok) { showToast(errorText(res), 'error'); return; }
        const logs = res.data.logs || [];
        adminAuditState.logs = logs;
        adminAuditState.total = res.data.total != null ? res.data.total : logs.length;
        renderAdminContent(adminAuditHtml());
    } catch {
        showToast('Не удалось загрузить аудит', 'error');
    }
}

async function loadMoreAudit() {
    try {
        const res = await api.listAudit(auditFilterParams({
            limit: 50,
            offset: adminAuditState.logs.length,
        }));
        if (!res.ok) { showToast(errorText(res), 'error'); return; }
        adminAuditState.logs = adminAuditState.logs.concat(res.data.logs || []);
        if (res.data.total != null) adminAuditState.total = res.data.total;
        renderAdminContent(adminAuditHtml());
    } catch {
        showToast('Не удалось загрузить аудит', 'error');
    }
}