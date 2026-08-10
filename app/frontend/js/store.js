/* ==========================================================================
 * store.js — состояние SPA в памяти. Единственный источник данных страниц.
 * ========================================================================== */
const store = {
    user: null,      // { id, name, surname, email, role }
    events: [],      // все события каталога
    myEvents: [],    // события текущего пользователя

    setUser(u) { this.user = u; },
    setEvents(e) { this.events = Array.isArray(e) ? e : []; },
    setMyEvents(e) { this.myEvents = Array.isArray(e) ? e : []; },

    isAdmin() { return !!this.user && this.user.role === 'ADMIN'; },

    clear() { this.user = null; this.events = []; this.myEvents = []; },
};