let currentUser = null;
let isOwnProfile = false;

document.addEventListener('DOMContentLoaded', async () => {
    const urlParams = new URLSearchParams(window.location.search);
    const userId = urlParams.get('id');

    if (!userId) {
        window.location.href = '/static/html/main.html';
        return;
    }

    await loadUserProfile(userId);
});

async function loadUserProfile(userId) {
    try {
        const response = await fetch(`/api/v1/user/${userId}`, { credentials: 'include' });

        if (!response.ok) {
            throw new Error('Failed to load profile');
        }

        const user = await response.json();
        currentUser = user;

        // Check if it's own profile
        try {
            const mainResponse = await fetch('/api/v1/', { credentials: 'include' });
            if (mainResponse.ok) {
                const mainData = await mainResponse.json();
                isOwnProfile = mainData.user_id === userId;
            }
        } catch (e) {
            isOwnProfile = false;
        }

        displayUserProfile(user);

        document.getElementById('profile-loading').style.display = 'none';
        document.getElementById('profile-view').style.display = 'block';

    } catch (error) {
        document.getElementById('profile-loading').innerHTML =
            '<p class="error">Ошибка загрузки профиля</p>';
    }
}

function displayUserProfile(user) {
    // Avatar
    const initial = user.name ? user.name.charAt(0).toUpperCase() : '?';
    document.getElementById('user-avatar').textContent = initial;

    // Basic info
    document.getElementById('user-fullname').textContent = `${user.name} ${user.surname}`;
    document.getElementById('user-role').textContent = user.role;
    document.getElementById('user-email').textContent = user.email;
    document.getElementById('user-phone').textContent = user.phone || 'Не указан';
    document.getElementById('user-bday').textContent = user.bday || 'Не указана';

    const genderMap = { 'male': 'Мужской', 'female': 'Женский' };
    document.getElementById('user-gender').textContent = genderMap[user.gender] || 'Не указан';

    document.getElementById('user-region').textContent = user.region || 'Не указан';
    document.getElementById('user-status').textContent = user.status || 'Не задан';
    document.getElementById('user-is-active').textContent = user.isActive ? 'Активен' : 'Заблокирован';

    // Bio
    document.getElementById('user-bio').textContent = user.bio || 'Нет информации.';

    // Meta
    document.getElementById('user-id').textContent = user.id;
    document.getElementById('user-created-at').textContent = user.createdAt || 'Н/Д';

    // Show edit button only for own profile
    if (!isOwnProfile) {
        document.getElementById('edit-profile-btn').style.display = 'none';
    }

    // Fill edit form
    document.getElementById('edit-name').value = user.name;
    document.getElementById('edit-surname').value = user.surname;
    document.getElementById('edit-email').value = user.email;
    document.getElementById('edit-phone').value = user.phone || '';
    document.getElementById('edit-bday').value = user.bday || '';
    document.getElementById('edit-gender').value = user.gender || '';
    document.getElementById('edit-region').value = user.region || '';
    document.getElementById('edit-status').value = user.status || '';
    document.getElementById('edit-bio').value = user.bio || '';
}

function toggleEditMode() {
    const view = document.getElementById('profile-view');
    const edit = document.getElementById('profile-edit');

    if (view.style.display === 'none') {
        view.style.display = 'block';
        edit.style.display = 'none';
    } else {
        view.style.display = 'none';
        edit.style.display = 'block';
    }

    document.getElementById('edit-error').textContent = '';
}

async function saveProfile(event) {
    event.preventDefault();

    const userId = currentUser.id;
    const userData = {
        name: document.getElementById('edit-name').value,
        surname: document.getElementById('edit-surname').value,
        email: document.getElementById('edit-email').value,
        phone: document.getElementById('edit-phone').value,
        bday: document.getElementById('edit-bday').value,
        gender: document.getElementById('edit-gender').value,
        region: document.getElementById('edit-region').value,
        status: document.getElementById('edit-status').value,
        bio: document.getElementById('edit-bio').value
    };

    const password = document.getElementById('edit-password').value;
    if (password) {
        userData.password = password;
    }

    try {
        const response = await fetch(`/api/v1/user/${userId}/edit_info`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include',
            body: JSON.stringify(userData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Ошибка сохранения');
        }

        // Reload profile
        await loadUserProfile(userId);

    } catch (error) {
        document.getElementById('edit-error').textContent = error.message;
    }
}