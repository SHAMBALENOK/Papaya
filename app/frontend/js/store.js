/* ==========================================================================
 * store.js — состояние SPA в памяти. Единственный источник данных страниц.
 * ========================================================================== */
const store = {
    user: null,          // { id, name, surname, email, role, university_id }
    searchQuery: '',     // последний поисковый запрос

    setUser(user) {
        this.user = user || null;
    },
    setSearchQuery(query) { this.searchQuery = query || ''; },

    isAdmin() { return !!this.user && this.user.role === 'ADMIN'; },

    /* Представитель университета: роль EDITOR + привязанный университет.
       Проверка та же, что на бэкенде (app/core/deps.py). */
    isUniversityRep() {
        return !!this.user
            && this.user.role === 'EDITOR'
            && !!this.user.university_id;
    },

    canManageUniversity() { return this.isAdmin() || this.isUniversityRep(); },

    roleLabel() {
        if (!this.user) return '';
        if (this.user.role === 'ADMIN') return 'Администратор Papaya';
        if (this.user.role === 'EDITOR') return 'Представитель университета';
        return 'Школьник';
    },

    clear() { this.user = null; this.searchQuery = ''; },
};
