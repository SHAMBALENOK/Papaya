function renderEvent(eventId) {
    const page = document.getElementById('page');
    page.innerHTML = '<div class="loading">Загрузка...</div>';

    api.getEvent(eventId).then(res => {
        if (!res.ok) {
            page.innerHTML = `
            <div class="event-detail">
                <div class="alert alert-error">Событие не найдено</div>
                <a href="#/" class="back-link">&larr; Вернуться к списку</a>
            </div>`;
            return;
        }

        const ev = res.data;
        const imgSrc = ev.picture || ev.preview_picture || null;
        const created = ev.createdAt ? ev.createdAt.slice(0, 10) : 'Н/Д';
        const updated = ev.updatedAt ? ev.updatedAt.slice(0, 10) : 'Н/Д';

        const statusHtml = ev.isActive
            ? '<span class="status-dot on"></span> Активно'
            : '<span class="status-dot off"></span> Неактивно';

        page.innerHTML = `
        <div class="event-detail">
            <a href="#/" class="back-link">&larr; Вернуться к списку</a>

            ${imgSrc ? `<img src="${escAttr(imgSrc)}" alt="${escAttr(ev.name)}" class="event-detail-img"
                 onerror="this.style.display='none'">` : ''}

            <h1>${escHtml(ev.name)}</h1>

            ${ev.disc ? `
            <div class="detail-section">
                <h3>Описание</h3>
                <p class="event-disc">${escHtml(ev.disc)}</p>
            </div>` : ''}

            <div class="detail-section">
                <h3>Информация</h3>
                <div class="detail-row">
                    <span class="detail-label">Статус</span>
                    <span class="detail-value">${statusHtml}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">ID События</span>
                    <span class="detail-value mono">${escHtml(ev.id)}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Создано</span>
                    <span class="detail-value">${created}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Обновлено</span>
                    <span class="detail-value">${updated}</span>
                </div>
            </div>
        </div>`;
    }).catch(() => {
        page.innerHTML = `
        <div class="event-detail">
            <div class="alert alert-error">Ошибка загрузки</div>
            <a href="#/" class="back-link">&larr; Вернуться к списку</a>
        </div>`;
    });
}