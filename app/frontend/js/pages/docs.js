/* ==========================================================================
 * pages/docs.js — документы: список, загрузка, скачивание, удаление,
 * запуск RSOSH-импорта. Бэкенд: app/routers/docs.py, app/routers/imports.py.
 * ========================================================================== */

function docTypeLabel(type) {
    const map = { RSOSH_LIST: 'Перечень РСОШ',
                  OLYMPIAD_REGULATION: 'Регламент олимпиады',
                  UNIVERSITY_DOCUMENT: 'Документ вуза',
                  OTHER: 'Другое' };
    return map[type] || type || '—';
}

function docStatusBadge(status) {
    const map = { UPLOADED: [UI.badgeNeutral, 'Загружен'],
                  PROCESSING: [UI.badgeNeutral, 'Обработка…'],
                  PROCESSED: [UI.badgeSuccess, 'Обработан'],
                  NEEDS_REVIEW: [UI.badgeDanger, 'Нужна проверка'],
                  FAILED: [UI.badgeDanger, 'Ошибка'] };
    const [cls, label] = map[status] || [UI.badgeNeutral, status || '—'];
    return `<span class="${UI.badge} ${cls}">${escHtml(label)}</span>`;
}

function docRow(doc) {
    const canManage = store.isAdmin() || store.user.role === 'ORGANIZATION_ADMIN';
    const canImport = doc.type === 'RSOSH_LIST' && (doc.status === 'UPLOADED' || doc.status === 'FAILED');
    const hasImport = doc.metadata && doc.metadata.rsosh;
    return `
    <div class="${UI.card} flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
                <span class="font-semibold truncate">${escHtml(doc.name)}</span>
                ${docStatusBadge(doc.status)}
                <span class="${UI.badge} ${UI.badgeNeutral}">${escHtml(docTypeLabel(doc.type))}</span>
            </div>
            <p class="mt-1 text-xs text-ink-soft truncate">Формат: ${escHtml(doc.mime_type || '—')} · Загружен: ${formatDate(doc.created_at)}</p>
            ${hasImport && doc.metadata.rsosh.state
                ? `<p class="mt-1 text-xs"><a href="#/imports/${doc.id}" class="text-ember">Импорт: ${escHtml(doc.metadata.rsosh.state === 'approved' ? 'подтверждён' : doc.metadata.rsosh.state)}</a></p>`
                : ''}
        </div>
        <div class="flex flex-wrap gap-2 shrink-0">
            <a class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}" href="/api/v1/docs/${doc.id}/file" download>Скачать</a>
            ${canImport ? `<button data-act="import" data-id="${doc.id}" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Запустить импорт</button>` : ''}
            ${hasImport && doc.metadata.rsosh.state === 'review'
                ? `<a class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}" href="#/imports/${doc.id}">Подтвердить</a>`
                : ''}
            ${canManage ? `<button data-act="delete" data-id="${doc.id}" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}">Удалить</button>` : ''}
        </div>
    </div>`;
}

function openUploadModal(onDone, orgs = []) {
    const canSelectOrg = store.isAdmin();
    const orgOptions = canSelectOrg && orgs.length
        ? orgs.map(o => ({ value: o.id, label: o.name }))
        : [{ value: store.user.organization_id || '', label: store.user.organization_id ? 'Моя организация' : 'Без организации' }];
    const body = `
    <form id="doc-form" class="space-y-4">
        <div id="modal-alert"></div>
        ${selectField({
            id: 'doc-type', name: 'type', label: 'Тип документа', value: 'RSOSH_LIST',
            options: [
                { value: 'RSOSH_LIST', label: 'Перечень РСОШ' },
                { value: 'OLYMPIAD_REGULATION', label: 'Регламент олимпиады' },
                { value: 'UNIVERSITY_DOCUMENT', label: 'Документ вуза' },
                { value: 'OTHER', label: 'Другое' },
            ],
        })}
        ${selectField({ id: 'doc-org', name: 'organization_id', label: 'Организация', value: orgOptions[0].value, options: orgOptions })}
        <label class="${UI.label}" for="doc-file">Файл (PDF, XLSX, DOCX, до 60 МБ)</label>
        <input id="doc-file" name="file" type="file" accept=".pdf,.xlsx,.docx" class="block w-full text-sm" required>
        <button type="submit" class="${UI.btn} ${UI.btnPrimary} w-full">Загрузить</button>
    </form>`;
    const { overlay, close } = openModal('Загрузка документа', body, { wide: true });

    overlay.querySelector('#doc-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = overlay.querySelector('button[type="submit"]');
        btn.disabled = true;
        const type = overlay.querySelector('#doc-type').value;
        const orgId = overlay.querySelector('#doc-org').value;
        const fd = new FormData();
        fd.append('file', overlay.querySelector('#doc-file').files[0]);
        const params = encodeURIComponent(type);
        const orgParam = orgId ? `&organization_id=${encodeURIComponent(orgId)}` : '';
        const res = await api.uploadDoc(fd, `?type=${params}${orgParam}`).catch(() => null);
        if (res && res.ok) {
            close();
            showToast('Документ загружен', 'success');
            if (onDone) onDone();
        } else {
            showModalError(overlay, res || { data: { detail: 'Сетевая ошибка' } });
            btn.disabled = false;
        }
    });
}

async function renderDocs() {
    const page = document.getElementById('page');
    if (!store.user) { navigate('#/auth'); return; }
    page.innerHTML = loadingHtml('Загружаем документы…');

    const [docsRes, orgRes] = await Promise.all([
        api.getDocs().catch(() => null),
        store.isAdmin() ? api.getOrganizations().catch(() => null) : Promise.resolve(null),
    ]);
    if (!docsRes || !docsRes.ok) {
        page.innerHTML = `${alertHtml(docsRes ? errorText(docsRes) : 'Сетевая ошибка', 'error')}
            <button id="docs-retry" class="${UI.btn} ${UI.btnPrimary} mt-4">Повторить</button>`;
        page.querySelector('#docs-retry').addEventListener('click', renderDocs);
        return;
    }

    const docs = Array.isArray(docsRes.data) ? docsRes.data : [];
    const orgs = orgRes && orgRes.ok && Array.isArray(orgRes.data) ? orgRes.data : [];
    const canManage = store.isAdmin() || store.user.role === 'ORGANIZATION_ADMIN';

    page.innerHTML = `
    <section class="max-w-5xl mx-auto px-4 py-8">
        <header class="flex items-center justify-between gap-4 mb-6">
            <div>
                <h1 class="text-2xl font-bold">Документы</h1>
                <p class="text-sm text-ink-soft">Перечни РСОШ и регламенты олимпиад</p>
            </div>
            ${canManage ? `<button id="doc-upload" class="${UI.btn} ${UI.btnPrimary}">Загрузить</button>` : ''}
        </header>
        ${docs.length === 0
            ? alertHtml('Документов пока нет', 'error')
            : `<div id="docs-list" class="space-y-4">${docs.map(docRow).join('')}</div>`}
    </section>`;

    const uploadBtn = page.querySelector('#doc-upload');
    if (uploadBtn) uploadBtn.addEventListener('click', () => openUploadModal(renderDocs, orgs));

    /* Делегирование вешается на свежий контейнер списка, а не на #page:
       иначе после каждого ре-рендера накапливались бы дублирующие обработчики. */
    const list = page.querySelector('#docs-list');
    if (!list) return;
    list.addEventListener('click', async (e) => {
        const target = e.target.closest('[data-act]');
        if (!target) return;
        const id = target.dataset.id;
        if (target.dataset.act === 'delete') {
            if (!window.confirm('Удалить документ?')) return;
            target.disabled = true;
            const res = await api.deleteDoc(id).catch(() => null);
            showToast(res && res.ok ? 'Документ удалён' : (res ? errorText(res) : 'Сетевая ошибка'),
                res && res.ok ? 'success' : 'error');
            renderDocs();
        } else if (target.dataset.act === 'import') {
            target.disabled = true;
            const res = await api.startRsoshImport(id).catch(() => null);
            if (res && res.ok) {
                showToast('Импорт запущен', 'success');
                navigate(`#/imports/${id}`);
            } else {
                showToast(res ? errorText(res) : 'Сетевая ошибка', 'error');
                target.disabled = false;
            }
        }
    });
}