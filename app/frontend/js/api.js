/* ==========================================================================
 * api.js — клиент API. Все запросы уходят с cookie (JWT: access/refresh).
 * Пути совпадают с роутерами FastAPI под префиксом /api/v1.
 *
 * Flow обновления сессии:
 *   1. Сервер на истёкший access отвечает 401 с detail.code=ACCESS_TOKEN_EXPIRED.
 *   2. request() в таком случае вызывает refreshSession() (POST /auth/refresh)
 *      и ПОВТОРЯЕТ исходный запрос ровно один раз (_retried=true).
 *   3. refreshSession() опирается на единый refreshPromise — параллельные
 *      запросы ждут один и тот же refresh, а не дергают его 5 раз подряд.
 *   4. POST /auth/refresh сам через request() не ходит (иначе получит 401 от
 *      невалидного refresh и запустит рекурсию refresh → refresh → …).
 *   5. Если refresh не удался — сессия считается мёртвой: store.clear() и уход
 *      на #/auth (кроме публичных страниц, где сбрасывать состояние не нужно).
 * ========================================================================== */
const API_BASE = '/api/v1';

/* Единый промис активного refresh: параллельные 401-ы делят один вызов. */
let refreshPromise = null;

function authErrorCode(data) {
    const detail = data && data.detail;
    if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
        return typeof detail.code === 'string' ? detail.code : '';
    }
    return '';
}

/* Ошибка, связанная с JWT в целом (для принудительного выхода из состояния). */
function isJwtAuthError(status, data) {
    if (status !== 401 && status !== 403) return false;
    const code = authErrorCode(data);
    if (code) {
        return code.startsWith('ACCESS_TOKEN_')
            || code.startsWith('REFRESH_TOKEN_');
    }
    const detail = data && typeof data.detail === 'string' ? data.detail.toLowerCase() : '';
    return detail.includes('access token')
        || detail.includes('refresh token')
        || detail.includes('token expired')
        || detail.includes('expired token');
}

/* Именно этот случай подлежит восстановлению через /auth/refresh. */
function isAccessExpiredError(status, data) {
    return status === 401 && authErrorCode(data) === 'ACCESS_TOKEN_EXPIRED';
}

function redirectToAuthAfterJwtError() {
    store.clear();
    if (typeof setChrome === 'function') setChrome(false);
    if (window.location.hash !== '#/auth') window.location.hash = '#/auth';
}

/* POST /auth/refresh через raw fetch — без интерцептора request(). */
async function refreshSession() {
    if (refreshPromise) return refreshPromise;
    refreshPromise = (async () => {
        try {
            const res = await fetch(`${API_BASE}/auth/refresh`, {
                method: 'POST',
                credentials: 'include',
                headers: {},
            });
            if (res.status !== 204 && res.headers.get('content-length') !== '0') {
                const data = await res.json().catch(() => null);
                if (!res.ok) console.error('[API] /auth/refresh →', res.status, data);
            }
            return res.ok;
        } catch (err) {
            console.error('[API] /auth/refresh → network error:', err);
            return false;
        } finally {
            refreshPromise = null;
        }
    })();
    return refreshPromise;
}

const api = {
    async request(method, path, body = null, isFormData = false, { skipAuthRedirect = false, _retried = false } = {}) {
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
            if (!_retried && isAccessExpiredError(res.status, data)) {
                const refreshed = await refreshSession();
                if (refreshed) {
                    /* Один повтор — не больше: при повторной ошибке выходим. */
                    return this.request(method, path, body, isFormData, {
                        skipAuthRedirect,
                        _retried: true,
                    });
                }
                if (!skipAuthRedirect) redirectToAuthAfterJwtError();
                return { ok: false, status: res.status, data };
            }
            if (!skipAuthRedirect && isJwtAuthError(res.status, data)) {
                redirectToAuthAfterJwtError();
            }
        }
        return { ok: res.ok, status: res.status, data };
    },

    get(path, options) { return this.request('GET', path, null, false, options); },
    post(path, body, options) { return this.request('POST', path, body, false, options); },
    postForm(path, formData, options) { return this.request('POST', path, formData, true, options); },
    patch(path, body, options) { return this.request('PATCH', path, body, false, options); },
    delete(path, options) { return this.request('DELETE', path, null, false, options); },

    /* Аутентификация */
    checkAuth()  { return this.get('/auth/'); },
    register(d)  { return this.post('/auth/register', d); },
    login(d)     { return this.post('/auth/login', d); },
    logout()     { return this.post('/auth/logout'); },
    /* Продление сессии доступно и напрямую (bootstrap), через raw fetch. */
    refresh()    { return refreshSession(); },

    /* Текущий пользователь: GET /api/v1/ отдаёт полный профиль из JWT */
    getMe()      { return this.get('/'); },

    /* Пользователи */
    getUsers()       { return this.get('/user/users'); },
    getUser(id)      { return this.get(`/user/${id}`); },
    editUser(id, d)  { return this.post(`/user/${id}/edit_info`, d); },

    /* Администрирование (роль ADMIN на бэкенде) */
    adminUsers()     { return this.get('/admin/users'); },
    banUser(id)      { return this.post(`/admin/ban/${id}`); },
    unbanUser(id)    { return this.post(`/admin/unban/${id}`); },
    grantAdmin(id)   { return this.post(`/admin/grant_admin/${id}`); },
    demoteAdmin(id)  { return this.post(`/admin/demote_admin/${id}`); },

    /* Организации (админ создаёт; редактирует админ или своя организация) */
    getOrganizations(params = '')   { return this.get(`/organizations${params}`); },
    getOrganization(id)             { return this.get(`/organizations/${id}`); },
    createOrganization(d)           { return this.post('/organizations', d); },
    updateOrganization(id, d)       { return this.patch(`/organizations/${id}`, d); },
    deleteOrganization(id)          { return this.delete(`/organizations/${id}`); },

    /* Олимпиады (создаёт орг-админ или админ) */
    getOlympiads(params = '')       { return this.get(`/olympiads${params}`); },
    getOlympiad(id)                 { return this.get(`/olympiads/${id}`); },
    createOlympiad(d)               { return this.post('/olympiads', d); },
    updateOlympiad(id, d)           { return this.patch(`/olympiads/${id}`, d); },
    deleteOlympiad(id)              { return this.delete(`/olympiads/${id}`); },

    /* Документы */
    getDocs(params = '')            { return this.get(`/docs${params}`); },
    getDoc(id)                      { return this.get(`/docs/${id}`); },
    uploadDoc(fd, params = '')      { return this.postForm(`/docs${params}`, fd); },
    updateDoc(id, d)                { return this.patch(`/docs/${id}`, d); },
    deleteDoc(id)                   { return this.delete(`/docs/${id}`); },

    /* RSOSH-импорт */
    getImports(params = '')          { return this.get(`/imports${params}`); },
    startRsoshImport(docId)         { return this.post('/imports/rsosh', { doc_id: docId }); },
    getImportStatus(id)             { return this.get(`/imports/${id}`); },
    getImportPreview(id)            { return this.get(`/imports/${id}/preview`); },
    confirmImport(id)               { return this.post(`/imports/${id}/confirm`); },
    rejectImport(id)                { return this.post(`/imports/${id}/reject`); },
};