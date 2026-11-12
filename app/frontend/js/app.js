/* ==========================================================================
 * app.js — утилиты, дизайн-система UI, chrome сайта, модалки, тосты.
 *
 * Принципы:
 *   - белый холст, тонкие разделители line, мягкие тени elev-1…elev-3;
 *   - бренд #007F5F — главные действия, активная навигация, ссылки;
 *   - leaf/lime/lemon — только вторичные акценты и небольшие маркеры;
 *   - текст — тёмные нейтрали ink / ink-soft / ink-faint;
 *   - движение короткое (150–220 мс) и только по transform/opacity.
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

    /* Кнопки: радиус 6px, заметный фокус, лёгкий отклик на нажатие. */
    btn: 'inline-flex items-center justify-center gap-2 font-semibold rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60 focus-visible:ring-offset-2 transition-[transform,background-color,color,box-shadow] duration-150 ease-out active:scale-[0.98] disabled:opacity-40 disabled:pointer-events-none',
    btnPrimary: 'bg-brand text-white px-6 py-3 shadow-elev-1 hover:bg-brand-strong hover:shadow-elev-2',
    btnSecondary: 'bg-brand-soft text-brand-strong px-6 py-3 hover:bg-brand-tint',
    btnDanger: 'bg-danger text-white px-4 py-2 text-sm shadow-elev-1 hover:bg-danger-strong hover:shadow-elev-2',
    btnGhost: 'text-ink-soft px-4 py-2 hover:text-ink hover:bg-mist focus-visible:ring-brand/60',
    btnSmall: 'px-4 py-2 text-sm',

    /* Поля без тяжёлых рамок: подложка mist, фокус — брендовое кольцо. */
    label: 'block text-sm font-semibold text-ink mb-2',
    input: 'w-full bg-mist rounded px-4 py-3 text-base text-ink placeholder:text-ink-faint focus:outline-none focus:ring-2 focus:ring-brand/40 transition-shadow',
    field: 'mb-6',

    card: 'bg-white shadow-elev-1',
    badge: 'inline-flex items-center gap-2 rounded px-3 py-1.5 text-xs font-semibold whitespace-nowrap',
    badgeNeutral: 'bg-mist text-ink-soft',
    badgeSuccess: 'bg-success-soft text-success',
    badgeDanger: 'bg-danger-soft text-danger',
    badgeAdmin: 'bg-brand text-white',
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
        return `<div class="rounded bg-success-soft px-5 py-4 mb-8 text-sm font-medium leading-relaxed flex items-start gap-3" role="status">
            <span class="w-2.5 h-2.5 rounded-full bg-success shrink-0 mt-1" aria-hidden="true"></span>
            <span>${escHtml(msg)}</span>
        </div>`;
    }
    return `<div class="rounded bg-danger-soft px-5 py-4 mb-8 text-sm font-medium leading-relaxed flex items-start gap-3" role="alert">
        <span class="w-2.5 h-2.5 rounded-full bg-danger shrink-0 mt-1" aria-hidden="true"></span>
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
        <span class="w-2 h-2 rounded-full bg-success/70" aria-hidden="true"></span>В перечне РСОШ
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

/** Статус правила льготы: черновик, проверено или отклонено. */
function benefitStatusBadge(status) {
    if (status === 'verified') {
        return `<span class="${UI.badge} ${UI.badgeSuccess}">Проверено</span>`;
    }
    if (status === 'rejected') {
        return `<span class="${UI.badge} ${UI.badgeDanger}">Отклонено</span>`;
    }
    return `<span class="${UI.badge} ${UI.badgePending}">Не проверено</span>`;
}

/* ---------- Поля форм ---------- */

function inputField({ id, label, name, type = 'text', value = '', placeholder = '', required = false, autocomplete = '' }) {
    return `<div class="${UI.field}">
        <label for="${id}" class="${UI.label}">${label}${required ? ' <span class="text-danger" aria-hidden="true">*</span>' : ''}</label>
        <input id="${id}" name="${name}" type="${type}" class="${UI.input}"
               value="${escAttr(value)}" placeholder="${escAttr(placeholder)}"
               ${required ? 'required' : ''} ${autocomplete ? `autocomplete="${autocomplete}"` : ''}>
    </div>`;
}

function passwordField({ id, label, name, placeholder = '', required = false, autocomplete = '' }) {
    // Кнопка «Показать/Скрыть» — часть поля, а не отдельный элемент: пароль
    // вводится вслепую, и возможность проверить ввод убирает опечатки.
    return `<div class="${UI.field}">
        <label for="${id}" class="${UI.label}">${label}${required ? ' <span class="text-danger" aria-hidden="true">*</span>' : ''}</label>
        <div class="relative">
            <input id="${id}" name="${name}" type="password" class="${UI.input} pr-24"
                   placeholder="${escAttr(placeholder)}"
                   ${required ? 'required' : ''} ${autocomplete ? `autocomplete="${autocomplete}"` : ''}>
            <button type="button" data-toggle-password="${id}" aria-pressed="false" aria-controls="${id}"
                    class="absolute inset-y-0 right-0 flex items-center px-4 text-sm font-semibold text-ink-soft hover:text-ink rounded-r focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60">Показать</button>
        </div>
    </div>`;
}

function textareaField({ id, label, name, value = '', rows = 4, placeholder = '', required = false }) {
    return `<div class="${UI.field}">
        <label for="${id}" class="${UI.label}">${label}${required ? ' <span class="text-danger" aria-hidden="true">*</span>' : ''}</label>
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

function openModal(title, bodyHtml, { wide = false, size = '', isDirty = null } = {}) {
    const overlay = document.createElement('div');
    overlay.className = 'fixed inset-0 z-50 modal-overlay bg-scrim flex items-center justify-center p-4 md:p-8';
    const widths = { lg: 'max-w-4xl', xl: 'max-w-6xl' };
    const widthClass = wide ? 'max-w-3xl' : (widths[size] || 'max-w-lg');
    overlay.innerHTML = `
    <div role="dialog" aria-modal="true" aria-label="${escAttr(title)}"
         class="bg-white rounded-lg shadow-elev-3 w-full ${widthClass} max-h-[85vh] overflow-y-auto modal-scroll">
        <div class="p-8 md:p-10">
            <div class="flex items-start justify-between gap-6 mb-8">
                <h2 class="text-2xl font-bold tracking-tight text-ink">${escHtml(title)}</h2>
                <button type="button" data-modal-close aria-label="Закрыть окно"
                        class="shrink-0 w-10 h-10 rounded bg-mist hover:bg-mist-deep text-ink-soft hover:text-ink flex items-center justify-center transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60">&times;</button>
            </div>
            <div class="modal-body">${bodyHtml}</div>
        </div>
    </div>`;
    document.body.appendChild(overlay);

    const onEsc = e => {
        if (e.key === 'Escape') close();
    };
    const close = () => {
        // close() идемпотентна и в любом случае снимает слушатель клавиатуры:
        // иначе закрытие по крестику или клику по подложке оставляло бы
        // обработчик, перехватывающий Escape.
        if (!overlay.isConnected) return;
        // Защита от потери несохранённых правок: все пути закрытия (Escape,
        // крестик, клик по подложке) идут сюда, поэтому проверка живёт здесь,
        // а не в каждом обработчике по отдельности.
        if (isDirty && isDirty() && !window.confirm('Изменения не сохранены. Закрыть окно без сохранения?')) {
            return;
        }
        document.removeEventListener('keydown', onEsc);
        overlay.remove();
    };
    overlay.querySelector('[data-modal-close]').addEventListener('click', close);
    // Закрытие по клику на подложку требует, чтобы И нажатие, И отпускание
    // пришлись на саму подложку. Иначе выделение текста внутри окна с
    // выводом курсора за его пределы (mouseup на подложке) ошибочно
    // закрывало модалку — click всплывает к общему предку mousedown/mouseup.
    let pressedOnOverlay = false;
    overlay.addEventListener('mousedown', e => { pressedOnOverlay = e.target === overlay; });
    overlay.addEventListener('mouseup', e => {
        if (e.target === overlay && pressedOnOverlay) close();
        pressedOnOverlay = false;
    });
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
    const accent = { success: 'bg-success', error: 'bg-danger', info: 'bg-brand' }[type] || 'bg-brand';
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
    let dirty = false;
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
    const { overlay, close } = openModal(
        isEdit ? 'Редактирование университета' : 'Новый университет',
        body,
        { isDirty: () => dirty }
    );
    ['input', 'change'].forEach(ev => overlay.addEventListener(ev, () => { dirty = true; }));

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
                dirty = false;
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
    let dirty = false;
    const body = `
        <div id="modal-alert"></div>
        <form id="olympiad-form">
            ${inputField({ id: 'ol-name', name: 'name', label: 'Название олимпиады', required: true, value: (olympiad || {}).name || '' })}
            ${inputField({ id: 'ol-organizer', name: 'organizer', label: 'Организатор', value: (olympiad || {}).organizer || '', placeholder: 'МФТИ, Минобрнауки России' })}
            ${inputField({ id: 'ol-site', name: 'official_url', label: 'Официальный сайт', type: 'url', value: (olympiad || {}).official_url || '', placeholder: 'https://…' })}
            ${inputField({ id: 'ol-preview', name: 'preview_image', label: 'Превью для карточек (URL)', type: 'url', value: (olympiad || {}).preview_image || '', placeholder: 'https://…' })}
            ${inputField({ id: 'ol-image', name: 'image', label: 'Большая картинка для страницы (URL)', type: 'url', value: (olympiad || {}).image || '', placeholder: 'https://…' })}
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
    const { overlay, close } = openModal(
        isEdit ? 'Редактирование олимпиады' : 'Новая олимпиада',
        body,
        { isDirty: () => dirty }
    );
    ['input', 'change'].forEach(ev => overlay.addEventListener(ev, () => { dirty = true; }));

    overlay.querySelector('[data-cancel]').addEventListener('click', close);
    overlay.querySelector('#olympiad-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const payload = {
            name: (fd.get('name') || '').trim(),
            official_url: (fd.get('official_url') || '').trim() || null,
            preview_image: (fd.get('preview_image') || '').trim() || null,
            image: (fd.get('image') || '').trim() || null,
            organizer: (fd.get('organizer') || '').trim() || null,
            description: (fd.get('description') || '').trim() || null,
        };
        const btn = e.target.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
            const res = isEdit
                ? await api.editOlympiad(olympiad.id, payload)
                : await api.addOlympiad(payload);
            if (res.ok) {
                dirty = false;
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
            <svg class="text-brand" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <rect x="4" y="11" width="16" height="10"></rect>
                <path d="M8 11V7a4 4 0 0 1 8 0v4"></path>
            </svg>
        </div>
        <h1 class="text-3xl md:text-4xl font-extrabold tracking-tight">${escHtml(title)}</h1>
        <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-md mx-auto">${escHtml(text)}</p>
        <a href="#/" class="${UI.btn} ${UI.btnPrimary} mt-10">На главную</a>
    </div>`;
}

/* ---------- Chrome: шапка и мобильное меню ---------- */

function setChrome(visible) {
    const header = document.getElementById('header');
    if (!header) return;
    header.classList.toggle('hidden', !visible);
    if (visible) renderHeader();
    else closeMobileMenu();
}

/** Открывает/закрывает мобильную панель навигации под шапкой. */
function toggleMobileMenu(force) {
    const menu = document.getElementById('mobile-menu');
    const btn = document.getElementById('menu-toggle');
    if (!menu || !btn) return;
    const open = typeof force === 'boolean' ? force : menu.hidden;
    menu.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
    btn.setAttribute('aria-label', open ? 'Закрыть меню' : 'Открыть меню');
}

function openMobileMenu() { toggleMobileMenu(true); }
function closeMobileMenu() { toggleMobileMenu(false); }

function navLinkClass(active) {
    const base = 'inline-flex items-center px-3 py-2 rounded text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60';
    return active
        ? `${base} text-brand-strong bg-brand-soft`
        : `${base} text-ink-soft hover:text-ink hover:bg-mist`;
}

function mobileNavLinkClass(active) {
    const base = 'block px-3 py-2.5 rounded text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60';
    return active
        ? `${base} text-brand-strong bg-brand-soft`
        : `${base} text-ink-soft hover:text-ink hover:bg-mist`;
}

/** Основные разделы. Порядок задаёт сценарий: сначала главная и каталоги. */
function navLinks() {
    const links = [
        { href: '#/', route: '/', label: 'Главная' },
        { href: '#/olympiads', route: '/olympiads', label: 'Олимпиады' },
        { href: '#/universities', route: '/universities', label: 'Университеты' },
    ];
    if (store.user) {
        /* «Мой университет» — кабинет представителя: у администратора он не
           показывается, иначе раздел дублировал бы модерацию БВИ в панели. */
        if (store.isUniversityRep()) {
            links.push({ href: '#/my-university', route: '/my-university', label: 'Мой университет' });
        }
        links.push({ href: '#/profile', route: '/profile', label: 'Профиль' });
    }
    if (store.isAdmin()) {
        links.push({ href: '#/admin/users', route: '/admin', label: 'Администрирование' });
    }
    return links;
}

/** Дополнительный каталог: не перегружает основную навигацию, но остаётся
 *  на виду в шапке и в мобильном меню. */
function secondaryNavLinks() {
    return [{ href: '#/benefits', route: '/benefits', label: 'Льготы' }];
}

function desktopAuthHtml() {
    if (!store.user) {
        return `
        <a href="#/auth" class="rounded px-3 py-2 text-sm font-semibold text-ink-soft hover:text-ink hover:bg-mist transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60">Войти</a>
        <a href="#/auth?tab=register" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Регистрация</a>`;
    }
    const initials = userInitials(store.user);
    return `
    <a href="#/profile" class="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-mist transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60">
        <span class="w-8 h-8 rounded-full bg-brand-soft text-brand-strong text-xs font-extrabold flex items-center justify-center shrink-0" aria-hidden="true">${escHtml(initials)}</span>
        <span class="hidden lg:block max-w-[12rem] truncate text-sm font-semibold text-ink">${escHtml(store.user.name)} ${escHtml(store.user.surname)}</span>
    </a>
    <button type="button" data-logout class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Выйти</button>`;
}

function mobileAuthHtml() {
    if (!store.user) {
        return `
        <a href="#/auth" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall} w-full">Войти</a>
        <a href="#/auth?tab=register" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall} w-full mt-2">Регистрация</a>`;
    }
    const initials = userInitials(store.user);
    return `
    <div class="flex items-center gap-3 py-2">
        <span class="w-9 h-9 rounded-full bg-brand-soft text-brand-strong text-xs font-extrabold flex items-center justify-center shrink-0" aria-hidden="true">${escHtml(initials)}</span>
        <div class="min-w-0">
            <p class="text-sm font-semibold text-ink truncate">${escHtml(store.user.name)} ${escHtml(store.user.surname)}</p>
            <p class="text-xs text-ink-soft truncate">${escHtml(store.roleLabel())}</p>
        </div>
    </div>
    <button type="button" data-logout class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall} w-full mt-1">Выйти</button>`;
}

function renderHeader() {
    const nav = document.getElementById('nav');
    const mobileNav = document.getElementById('mobile-nav');
    const actions = document.getElementById('auth-actions');
    const mobileAuth = document.getElementById('mobile-auth');
    if (!nav && !mobileNav && !actions && !mobileAuth) return;

    const primary = navLinks();
    const extra = secondaryNavLinks();
    const all = primary.concat(extra);

    if (nav) {
        nav.innerHTML = primary.map(l =>
            `<a href="${l.href}" data-route="${l.route}" class="${navLinkClass(false)}">${l.label}</a>`
        ).join('') + `
            <span class="mx-2 h-5 w-px bg-line" aria-hidden="true"></span>
            ${extra.map(l =>
                `<a href="${l.href}" data-route="${l.route}" class="${navLinkClass(false)}">${l.label}</a>`
            ).join('')}`;
    }

    if (mobileNav) {
        mobileNav.innerHTML = all.map(l =>
            `<a href="${l.href}" data-route="${l.route}" class="${mobileNavLinkClass(false)}">${l.label}</a>`
        ).join('');
    }

    if (actions) actions.innerHTML = desktopAuthHtml();
    if (mobileAuth) mobileAuth.innerHTML = mobileAuthHtml();

    document.querySelectorAll('[data-logout]').forEach(btn =>
        btn.addEventListener('click', logout)
    );

    highlightNav(routePath());
}

function highlightNav(path) {
    let current = path || '/';
    if (current.startsWith('/universities')) current = '/universities';
    else if (current.startsWith('/olympiads')) current = '/olympiads';
    else if (current.startsWith('/benefits')) current = '/benefits';
    else if (current.startsWith('/admin')) current = '/admin';
    else if (current === '/my-university') current = '/my-university';
    document.querySelectorAll('#nav a[data-route]').forEach(a => {
        const active = a.dataset.route === current;
        a.setAttribute('aria-current', active ? 'page' : 'false');
        a.className = navLinkClass(active);
    });
    document.querySelectorAll('#mobile-nav a[data-route]').forEach(a => {
        const active = a.dataset.route === current;
        a.setAttribute('aria-current', active ? 'page' : 'false');
        a.className = mobileNavLinkClass(active);
    });
    closeMobileMenu();
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
    renderHeader();
    navigate('#/');
}

function bindChromeControls() {
    const toggle = document.getElementById('menu-toggle');
    if (toggle) toggle.addEventListener('click', () => toggleMobileMenu());
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') closeMobileMenu();
    });
    /* На широком экране мобильная панель не должна оставаться открытой. */
    const desktop = window.matchMedia('(min-width: 768px)');
    const syncViewport = e => { if (e.matches) closeMobileMenu(); };
    if (desktop.addEventListener) desktop.addEventListener('change', syncViewport);
    else if (desktop.addListener) desktop.addListener(syncViewport);
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
