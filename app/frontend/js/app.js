/* ==========================================================================
 * app.js — утилиты, дизайн-система UI, chrome дашборда, модалки, FAB.
 *
 * Принципы разделения блоков:
 *   - border: none;
 *   - «воздух»: секции py-14…py-20, гриды gap-8, карточки p-8…p-12;
 *   - глубина: elev-1 / elev-2 / elev-3;
 *   - база: #FFFFFF/#FFFFFC, текст #1A1A1A;
 *     sage #CBE896, sand #C6BFA9, ember #FF7F11, crimson #FF1B1C.
 * ========================================================================== */

function escHtml(str) {
    if (str === null || str === undefined) return '';
    const d = document.createElement('div');
    d.textContent = String(str);
    return d.innerHTML;
}

function escAttr(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

const UI = {
    eyebrow: 'eyebrow',

    /* Кнопки: радиус 4px, фокус-кольцо, без границ. Отступы кратны 4px. */
    btn: 'inline-flex items-center justify-center gap-2 font-semibold rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/70 focus-visible:ring-offset-2 transition-all duration-200 disabled:opacity-40 disabled:pointer-events-none',
    btnPrimary: 'bg-ink text-white px-6 py-3 shadow-elev-1 hover:bg-ink-deep hover:shadow-elev-2',
    btnSecondary: 'bg-sand text-ink px-6 py-3 shadow-elev-1 hover:shadow-elev-2',
    btnDanger: 'bg-crimson text-ink px-4 py-2 text-sm shadow-elev-1 hover:shadow-elev-2',
    btnGhost: 'text-ink-soft px-4 py-2 hover:text-ink hover:bg-mist focus-visible:ring-ink/60',
    btnSmall: 'px-4 py-2 text-sm',

    /* Поля без рамок: отделены подложкой mist, фокус — кольцо 2px. */
    label: 'block text-sm font-semibold text-ink mb-2',
    input: 'w-full bg-mist rounded px-4 py-3 text-base text-ink placeholder:text-ink-faint focus:outline-none focus:ring-2 focus:ring-ink/40 transition-shadow',
    field: 'mb-6',

    card: 'bg-white shadow-elev-1',
    badge: 'inline-flex items-center gap-2 rounded px-3 py-1.5 text-xs font-semibold whitespace-nowrap',
    badgeNeutral: 'bg-sand text-ink',
    badgeSuccess: 'bg-sage text-ink',
    badgeDanger: 'bg-crimson text-ink',
    badgeAdmin: 'bg-ink text-white',
};

function loadingHtml(text = 'Загрузка…') {
    return `<div class="py-32 text-center" role="status"><p class="text-lg text-ink-soft animate-pulse">${escHtml(text)}</p></div>`;
}

function alertHtml(msg, kind = 'error') {
    if (kind === 'success') {
        return `<div class="rounded bg-sage px-6 py-4 mb-8 text-sm font-medium leading-relaxed flex items-start gap-3" role="status">
            <span class="w-2.5 h-2.5 rounded-full bg-ink shrink-0 mt-1" aria-hidden="true"></span>
            <span>${escHtml(msg)}</span>
        </div>`;
    }
    return `<div class="rounded bg-crimson/10 px-6 py-4 mb-8 text-sm font-medium leading-relaxed flex items-start gap-3" role="alert">
        <span class="w-2.5 h-2.5 rounded-full bg-crimson shrink-0 mt-1" aria-hidden="true"></span>
        <span>${escHtml(msg)}</span>
    </div>`;
}

function errorText(res) {
    const d = res && res.data ? res.data.detail : null;
    if (Array.isArray(d)) return d.map(x => (x && x.msg) ? x.msg : String(x)).join('; ');
    return d || 'Произошла ошибка. Попробуйте ещё раз.';
}

function formatDate(iso) {
    if (!iso) return 'Н/Д';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return 'Н/Д';
    return d.toLocaleDateString('ru-RU');
}

function userFromDashboard(d) {
    return {
        id: d.user_id,
        name: d.user_name,
        surname: d.user_surname,
        email: d.user_email,
        role: d.user_role || 'USER',
    };
}

function userFromProfile(d) {
    return {
        id: d.id,
        name: d.name,
        surname: d.surname,
        email: d.email,
        role: d.role || 'USER',
    };
}

function userInitials(user) {
    if (!user) return '?';
    const a = (user.name || '?')[0] || '?';
    const b = (user.surname || '')[0] || '';
    return (a + b).toUpperCase();
}

/* ---------- Поля форм ---------- */

function inputField({ id, label, name, type = 'text', value = '', placeholder = '', required = false, autocomplete = '' }) {
    return `<div class="${UI.field}">
        <label for="${id}" class="${UI.label}">${label}${required ? ' <span class="text-crimson" aria-hidden="true">*</span>' : ''}</label>
        <input id="${id}" name="${name}" type="${type}" class="${UI.input}"
               value="${escAttr(value)}" placeholder="${escAttr(placeholder)}"
               ${required ? 'required' : ''} ${autocomplete ? `autocomplete="${autocomplete}"` : ''}>
    </div>`;
}

function textareaField({ id, label, name, value = '', rows = 4, placeholder = '', required = false }) {
    return `<div class="${UI.field}">
        <label for="${id}" class="${UI.label}">${label}${required ? ' <span class="text-crimson" aria-hidden="true">*</span>' : ''}</label>
        <textarea id="${id}" name="${name}" rows="${rows}" class="${UI.input} resize-y"
                  placeholder="${escAttr(placeholder)}" ${required ? 'required' : ''}>${escHtml(value)}</textarea>
    </div>`;
}

function selectField({ id, label, name, options, value = '' }) {
    const opts = options.map(o =>
        `<option value="${escAttr(o.value)}" ${o.value === value ? 'selected' : ''}>${escHtml(o.label)}</option>`
    ).join('');
    return `<div class="${UI.field}">
        <label for="${id}" class="${UI.label}">${label}</label>
        <select id="${id}" name="${name}" class="${UI.input}">${opts}</select>
    </div>`;
}

/* ---------- Модальные окна ---------- */

function openModal(title, bodyHtml, { wide = false } = {}) {
    const overlay = document.createElement('div');
    overlay.className = 'fixed inset-0 z-50 bg-ink/40 flex items-center justify-center p-4 md:p-8';
    overlay.innerHTML = `
    <div role="dialog" aria-modal="true" aria-label="${escAttr(title)}"
         class="bg-white shadow-elev-3 w-full ${wide ? 'max-w-2xl' : 'max-w-lg'} max-h-[85vh] overflow-y-auto modal-scroll">
        <div class="p-8 md:p-12">
            <div class="flex items-start justify-between gap-6 mb-10">
                <h2 class="text-2xl font-bold tracking-tight text-ink">${title}</h2>
                <button type="button" data-modal-close aria-label="Закрыть окно"
                        class="shrink-0 w-10 h-10 rounded bg-mist hover:bg-mist-deep text-ink-soft hover:text-ink flex items-center justify-center transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">&times;</button>
            </div>
            <div class="modal-body">${bodyHtml}</div>
        </div>
    </div>`;
    document.body.appendChild(overlay);

    const close = () => overlay.remove();
    overlay.querySelector('[data-modal-close]').addEventListener('click', close);
    overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
    const onEsc = e => {
        if (e.key === 'Escape') { close(); document.removeEventListener('keydown', onEsc); }
    };
    document.addEventListener('keydown', onEsc);

    const first = overlay.querySelector('input, textarea, select');
    if (first) first.focus();

    return { overlay, close };
}

function showModalError(overlay, res) {
    const el = overlay.querySelector('#modal-alert');
    if (el) el.innerHTML = alertHtml(errorText(res), 'error');
}

/* ---------- Тосты ---------- */
function showToast(message, type = 'info', duration = 3500) {
    const container = document.getElementById('toast-container');
    const accent = { success: 'bg-sage', error: 'bg-crimson', info: 'bg-ember' }[type] || 'bg-ember';
    const toast = document.createElement('div');
    toast.className = 'toast pointer-events-auto flex items-stretch gap-4 bg-white shadow-elev-3 pr-6 py-4 min-w-[260px] max-w-sm';
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
    toast.innerHTML = `
        <span class="w-1.5 ${accent} rounded-full shrink-0" aria-hidden="true"></span>
        <p class="self-center text-sm font-medium text-ink leading-snug">${escHtml(message)}</p>`;
    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('toast-visible'));
    setTimeout(() => {
        toast.classList.remove('toast-visible');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

/* ---------- Chrome: сайдбар дашборда ---------- */

function setChrome(visible) {
    const sidebar = document.getElementById('sidebar');
    const header = document.getElementById('header');
    const frame = document.getElementById('app-frame');
    if (!sidebar || !header || !frame) return;

    if (visible) {
        sidebar.classList.add('is-chrome');
        header.classList.remove('hidden');
        frame.classList.add('is-chrome');
        renderHeader();
    } else {
        sidebar.classList.remove('is-chrome', 'is-open');
        header.classList.add('hidden');
        frame.classList.remove('is-chrome');
        closeSidebar();
    }
}

function openSidebar() {
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    const btn = document.getElementById('sidebar-open');
    if (!sidebar) return;
    sidebar.classList.add('is-open');
    if (backdrop) {
        backdrop.hidden = false;
        backdrop.classList.remove('hidden');
    }
    if (btn) btn.setAttribute('aria-expanded', 'true');
}

function closeSidebar() {
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    const btn = document.getElementById('sidebar-open');
    if (sidebar) sidebar.classList.remove('is-open');
    if (backdrop) {
        backdrop.hidden = true;
        backdrop.classList.add('hidden');
    }
    if (btn) btn.setAttribute('aria-expanded', 'false');
}

function navLinkClass(active) {
    const base = 'w-full text-left px-4 py-3 rounded text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60';
    return active
        ? `${base} bg-ink text-white`
        : `${base} text-ink-soft hover:text-ink hover:bg-mist`;
}

function renderHeader() {
    const nav = document.getElementById('nav');
    const userBox = document.getElementById('sidebar-user');
    if (!nav) return;
    if (!store.user) {
        nav.innerHTML = '';
        if (userBox) userBox.innerHTML = '';
        return;
    }

    const links = [
        { href: '#/olympiads', route: '/olympiads', label: 'Олимпиады' },
        { href: '#/organizations', route: '/organizations', label: 'Организации' },
        { href: '#/docs', route: '/docs', label: 'Документы' },
        { href: '#/users', route: '/users', label: 'Пользователи' },
        { href: '#/profile', route: '/profile', label: 'Профиль' },
    ];
    if (store.isAdmin()) {
        links.push({ href: '#/admin/users', route: '/admin', label: 'Админ' });
    }

    nav.innerHTML = links.map(l =>
        `<a href="${l.href}" data-route="${l.route}" class="${navLinkClass(false)}">${l.label}</a>`
    ).join('');

    if (userBox) {
        const initials = userInitials(store.user);
        userBox.innerHTML = `
        <div class="bg-mist rounded p-4">
            <div class="flex items-center gap-3 min-w-0">
                <div class="w-10 h-10 rounded bg-ember text-ink text-sm font-extrabold flex items-center justify-center shrink-0" aria-hidden="true">${escHtml(initials)}</div>
                <div class="min-w-0">
                    <p class="font-semibold text-sm truncate">${escHtml(store.user.name)} ${escHtml(store.user.surname)}</p>
                    <p class="text-xs text-ink-soft truncate">${escHtml(store.user.email || '')}</p>
                </div>
            </div>
            <button id="btn-logout" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall} w-full mt-4">Выйти</button>
        </div>`;
        document.getElementById('btn-logout').addEventListener('click', logout);
    }

    highlightNav(getRoute());
}

function highlightNav(path) {
    let current = path || '/';
    if (path.startsWith('/users/')) current = '/users';
    else if (path.startsWith('/organizations/')) current = '/organizations';
    else if (path.startsWith('/olympiads/')) current = '/olympiads';
    else if (path.startsWith('/imports/')) current = '/docs';
    else if (path.startsWith('/admin')) current = '/admin';
    document.querySelectorAll('#nav a[data-route]').forEach(a => {
        const active = a.dataset.route === current;
        a.setAttribute('aria-current', active ? 'page' : 'false');
        a.className = navLinkClass(active);
    });
    closeSidebar();
}

/* ---------- Bootstrap сессии ---------- */
async function bootstrap() {
    const route = getRoute() || '/';
    const isPublicRoute = route === '/' || route === '/welcome' || route === '/auth';

    try {
        /* На публичных страницах отсутствие JWT не должно уводить с визитки. */
        const res = await api.getMe({ skipAuthRedirect: isPublicRoute });
        if (res.ok && res.data && res.data.id) {
            store.setUser(userFromProfile(res.data));
        } else if (!isPublicRoute) {
            navigate('#/auth');
        }
    } catch (err) {
        console.error('[bootstrap] ошибка проверки сессии:', err);
        if (!isPublicRoute) navigate('#/auth');
    }
    renderHeader();
}

async function logout() {
    try { await api.logout(); } catch { /* сессия истечёт сама */ }
    store.clear();
    setChrome(false);
    navigate('#/auth');
}

function bindChromeControls() {
    const openBtn = document.getElementById('sidebar-open');
    const closeBtn = document.getElementById('sidebar-close');
    const backdrop = document.getElementById('sidebar-backdrop');
    if (openBtn) openBtn.addEventListener('click', openSidebar);
    if (closeBtn) closeBtn.addEventListener('click', closeSidebar);
    if (backdrop) backdrop.addEventListener('click', closeSidebar);
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') closeSidebar();
    });
}

/* ---------- Запуск приложения ---------- */
(async function init() {
    bindChromeControls();

    const route = getRoute() || '/';
    const isPublicRoute = route === '/' || route === '/welcome' || route === '/auth';

    /*
     * Публичный экран не должен ждать ответа API: при недоступных БД/Redis
     * проверка сессии может занять время, но визитка и авторизация уже видны.
     */
    if (isPublicRoute) {
        router();
    } else {
        const page = document.getElementById('page');
        if (page) page.innerHTML = loadingHtml('Проверяем сессию…');
    }

    await bootstrap();
    router();
})();