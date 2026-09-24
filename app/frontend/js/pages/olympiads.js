/* ==========================================================================
 * pages/olympiads.js — каталог и детальная карточка олимпиад.
 * Создаёт/правит орг-админ своей организации или ADMIN.
 * Бэкенд: app/routers/olympiads.py (#/olympiads, #/olympiads/{id}).
 * ========================================================================== */

function statusBadge(status) {
    const map = { PUBLISHED: [UI.badgeSuccess, 'Опубликована'],
                  DRAFT: [UI.badgeNeutral, 'Черновик'],
                  ARCHIVED: [UI.badgeDanger, 'Архив'] };
    const [cls, label] = map[status] || [UI.badgeNeutral, status || '—'];
    return `<span class="${UI.badge} ${cls}">${escHtml(label)}</span>`;
}

function splitList(text) {
    return text.split(/[;,]/).map(s => s.trim()).filter(Boolean);
}

function olympiadCard(oly) {
    const subjects = (Array.isArray(oly.subjects) ? oly.subjects : []).slice(0, 3);
    const levels = (Array.isArray(oly.levels) ? oly.levels : []).join('‑');
    const years = (Array.isArray(oly.years) ? oly.years : []).slice(0, 3).join(', ');
    const accent = oly.status === 'ARCHIVED' ? 'bg-crimson'
        : oly.status === 'DRAFT' ? 'bg-sand'
        : 'bg-sage';
    return `
    <a href="#/olympiads/${oly.id}"
       title="${escAttr(oly.name)}"
       class="group flex flex-col bg-white shadow-elev-1 hover:shadow-elev-2 hover:-translate-y-0.5 transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">
        <div class="h-1 ${accent}" aria-hidden="true"></div>
        <div class="p-5 flex flex-col grow">
            <div class="flex items-start justify-between gap-2">
                <h2 class="font-bold text-ink leading-snug line-clamp-2">${escHtml(oly.name)}</h2>
                ${statusBadge(oly.status)}
            </div>
            ${oly.description ? `<p class="mt-2 text-sm text-ink-soft leading-relaxed line-clamp-2">${escHtml(oly.description)}</p>` : ''}
            ${subjects.length ? `
            <div class="mt-3 flex flex-wrap gap-1.5">
                ${subjects.map(s => `<span class="${UI.badge} ${UI.badgeNeutral}">${escHtml(s)}</span>`).join('')}
            </div>` : ''}
            <div class="mt-auto pt-4 flex items-center justify-between gap-3 text-xs">
                ${levels ? `<span class="font-semibold text-ink">уровень ${escHtml(levels)}</span>` : '<span></span>'}
                ${years ? `<span class="text-ink-soft">${escHtml(years)}</span>` : ''}
            </div>
            <p class="mt-3 text-sm font-semibold text-ink group-hover:text-black transition-colors">Подробнее →</p>
        </div>
    </a>`;
}

function openOlympiadModal(onDone, oly = null, orgs = []) {
    const isOrgAdmin = store.user.role === 'ORGANIZATION_ADMIN';
    const data = oly || {};
    const orgOptions = orgs.length
        ? orgs.map(o => ({ value: o.id, label: o.name }))
        : [];
    const body = `
    <form id="oly-form" class="space-y-4">
        <div id="modal-alert"></div>
        ${inputField({ id: 'oly-name', name: 'name', label: 'Название', value: data.name || '', required: true })}
        ${isOrgAdmin
            ? `<input type="hidden" id="oly-org" value="${escAttr(store.user.organization_id || '')}">`
            : selectField({ id: 'oly-org', name: 'organizer', label: 'Организатор', value: data.organizer_ids && data.organizer_ids[0], options: orgOptions })}
        ${inputField({ id: 'oly-subjects', name: 'subjects', label: 'Предметы (через запятую)', value: (data.subjects || []).join(', ') })}
        ${inputField({ id: 'oly-levels', name: 'levels', label: 'Уровни РСОШ (1, 2, 3)', value: (data.levels || []).join(', ') })}
        ${inputField({ id: 'oly-years', name: 'years', label: 'Годы (2000, 2001…)', value: (data.years || []).join(', ') })}
        ${textareaField({ id: 'oly-desc', name: 'description', label: 'Описание', value: data.description || '' })}
        ${oly ? selectField({
            id: 'oly-status', name: 'status', label: 'Статус', value: data.status || 'DRAFT',
            options: [
                { value: 'DRAFT', label: 'Черновик' },
                { value: 'PUBLISHED', label: 'Опубликована' },
                { value: 'ARCHIVED', label: 'Архив' },
            ],
        }) : ''}
        <button type="submit" class="${UI.btn} ${UI.btnPrimary} w-full">${oly ? 'Сохранить' : 'Создать'}</button>
    </form>`;
    const { overlay, close } = openModal(oly ? 'Редактирование олимпиады' : 'Новая олимпиада', body, { wide: true });

    overlay.querySelector('#oly-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = overlay.querySelector('button[type="submit"]');
        btn.disabled = true;
        const orgId = overlay.querySelector('#oly-org').value;
        const payload = {
            name: overlay.querySelector('#oly-name').value.trim(),
            subjects: splitList(overlay.querySelector('#oly-subjects').value),
            levels: splitList(overlay.querySelector('#oly-levels').value),
            years: splitList(overlay.querySelector('#oly-years').value),
            description: overlay.querySelector('#oly-desc').value.trim() || null,
            organizer_ids: orgId ? [orgId] : (data.organizer_ids || []),
        };
        if (oly) payload.status = overlay.querySelector('#oly-status').value;
        try {
            const res = oly
                ? await api.updateOlympiad(oly.id, payload)
                : await api.createOlympiad(payload);
            if (res.ok) {
                close();
                showToast(oly ? 'Олимпиада обновлена' : 'Олимпиада создана', 'success');
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

async function renderOlympiads() {
    const page = document.getElementById('page');
    if (!store.user) { navigate('#/auth'); return; }
    page.innerHTML = loadingHtml('Загружаем олимпиады…');

    const [listRes, orgRes] = await Promise.all([
        api.getOlympiads().catch(() => null),
        store.isAdmin() ? api.getOrganizations().catch(() => null) : Promise.resolve(null),
    ]);
    if (!listRes || !listRes.ok) {
        page.innerHTML = `${alertHtml(listRes ? errorText(listRes) : 'Сетевая ошибка', 'error')}
            <button id="oly-retry" class="${UI.btn} ${UI.btnPrimary} mt-4">Повторить</button>`;
        page.querySelector('#oly-retry').addEventListener('click', renderOlympiads);
        return;
    }

    const olympiads = Array.isArray(listRes.data) ? listRes.data : [];
    const orgs = orgRes && orgRes.ok && Array.isArray(orgRes.data) ? orgRes.data : [];
    const canManage = store.isAdmin() || store.user.role === 'ORGANIZATION_ADMIN';

    page.innerHTML = `
    <section class="pt-4 pb-16 md:pb-20">
        <div class="flex flex-wrap items-end justify-between gap-6">
            <div class="max-w-2xl">
                <p class="${UI.eyebrow}">Каталог</p>
                <h1 class="mt-4 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">Олимпиады</h1>
                <p class="mt-6 text-lg text-ink-soft leading-relaxed">Перечень РСОШ и другие олимпиады для школьников. Откройте карточку, чтобы узнать подробности.</p>
            </div>
            ${canManage ? `<button id="oly-create" class="${UI.btn} ${UI.btnPrimary}">Создать</button>` : ''}
        </div>
        ${olympiads.length === 0
            ? `<div class="mt-16">${alertHtml('Олимпиад пока нет', 'error')}</div>`
            : `<div class="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">${olympiads.map(olympiadCard).join('')}</div>`}
    </section>`;

    const createBtn = page.querySelector('#oly-create');
    if (createBtn) createBtn.addEventListener('click', () => openOlympiadModal(renderOlympiads, null, orgs));
}

async function renderOlympiad(olyId) {
    const page = document.getElementById('page');
    if (!store.user) { navigate('#/auth'); return; }
    page.innerHTML = loadingHtml('Загружаем олимпиаду…');

    const [olyRes, orgRes] = await Promise.all([
        api.getOlympiad(olyId).catch(() => null),
        store.isAdmin() ? api.getOrganizations().catch(() => null) : Promise.resolve(null),
    ]);
    if (!olyRes || !olyRes.ok) {
        page.innerHTML = `${alertHtml(olyRes ? errorText(olyRes) : 'Сетевая ошибка', 'error')}
            <button id="oly-back" class="${UI.btn} ${UI.btnPrimary} mt-4">Назад</button>`;
        page.querySelector('#oly-back').addEventListener('click', () => navigate('#/olympiads'));
        return;
    }
    const oly = olyRes.data;
    const orgs = orgRes && orgRes.ok && Array.isArray(orgRes.data) ? orgRes.data : [];
    const orgIndex = Object.fromEntries(orgs.map(o => [o.id, o.name]));
    const canManage = store.isAdmin() || store.user.role === 'ORGANIZATION_ADMIN';

    const rows = [
        ['Статус', statusBadge(oly.status)],
        ['Предметы', (oly.subjects || []).join(', ')],
        ['Уровни', (oly.levels || []).join(', ')],
        ['Годы', (oly.years || []).join(', ')],
        ['Организаторы', (oly.organizer_ids || []).map(id => orgIndex[id] || id).join(', ')],
        ['Описание', oly.description],
        ['Регистрация', oly.registration_url ? `<a class="text-ember" href="${escAttr(oly.registration_url)}" target="_blank" rel="noopener">${escHtml(oly.registration_url)}</a>` : null],
        ['Официальный сайт', oly.official_url ? `<a class="text-ember" href="${escAttr(oly.official_url)}" target="_blank" rel="noopener">${escHtml(oly.official_url)}</a>` : null],
    ];

    page.innerHTML = `
    <section class="max-w-3xl mx-auto px-4 py-8">
        <nav class="mb-4"><a href="#/olympiads" class="text-sm text-ember">← Все олимпиады</a></nav>
        <div class="flex items-start justify-between gap-4 mb-6">
            <h1 class="text-2xl font-bold">${escHtml(oly.name)}</h1>
            ${canManage ? `
            <div class="flex gap-2 shrink-0">
                <button id="oly-edit" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Редактировать</button>
                <button id="oly-delete" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}">Удалить</button>
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

    const editBtn = page.querySelector('#oly-edit');
    if (editBtn) editBtn.addEventListener('click', () => openOlympiadModal(renderOlympiad.bind(null, oly.id), oly, orgs));

    const deleteBtn = page.querySelector('#oly-delete');
    if (deleteBtn) deleteBtn.addEventListener('click', async () => {
        if (!window.confirm(`Удалить олимпиаду «${oly.name}»?`)) return;
        deleteBtn.disabled = true;
        const res = await api.deleteOlympiad(oly.id).catch(() => null);
        if (res && res.ok) {
            showToast('Олимпиада удалена', 'success');
            navigate('#/olympiads');
        } else {
            showToast(res ? errorText(res) : 'Сетевая ошибка', 'error');
            deleteBtn.disabled = false;
        }
    });
}