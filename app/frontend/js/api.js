const API_BASE = '/api/v1';

const api = {
    async request(method, path, body = null, isFormData = false) {
        const opts = {
            method,
            credentials: 'include',
            headers: {},
        };
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
        return { ok: res.ok, status: res.status, data };
    },

    get(path) { return this.request('GET', path); },
    post(path, body) { return this.request('POST', path, body); },

    // Auth
    checkAuth() { return this.get('/auth/'); },
    register(data) { return this.post('/auth/register', data); },
    login(data) { return this.post('/auth/login', data); },
    logout() { return this.get('/auth/logout'); },

    // Main
    getMain() { return this.get('/'); },

    // User
    getUser(id) { return this.get(`/user/${id}`); },
    editUser(id, data) { return this.post(`/user/${id}/edit_info`, data); },

    // Стало:
    getEvent(id) { return this.get(`/events/${id}`); },
    addEvent(userData, eventData) {
    return this.post('/events/add_event', { ...userData, ...eventData });
    },
    editEvent(userData, eventData) {
    return this.post('/events/edit_event', { ...userData, ...eventData });
    },
};