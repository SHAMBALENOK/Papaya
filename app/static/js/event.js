document.addEventListener('DOMContentLoaded', async () => {
    const urlParams = new URLSearchParams(window.location.search);
    const eventId = urlParams.get('id');

    if (!eventId) {
        window.location.href = '/static/html/main.html';
        return;
    }

    await loadEventDetails(eventId);
});

async function loadEventDetails(eventId) {
    try {
        const response = await fetch(`/api/v1/event/${eventId}`, { credentials: 'include' });

        if (response.status === 401 || response.status === 403) {
            window.location.href = '/static/html/auth.html';
            return;
        }

        if (!response.ok) {
            throw new Error('Event not found');
        }

        const event = await response.json();
        displayEvent(event);

        document.getElementById('event-loading').style.display = 'none';
        document.getElementById('event-view').style.display = 'block';

    } catch (error) {
        document.getElementById('event-loading').innerHTML =
            '<p class="error">Ошибка загрузки события</p>';
    }
}

function displayEvent(event) {
    const imgUrl = event.picture || event.preview_picture ||
                   'https://placehold.co/600x400/e9ecef/95a5a6?text=No+Preview';
    document.getElementById('event-image').src = imgUrl;

    document.getElementById('event-name').textContent = event.name;

    const paramsContainer = document.getElementById('event-params');
    let paramsHTML = '';

    if (event.min_grade && event.max_grade &&
        event.min_grade !== '' && event.max_grade !== '') {
        paramsHTML += `<div class="param-item">Классы: ${event.min_grade} - ${event.max_grade}</div>`;
    }

    if (event.min_age && event.max_age &&
        event.min_age !== '' && event.max_age !== '') {
        paramsHTML += `<div class="param-item">Возраст: ${event.min_age} - ${event.max_age} лет</div>`;
    }

    if (event.place && event.place !== 'null' && event.place.trim() !== '') {
        paramsHTML += `<div class="param-item">Место проведения: ${event.place}</div>`;
    }

    paramsContainer.innerHTML = paramsHTML;

    const detailsContainer = document.getElementById('event-details');
    let detailsHTML = '';
    let hasDetails = false;

    if (event.course && event.course !== 'null' && event.course.trim() !== '') {
        detailsHTML += `<div class="detail-item">Курс / Направление: ${event.course}</div>`;
        hasDetails = true;
    }

    if (event.profile && event.profile !== 'null' && event.profile.trim() !== '') {
        detailsHTML += `<div class="detail-item">Профиль: ${event.profile}</div>`;
        hasDetails = true;
    }

    if (event.level && event.level !== 'null' && event.level.trim() !== '') {
        detailsHTML += `<div class="detail-item">Уровень: ${event.level}</div>`;
        hasDetails = true;
    }

    if (event.diploma && event.diploma !== 'null' && event.diploma.trim() !== '') {
        detailsHTML += `<div class="detail-item">Награда / Диплом: ${event.diploma}</div>`;
        hasDetails = true;
    }

    if (hasDetails) {
        document.getElementById('event-details-section').style.display = 'block';
        detailsContainer.innerHTML = detailsHTML;
    }

    const statusBadge = document.getElementById('event-status');
    const statusText = statusBadge.querySelector('.status-text');
    const statusDot = statusBadge.querySelector('.status-dot');

    if (event.isActive) {
        statusBadge.classList.add('active');
        statusText.textContent = 'Активно';
    } else {
        statusBadge.classList.remove('active');
        statusText.textContent = 'Неактивно';
    }

    document.getElementById('event-id').textContent = event.id;
    document.getElementById('event-updated').textContent =
        event.updatedAt ? event.updatedAt.slice(0, 10) : 'Н/Д';
}