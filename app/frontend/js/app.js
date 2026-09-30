/* ==========================================================================
 * app.js — утилиты, дизайн-система UI, chrome сайта, модалки, тосты.
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
    badgePending: 'bg-mist text-ink-soft',
};

function loadingHtml(text = 'Загрузка…') {
    return `<div class="py-32 text-center" role="status"><p class="text-lg text-ink-soft animate-pulse">${escHtml(text)}</p></div>`;
}

function emptyHtml(title, text, actionHtml = '') {
    return `<div class="py-24 text-center max-w-md mx-auto">
        <h2 class="text-2xl font-bold tracking-tight">${escHtml(title)}</h2>
        <p class="mt-4 text-ink-soft leading-relaxed">${escHtml(text)}</p>
        ${actionHtml ? `<div class="flex flex-wrap justify-center gap-3 mt-10">${actionHtml}</div>` : ''}
    </div>`;
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

function userInitials(user) {
    if (!user) return '?';
    const a = (user.name || '?')[0] || '?';
    const b = (user.surname || '')[0] || '';
    return (a + b).toUpperCase();
}

function olympiadStatusBadge(status) {
    if (status === 'ARCHIVED') {
        return `<span class="${UI.badge} ${UI.badgeNeutral}">Нет в перечне РСОШ</span>`;
    }
    return `<span class="${UI.badge} ${UI.badgeSuccess}">
        <span class="w-2 h-2 rounded-full bg-ink/60" aria-hidden="true"></span>В перечне РСОШ
    </span>`;
}

/** Человеческое объяснение архива — по причине, а не только по статусу.
 *
 * Причины две, и администратору важно их различать: олимпиада, исчезнувшая из
 * перечня РСОШ, вернётся сама при следующем импорте, а исключённую вручную
 * можно вернуть только из панели. Пользователю эти enum-значения не
 * показываются — на публичных страницах текст общий (см.
 * `archivedOlympiadNotice` в pages/olympiads.js).
 */
function archiveReasonText(reason) {
    if (reason === 'MANUAL') {
        return 'Олимпиада архивирована администратором Papaya. '
             + 'Вернуть её в актуальные можно здесь же, в панели администратора.';
    }
    return 'Олимпиада архивирована: её нет в актуальном перечне РСОШ. '
         + 'Она вернётся автоматически, если снова появится в перечне.';
}

function bviStatusBadge(status) {
    if (status === 'CONFIRMED') {
        return `<span class="${UI.badge} ${UI.badgeSuccess}">Подтверждено</span>`;
    }
    return `<span class="${UI.badge} ${UI.badgePending}">Ждёт подтверждения</span>`;
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
         class="bg-white shadow-elev-3 w-full ${wide ? 'max-w-3xl' : 'max-w-lg'} max-h-[85vh] overflow-y-auto modal-scroll">
        <div class="p-8 md:p-12">
            <div class="flex items-start justify-between gap-6 mb-10">
                <h2 class="text-2xl font-bold tracking-tight text-ink">${escHtml(title)}</h2>
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

/* ---------- Модалки каталога ---------- */

function openUniversityFormModal(university, onDone) {
    const isEdit = !!university;
    const body = `
        <div id="modal-alert"></div>
        <form id="university-form">
            ${inputField({ id: 'un-name', name: 'name', label: 'Полное название', required: true, value: (university || {}).name || '' })}
            ${inputField({ id: 'un-short', name: 'short_name', label: 'Краткое название / аббревиатура', value: (university || {}).short_name || '', placeholder: 'МФТИ' })}
            ${inputField({ id: 'un-site', name: 'website', label: 'Официальный сайт', type: 'url', value: (university || {}).website || '', placeholder: 'https://…' })}
            ${inputField({ id: 'un-preview', name: 'preview_image', label: 'Превью для карточек (URL)', type: 'url', value: (university || {}).preview_image || '', placeholder: 'https://…' })}
            ${inputField({ id: 'un-image', name: 'image', label: 'Большая картинка для страницы (URL)', type: 'url', value: (university || {}).image || '', placeholder: 'https://…' })}
            ${textareaField({ id: 'un-desc', name: 'description', label: 'Описание', value: (university || {}).description || '' })}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">${isEdit ? 'Сохранить' : 'Создать университет'}</button>
            </div>
        </form>`;
    const { overlay, close } = openModal(isEdit ? 'Редактирование университета' : 'Новый университет', body);

    overlay.querySelector('[data-cancel]').addEventListener('click', close);
    overlay.querySelector('#university-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const payload = {
            name: (fd.get('name') || '').trim(),
            short_name: (fd.get('short_name') || '').trim() || null,
            website: (fd.get('website') || '').trim() || null,
            preview_image: (fd.get('preview_image') || '').trim() || null,
            image: (fd.get('image') || '').trim() || null,
            description: (fd.get('description') || '').trim() || null,
        };
        const btn = e.target.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
            const res = isEdit
                ? await api.editUniversity(university.id, payload)
                : await api.addUniversity(payload);
            if (res.ok) {
                close();
                showToast(isEdit ? 'Университет обновлён' : 'Университет создан', 'success');
                if (onDone) onDone();
                return;
            }
            showModalError(overlay, res);
        } catch {
            showModalError(overlay, { data: { detail: 'Сетевая ошибка' } });
        }
        btn.disabled = false;
    });
}

function openOlympiadFormModal(olympiad, onDone) {
    const isEdit = !!olympiad;
    const body = `
        <div id="modal-alert"></div>
        <form id="olympiad-form">
            ${inputField({ id: 'ol-name', name: 'name', label: 'Название олимпиады', required: true, value: (olympiad || {}).name || '' })}
            ${inputField({ id: 'ol-site', name: 'official_url', label: 'Официальный сайт', type: 'url', value: (olympiad || {}).official_url || '', placeholder: 'https://…' })}
            ${inputField({ id: 'ol-preview', name: 'preview_image', label: 'Превью для карточек (URL)', type: 'url', value: (olympiad || {}).preview_image || '', placeholder: 'https://…' })}
            ${inputField({ id: 'ol-image', name: 'image', label: 'Большая картинка для страницы (URL)', type: 'url', value: (olympiad || {}).image || '', placeholder: 'https://…' })}
            ${inputField({ id: 'ol-source', name: 'source_url', label: 'Источник информации (ссылка)', type: 'url', value: (olympiad || {}).source_url || '', placeholder: 'https://…' })}
            ${textareaField({ id: 'ol-desc', name: 'description', label: 'Описание', value: (olympiad || {}).description || '' })}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">${isEdit ? 'Сохранить' : 'Создать олимпиаду'}</button>
            </div>
        </form>
        <p class="mt-8 text-sm text-ink-soft leading-relaxed">
            Ручное создание — резервный способ. Основной путь наполнения каталога —
            импорт официальных документов РСОШ (вкладка «Импорт РСОШ»).
        </p>`;
    const { overlay, close } = openModal(isEdit ? 'Редактирование олимпиады' : 'Новая олимпиада', body);

    overlay.querySelector('[data-cancel]').addEventListener('click', close);
    overlay.querySelector('#olympiad-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const payload = {
            name: (fd.get('name') || '').trim(),
            official_url: (fd.get('official_url') || '').trim() || null,
            preview_image: (fd.get('preview_image') || '').trim() || null,
            image: (fd.get('image') || '').trim() || null,
            source_url: (fd.get('source_url') || '').trim() || null,
            description: (fd.get('description') || '').trim() || null,
        };
        const btn = e.target.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
            const res = isEdit
                ? await api.editOlympiad(olympiad.id, payload)
                : await api.addOlympiad(payload);
            if (res.ok) {
                close();
                showToast(isEdit ? 'Олимпиада обновлена' : 'Олимпиада создана', 'success');
                if (onDone) onDone();
                return;
            }
            showModalError(overlay, res);
        } catch {
            showModalError(overlay, { data: { detail: 'Сетевая ошибка' } });
        }
        btn.disabled = false;
    });
}

function renderForbidden(title, text) {
    const page = document.getElementById('page');
    page.innerHTML = `
    <div class="max-w-narrow mx-auto py-24 md:py-32 text-center">
        <div class="mx-auto w-16 h-16 rounded bg-mist flex items-center justify-center mb-10" aria-hidden="true">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#FF7F11" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <rect x="4" y="11" width="16" height="10"></rect>
                <path d="M8 11V7a4 4 0 0 1 8 0v4"></path>
            </svg>
        </div>
        <h1 class="text-3xl md:text-4xl font-extrabold tracking-tight">${escHtml(title)}</h1>
        <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-md mx-auto">${escHtml(text)}</p>
        <a href="#/" class="${UI.btn} ${UI.btnPrimary} mt-10">На главную</a>
    </div>`;
}

/* ---------- Chrome: сайдбар ---------- */

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

function navLinks() {
    const links = [
        { href: '#/', route: '/', label: 'Главная' },
        { href: '#/universities', route: '/universities', label: 'Университеты' },
        { href: '#/olympiads', route: '/olympiads', label: 'Олимпиады' },
    ];
    if (store.user) {
        if (store.canManageUniversity()) {
            links.push({ href: '#/my-university', route: '/my-university', label: 'Мой университет' });
        }
        links.push({ href: '#/profile', route: '/profile', label: 'Профиль' });
    }
    if (store.isAdmin()) {
        links.push({ href: '#/admin/users', route: '/admin', label: 'Администрирование' });
    }
    return links;
}

function renderHeader() {
    const nav = document.getElementById('nav');
    const userBox = document.getElementById('sidebar-user');
    if (!nav) return;

    nav.innerHTML = navLinks().map(l =>
        `<a href="${l.href}" data-route="${l.route}" class="${navLinkClass(false)}">${l.label}</a>`
    ).join('');

    if (userBox) {
        if (!store.user) {
            userBox.innerHTML = `
            <div class="bg-mist rounded p-4">
                <p class="text-sm text-ink-soft leading-relaxed">
                    Каталоги и поиск открыты без входа. Войдите, чтобы управлять
                    каталогом и БВИ своего университета.
                </p>
                <a href="#/auth" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall} w-full mt-4">Войти</a>
            </div>`;
        } else {
            const initials = userInitials(store.user);
            userBox.innerHTML = `
            <div class="bg-mist rounded p-4">
                <div class="flex items-center gap-3 min-w-0">
                    <div class="w-10 h-10 rounded bg-ember text-ink text-sm font-extrabold flex items-center justify-center shrink-0" aria-hidden="true">${escHtml(initials)}</div>
                    <div class="min-w-0">
                        <p class="font-semibold text-sm truncate">${escHtml(store.user.name)} ${escHtml(store.user.surname)}</p>
                        <p class="text-xs text-ink-soft truncate">${escHtml(store.roleLabel())}</p>
                    </div>
                </div>
                <button id="btn-logout" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall} w-full mt-4">Выйти</button>
            </div>`;
            document.getElementById('btn-logout').addEventListener('click', logout);
        }
    }

    highlightNav(routePath());
}

function highlightNav(path) {
    let current = path || '/';
    if (current.startsWith('/universities')) current = '/universities';
    else if (current.startsWith('/olympiads')) current = '/olympiads';
    else if (current.startsWith('/admin')) current = '/admin';
    else if (current === '/my-university') current = '/my-university';
    document.querySelectorAll('#nav a[data-route]').forEach(a => {
        const active = a.dataset.route === current;
        a.setAttribute('aria-current', active ? 'page' : 'false');
        a.className = navLinkClass(active);
    });
    closeSidebar();
}

/* ---------- Bootstrap сессии ---------- */
async function bootstrap() {
    try {
        /* Каталоги публичны: проверка сессии не должна блокировать первый экран. */
        const res = await api.getMe();
        if (res.ok && res.data && res.data.id) {
            store.setUser({
                id: res.data.id,
                name: res.data.name,
                surname: res.data.surname,
                email: res.data.email,
                role: res.data.role || 'USER',
                university_id: res.data.university_id || null,
            });
        }
    } catch (err) {
        console.error('[bootstrap] ошибка проверки сессии:', err);
    }
    renderHeader();
}

async function logout() {
    try { await api.logout(); } catch { /* сессия истечёт сама */ }
    store.clear();
    navigate('#/');
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
    const page = document.getElementById('page');
    if (page && !isPublicRoute(routePath())) {
        page.innerHTML = loadingHtml('Проверяем сессию…');
    }
    await bootstrap();
    router();
})();
