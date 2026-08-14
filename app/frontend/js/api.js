/* ==========================================================================
 * api.js — клиент API. Все запросы уходят с cookie (JWT: access/refresh).
 * Пути совпадают с роутерами FastAPI под префиксом /api/v1.
 * ========================================================================== */
const API_BASE = '/api/v1';

function isJwtAuthError(status, data) {
    if (status !== 401 && status !== 403) return false;
    const detail = data && typeof data.detail === 'string' ? data.detail.toLowerCase() : '';
    return detail.includes('access token')
        || detail.includes('refresh token')
        || detail.includes('token expired')
        || detail.includes('expired token');
}

function redirectToAuthAfterJwtError() {
    store.clear();
    if (typeof setChrome === 'function') setChrome(false);
    if (typeof setFab === 'function') setFab(false);
    if (window.location.hash !== '#/auth') window.location.hash = '#/auth';
}

const api = {
    async request(method, path, body = null, isFormData = false, { skipAuthRedirect = false } = {}) {
        const opts = { method, credentials: 'include', headers: {} };
        if (body && !isFormData) {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(body);
        } else if (body && isFormData) {
            opts.body = body;
        }
        const res = await fetch(`${API_BASE}${path}`, opts);
        if (res.status === 204 || res.headers.get('content-length') === '0') {
            return { ok: res.ok, status: res.status, data: null };
        }
        const data = await res.json().catch(() => null);
        if (!res.ok) {
            console.error(`[API] ${method} ${path} → ${res.status}`, data);
            if (!skipAuthRedirect && isJwtAuthError(res.status, data)) {
                redirectToAuthAfterJwtError();
            }
        }
        return { ok: res.ok, status: res.status, data };
    },

    get(path, options) { return this.request('GET', path, null, false, options); },
    post(path, body, options) { return this.request('POST', path, body, false, options); },
    postForm(path, formData, options) { return this.request('POST', path, formData, true, options); },

    /* Аутентификация */
    checkAuth()  { return this.get('/auth/'); },
    register(d)  { return this.post('/auth/register', d); },
    login(d)     { return this.post('/auth/login', d); },
    logout()     { return this.get('/auth/logout'); },

    /* Текущий пользователь: GET /api/v1/ отдаёт полный профиль из JWT */
    getMe()      { return this.get('/'); },

    /* Главный экран: пользователь (с ролью) + все события */
    getDashboard(options) { return this.get('/events/dashboard', options); },
    getMyEvents()  { return this.get('/events/dashboard/my_events'); },

    /* Пользователи */
    getUsers()       { return this.get('/user/users'); },
    getUser(id)      { return this.get(`/user/${id}`); },
    editUser(id, d)  { return this.post(`/user/${id}/edit_info`, d); },

    /* События — пути совпадают с app/routers/events.py */
    getEvent(id)     { return this.get(`/events/${id}`); },
    addEvent(d)      { return this.post('/events/add_event', d); },
    editEvent(d)     { return this.post(`/events/edit_event/${d.id}`, d); },
    addEventsPdf(fd) { return this.postForm('/events/add_events_via_tables', fd); },

    /* Администрирование (роль ADMIN на бэкенде) */
    adminUsers()     { return this.get('/admin/users'); },
    adminEvents()    { return this.get('/admin/events'); },
    banUser(id)      { return this.get(`/admin/ban/${id}`); },
    unbanUser(id)    { return this.get(`/admin/unban/${id}`); },
    grantAdmin(id)   { return this.get(`/admin/grant_admin/${id}`); },
    demoteAdmin(id)  { return this.get(`/admin/demote_admin/${id}`); },
    archiveEvent(id) { return this.get(`/admin/archive_event/${id}`); },
};