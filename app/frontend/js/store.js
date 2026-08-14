/* ==========================================================================
 * store.js — состояние SPA в памяти. Единственный источник данных страниц.
 * Поля пользователя заполняются только из ответов API.
 * ========================================================================== */
const store = {
    user: null,      // { id, name, surname, email, role }
    events: [],      // каталог (GET /events/dashboard)
    myEvents: [],    // GET /events/dashboard/my_events

    setUser(u) { this.user = u; },
    setEvents(e) { this.events = Array.isArray(e) ? e : []; },
    setMyEvents(e) { this.myEvents = Array.isArray(e) ? e : []; },

    isAdmin() { return !!this.user && this.user.role === 'ADMIN'; },
    /* EDITOR и ADMIN могут создавать/править события (проверка та же, что на бэкенде) */
    canManageEvents() {
        return !!this.user && (this.user.role === 'ADMIN' || this.user.role === 'EDITOR');
    },

    clear() { this.user = null; this.events = []; this.myEvents = []; },
};