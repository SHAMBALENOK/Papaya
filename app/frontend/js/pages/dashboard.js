function renderDashboard() {
    const page = document.getElementById('page');
    page.innerHTML = '<div class="loading">Загрузка...</div>';

    api.getMain().then(res => {
        if (!res.ok) { navigate('#/auth'); return; }
        store.setUser({
            id: res.data.user_id,
            name: res.data.user_name,
            surname: res.data.user_surname,
            email: res.data.user_email,
        });
        store.setEvents(res.data.events || []);
        drawDashboard();
    }).catch(() => navigate('#/auth'));
}

function drawDashboard() {
    const page = document.getElementById('page');
    const events = store.events;

    let cards = '';
    if (!events.length) {
        cards = `
        <div class="empty-state">
            <div class="emoji">&#128532;</div>
            <p>Событий пока нет</p>
            <span>Загляните позже, мы обязательно добавим что-нибудь интересное!</span>
        </div>`;
    } else {
        cards = '<div class="events-grid">' + events.map(ev => {
            const img = ev.preview_picture || 'https://placehold.co/600x400/e9ecef/95a5a6?text=No+Preview';
            return `
            <a href="#/event/${ev.id}" class="event-card">
                <img class="card-img" src="${escAttr(img)}" alt="${escAttr(ev.name)}"
                     onerror="this.src='https://placehold.co/600x400/e9ecef/95a5a6?text=No+Preview'">
                <div class="card-body">
                    <h3>${escHtml(ev.name)}</h3>
                    <p>${escHtml(ev.disc || 'Без описания')}</p>
                </div>
            </a>`;
        }).join('') + '</div>';
    }

    page.innerHTML = `
    <div class="dashboard-header">
      <h1 class="section-title">Актуальные олимпиады</h1>
      <div style="display:flex;gap:8px;">
        <button id="btn-add-pdf" class="btn btn-outline">PDF</button>
        <button id="btn-add-event" class="btn btn-primary">+ Добавить</button>
      </div>
    </div>
    ${cards}`;

    document.getElementById('btn-add-event').addEventListener('click', openAddEventModal);
    document.getElementById('btn-add-pdf').addEventListener('click', openPdfModal);
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
                <label>Название *</label>
                <input name="name" required>
            </div>
            <div class="form-group">
                <label>Описание</label>
                <textarea name="disc" rows="4" placeholder="Описание олимпиады..."></textarea>
            </div>
            <div class="form-group">
                <label>URL превью</label>
                <input name="preview_picture" type="url" placeholder="https://...">
            </div>
            <div class="form-group">
                <label>URL полное фото</label>
                <input name="picture" type="url" placeholder="https://...">
            </div>
            <div class="modal-actions">
                <button type="button" id="modal-cancel" class="btn btn-outline">Отмена</button>
                <button type="submit" class="btn btn-primary">Создать событие</button>
            </div>
        </form>
    </div>`;
    document.body.appendChild(overlay);

    overlay.querySelector('#modal-cancel').addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });

    overlay.querySelector('#add-event-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const now = new Date().toISOString();
        const res = await api.addEvent({
            id: '',
            owner: store.user.id,
            name: fd.get('name'),
            disc: fd.get('disc') || null,
            preview_picture: fd.get('preview_picture') || null,
            picture: fd.get('picture') || null,
            isActive: true,
            createdAt: now,
            updatedAt: now,
        });
        if (res.ok) {
          overlay.remove();
          renderDashboard();
          showToast('Событие создано', 'success');
        }
        else {
            overlay.querySelector('#modal-alert').innerHTML =
                `<div class="alert alert-error">${escHtml(res.data?.detail || 'Ошибка')}</div>`;
        }
    });

}
function openPdfModal() {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
  <div class="modal">
    <h2>Импорт из PDF</h2>
    <div id="pdf-alert"></div>
    <form id="pdf-form">
      <div class="form-group">
        <label>PDF-файл с таблицей *</label>
        <input name="file" type="file" accept=".pdf" required>
      </div>
      <div class="modal-actions">
        <button type="button" id="pdf-cancel" class="btn btn-outline">Отмена</button>
        <button type="submit" class="btn btn-primary">Загрузить</button>
      </div>
    </form>
  </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('#pdf-cancel').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });

  overlay.querySelector('#pdf-form').addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const res = await api.addEventsPdf(fd);
    if (res.ok && Array.isArray(res.data)) {
      overlay.remove();
      // Обновляем store и перерисовываем — события сразу на dashboard
      store.setEvents([...store.events, ...res.data]);
      drawDashboard();
      showToast(`Добавлено событий: ${res.data.length}`, 'success');
    } else {
      overlay.querySelector('#pdf-alert').innerHTML =
        `<div class="alert alert-error">${escHtml(res.data?.detail || 'Ошибка')}</div>`;
    }
  });
}