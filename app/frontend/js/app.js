function escHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escAttr(str) {
    if (!str) return '';
    return str.replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Init
(async function init() {
    const res = await api.checkAuth().catch(() => ({ ok: false }));
    if (!res.ok && res.status !== 200) {
        navigate('#/auth');
    } else {
        if (!window.location.hash || window.location.hash === '#/') {
            navigate('#/');
        }
    }
    router();

    document.getElementById('btn-logout').addEventListener('click', async () => {
        await api.logout();
        store.clear();
        navigate('#/auth');
    });
})();