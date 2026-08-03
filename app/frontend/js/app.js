function escHtml(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

function escAttr(str) {
    if (!str) return '';
    return str.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

(async function init() {
    const res = await api.checkAuth().catch(() => ({ ok: false }));
    if (!res.ok && res.status !== 200) {
        navigate('#/auth');
    } else {
        if (!window.location.hash || window.location.hash === '#/') navigate('#/');
    }
    router();

    document.getElementById('btn-logout').addEventListener('click', async () => {
        await api.logout();
        store.clear();
        navigate('#/auth');
    });
})();

function showToast(message, type = 'info', duration = 3500) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  // анимация появления
  requestAnimationFrame(() => toast.classList.add('toast-visible'));
  setTimeout(() => {
    toast.classList.remove('toast-visible');
    toast.addEventListener('transitionend', () => toast.remove());
  }, duration);
}