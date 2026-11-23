/* ==========================================================================
 * pages/profile.js — «Мой профиль».
 * Источник: GET /api/v1/ (полный объект пользователя).
 * Запасной источник: GET /api/v1/user/{id} — тот же UserResponse.
 * ========================================================================== */

async function renderProfile() {
    const page = document.getElementById('page');
    if (!store.user) { navigate('#/auth'); return; }
    page.innerHTML = loadingHtml();

    let res = { ok: false, data: null };

    /* Основной маршрут профиля текущего пользователя */
    try { res = await api.getMe(); } catch (err) {
        console.error('[profile] GET / не удался:', err);
        res = { ok: false, data: null };
    }

    /* Запасной путь — тот же набор полей по id из сессии */
    const meLooksValid = res.ok && res.data && res.data.id;
    if (!meLooksValid && store.user.id) {
        try { res = await api.getUser(store.user.id); } catch (err) {
            console.error('[profile] GET /user/{id} не удался:', err);
        }
    }

    if (!res.ok || !res.data || !res.data.id) {
        page.innerHTML = `
        <div class="max-w-narrow mx-auto py-24">
            ${alertHtml('Не удалось загрузить профиль', 'error')}
            <div class="flex flex-wrap gap-3">
                <button type="button" id="profile-retry" class="${UI.btn} ${UI.btnPrimary}">Повторить</button>
                <a href="#/" class="${UI.btn} ${UI.btnSecondary}">На главную</a>
            </div>
        </div>`;
        const retry = document.getElementById('profile-retry');
        if (retry) retry.addEventListener('click', renderProfile);
        return;
    }

    store.setUser({
        id: res.data.id,
        name: res.data.name,
        surname: res.data.surname,
        email: res.data.email,
        role: res.data.role || 'USER',
        university_id: res.data.university_id || null,
    });
    renderHeader();

    page.innerHTML = userProfileHtml(res.data, { editable: true });
    const editBtn = document.getElementById('btn-edit-profile');
    if (editBtn) editBtn.addEventListener('click', () => openEditProfileModal(res.data));
    if (res.data.role === 'USER') renderRepresentativeApplicationSection();
    renderUniversityProposalSection();
    if (res.data.role !== 'ADMIN') renderAdminApplicationSection();
}

function userProfileHtml(u, { editable = false } = {}) {
    const initials = (((u.name || '?')[0] || '?') + ((u.surname || '')[0] || '')).toUpperCase();
    const genderText = u.gender === 'male' ? 'Мужской' : u.gender === 'female' ? 'Женский' : 'Не указан';
    const accBadge = u.isActive
        ? `<span class="${UI.badge} ${UI.badgeSuccess}"><span class="w-2 h-2 rounded-full bg-success/70" aria-hidden="true"></span>Активен</span>`
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
        <a href="#/" class="inline-flex items-center gap-2 text-ink-soft font-semibold hover:text-ink transition-colors rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-brand">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5M12 19l-7-7 7-7"></path></svg>
            На главную
        </a>

        <header class="mt-12 flex flex-col sm:flex-row sm:items-center gap-8">
            <div class="w-24 h-24 rounded bg-brand-soft text-brand-strong text-3xl font-extrabold flex items-center justify-center shrink-0" aria-hidden="true">${escHtml(initials)}</div>
            <div class="min-w-0 flex-1">
                <h1 class="text-3xl md:text-4xl font-extrabold tracking-tight leading-tight">${escHtml(u.name)} ${escHtml(u.surname)}</h1>
                <p class="mt-3 text-lg text-ink-soft">${escHtml(u.email)}</p>
            </div>
            ${editable ? `
            <div class="flex flex-wrap gap-3 shrink-0">
                <button id="btn-edit-profile" class="${UI.btn} ${UI.btnPrimary}">Редактировать</button>
            </div>` : ''}
        </header>

        ${editable ? pageGuideHtml([
            { id: 'profile-data-section', label: 'Данные профиля' },
            { id: 'profile-bio-title', label: 'О себе' },
            ...(u.role === 'USER' ? [{ id: 'rep-application-section', label: 'Представительство' }] : []),
            { id: 'university-proposal-section', label: 'Предложить вуз' },
            ...(u.role !== 'ADMIN' ? [{ id: 'admin-application-section', label: 'Стать администратором' }] : []),
        ]) : ''}

        <section id="profile-data-section" class="mt-16" aria-label="Данные профиля">
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

        ${editable && u.role === 'USER'
            ? '<section id="rep-application-section" class="mt-16" aria-live="polite"></section>'
            : ''}

        ${editable
            ? '<section id="university-proposal-section" class="mt-16" aria-live="polite"></section>'
            : ''}

        ${editable && u.role !== 'ADMIN'
            ? '<section id="admin-application-section" class="mt-16" aria-live="polite"></section>'
            : ''}

        <p class="mt-14 mb-4 text-sm text-ink-faint">Зарегистрирован: ${formatDate(u.createdAt)}</p>
    </div>`;
}

function openEditProfileModal(u) {
    let dirty = false;
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
    const { overlay, close } = openModal('Изменение данных профиля', body, { wide: true, isDirty: () => dirty });
    ['input', 'change'].forEach(ev => overlay.addEventListener(ev, () => { dirty = true; }));
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    overlay.querySelector('#edit-profile-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const btn = e.target.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
            const res = await api.editUser(u.id, {
                name: fd.get('name'),
                surname: fd.get('surname'),
                email: fd.get('email'),
                gender: fd.get('gender') || null,
                bday: fd.get('bday') || null,
                bio: fd.get('bio') || null,
                phone: fd.get('phone') || null,
                country: fd.get('country') || null,
                region: fd.get('region') || null,
                status: fd.get('status') || null,
            });
            if (res.ok) {
                dirty = false;
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

/* --------------------- Заявка на роль администратора --------------------- */

/** Блок в профиле: подать заявку на ADMIN или увидеть её статус.
 *
 * Роль ADMIN даёт доступ ко всему каталогу и управлению ролями, поэтому
 * заявка требует контакт и мотивационное письмо. Одобрение сразу выдаёт роль,
 * но только другому человеку: свою заявку одобрить нельзя (проверка сервера).
 */
async function renderAdminApplicationSection() {
    const box = document.getElementById('admin-application-section');
    if (!box) return;
    box.innerHTML = loadingHtml('Проверяем заявку…');

    const res = await api.listMyAdminApplications().catch(() => ({ ok: false, data: null }));
    const header = `
        <p class="${UI.eyebrow}">Администрирование</p>
        <h2 class="mt-5 text-2xl font-extrabold tracking-tight">Стать администратором Papaya</h2>`;

    if (!res.ok) {
        box.innerHTML = `${header}
            <div class="mt-6">${alertHtml('Не удалось загрузить статус заявки', 'error')}</div>`;
        return;
    }

    const applications = (res.data && res.data.applications) || [];
    const latest = applications[0] || null;

    if (latest && latest.status === 'pending') {
        box.innerHTML = `${header}
        <div class="${UI.card} px-8 py-6 mt-8">
            <div class="flex flex-wrap items-center gap-3">
                <span class="${UI.badge} ${UI.badgePending}">На рассмотрении</span>
                <span class="text-sm text-ink-faint">от ${formatDateTime(latest.createdAt)}</span>
            </div>
            <p class="mt-4 text-sm text-ink-soft">Почта для связи: ${escHtml(latest.contact_email || 'не указана')}</p>
            <p class="mt-3 text-sm text-ink leading-relaxed whitespace-pre-wrap">${escHtml(latest.motivation || '')}</p>
            <p class="mt-4 text-sm text-ink-soft leading-relaxed">
                Рассматривает другой администратор Papaya: одобрить собственную
                заявку нельзя. После одобрения роль выдаётся сразу.
            </p>
        </div>`;
        return;
    }

    if (latest && latest.status === 'approved') {
        box.innerHTML = `${header}
        <div class="${UI.card} px-8 py-6 mt-8">
            <span class="${UI.badge} ${UI.badgeSuccess}">Заявка одобрена</span>
            <p class="mt-4 text-sm text-ink-soft leading-relaxed">
                Роль администратора выдана. Если раздел «Администрирование» ещё не
                появился в меню, обновите страницу.
            </p>
        </div>`;
        return;
    }

    box.innerHTML = `${header}
        <p class="mt-5 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Администратор ведёт каталог олимпиад и университетов, модерирует льготы
            и заявки, запускает импорт РСОШ. Заявку рассматривает другой
            администратор: свою одобрить нельзя.
        </p>
        ${latest && latest.status === 'rejected'
            ? `<div class="mt-8">${alertHtml(
                'Предыдущая заявка отклонена'
                + (latest.rejection_reason ? `: ${latest.rejection_reason}` : '')
                + '. Можно подать новую.', 'error')}</div>`
            : ''}
        <form id="admin-application-form" class="mt-8 max-w-2xl">
            <div id="admin-application-alert"></div>
            ${inputField({
                id: 'aa-contact-email',
                name: 'contact_email',
                label: 'Почта для связи',
                type: 'email',
                required: true,
                value: (store.user && store.user.email) || '',
                autocomplete: 'email',
            })}
            ${textareaField({
                id: 'aa-motivation',
                name: 'motivation',
                label: 'Почему вы хотите стать администратором',
                rows: 5,
                required: true,
                placeholder: 'Опыт модерации, знание олимпиад и вузов, готовность проверять данные…',
            })}
            <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Отправить заявку</button>
        </form>`;

    const form = document.getElementById('admin-application-form');
    form.addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(form);
        const alertBox = document.getElementById('admin-application-alert');
        const contactEmail = (fd.get('contact_email') || '').trim();
        const motivation = (fd.get('motivation') || '').trim();
        if (!contactEmail || !motivation) {
            alertBox.innerHTML = alertHtml('Заполните почту и мотивацию', 'error');
            return;
        }
        const btn = form.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
            const created = await api.createAdminApplication({
                contact_email: contactEmail,
                motivation,
            });
            if (created.ok) {
                showToast('Заявка отправлена администратору', 'success');
                await renderAdminApplicationSection();
                return;
            }
            alertBox.innerHTML = alertHtml(errorText(created), 'error');
        } catch {
            alertBox.innerHTML = alertHtml('Сетевая ошибка', 'error');
        }
        btn.disabled = false;
    });
}

/** Блок в профиле: подать заявку или увидеть её статус.
 *
 * Раньше заявку можно было создать только запросом к API: пользователь не
 * видел ни формы, ни результата рассмотрения. Роль назначалась вручную.
 */
async function renderRepresentativeApplicationSection() {
    const box = document.getElementById('rep-application-section');
    if (!box) return;

    box.innerHTML = loadingHtml('Проверяем заявки…');

    const [appsRes, uniRes] = await Promise.all([
        api.listMyRepresentativeApplications().catch(() => ({ ok: false, data: null })),
        api.listUniversities().catch(() => ({ ok: false, data: null })),
    ]);

    if (!appsRes.ok) {
        box.innerHTML = `
            <p class="${UI.eyebrow}">Представительство</p>
            <div class="mt-6">${alertHtml('Не удалось загрузить статус заявки', 'error')}</div>`;
        return;
    }

    const applications = (appsRes.data && appsRes.data.applications) || [];
    const universities = (uniRes.ok && uniRes.data && uniRes.data.universities) || [];
    const latest = applications[0] || null;
    const header = `
        <p class="${UI.eyebrow}">Представительство</p>
        <h2 class="mt-5 text-2xl font-extrabold tracking-tight">Стать представителем университета</h2>`;

    if (latest && latest.status === 'pending') {
        box.innerHTML = `${header}
        <div class="${UI.card} px-8 py-6 mt-8">
            <div class="flex flex-wrap items-center gap-3">
                <span class="${UI.badge} ${UI.badgePending}">На рассмотрении</span>
                <span class="text-sm text-ink-faint">от ${formatDate(latest.createdAt)}</span>
            </div>
            <p class="mt-4 text-ink">Университет: <span class="font-semibold">${escHtml(latest.university_name || 'не найден')}</span></p>
            ${latest.contact_email ? `<p class="mt-2 text-sm text-ink-soft">Почта для связи: ${escHtml(latest.contact_email)}</p>` : ''}
            ${latest.justification ? `<p class="mt-3 text-sm text-ink leading-relaxed whitespace-pre-wrap">${escHtml(latest.justification)}</p>` : ''}
            ${attachmentThumbsHtml(latest.attachments, 'Фотографии')}
            ${attachmentLinksHtml(latest.attachments, 'Приложенные документы')}
            <p class="mt-4 text-sm text-ink-soft leading-relaxed">
                Администратор Papaya рассмотрит заявку. После одобрения в меню появится
                раздел «Мой университет», где можно вести правила льгот.
            </p>
        </div>`;
        return;
    }

    if (latest && latest.status === 'approved') {
        box.innerHTML = `${header}
        <div class="${UI.card} px-8 py-6 mt-8">
            <span class="${UI.badge} ${UI.badgeSuccess}">Заявка одобрена</span>
            <p class="mt-4 text-ink">Университет: <span class="font-semibold">${escHtml(latest.university_name || 'не найден')}</span></p>
            <p class="mt-4 text-sm text-ink-soft leading-relaxed">
                Доступ к кабинету представителя уже открыт. Если раздел «Мой университет»
                ещё не появился в меню, обновите страницу.
            </p>
            ${attachmentThumbsHtml(latest.attachments, 'Фотографии')}
            ${attachmentLinksHtml(latest.attachments, 'Приложенные документы')}
        </div>`;
        return;
    }

    if (!universities.length) {
        box.innerHTML = `${header}
        <p class="mt-5 text-lg text-ink-soft leading-relaxed">
            Каталог университетов пока пуст. Заявку можно будет подать, когда
            администратор добавит университет.
        </p>`;
        return;
    }

    const options = [{ value: '', label: 'Выберите университет' }]
        .concat(universities.map(item => ({
            value: item.id,
            label: item.short_name || item.name,
        })));

    box.innerHTML = `${header}
        <p class="mt-5 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Представитель ведёт правила льгот своего университета: выбирает олимпиады
            из каталога и прикладывает документы-основания. Заявку рассматривает
            администратор Papaya.
        </p>
        ${latest && latest.status === 'rejected'
            ? `<div class="mt-8">${alertHtml(
                'Предыдущая заявка отклонена'
                + (latest.rejection_reason ? `: ${latest.rejection_reason}` : '')
                + '. Можно подать новую.', 'error')}</div>`
            : ''}
        <form id="rep-application-form" class="mt-8 max-w-2xl">
            <div id="rep-application-alert"></div>
            ${selectField({
                id: 'rep-application-university',
                name: 'university_id',
                label: 'Университет',
                options,
                value: '',
            })}
            ${inputField({
                id: 'rep-application-email',
                name: 'contact_email',
                label: 'Почта для связи',
                type: 'email',
                required: true,
                value: (store.user && store.user.email) || '',
                autocomplete: 'email',
            })}
            ${textareaField({
                id: 'rep-application-justification',
                name: 'justification',
                label: 'Почему вы представляете этот университет',
                rows: 4,
                placeholder: 'Должность, подразделение, ссылка на страницу сотрудника…',
            })}
            <div class="rounded bg-brand-soft/60 border border-brand/20 px-5 py-4 mb-6 text-sm leading-relaxed text-ink">
                <p class="font-semibold">Совет: приложите фото и подтверждающие документы</p>
                <p class="mt-2 text-ink-soft">Заявки с фотографией и документами рассматриваются быстрее и чаще одобряются.
                Подойдут фото или скан документа с ФИО, справка о должности или учёбе, пропуск,
                доверенность или ссылка на профиль сотрудника на сайте вуза. Документы видит
                только администратор Papaya.</p>
            </div>
            <div class="${UI.field}">
                <label for="rep-application-photo" class="${UI.label}">Ваше фото (необязательно)</label>
                <input id="rep-application-photo" type="file" accept=".png,.jpg,.jpeg" class="${UI.input} py-2">
                <p class="mt-2 text-xs text-ink-faint">PNG или JPG. Помогает администратору узнать вас при проверке.</p>
            </div>
            <div class="${UI.field}">
                <label for="rep-application-files" class="${UI.label}">Подтверждающие документы (необязательно)</label>
                <input id="rep-application-files" type="file" multiple accept=".pdf,.png,.jpg,.jpeg" class="${UI.input} py-2">
                <p class="mt-2 text-xs text-ink-faint">PDF, PNG или JPG. Можно выбрать несколько файлов.</p>
            </div>
            <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Отправить заявку</button>
        </form>`;

    const form = document.getElementById('rep-application-form');
    form.addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(form);
        const universityId = fd.get('university_id') || '';
        const alertBox = document.getElementById('rep-application-alert');
        if (!universityId) {
            alertBox.innerHTML = alertHtml('Выберите университет', 'error');
            return;
        }
        const btn = form.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
            const res = await api.createRepresentativeApplication({
                university_id: universityId,
                justification: (fd.get('justification') || '').trim() || null,
                contact_email: (fd.get('contact_email') || '').trim() || null,
            });
            if (res.ok) {
                const files = form.querySelector('#rep-application-files').files;
                const photo = form.querySelector('#rep-application-photo').files[0];
                const failed = [];
                if (photo) {
                    const upload = new FormData();
                    upload.append('file', photo);
                    upload.append('kind', 'photo');
                    upload.append('name', `Фото: ${photo.name}`);
                    const upRes = await api.uploadRepresentativeApplicationAttachment(
                        res.data.id, upload
                    ).catch(() => ({ ok: false }));
                    if (!upRes.ok) failed.push(photo.name);
                }
                for (const file of Array.from(files || [])) {
                    const upload = new FormData();
                    upload.append('file', file);
                    const upRes = await api.uploadRepresentativeApplicationAttachment(
                        res.data.id, upload
                    ).catch(() => ({ ok: false }));
                    if (!upRes.ok) failed.push(file.name);
                }
                showToast(
                    failed.length
                        ? 'Заявка отправлена, но часть файлов не загрузилась'
                        : 'Заявка отправлена администратору',
                    failed.length ? 'error' : 'success'
                );
                await renderRepresentativeApplicationSection();
                return;
            }
            alertBox.innerHTML = alertHtml(errorText(res), 'error');
        } catch {
            alertBox.innerHTML = alertHtml('Сетевая ошибка', 'error');
        }
        btn.disabled = false;
    });
}

/**
 * Предложка университета: любой пользователь может предложить вуз, которого
 * нет в каталоге. После одобрения он становится представителем созданного вуза.
 */
async function renderUniversityProposalSection() {
    const box = document.getElementById('university-proposal-section');
    if (!box) return;

    box.innerHTML = loadingHtml('Проверяем предложки…');
    const res = await api.listMyUniversityProposals().catch(() => ({ ok: false }));

    const header = `
        <p class="${UI.eyebrow}">Каталог</p>
        <h2 class="mt-5 text-2xl font-extrabold tracking-tight">Предложить университет</h2>`;

    if (!res.ok) {
        box.innerHTML = `${header}
            <div class="mt-6">${alertHtml('Не удалось загрузить предложки', 'error')}</div>`;
        return;
    }

    const proposals = (res.data && res.data.requests) || [];
    const latest = proposals[0] || null;

    if (latest && latest.status === 'pending') {
        box.innerHTML = `${header}
        <div class="${UI.card} px-8 py-6 mt-8">
            <div class="flex flex-wrap items-center gap-3">
                <span class="${UI.badge} ${UI.badgePending}">На рассмотрении</span>
                <span class="text-sm text-ink-faint">от ${formatDate(latest.createdAt)}</span>
            </div>
            <p class="mt-4 text-ink">Университет: <span class="font-semibold">${escHtml(latest.name)}</span></p>
            ${latest.description ? `<p class="mt-3 text-sm text-ink leading-relaxed whitespace-pre-wrap">${escHtml(latest.description)}</p>` : ''}
            ${attachmentLinksHtml(latest.attachments, 'Приложенные документы')}
            <p class="mt-4 text-sm text-ink-soft leading-relaxed">
                ${(latest.payload || {}).become_representative
                    ? 'После одобрения администратор назначит вас представителем этого университета и откроет раздел «Мой университет».'
                    : 'Предложка добавит вуз в каталог. Роль представителя не выдаётся: при подаче не была отмечена галочка «Хочу стать представителем».'}
            </p>
        </div>`;
        return;
    }

    if (latest && latest.status === 'approved') {
        box.innerHTML = `${header}
        <div class="${UI.card} px-8 py-6 mt-8">
            <span class="${UI.badge} ${UI.badgeSuccess}">Университет добавлен</span>
            <p class="mt-4 text-ink">Университет: <span class="font-semibold">${escHtml(latest.name)}</span></p>
            <p class="mt-4 text-sm text-ink-soft leading-relaxed">
                ${(latest.payload || {}).become_representative
                    ? 'Вы назначены представителем этого университета. Если раздел «Мой университет» ещё не появился в меню, обновите страницу.'
                    : 'Университет появился в каталоге. Роль представителя не выдавалась — при подаче не была отмечена галочка «Хочу стать представителем».'}
            </p>
            ${attachmentLinksHtml(latest.attachments, 'Приложенные документы')}
        </div>`;
        return;
    }

    box.innerHTML = `${header}
        <p class="mt-5 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Если вашего университета нет в каталоге, предложите его. После проверки
            администратор создаст вуз. Если вы отметите «Хочу стать представителем»,
            он назначит вас представителем — без галочки вуз просто появится в каталоге.
        </p>
        ${latest && latest.status === 'rejected'
            ? `<div class="mt-8">${alertHtml(
                'Предыдущая предложка отклонена'
                + (latest.rejection_reason ? `: ${latest.rejection_reason}` : '')
                + '. Можно подать новую.', 'error')}</div>`
            : ''}
        <form id="university-proposal-form" class="mt-8 max-w-2xl">
            <div id="university-proposal-alert"></div>
            ${inputField({
                id: 'up-name',
                name: 'name',
                label: 'Полное название университета',
                required: true,
                placeholder: 'Московский физико-технический институт',
            })}
            ${inputField({
                id: 'up-short',
                name: 'short_name',
                label: 'Краткое название / аббревиатура',
                placeholder: 'МФТИ',
            })}
            ${inputField({
                id: 'up-site',
                name: 'website',
                label: 'Официальный сайт',
                type: 'url',
                placeholder: 'https://…',
            })}
            ${inputField({
                id: 'up-preview',
                name: 'preview_image',
                label: 'Маленькое фото для карточки (URL)',
                type: 'url',
                placeholder: 'https://…',
            })}
            ${inputField({
                id: 'up-image',
                name: 'image',
                label: 'Большая картинка для страницы (URL)',
                type: 'url',
                placeholder: 'https://…',
            })}
            ${textareaField({
                id: 'up-desc',
                name: 'description',
                label: 'Описание',
                rows: 4,
                placeholder: 'Чем университет полезен школьнику, какие олимпиады принимает…',
            })}
            <div class="${UI.field}">
                <label class="flex items-start gap-3 text-sm text-ink">
                    <input id="up-become-representative" type="checkbox" name="become_representative" class="mt-1">
                    <span>
                        <span class="font-semibold">Хочу стать представителем этого университета</span>
                        <span class="block mt-1 text-ink-soft">После одобрения администратор назначит вас представителем: вы сможете вести правила льгот и загружать приказы.</span>
                    </span>
                </label>
            </div>
            <div id="up-representative-fields" class="hidden">
                ${inputField({
                    id: 'up-contact-email',
                    name: 'contact_email',
                    label: 'Почта для связи',
                    type: 'email',
                    value: (store.user && store.user.email) || '',
                    autocomplete: 'email',
                })}
                ${textareaField({
                    id: 'up-rep-justification',
                    name: 'representative_justification',
                    label: 'Почему вы можете представлять этот университет',
                    rows: 3,
                    placeholder: 'Должность, подразделение, ссылка на страницу сотрудника…',
                })}
            </div>
            <div class="rounded bg-brand-soft/60 border border-brand/20 px-5 py-4 mb-6 text-sm leading-relaxed text-ink">
                <p class="font-semibold">Совет: приложите подтверждающие документы</p>
                <p class="mt-2 text-ink-soft">Предложки с документами рассматриваются быстрее и чаще одобряются.
                Подойдут фото или скан документа с ФИО, справка о должности или учёбе, пропуск,
                доверенность или ссылка на профиль сотрудника на сайте вуза. Документы видит
                только администратор Papaya.</p>
            </div>
            <div class="${UI.field}">
                <label for="university-proposal-files" class="${UI.label}">Подтверждающие документы (необязательно)</label>
                <input id="university-proposal-files" type="file" multiple accept=".pdf,.png,.jpg,.jpeg" class="${UI.input} py-2">
                <p class="mt-2 text-xs text-ink-faint">PDF, PNG или JPG. Можно выбрать несколько файлов.</p>
            </div>
            <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Отправить предложку</button>
        </form>`;

    const form = document.getElementById('university-proposal-form');
    const repToggle = form.querySelector('#up-become-representative');
    const repFields = form.querySelector('#up-representative-fields');
    const syncRepFields = () => {
        const enabled = repToggle.checked;
        repFields.classList.toggle('hidden', !enabled);
        repFields.querySelectorAll('input, textarea').forEach(el => {
            el.disabled = !enabled;
            el.required = enabled && el.name === 'contact_email';
        });
    };
    repToggle.addEventListener('change', syncRepFields);
    syncRepFields();

    form.addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(form);
        const alertBox = document.getElementById('university-proposal-alert');
        const becomeRepresentative = fd.get('become_representative') === 'on';
        const contactEmail = (fd.get('contact_email') || '').trim();
        if (becomeRepresentative && !contactEmail) {
            alertBox.innerHTML = alertHtml('Укажите почту для связи', 'error');
            return;
        }
        const btn = form.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
            const res = await api.createUniversityProposal({
                name: (fd.get('name') || '').trim(),
                short_name: (fd.get('short_name') || '').trim() || null,
                website: (fd.get('website') || '').trim() || null,
                preview_image: (fd.get('preview_image') || '').trim() || null,
                image: (fd.get('image') || '').trim() || null,
                description: (fd.get('description') || '').trim() || null,
                become_representative: becomeRepresentative,
                contact_email: becomeRepresentative ? contactEmail : null,
                representative_justification: becomeRepresentative
                    ? ((fd.get('representative_justification') || '').trim() || null)
                    : null,
            });
            if (res.ok) {
                const files = form.querySelector('#university-proposal-files').files;
                const failed = [];
                for (const file of Array.from(files || [])) {
                    const upload = new FormData();
                    upload.append('file', file);
                    const upRes = await api.uploadRequestAttachment(
                        res.data.id, upload
                    ).catch(() => ({ ok: false }));
                    if (!upRes.ok) failed.push(file.name);
                }
                showToast(
                    failed.length
                        ? 'Предложка отправлена, но часть файлов не загрузилась'
                        : 'Предложка отправлена администратору',
                    failed.length ? 'error' : 'success'
                );
                await renderUniversityProposalSection();
                return;
            }
            alertBox.innerHTML = alertHtml(errorText(res), 'error');
        } catch {
            alertBox.innerHTML = alertHtml('Сетевая ошибка', 'error');
        }
        btn.disabled = false;
    });
}