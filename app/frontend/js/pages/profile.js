function renderProfile() {
    const page = document.getElementById('page');
    if (!store.user) { navigate('#/auth'); return; }
    page.innerHTML = '<div class="loading">Загрузка...</div>';

    api.getUser(store.user.id).then(res => {
        if (!res.ok) {
            page.innerHTML = '<div class="alert alert-error">Не удалось загрузить профиль</div>';
            return;
        }
        const u = res.data;
        const initials = ((u.name||'?')[0] + (u.surname||'')[0] || '?').toUpperCase();
        const genderText = u.gender === 'male' ? 'Мужской' : u.gender === 'female' ? 'Женский' : 'Не указан';
        const accHtml = u.isActive
            ? '<span class="status-badge status-active">Активен</span>'
            : '<span class="status-badge status-inactive">Заблокирован</span>';
        const regDate = u.createdAt ? String(u.createdAt).slice(0,10) : 'Н/Д';

        page.innerHTML = `
        <div class="profile-layout">
            <a href="#/" class="back-link">&#127816; На главную</a>

            <div class="profile-card">
                <div class="profile-header">
                    <div class="avatar">${escHtml(initials)}</div>
                    <div>
                        <h2>${escHtml(u.name)} ${escHtml(u.surname)}</h2>
                        <span class="role-badge">${escHtml(u.role || 'USER')}</span>
                    </div>
                    <button id="btn-edit-profile" class="btn btn-outline btn-sm">Редактировать профиль</button>
                </div>

                <div class="profile-fields">
                    <div class="profile-field">
                        <span class="label">Email</span>
                        <span class="value">${escHtml(u.email)}</span>
                    </div>
                    <div class="profile-field">
                        <span class="label">Телефон</span>
                        <span class="value">${escHtml(u.phone || 'Не указан')}</span>
                    </div>
                    <div class="profile-field">
                        <span class="label">Дата рождения</span>
                        <span class="value">${escHtml(u.bday || 'Не указана')}</span>
                    </div>
                    <div class="profile-field">
                        <span class="label">Пол</span>
                        <span class="value">${genderText}</span>
                    </div>
                    <div class="profile-field">
                        <span class="label">Страна</span>
                        <span class="value">${escHtml(u.country || 'Не указана')}</span>
                    </div>
                    <div class="profile-field">
                        <span class="label">Регион</span>
                        <span class="value">${escHtml(u.region || 'Не указан')}</span>
                    </div>
                    <div class="profile-field">
                        <span class="label">Статус</span>
                        <span class="value">${escHtml(u.status || 'Не задан')}</span>
                    </div>
                    <div class="profile-field">
                        <span class="label">Аккаунт</span>
                        <span class="value">${accHtml}</span>
                    </div>
                    <div class="profile-field">
                        <span class="label">ID</span>
                        <span class="value mono">${escHtml(u.id)}</span>
                    </div>
                </div>

                <div class="profile-bio">
                    <h3>О себе</h3>
                    <p>${escHtml(u.bio || 'Нет информации.')}</p>
                </div>
                <div class="profile-reg">Зарегистрирован: ${regDate}</div>

                <!-- Управление событиями -->
                <div class="events-mgmt">
                    <h3>Управление событиями</h3>

                    <div class="mgmt-grid">
                        <!-- Создать событие -->
                        <div class="mgmt-card">
                            <h4>Создать событие</h4>
                            <div id="mgmt-create-alert"></div>
                            <form id="mgmt-create-form">
                                <div class="form-group">
                                    <label>Название *</label>
                                    <input name="name" required>
                                </div>
                                <div class="form-group">
                                    <label>Описание</label>
                                    <textarea name="disc" rows="3"></textarea>
                                </div>
                                <div class="form-group">
                                    <label>URL превью</label>
                                    <input name="preview_picture" type="url" placeholder="https://...">
                                </div>
                                <div class="form-group">
                                    <label>URL полное фото</label>
                                    <input name="picture" type="url" placeholder="https://...">
                                </div>
                                <button type="submit" class="btn btn-primary btn-sm btn-block">Создать событие</button>
                            </form>
                        </div>

                        <!-- Загрузить из PDF -->
                        <div class="mgmt-card">
                            <h4>Добавить события из PDF-таблицы</h4>
                            <div id="mgmt-pdf-alert"></div>
                            <form id="mgmt-pdf-form">
                                <div class="form-group">
                                    <label>PDF-файл с таблицей мероприятий</label>
                                    <input name="file" type="file" accept=".pdf" required>
                                </div>
                                <p class="mgmt-hint">Загрузите PDF таблицу со списком мероприятий для автоматического импорта.</p>
                                <button type="submit" class="btn btn-primary btn-sm btn-block" id="pdf-submit-btn">Загрузить и добавить</button>
                            </form>
                        </div>

                        <!-- Редактировать событие -->
                        <div class="mgmt-card mgmt-card-wide">
                            <h4>Редактировать существующее</h4>
                            <div id="mgmt-edit-alert"></div>
                            <form id="mgmt-edit-form">
                                <div class="form-group">
                                    <label>ID события *</label>
                                    <input name="event_id" required placeholder="UUID события">
                                </div>
                                <div class="form-row">
                                    <div class="form-group">
                                        <label>Название *</label>
                                        <input name="name" required>
                                    </div>
                                    <div class="form-group">
                                        <label>Описание</label>
                                        <textarea name="disc" rows="2"></textarea>
                                    </div>
                                </div>
                                <div class="form-row">
                                    <div class="form-group">
                                        <label>URL превью</label>
                                        <input name="preview_picture" type="url">
                                    </div>
                                    <div class="form-group">
                                        <label>URL полное фото</label>
                                        <input name="picture" type="url">
                                    </div>
                                </div>
                                <button type="submit" class="btn btn-outline btn-sm btn-block">Обновить событие</button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        </div>`;

        // Edit profile
        document.getElementById('btn-edit-profile').addEventListener('click', () => openEditProfileModal(u));

        // Create event
        document.getElementById('mgmt-create-form').addEventListener('submit', async e => {
            e.preventDefault();
            const fd = new FormData(e.target);
            const now = new Date().toISOString();
            const res = await api.addEvent({
                id: '', owner: u.id,
                name: fd.get('name'),
                disc: fd.get('disc') || null,
                preview_picture: fd.get('preview_picture') || null,
                picture: fd.get('picture') || null,
                isActive: true, createdAt: now, updatedAt: now,
            });
            const el = document.getElementById('mgmt-create-alert');
            if (res.ok) {
                el.innerHTML = '<div class="alert alert-success">Событие создано</div>';
                e.target.reset();
            } else {
                el.innerHTML = `<div class="alert alert-error">${escHtml(res.data?.detail || 'Ошибка')}</div>`;
            }
        });

        // PDF upload
        document.getElementById('mgmt-pdf-form').addEventListener('submit', async e => {
            e.preventDefault();
            const btn = document.getElementById('pdf-submit-btn');
            const el = document.getElementById('mgmt-pdf-alert');
            const fileInput = e.target.querySelector('input[type=file]');
            if (!fileInput.files.length) {
                el.innerHTML = '<div class="alert alert-error">Выберите файл</div>';
                return;
            }
            btn.disabled = true;
            btn.textContent = 'Обработка файла...';
            el.innerHTML = '<div class="alert alert-success">Пожалуйста, подождите. Это может занять некоторое время.</div>';

            const fd = new FormData();
            fd.append('file', fileInput.files[0]);
            const res = await api.addEventsPdf(fd);

            btn.disabled = false;
            btn.textContent = 'Загрузить и добавить';
            if (res.ok) {
                el.innerHTML = '<div class="alert alert-success">События успешно импортированы</div>';
                e.target.reset();
            } else {
                el.innerHTML = `<div class="alert alert-error">${escHtml(res.data?.detail || 'Ошибка импорта')}</div>`;
            }
        });

        // Edit event
        document.getElementById('mgmt-edit-form').addEventListener('submit', async e => {
            e.preventDefault();
            const fd = new FormData(e.target);
            const now = new Date().toISOString();
            const res = await api.editEvent({
                id: fd.get('event_id'),
                owner: u.id,
                name: fd.get('name'),
                disc: fd.get('disc') || null,
                preview_picture: fd.get('preview_picture') || null,
                picture: fd.get('picture') || null,
                isActive: true, createdAt: now, updatedAt: now,
            });
            const el = document.getElementById('mgmt-edit-alert');
            if (res.ok) {
                el.innerHTML = '<div class="alert alert-success">Событие обновлено</div>';
            } else {
                el.innerHTML = `<div class="alert alert-error">${escHtml(res.data?.detail || 'Ошибка')}</div>`;
            }
        });
    });
}

function openEditProfileModal(u) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
    <div class="modal">
        <h2>Изменение данных профиля</h2>
        <div id="modal-alert"></div>
        <form id="edit-profile-form">
            <div class="form-row">
                <div class="form-group">
                    <label>Имя</label>
                    <input name="name" value="${escAttr(u.name || '')}">
                </div>
                <div class="form-group">
                    <label>Фамилия</label>
                    <input name="surname" value="${escAttr(u.surname || '')}">
                </div>
            </div>
            <div class="form-group">
                <label>Email</label>
                <input name="email" type="email" value="${escAttr(u.email || '')}">
            </div>
            <div class="form-group">
                <label>Телефон</label>
                <input name="phone" value="${escAttr(u.phone || '')}">
            </div>
            <div class="form-group">
                <label>Дата рождения (YYYY-MM-DD)</label>
                <input name="bday" value="${escAttr(u.bday || '')}">
            </div>
            <div class="form-group">
                <label>Пол</label>
                <select name="gender">
                    <option value="">Не указан</option>
                    <option value="male"   ${u.gender==='male'?'selected':''}>Мужской</option>
                    <option value="female" ${u.gender==='female'?'selected':''}>Женский</option>
                </select>
            </div>
            <div class="form-group">
                <label>Страна</label>
                <input name="country" value="${escAttr(u.country || '')}">
            </div>
            <div class="form-group">
                <label>Регион</label>
                <input name="region" value="${escAttr(u.region || '')}">
            </div>
            <div class="form-group">
                <label>Статус (текст)</label>
                <input name="status" value="${escAttr(u.status || '')}">
            </div>
            <div class="form-group">
                <label>О себе</label>
                <textarea name="bio" rows="3">${escHtml(u.bio || '')}</textarea>
            </div>
            <div class="modal-actions">
                <button type="button" id="modal-cancel" class="btn btn-outline">Отмена</button>
                <button type="submit" class="btn btn-primary">Сохранить</button>
            </div>
        </form>
    </div>`;
    document.body.appendChild(overlay);

    overlay.querySelector('#modal-cancel').addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });

    overlay.querySelector('#edit-profile-form').addEventListener('submit', async e => {
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
            role: u.role || 'USER',
        });
        if (res.ok) { overlay.remove(); renderProfile(); }
        else {
            overlay.querySelector('#modal-alert').innerHTML =
                `<div class="alert alert-error">${escHtml(res.data?.detail || 'Ошибка')}</div>`;
        }
    });
}