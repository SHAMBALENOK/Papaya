/* ==========================================================================
 * pages/organizations.js — каталог и детальная карточка организаций.
 * Создавать может только ADMIN; редактировать/удалять — ADMIN или сама
 * организация (ORGANIZATION_ADMIN). Бэкенд: app/routers/organizations.py.
 * ========================================================================== */

function orgTypeBadge(type) {
    const labels = { UNIVERSITY: 'Вуз', ORGANIZER: 'Организатор',
                     SCHOOL: 'Школа', OTHER: 'Другое' };
    return `<span class="${UI.badge} ${UI.badgeNeutral}">${escHtml(labels[type] || type || '—')}</span>`;
}

function orgCard(org) {
    return `
    <a href="#/organizations/${org.id}" class="${UI.card} block hover:shadow-elev-2 transition-shadow">
        <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
                <p class="font-semibold truncate">${escHtml(org.name)}</p>
                ${org.short_name ? `<p class="text-sm text-ink-soft truncate">${escHtml(org.short_name)}</p>` : ''}
            </div>
            ${orgTypeBadge(org.type)}
        </div>
        ${org.description ? `<p class="mt-3 text-sm text-ink-soft line-clamp-2">${escHtml(org.description)}</p>` : ''}
        ${org.website ? `<p class="mt-2 text-xs text-ink-soft truncate">${escHtml(org.website)}</p>` : ''}
    </a>`;
}

function openOrgModal(onDone, org = null) {
    const body = `
    <form id="org-form" class="space-y-4">
        <div id="modal-alert"></div>
        ${inputField({ id: 'org-name', name: 'name', label: 'Название', value: (org && org.name) || '', required: true })}
        ${inputField({ id: 'org-short', name: 'short_name', label: 'Краткое название', value: (org && org.short_name) || '' })}
        ${selectField({
            id: 'org-type', name: 'type', label: 'Тип',
            value: (org && org.type) || 'ORGANIZER',
            options: [
                { value: 'UNIVERSITY', label: 'Вуз' },
                { value: 'ORGANIZER', label: 'Организатор' },
                { value: 'SCHOOL', label: 'Школа' },
                { value: 'OTHER', label: 'Другое' },
            ],
        })}
        ${inputField({ id: 'org-site', name: 'website', label: 'Сайт', value: (org && org.website) || '' })}
        ${textareaField({ id: 'org-desc', name: 'description', label: 'Описание', value: (org && org.description) || '' })}
        <button type="submit" class="${UI.btn} ${UI.btnPrimary} w-full">${org ? 'Сохранить' : 'Создать'}</button>
    </form>`;
    const { overlay, close } = openModal(org ? 'Редактирование организации' : 'Новая организация', body, { wide: true });

    overlay.querySelector('#org-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = overlay.querySelector('button[type="submit"]');
        btn.disabled = true;
        const data = {
            name: overlay.querySelector('#org-name').value.trim(),
            short_name: overlay.querySelector('#org-short').value.trim() || null,
            type: overlay.querySelector('#org-type').value,
            website: overlay.querySelector('#org-site').value.trim() || null,
            description: overlay.querySelector('#org-desc').value.trim() || null,
        };
        try {
            const res = org
                ? await api.updateOrganization(org.id, data)
                : await api.createOrganization(data);
            if (res.ok) {
                close();
                showToast(org ? 'Организация обновлена' : 'Организация создана', 'success');
                if (onDone) onDone();
            } else {
                showModalError(overlay, res);
                btn.disabled = false;
            }
        } catch {
            showModalError(overlay, { data: { detail: 'Сетевая ошибка' } });
            btn.disabled = false;
        }
    });
}

async function renderOrganizations() {
    const page = document.getElementById('page');
    if (!store.user) { navigate('#/auth'); return; }
    page.innerHTML = loadingHtml('Загружаем организации…');

    const res = await api.getOrganizations().catch(() => null);
    if (!res || !res.ok) {
        page.innerHTML = `${alertHtml(res ? errorText(res) : 'Сетевая ошибка', 'error')}
            <button id="orgs-retry" class="${UI.btn} ${UI.btnPrimary} mt-4">Повторить</button>`;
        page.querySelector('#orgs-retry').addEventListener('click', renderOrganizations);
        return;
    }

    store.setUser({ ...store.user });
    const orgs = Array.isArray(res.data) ? res.data : [];
    const canCreate = store.isAdmin();

    page.innerHTML = `
    <section class="max-w-5xl mx-auto px-4 py-8">
        <header class="flex items-center justify-between gap-4 mb-6">
            <div>
                <h1 class="text-2xl font-bold">Организации</h1>
                <p class="text-sm text-ink-soft">Организаторы, вузы и школы — участники перечня</p>
            </div>
            ${canCreate ? `<button id="org-create" class="${UI.btn} ${UI.btnPrimary}">Создать</button>` : ''}
        </header>
        ${orgs.length === 0
            ? alertHtml('Пока нет ни одной организации', 'error')
            : `<div class="grid gap-4 sm:grid-cols-2">${orgs.map(orgCard).join('')}</div>`}
    </section>`;

    const createBtn = page.querySelector('#org-create');
    if (createBtn) createBtn.addEventListener('click', () => openOrgModal(renderOrganizations));
}

async function renderOrganization(orgId) {
    const page = document.getElementById('page');
    if (!store.user) { navigate('#/auth'); return; }
    page.innerHTML = loadingHtml('Загружаем организацию…');

    const res = await api.getOrganization(orgId).catch(() => null);
    if (!res || !res.ok) {
        page.innerHTML = `${alertHtml(res ? errorText(res) : 'Сетевая ошибка', 'error')}
            <button id="org-retry" class="${UI.btn} ${UI.btnPrimary} mt-4">Назад</button>`;
        page.querySelector('#org-retry').addEventListener('click', () => navigate('#/organizations'));
        return;
    }
    const org = res.data;
    const isOwn = store.user.role === 'ORGANIZATION_ADMIN'
        && store.user.organization_id === org.id;
    const canManage = store.isAdmin() || isOwn;

    const contacts = org.contacts || {};
    const rows = [
        ['Краткое название', org.short_name],
        ['Тип', orgTypeBadge(org.type)],
        ['Сайт', org.website ? `<a class="text-ember" href="${escAttr(org.website)}" target="_blank" rel="noopener">${escHtml(org.website)}</a>` : null],
        ['Описание', org.description],
        ['Контакты', Object.keys(contacts).length
            ? Object.entries(contacts).map(([k, v]) => `${escHtml(k)}: ${escHtml(String(v))}`).join('<br>')
            : null],
    ];

    page.innerHTML = `
    <section class="max-w-3xl mx-auto px-4 py-8">
        <nav class="mb-4"><a href="#/organizations" class="text-sm text-ember">← Все организации</a></nav>
        <div class="flex items-start justify-between gap-4 mb-6">
            <div>
                <h1 class="text-2xl font-bold">${escHtml(org.name)}</h1>
                ${orgTypeBadge(org.type)}
            </div>
            ${canManage ? `
            <div class="flex gap-2 shrink-0">
                <button id="org-edit" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Редактировать</button>
                <button id="org-delete" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}">Удалить</button>
            </div>` : ''}
        </div>
        <div class="${UI.card} divide-y divide-mist">
            ${rows.filter(([, v]) => v !== null && v !== '').map(([label, value]) => `
                <div class="flex justify-between gap-4 py-3">
                    <dt class="text-sm text-ink-soft shrink-0">${escHtml(label)}</dt>
                    <dd class="text-sm text-right">${value}</dd>
                </div>`).join('')}
        </div>
    </section>`;

    const editBtn = page.querySelector('#org-edit');
    if (editBtn) editBtn.addEventListener('click', () => openOrgModal(renderOrganization.bind(null, org.id), org));

    const deleteBtn = page.querySelector('#org-delete');
    if (deleteBtn) deleteBtn.addEventListener('click', async () => {
        if (!window.confirm(`Удалить организацию «${org.name}»?`)) return;
        deleteBtn.disabled = true;
        const res = await api.deleteOrganization(org.id).catch(() => null);
        if (res && res.ok) {
            showToast('Организация удалена', 'success');
            navigate('#/organizations');
        } else {
            showToast(res ? errorText(res) : 'Сетевая ошибка', 'error');
            deleteBtn.disabled = false;
        }
    });
}