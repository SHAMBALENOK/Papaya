const store = {
    user: null,
    events: [],

    setUser(u) { this.user = u; },
    setEvents(e) { this.events = e; },
    clear() { this.user = null; this.events = []; },
};