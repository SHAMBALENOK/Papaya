function renderDashboard() {
    const page = document.getElementById('page');
    page.innerHTML = `<div class="loading">Загрузка...</div>`;

    api.getMain().then(res => {
        if (!res.ok) {
            navigate('#/auth');
            return;
        }
        store.setUser({
            id: res.data.user_id,
            name: res.data.user_name,
            surname: res.data.user_surname,
            email: res.data.user_email,
        });
        store.setEvents(res.data.events || []);
        drawDashboard();
    }).catch(() => {
        navigate('#/auth');
    });
}

function drawDashboard() {
    const page = document.getElementById('page');
    const events = store.events;

    let cardsHtml = '';
    if (events.length === 0) {
        cardsHtml = '<p style="color:var(--text-muted)">Пока нет олимпиад.</p>';
    } else {
        cardsHtml = '<div class="events-grid">' + events.map(ev => `
            <a href="#/event/${ev.id}" class="event-card">
                ${ev.preview_picture ? `<img src="${ev.preview_picture}" class="event-img" alt="">` : '<div class="event-img"></div>'}
                <h3>${escHtml(ev.name)}</h3>
                <p>${escHtml(ev.disc || 'Без описания')}</p>
            </a>
        `).join('') + '</div>';
    }

    page.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;">
            <h1 class="section-title" style="margin-bottom:0">Олимпиады</h1>
            <button class="btn btn-primary" id="btn-add-event">+ Добавить</button>
        </div>
        ${cardsHtml}
    `;

    document.getElementById('btn-add-event').addEventListener('click', openAddEventModal);
}

function openAddEventModal() {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
        <div class="modal">
            <h2>Новое событие</h2>
            <div id="modal-alert"></div>
            <form id="add-event-form">
                <div class="form-group">
                    <label>Название</label>
                    <input type="text" name="name" required>
                </div>
                <div class="form-group">
                    <label>Описание</label>
                    <textarea name="disc"></textarea>
                </div>
                <div class="form-group">
                    <label>URL превью-картинки</label>
                    <input type="text" name="preview_picture" placeholder="https://...">
                </div>
                <div class="form-group">
                    <label>URL картинки</label>
                    <input type="text" name="picture" placeholder="https://...">
                </div>
                <div class="modal-actions">
                    <button type="button" class="btn btn-outline" id="modal-cancel">Отмена</button>
                    <button type="submit" class="btn btn-primary">Создать</button>
                </div>
            </form>
        </div>
    `;
    document.body.appendChild(overlay);

    overlay.querySelector('#modal-cancel').addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

    overlay.querySelector('#add-event-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const now = new Date().toISOString();
        const res = await api.addEvent(
            { id: store.user.id, name: store.user.name, surname: store.user.surname, email: store.user.email, isActive: true },
            {
                id: crypto.randomUUID(),
                owner: store.user.id,
                name: fd.get('name'),
                disc: fd.get('disc') || null,
                preview_picture: fd.get('preview_picture') || null,
                picture: fd.get('picture') || null,
                isActive: true,
                createdAt: now,
                updatedAt: now,
            }
        );
        if (res.ok) {
            overlay.remove();
            renderDashboard();
        } else {
            overlay.querySelector('#modal-alert').innerHTML =
                `<div class="alert alert-error">${res.data?.detail || 'Ошибка'}</div>`;
        }
    });
}