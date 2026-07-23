function renderProfile() {
    const page = document.getElementById('page');
    if (!store.user) { navigate('#/auth'); return; }

    page.innerHTML = `<div class="loading">Загрузка...</div>`;

    api.getUser(store.user.id).then(res => {
        if (!res.ok) {
            page.innerHTML = `<div class="alert alert-error">Не удалось загрузить профиль</div>`;
            return;
        }
        const u = res.data;
        page.innerHTML = `
            <div class="profile-card">
                <h2>Профиль</h2>
                <div id="profile-alert"></div>
                <div class="profile-field"><span class="label">Имя</span><span>${escHtml(u.name)}</span></div>
                <div class="profile-field"><span class="label">Фамилия</span><span>${escHtml(u.surname)}</span></div>
                <div class="profile-field"><span class="label">Email</span><span>${escHtml(u.email)}</span></div>
                <div class="profile-field"><span class="label">Пол</span><span>${escHtml(u.gender || '—')}</span></div>
                <div class="profile-field"><span class="label">Дата рождения</span><span>${escHtml(u.bday || '—')}</span></div>
                <div class="profile-field"><span class="label">О себе</span><span>${escHtml(u.bio || '—')}</span></div>
                <div class="profile-field"><span class="label">Телефон</span><span>${escHtml(u.phone || '—')}</span></div>
                <div class="profile-field"><span class="label">Страна</span><span>${escHtml(u.country || '—')}</span></div>
                <div class="profile-field"><span class="label">Регион</span><span>${escHtml(u.region || '—')}</span></div>
                <div class="profile-field"><span class="label">Статус</span><span>${escHtml(u.status || '—')}</span></div>
                <div style="margin-top:24px">
                    <button class="btn btn-primary" id="btn-edit-profile">Редактировать</button>
                </div>
            </div>
        `;
        document.getElementById('btn-edit-profile').addEventListener('click', () => openEditProfileModal(u));
    });
}

function openEditProfileModal(u) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
        <div class="modal">
            <h2>Редактирование профиля</h2>
            <div id="modal-alert"></div>
            <form id="edit-profile-form">
                <div class="form-group">
                    <label>Имя</label>
                    <input type="text" name="name" value="${escAttr(u.name)}">
                </div>
                <div class="form-group">
                    <label>Фамилия</label>
                    <input type="text" name="surname" value="${escAttr(u.surname)}">
                </div>
                <div class="form-group">
                    <label>Email</label>
                    <input type="email" name="email" value="${escAttr(u.email)}" required>
                </div>
                <div class="form-group">
                    <label>Пол</label>
                    <select name="gender">
                        <option value="">—</option>
                        <option value="male" ${u.gender==='male'?'selected':''}>Мужской</option>
                        <option value="female" ${u.gender==='female'?'selected':''}>Женский</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Дата рождения</label>
                    <input type="date" name="bday" value="${u.bday || ''}">
                </div>
                <div class="form-group">
                    <label>О себе</label>
                    <textarea name="bio">${escHtml(u.bio || '')}</textarea>
                </div>
                <div class="form-group">
                    <label>Телефон</label>
                    <input type="text" name="phone" value="${escAttr(u.phone || '')}">
                </div>
                <div class="form-group">
                    <label>Страна</label>
                    <input type="text" name="country" value="${escAttr(u.country || '')}">
                </div>
                <div class="form-group">
                    <label>Регион</label>
                    <input type="text" name="region" value="${escAttr(u.region || '')}">
                </div>
                <div class="form-group">
                    <label>Статус</label>
                    <input type="text" name="status" value="${escAttr(u.status || '')}">
                </div>
                <div class="form-group">
                    <label>Роль</label>
                    <select name="role">
                        <option value="student" ${u.role==='student'?'selected':''}>Школьник</option>
                        <option value="teacher" ${u.role==='teacher'?'selected':''}>Учитель</option>
                        <option value="org" ${u.role==='org'?'selected':''}>Организация</option>
                    </select>
                </div>
                <div class="modal-actions">
                    <button type="button" class="btn btn-outline" id="modal-cancel">Отмена</button>
                    <button type="submit" class="btn btn-primary">Сохранить</button>
                </div>
            </form>
        </div>
    `;
    document.body.appendChild(overlay);

    overlay.querySelector('#modal-cancel').addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

    overlay.querySelector('#edit-profile-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const res = await api.editUser(u.id, {
            id: u.id,
            name: fd.get('name'),
            surname: fd.get('surname'),
            email: fd.get('email'),
            isActive: true,
            gender: fd.get('gender') || null,
            bday: fd.get('bday') || null,
            bio: fd.get('bio') || null,
            phone: fd.get('phone') || null,
            country: fd.get('country') || null,
            region: fd.get('region') || null,
            status: fd.get('status') || null,
            role: fd.get('role'),
        });
        if (res.ok) {
            overlay.remove();
            renderProfile();
        } else {
            overlay.querySelector('#modal-alert').innerHTML =
                `<div class="alert alert-error">${res.data?.detail || 'Ошибка'}</div>`;
        }
    });
}