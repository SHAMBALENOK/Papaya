document.addEventListener('DOMContentLoaded', async () => {
    await loadUserData();
    await loadEvents();
});

async function loadUserData() {
    try {
        const response = await fetch('/api/v1/', { credentials: 'include' });

        if (response.status === 401 || response.status === 403) {
            window.location.href = '/static/html/auth.html';
            return;
        }

        if (!response.ok) {
            throw new Error('Failed to fetch user data');
        }

        const data = await response.json();

        const navLinks = document.getElementById('nav-links');
        navLinks.innerHTML = `
            <a href="/static/html/user_detail.html?id=${data.user_id}">Профиль</a>
            <a href="#" onclick="logout(); return false;">Выйти</a>
        `;
    } catch (error) {
        console.error('Error loading user data:', error);
        document.getElementById('nav-links').innerHTML = `<a href="/static/html/auth.html">Войти / Регистрация</a>`;
    }
}

async function loadEvents() {
    try {
        const response = await fetch('/api/v1/', { credentials: 'include' });
        if (!response.ok) throw new Error('Failed to load events');

        const data = await response.json();
        const container = document.getElementById('events-container');

        if (!data.events || data.events.length === 0) {
            container.innerHTML = `
                <div class="no-events">
                    <p>Событий пока нет</p>
                    <p>Загляните позже, мы обязательно добавим что-нибудь интересное!</p>
                </div>
            `;
            return;
        }

        container.innerHTML = data.events.map(event => {
            const imgSrc = event.preview_picture || 'https://placehold.co/600x400/e9ecef/95a5a6?text=No+Preview';
            return `
                <div class="event-card">
                    <img src="${imgSrc}" alt="${event.name}">
                    <h3>${event.name}</h3>
                    <a href="/static/html/event_detail.html?id=${event.id}" class="btn">Подробнее</a>
                </div>
            `;
        }).join('');

    } catch (error) {
        document.getElementById('events-container').innerHTML =
            '<p class="error">Ошибка загрузки событий</p>';
    }
}

async function logout() {
    try {
        await fetch('/api/v1/auth/logout', { credentials: 'include' });
        window.location.href = '/static/html/auth.html';
    } catch (error) {
        console.error('Logout failed:', error);
    }
}