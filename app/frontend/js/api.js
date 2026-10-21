/* ==========================================================================
 * api.js — клиент API. Все запросы уходят с cookie (JWT: access/refresh).
 * Пути совпадают с роутерами FastAPI под префиксом /api/v1.
 *
 * Каталоги (университеты, олимпиады, поиск) публичные — регистрация для них
 * не нужна: главный сценарий Papaya доступен гостю.
 * ========================================================================== */
const API_BASE = '/api/v1';

/* Имена фильтров в интерфейсе — в camelCase, в API — в snake_case.
 * Без приведения ключей фильтр «вид льготы» уезжал бы под именем
 * `benefitType`, а сервер его тихо игнорировал: список выглядел бы
 * отфильтрованным, а остался бы прежним. */
const FILTER_KEYS = {
    benefitType: 'benefit_type',
    verificationStatus: 'verification_status',
    includePending: 'include_pending',
    universityId: 'university_id',
    olympiadId: 'olympiad_id',
};

function filterQuery(filters) {
    const params = new URLSearchParams();
    Object.entries(filters || {}).forEach(([key, value]) => {
        if (value === undefined || value === null || value === '') return;
        params.set(FILTER_KEYS[key] || key, value);
    });
    return params.toString();
}

/* Query-строка для постраничных административных списков (limit/offset/search).
   Пустой объект даёт пустую строку — вызов без параметров возвращает всё. */
function adminQuery(opts) {
    if (!opts) return '';
    const params = new URLSearchParams();
    if (opts.search) params.set('search', opts.search);
    if (opts.limit != null) params.set('limit', opts.limit);
    if (opts.offset != null) params.set('offset', opts.offset);
    const query = params.toString();
    return query ? `?${query}` : '';
}

function isJwtAuthError(status, data) {
    if (status !== 401 && status !== 403) return false;
    const detail = data && typeof data.detail === 'string' ? data.detail.toLowerCase() : '';
    return detail.includes('access token')
        || detail.includes('refresh token')
        || detail.includes('token expired')
        || detail.includes('expired token');
}

/* Протухший access-токен — не повод выкидывать пользователя: сессия
   продлевается через POST /auth/refresh (ротация refresh-токена), после
   чего исходный запрос повторяется один раз.

   Поводом считается не только «access token expired», но и «access token
   missing»: access-cookie короткоживущая, и браузер удаляет её раньше
   refresh-cookie. Тогда следующий запрос приходит вообще без токена, и сервер
   отвечает «Access token missing». Это то же самое событие «access-токена
   нет», и его тоже нужно закрывать refresh'ем, а не разлогинивать. Блокировку
   аккаунта («Account is blocked») трогать нельзя: там refresh не поможет. */
function isAccessTokenExpiredError(status, data) {
    if (status !== 401) return false;
    const detail = data && typeof data.detail === 'string' ? data.detail.toLowerCase() : '';
    if (detail.includes('blocked')) return false;
    return detail.includes('access token');
}

/* Однопоточное обновление: параллельные 401 от нескольких запросов должны
   дождаться одного POST /auth/refresh, а не слать конкурентные ротации
   (вторая из них получила бы 401 reuse и разлогинила бы пользователя). */
let refreshInFlight = null;

async function refreshSession() {
    if (!refreshInFlight) {
        refreshInFlight = fetch(`${API_BASE}/auth/refresh`, {
            method: 'POST',
            credentials: 'include',
        }).then(res => {
            // 200 — ротация прошла; всё остальное (401 reuse/истёк, 403
            // блокировка) — сессии нет, дальше только экран входа.
            return res.ok;
        }).catch(() => false).finally(() => {
            refreshInFlight = null;
        });
    }
    return refreshInFlight;
}

function redirectToAuthAfterJwtError() {
    store.clear();
    if (typeof renderHeader === 'function') renderHeader();
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
        let res = await fetch(`${API_BASE}${path}`, opts);
        let data = res.status === 204 || res.headers.get('content-length') === '0'
            ? null
            : await res.json().catch(() => null);

        if (!res.ok && isAccessTokenExpiredError(res.status, data)) {
            const refreshed = await refreshSession();
            if (refreshed) {
                res = await fetch(`${API_BASE}${path}`, opts);
                data = res.status === 204 || res.headers.get('content-length') === '0'
                    ? null
                    : await res.json().catch(() => null);
            }
        }

        if (!res.ok) {
            console.error(`[API] ${method} ${path} → ${res.status}`, data);
            if (!skipAuthRedirect && isJwtAuthError(res.status, data)) {
                redirectToAuthAfterJwtError();
            }
        }
        return { ok: res.ok, status: res.status, data };
    },

    get(path, options) { return this.request('GET', path, null, false, options); },
    put(path, body, options) { return this.request('PUT', path, body, false, options); },
    post(path, body, options) { return this.post_(path, body, false, options); },
    postForm(path, formData, options) { return this.post_(path, formData, true, options); },
    post_(path, body, isFormData, options) {
        return this.request('POST', path, body, isFormData, options);
    },

    /* Аутентификация */
    register(d)  { return this.post('/auth/register', d); },
    login(d)     { return this.post('/auth/login', d); },
    logout()     { return this.post('/auth/logout'); },

    /* Текущий пользователь: GET /api/v1/ отдаёт полный профиль из JWT.
       Для гостя ответ 401 — это норма, поэтому редиректа на /auth нет. */
    getMe()      { return this.get('/', { skipAuthRedirect: true }); },
    getUser(id)  { return this.get(`/user/${id}`); },
    editUser(id, d) { return this.post(`/user/${id}/edit_info`, d); },

    /* Каталоги (публичные) */
    listUniversities(search) {
        const query = search ? `?search=${encodeURIComponent(search)}` : '';
        return this.get(`/universities${query}`, { skipAuthRedirect: true });
    },
    getUniversity(id) { return this.get(`/universities/${id}`, { skipAuthRedirect: true }); },
    getUniversityOlympiads(id, includePending, filters) {
        const params = new URLSearchParams();
        if (includePending) params.set('include_pending', 'true');
        const query = filterQuery(filters);
        return this.get(
            `/universities/${id}/olympiads${query ? `?${query}` : ''}`,
            { skipAuthRedirect: true },
        );
    },
    addUniversity(d)     { return this.post('/universities/add_university', d); },
    editUniversity(id, d) { return this.post(`/universities/edit_university/${id}`, d); },
    requestBvi(universityId, olympiadId) {
        return this.post(`/universities/${universityId}/bvi`, { olympiad_id: olympiadId });
    },
    removeBvi(universityId, olympiadId) {
        return this.post(`/universities/${universityId}/bvi/remove`, { olympiad_id: olympiadId });
    },

    /* Правила льгот: вид льготы, проверка, подтверждение вузом, версии. */
    listBenefitRules(universityId, filters) {
        const query = filterQuery(filters);
        return this.get(
            `/universities/${universityId}/benefit-rules${query ? `?${query}` : ''}`,
            { skipAuthRedirect: true },
        );
    },
    updateBenefitRule(universityId, olympiadId, body) {
        return this.put(`/universities/${universityId}/benefit-rules/${olympiadId}`, body);
    },
    benefitRuleVersions(universityId, olympiadId) {
        return this.get(`/universities/${universityId}/benefit-rules/${olympiadId}/versions`);
    },
    rollbackBenefitRule(universityId, olympiadId, version) {
        return this.post(`/universities/${universityId}/benefit-rules/${olympiadId}/rollback/${version}`);
    },
    confirmBenefitRuleByUniversity(universityId, olympiadId, confirmed) {
        return this.post(
            `/universities/${universityId}/benefit-rules/${olympiadId}/university-confirmation`,
            { confirmed: confirmed !== false },
        );
    },

    /* Сезоны олимпиады и профили. */
    listOlympiadSeasons(id) { return this.get(`/olympiads/${id}/seasons`, { skipAuthRedirect: true }); },
    getOlympiadSeason(id, seasonId) {
        return this.get(`/olympiads/${id}/seasons/${seasonId}`, { skipAuthRedirect: true });
    },
    upsertOlympiadSeason(id, year, body) {
        return this.put(`/olympiads/${id}/seasons/${year}`, body);
    },
    archiveOlympiadSeason(id, seasonId) {
        return this.post(`/olympiads/${id}/seasons/${seasonId}/archive`);
    },
    addOlympiadSeasonProfile(id, seasonId, body) {
        return this.post(`/olympiads/${id}/seasons/${seasonId}/profiles`, body);
    },

    /* Образовательные программы университета. */
    listUniversityPrograms(universityId) {
        return this.get(`/universities/${universityId}/programs`, { skipAuthRedirect: true });
    },
    saveUniversityPrograms(universityId, programs) {
        return this.put(`/universities/${universityId}/programs`, { programs });
    },

    /* Заявки на роль представителя вуза. */
    submitApplication(body)      { return this.post('/applications', body); },
    myApplications()             { return this.get('/applications/mine'); },
    listApplications(status) {
        const query = status ? `?status=${encodeURIComponent(status)}` : '';
        return this.get(`/applications${query}`);
    },
    decideApplication(id, body)  { return this.post(`/applications/${id}/decision`, body); },

    /* Доступность документа-источника (независимо от статуса обработки). */
    setDocAvailability(id, availability) {
        return this.post(`/docs/${id}/availability`, { availability });
    },

    listOlympiads(search, includeArchived) {
        const params = new URLSearchParams();
        if (search) params.set('search', search);
        if (includeArchived) params.set('include_archived', 'true');
        const query = params.toString();
        return this.get(`/olympiads${query ? `?${query}` : ''}`, { skipAuthRedirect: true });
    },
    getOlympiad(id)      { return this.get(`/olympiads/${id}`, { skipAuthRedirect: true }); },
    getOlympiadUniversities(id) { return this.get(`/olympiads/${id}/universities`, { skipAuthRedirect: true }); },
    getOlympiadSource(id) { return this.get(`/olympiads/${id}/source`, { skipAuthRedirect: true }); },
    /* Публичная ссылка на файл документа-источника олимпиады (если есть). */
    olympiadSourceFileUrl(id) { return `${API_BASE}/olympiads/${id}/source/file`; },
    addOlympiad(d)       { return this.post('/olympiads/add_olympiad', d); },
    editOlympiad(id, d)  { return this.post(`/olympiads/edit_olympiad/${id}`, d); },

    /* Поиск по обоим каталогам */
    search(q) { return this.get(`/search?q=${encodeURIComponent(q || '')}`, { skipAuthRedirect: true }); },

    /* Документы-источники и импорт РСОШ (администратор) */
    uploadDoc(formData) { return this.postForm('/docs/upload', formData); },
    docFileUrl(id)      { return `${API_BASE}/docs/${id}/file`; },

    listImports()             { return this.get('/imports'); },
    startRsoshImport(docId)   { return this.post('/imports/rsosh', { doc_id: docId }); },
    importPreview(id)         { return this.get(`/imports/${id}/preview`); },
    confirmImport(id, body)   { return this.post(`/imports/${id}/confirm`, body || {}); },
    rejectImport(id)          { return this.post(`/imports/${id}/reject`); },
    pauseImport(id)           { return this.post(`/imports/${id}/pause`); },
    resumeImport(id)          { return this.post(`/imports/${id}/resume`); },
    /* Сохранить выбор администратора вместе с прогоном (переживает
       перезагрузку страницы). */
    saveImportSelection(id, body) { return this.put(`/imports/${id}/selection`, body); },
    /* Добавить/убрать олимпиаду вручную прямо в меню документа РСОШ. */
    addImportCandidate(id, body) { return this.post(`/imports/${id}/candidates`, body); },
    removeImportCandidate(id, nameNorm) {
        return this.post(`/imports/${id}/candidates/remove`, { name_norm: nameNorm });
    },

    /* Импорт приказов университетов (администратор). Отдельные маршруты:
       приказ не создаёт олимпиад, а заводит заявки БВИ на существующие. */
    listUniversityImports()          { return this.get('/imports/university'); },
    startUniversityImport(docId)     { return this.post('/imports/university', { doc_id: docId }); },
    universityImportPreview(id)      { return this.get(`/imports/university/${id}/preview`); },
    confirmUniversityImport(id, body) { return this.post(`/imports/university/${id}/confirm`, body || {}); },
    rejectUniversityImport(id)       { return this.post(`/imports/university/${id}/reject`); },
    pauseUniversityImport(id)        { return this.post(`/imports/university/${id}/pause`); },
    resumeUniversityImport(id)       { return this.post(`/imports/university/${id}/resume`); },
    saveUniversitySelection(id, body) { return this.put(`/imports/university/${id}/selection`, body); },

    /* Администрирование */
    adminUsers(opts) {
        return this.get(`/admin/users${adminQuery(opts)}`);
    },
    adminOlympiads(opts) {
        return this.get(`/admin/olympiads${adminQuery(opts)}`);
    },
    adminBviLinks(status, opts) {
        const params = new URLSearchParams();
        if (status) params.set('status', status);
        if (opts && opts.limit != null) params.set('limit', opts.limit);
        if (opts && opts.offset != null) params.set('offset', opts.offset);
        const query = params.toString();
        return this.get(`/admin/bvi${query ? `?${query}` : ''}`);
    },
    banUser(id)      { return this.post(`/admin/ban/${id}`); },
    unbanUser(id)    { return this.post(`/admin/unban/${id}`); },
    /* Единственный способ назначить, снять или повысить роль: роль и
       университет меняются одним запросом, поэтому EDITOR без университета
       получить нельзя, а отдельных grant_admin/demote_admin в API нет. */
    setUserRole(id, role, universityId) {
        return this.post(`/admin/role/${id}`, {
            role,
            university_id: universityId || null,
        });
    },
    /** Модерация заявки БВИ.
     *
     * Действия явные: 'confirm' (подтвердить), 'reject' (отклонить заявку) и
     * 'revoke' (отозвать подтверждение). Произвольной смены статуса нет:
     * отзыв подтверждения — это удаление связи, а не возврат в PENDING.
     */
    moderateBvi(universityId, olympiadId, action) {
        return this.post(
            `/universities/${universityId}/bvi/${olympiadId}/moderation`, { action });
    },
    archiveOlympiad(id, archived) {
        return this.post(`/admin/archive_olympiad/${id}?archived=${archived === false ? 'false' : 'true'}`);
    },
};
