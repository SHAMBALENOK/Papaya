/* ==========================================================================
 * pages/profile.js — «Мой профиль».
 * Страница маршрута GET /api/v1/ (сводка текущего пользователя):
 * id, email, name, surname, gender, bday, bio, phone, country, region,
 * status, role, isActive, createdAt, updatedAt — всё, что отдаёт бэкенд.
 *
 * userProfileHtml(u, { editable }) — общий рендер карточки пользователя,
 * используется также на публичной странице #/users/{id} (users.js).
 * ========================================================================== */

async function renderProfile() {
    const page = document.getElementById('page');
    if (!store.user) { navigate('#/auth'); return; }
    page.innerHTML = loadingHtml();

    let res;
    try { res = await api.getMe(); } catch { res = { ok: false }; }

    if (!res.ok || !res.data) {
        page.innerHTML = `
        <div class="max-w-narrow mx-auto py-24">
            ${alertHtml('Не удалось загрузить профиль', 'error')}
            <a href="#/" class="${UI.btn} ${UI.btnSecondary}">На главную</a>
        </div>`;
        return;
    }

    page.innerHTML = userProfileHtml(res.data, { editable: true });
    document.getElementById('btn-edit-profile').addEventListener('click', () => openEditProfileModal(res.data));
}

/* Общий рендер карточки пользователя (поля — только из ответа API) */
function userProfileHtml(u, { editable = false } = {}) {
    const initials = (((u.name || '?')[0] || '?') + ((u.surname || '')[0] || '')).toUpperCase();
    const genderText = u.gender === 'male' ? 'Мужской' : u.gender === 'female' ? 'Женский' : 'Не указан';
    const accBadge = u.isActive
        ? `<span class="${UI.badge} ${UI.badgeSuccess}"><span class="w-2 h-2 rounded-full bg-ink/60" aria-hidden="true"></span>Активен</span>`
        : `<span class="${UI.badge} ${UI.badgeDanger}">Заблокирован</span>`;

    const fields = [
        ['Email', escHtml(u.email)],
        ['Телефон', escHtml(u.phone || 'Не указан')],
        ['Дата рождения', escHtml(u.bday || 'Не указана')],
        ['Пол', escHtml(genderText)],
        ['Страна', escHtml(u.country || 'Не указана')],
        ['Регион', escHtml(u.region || 'Не указан')],
        ['Статус', escHtml(u.status || 'Не задан')],
        ['Роль', `<span class="${UI.badge} ${u.role === 'ADMIN' ? UI.badgeAdmin : UI.badgeNeutral}">${escHtml(u.role || 'USER')}</span>`],
        ['Аккаунт', accBadge],
        ['ID', `<span class="text-sm text-ink-soft break-all">${escHtml(u.id)}</span>`],
    ];

    return `
    <div class="max-w-narrow mx-auto py-4">
        <a href="${editable ? '#/' : '#/users'}" class="inline-flex items-center gap-2 text-ink-soft font-semibold hover:text-ink transition-colors rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5M12 19l-7-7 7-7"></path></svg>
            ${editable ? 'На главную' : 'К списку пользователей'}
        </a>

        <!-- Шапка профиля -->
        <header class="mt-12 flex flex-col sm:flex-row sm:items-center gap-8">
            <div class="w-24 h-24 rounded bg-ember text-ink text-3xl font-extrabold flex items-center justify-center shrink-0" aria-hidden="true">${escHtml(initials)}</div>
            <div class="min-w-0 flex-1">
                <h1 class="text-3xl md:text-4xl font-extrabold tracking-tight leading-tight">${escHtml(u.name)} ${escHtml(u.surname)}</h1>
                <p class="mt-3 text-lg text-ink-soft">${escHtml(u.email)}</p>
            </div>
            ${editable ? `
            <div class="flex flex-wrap gap-3 shrink-0">
                <a href="#/my-events" class="${UI.btn} ${UI.btnSecondary}">Мои события</a>
                <button id="btn-edit-profile" class="${UI.btn} ${UI.btnPrimary}">Редактировать</button>
            </div>` : ''}
        </header>

        <!-- Поля: сетка с крупными зазорами, разделение только «воздухом» -->
        <section class="mt-16" aria-label="Данные профиля">
            <h2 class="${UI.eyebrow}">Данные профиля</h2>
            <dl class="mt-8 grid sm:grid-cols-2 gap-x-12 gap-y-9">
                ${fields.map(([label, value]) => `
                <div>
                    <dt class="text-sm font-medium text-ink-faint">${label}</dt>
                    <dd class="mt-2 text-base leading-relaxed">${value}</dd>
                </div>`).join('')}
            </dl>
        </section>

        <section class="mt-16" aria-labelledby="profile-bio-title">
            <h2 id="profile-bio-title" class="${UI.eyebrow}">О себе</h2>
            <p class="mt-7 text-lg text-ink leading-[1.8]">${escHtml(u.bio || 'Нет информации.')}</p>
        </section>

        <p class="mt-14 mb-4 text-sm text-ink-faint">Зарегистрирован: ${formatDate(u.createdAt)}</p>
    </div>`;
}

function openEditProfileModal(u) {
    const body = `
        <div id="modal-alert"></div>
        <form id="edit-profile-form">
            <div class="grid sm:grid-cols-2 gap-x-4">
                ${inputField({ id: 'pf-name', name: 'name', label: 'Имя', value: u.name || '', autocomplete: 'given-name' })}
                ${inputField({ id: 'pf-surname', name: 'surname', label: 'Фамилия', value: u.surname || '', autocomplete: 'family-name' })}
            </div>
            ${inputField({ id: 'pf-email', name: 'email', label: 'Email', type: 'email', value: u.email || '', autocomplete: 'email' })}
            ${inputField({ id: 'pf-phone', name: 'phone', label: 'Телефон', value: u.phone || '', autocomplete: 'tel' })}
            ${inputField({ id: 'pf-bday', name: 'bday', label: 'Дата рождения (ГГГГ-ММ-ДД)', value: u.bday || '', autocomplete: 'bday' })}
            ${selectField({ id: 'pf-gender', name: 'gender', label: 'Пол', value: u.gender || '', options: [
                { value: '', label: 'Не указан' },
                { value: 'male', label: 'Мужской' },
                { value: 'female', label: 'Женский' },
            ]})}
            <div class="grid sm:grid-cols-2 gap-x-4">
                ${inputField({ id: 'pf-country', name: 'country', label: 'Страна', value: u.country || '', autocomplete: 'country-name' })}
                ${inputField({ id: 'pf-region', name: 'region', label: 'Регион', value: u.region || '' })}
            </div>
            ${inputField({ id: 'pf-status', name: 'status', label: 'Статус (школьник, студент, учитель…)', value: u.status || '' })}
            ${textareaField({ id: 'pf-bio', name: 'bio', label: 'О себе', value: u.bio || '', rows: 3 })}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Сохранить</button>
            </div>
        </form>`;
    const { overlay, close } = openModal('Изменение данных профиля', body, { wide: true });
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    overlay.querySelector('#edit-profile-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const btn = e.target.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
            const res = await api.editUser(u.id, {
                id: u.id,
                name: fd.get('name'),
                surname: fd.get('surname'),
                email: fd.get('email'),
                isActive: u.isActive !== false,
                gender: fd.get('gender') || null,
                bday: fd.get('bday') || null,
                bio: fd.get('bio') || null,
                phone: fd.get('phone') || null,
                country: fd.get('country') || null,
                region: fd.get('region') || null,
                status: fd.get('status') || null,
                role: u.role || 'USER',
            });
            if (res.ok) {
                close();
                showToast('Профиль обновлён', 'success');
                renderProfile();
            } else {
                showModalError(overlay, res);
            }
        } catch {
            showModalError(overlay, { data: { detail: 'Сетевая ошибка' } });
        }
        btn.disabled = false;
    });
}