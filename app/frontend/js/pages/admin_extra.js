function adminRepAppsHtml(items) {
    return `
    <div class="space-y-4">
        <h2 class="text-2xl font-extrabold tracking-tight">Заявки представителей</h2>
        ${items.length ? items.map(a => `
            <article class="${UI.card}">
                <p class="font-semibold">${escHtml(a.status)}</p>
                <p class="text-sm text-ink-soft mt-1">Пользователь: ${escHtml(a.user_id)}</p>
                <p class="text-sm text-ink-soft">Вуз: ${escHtml(a.university_id)}</p>
                ${a.justification ? `<p class="text-sm mt-2">${escHtml(a.justification)}</p>` : ''}
                ${a.status === 'pending' ? `
                    <div class="mt-3 flex gap-2">
                        <button class="admin-action ${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}" data-act="approveRepApp" data-id="${escAttr(a.id)}">Одобрить</button>
                        <button class="admin-action ${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}" data-act="rejectRepApp" data-id="${escAttr(a.id)}">Отклонить</button>
                    </div>` : ''}
            </article>`).join('') : emptyHtml('Заявок нет', 'Новые заявки появятся здесь.')}
    </div>`;
}

function adminAuditHtml(items) {
    return `
    <div class="space-y-4">
        <h2 class="text-2xl font-extrabold tracking-tight">Аудит</h2>
        ${items.length ? items.map(l => `
            <article class="${UI.card}">
                <p class="font-semibold">${escHtml(l.action)} · ${escHtml(l.entity_type)}</p>
                <p class="text-sm text-ink-soft mt-1">${escHtml(l.createdAt || '')} · пользователь ${escHtml(l.user_id || '—')}</p>
            </article>`).join('') : emptyHtml('Записей нет', 'Действия появятся после изменений.')}
    </div>`;
}