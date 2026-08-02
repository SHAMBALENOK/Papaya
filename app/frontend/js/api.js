const API_BASE = '/api/v1';

const api = {
    async request(method, path, body = null, isFormData = false) {
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
        return { ok: res.ok, status: res.status, data };
    },

    get(path) { return this.request('GET', path); },
    post(path, body) { return this.request('POST', path, body); },
    postForm(path, formData) { return this.request('POST', path, formData, true); },

    checkAuth()  { return this.get('/auth/'); },
    register(d)  { return this.post('/auth/register', d); },
    login(d)     { return this.post('/auth/login', d); },
    logout()     { return this.get('/auth/logout'); },

    getMain()    { return this.get('/'); },

    getUser(id)      { return this.get(`/user/${id}`); },
    editUser(id, d)  { return this.post(`/user/${id}/edit_info`, d); },

    getEvent(id)     { return this.get(`/events/${id}`); },
    addEvent(d)      { return this.post('/events/add_event', d); },
    editEvent(d)     { return this.post('/events/edit_event', d); },
    addEventsPdf(fd) { return this.postForm('/events/add_events_via_pdf_tables', fd); },
};