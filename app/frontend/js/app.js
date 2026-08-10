/* ==========================================================================
 * app.js — утилиты, дизайн-система UI, общие модалки, FAB, инициализация.
 *
 * Принципы разделения блоков (по ТЗ):
 *   - border: none — у блоков нет границ;
 *   - «воздух»: секции py-16…py-24, гриды gap-8, карточки p-8…p-12;
 *   - глубина: elev-1 (покой) / elev-2 (hover) / elev-3 (модалки, шапка).
 *
 * Палитра акцентов:
 *   #064789 — ключевые действия; #427AA1 — навигация;
 *   #EBF2FA — подложки; #679436 — FAB и позитивные статусы;
 *   #A5BE00 — декоративные акценты (логотип, маркеры надзаголовков).
 * ========================================================================== */

/* ---------- Защита от XSS ---------- */
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

/* ---------- ДИЗАЙН-СИСТЕМА ---------- */
const UI = {
    /* Надзаголовок секции: класс .eyebrow определён в style.css
       (текст #427AA1 + декоративный маркер #A5BE00) */
    eyebrow: 'eyebrow',

    /* Кнопки: радиус 4px, фокус-кольцо box-shadow (без границ) */
    btn: 'inline-flex items-center justify-center gap-2 font-semibold rounded transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none',
    btnPrimary: 'bg-primary text-white px-6 py-3 shadow-elev-1 hover:bg-primary-deep hover:shadow-elev-2 focus-visible:ring-primary',
    btnSecondary: 'bg-lime-btn text-white px-6 py-3 shadow-elev-1 hover:shadow-elev-2 focus-visible:ring-navy',
    btnSuccess: 'bg-moss-btn text-white px-6 py-3 shadow-elev-1 hover:shadow-elev-2 focus-visible:ring-moss-deep',
    btnDanger: 'bg-danger text-white px-4 py-2 text-sm shadow-elev-1 hover:shadow-elev-2 focus-visible:ring-danger',
    btnGhost: 'text-navy px-4 py-2 hover:text-primary hover:bg-tint focus-visible:ring-navy',
    btnSmall: 'px-4 py-2 text-sm',

    /* Формы: поля без границ — от белого фона их отделяет подложка tint */
    label: 'block text-sm font-semibold text-ink mb-2',
    input: 'w-full bg-tint rounded px-4 py-3 text-base text-ink placeholder:text-ink/35 focus:outline-none focus:ring-2 focus:ring-primary/60 transition-shadow',
    field: 'mb-6',

    /* Поверхности и бейджи */
    card: 'bg-white rounded shadow-elev-1',
    badge: 'inline-flex items-center gap-2 rounded px-3 py-1.5 text-xs font-semibold whitespace-nowrap',
    badgeSuccess: 'bg-moss-light text-moss-deep',
    badgeNeutral: 'bg-tint text-ink/60',
    badgeDanger: 'bg-danger-light text-danger',
    badgeAdmin: 'bg-primary text-white',
};

/* ---------- Общие helpers ---------- */

function loadingHtml(text = 'Загрузка…') {
    return `<div class="py-32 text-center" role="status"><p class="text-lg text-ink/50 animate-pulse">${escHtml(text)}</p></div>`;
}

function alertHtml(msg, kind = 'error') {
    const cls = kind === 'success' ? 'bg-moss-light text-moss-deep' : 'bg-danger-light text-danger';
    return `<div class="rounded ${cls} px-6 py-4 mb-8 text-sm font-medium leading-relaxed" role="alert">${escHtml(msg)}</div>`;
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

/* ---------- Поля форм ---------- */

function inputField({ id, label, name, type = 'text', value = '', placeholder = '', required = false, autocomplete = '' }) {
    return `<div class="${UI.field}">
        <label for="${id}" class="${UI.label}">${label}${required ? ' <span class="text-danger" aria-hidden="true">*</span>' : ''}</label>
        <input id="${id}" name="${name}" type="${type}" class="${UI.input}"
               value="${escAttr(value)}" placeholder="${escAttr(placeholder)}"
               ${required ? 'required' : ''} ${autocomplete ? `autocomplete="${autocomplete}"` : ''}>
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

function openModal(title, bodyHtml, { wide = false } = {}) {
    const overlay = document.createElement('div');
    overlay.className = 'fixed inset-0 z-50 bg-ink/40 flex items-center justify-center p-4 md:p-8';
    overlay.innerHTML = `
    <div role="dialog" aria-modal="true" aria-label="${escAttr(title)}"
         class="bg-white rounded shadow-elev-3 w-full ${wide ? 'max-w-2xl' : 'max-w-lg'} max-h-[85vh] overflow-y-auto modal-scroll">
        <div class="p-8 md:p-12">
            <div class="flex items-start justify-between gap-6 mb-10">
                <h2 class="text-2xl font-bold tracking-tight text-ink">${title}</h2>
                <button type="button" data-modal-close aria-label="Закрыть окно"
                        class="shrink-0 w-10 h-10 rounded bg-tint hover:bg-tint-deep text-ink/60 hover:text-ink flex items-center justify-center transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-navy">&times;</button>
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
    const accent = { success: 'bg-moss', error: 'bg-danger', info: 'bg-navy' }[type] || 'bg-navy';
    const toast = document.createElement('div');
    toast.className = 'toast pointer-events-auto flex items-stretch gap-4 bg-white rounded shadow-elev-3 pr-6 py-4 min-w-[260px] max-w-sm';
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

/* ---------- Модалки событий ---------- */

function openAddEventModal(onDone) {
    const body = `
        <div id="modal-alert"></div>
        <form id="add-event-form">
            ${inputField({ id: 'ev-name', name: 'name', label: 'Название', required: true })}
            ${textareaField({ id: 'ev-disc', name: 'disc', label: 'Описание', placeholder: 'Описание олимпиады…' })}
            ${inputField({ id: 'ev-preview', name: 'preview_picture', label: 'URL превью', type: 'url', placeholder: 'https://…' })}
            ${inputField({ id: 'ev-picture', name: 'picture', label: 'URL полного фото', type: 'url', placeholder: 'https://…' })}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Создать событие</button>
            </div>
        </form>`;
    const { overlay, close } = openModal('Новое событие', body);
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    overlay.querySelector('#add-event-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const btn = e.target.querySelector('button[type="submit"]');
        btn.disabled = true;
        const now = new Date().toISOString();
        try {
            const res = await api.addEvent({
                id: '',
                owner: store.user.id,
                name: fd.get('name'),
                disc: fd.get('disc') || null,
                preview_picture: fd.get('preview_picture') || null,
                picture: fd.get('picture') || null,
                isActive: true,
                createdAt: now,
                updatedAt: now,
            });
            if (res.ok) {
                close();
                showToast('Событие создано', 'success');
                if (onDone) onDone();
            } else {
                showModalError(overlay, res);
            }
        } catch {
            showModalError(overlay, { data: { detail: 'Сетевая ошибка' } });
        }
        btn.disabled = false;
    });
}

function openPdfModal(onDone) {
    const body = `
        <div id="modal-alert"></div>
        <form id="pdf-form">
            <div class="${UI.field}">
                <label for="pdf-file" class="${UI.label}">PDF-файл с таблицей мероприятий <span class="text-danger" aria-hidden="true">*</span></label>
                <input id="pdf-file" name="file" type="file" accept=".pdf" required
                       class="block w-full cursor-pointer text-sm text-ink/70 file:mr-4 file:rounded file:px-5 file:py-2.5 file:text-sm file:font-semibold file:bg-primary file:text-white hover:file:bg-primary-deep file:transition-colors file:cursor-pointer">
                <p class="mt-2 text-sm text-ink/50 leading-relaxed">Таблица будет распознана автоматически, события добавятся в каталог.</p>
            </div>
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Загрузить</button>
            </div>
        </form>`;
    const { overlay, close } = openModal('Импорт из PDF', body);
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    overlay.querySelector('#pdf-form').addEventListener('submit', async e => {
        e.preventDefault();
        const btn = e.target.querySelector('button[type="submit"]');
        btn.disabled = true;
        btn.textContent = 'Обработка файла…';
        try {
            const fd = new FormData(e.target);
            const res = await api.addEventsPdf(fd);
            if (res.ok && Array.isArray(res.data)) {
                close();
                showToast(`Добавлено событий: ${res.data.length}`, 'success');
                if (onDone) onDone();
            } else {
                showModalError(overlay, res);
            }
        } catch {
            showModalError(overlay, { data: { detail: 'Сетевая ошибка' } });
        }
        btn.disabled = false;
        btn.textContent = 'Загрузить';
    });
}

/* Редактирование события (общая для «Моих событий» и FAB) */
function openEditEventModal(ev, onDone) {
    const body = `
        <div id="modal-alert"></div>
        <form id="edit-event-form">
            ${inputField({ id: 'ee-name', name: 'name', label: 'Название', required: true, value: ev.name || '' })}
            ${textareaField({ id: 'ee-disc', name: 'disc', label: 'Описание', value: ev.disc || '' })}
            ${inputField({ id: 'ee-preview', name: 'preview_picture', label: 'URL превью', type: 'url', value: ev.preview_picture || '' })}
            ${inputField({ id: 'ee-picture', name: 'picture', label: 'URL полного фото', type: 'url', value: ev.picture || '' })}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Сохранить</button>
            </div>
        </form>`;
    const { overlay, close } = openModal('Редактирование события', body);
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    overlay.querySelector('#edit-event-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const btn = e.target.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
            const res = await api.editEvent({
                id: ev.id,
                owner: ev.owner || store.user.id,
                name: fd.get('name'),
                disc: fd.get('disc') || null,
                preview_picture: fd.get('preview_picture') || null,
                picture: fd.get('picture') || null,
                isActive: ev.isActive !== false,
                createdAt: ev.createdAt || new Date().toISOString(),
                updatedAt: new Date().toISOString(),
            });
            if (res.ok) {
                close();
                showToast('Событие обновлено', 'success');
                if (onDone) onDone();
            } else {
                showModalError(overlay, res);
            }
        } catch {
            showModalError(overlay, { data: { detail: 'Сетевая ошибка' } });
        }
        btn.disabled = false;
    });
}

/* «Обновить событие»: шаг 1 — выбор своего события, шаг 2 — форма */
async function openUpdateEventModal(onDone) {
    if (!store.myEvents.length) {
        try {
            const res = await api.getMyEvents();
            if (res.ok && res.data) store.setMyEvents(res.data.events);
        } catch (err) {
            console.error('[update-event] ошибка загрузки:', err);
        }
    }
    const events = store.myEvents;

    if (!events.length) {
        const { overlay } = openModal('Обновить событие', `
            <p class="text-ink/60 leading-relaxed">У вас пока нет собственных событий — обновлять нечего. Добавьте первое событие через меню «+».</p>
            <div class="flex justify-end mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnPrimary}">Понятно</button>
            </div>`);
        overlay.querySelector('[data-cancel]').addEventListener('click', () => overlay.remove());
        return;
    }

    const listHtml = `
        <p class="text-sm text-ink/50 leading-relaxed mb-6">Выберите событие, данные которого нужно обновить.</p>
        <div class="space-y-3">
            ${events.map(ev => `
            <button type="button" data-pick="${escAttr(ev.id)}"
                    class="w-full text-left bg-tint/60 hover:bg-tint rounded px-6 py-4 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary">
                <span class="block font-semibold text-ink truncate">${escHtml(ev.name)}</span>
                <span class="block mt-1 text-sm text-ink/50">Обновлено ${formatDate(ev.updatedAt)}</span>
            </button>`).join('')}
        </div>`;

    const { overlay, close } = openModal('Обновить событие', listHtml);
    overlay.querySelectorAll('[data-pick]').forEach(btn =>
        btn.addEventListener('click', () => {
            const ev = events.find(e => e.id === btn.dataset.pick);
            if (ev) { close(); openEditEventModal(ev, onDone); }
        }));
}

/* ---------- FAB «+»: единая точка действий со событиями ----------
 * Зелёный квадрат #679436 (позитивное действие), тень elev-2/elev-3.
 * Показывается на «Каталоге» и «Моих событиях». */

function setFab(visible) {
    const existing = document.getElementById('fab');
    if (visible) {
        if (!existing) mountFab();
        else existing.classList.remove('hidden');
    } else if (existing) {
        closeFabMenu();
        existing.classList.add('hidden');
    }
}

function mountFab() {
    const wrap = document.createElement('div');
    wrap.id = 'fab';
    wrap.className = 'fixed bottom-6 right-6 md:bottom-10 md:right-10 z-40 flex flex-col items-end gap-4';
    wrap.innerHTML = `
        <div id="fab-menu" role="menu" aria-label="Действия со событиями"
             class="flex flex-col items-stretch gap-3 opacity-0 translate-y-2 pointer-events-none transition-all duration-200">
            <button type="button" role="menuitem" data-fab="pdf"
                    class="flex items-center gap-3 whitespace-nowrap text-left bg-white rounded shadow-elev-2 hover:shadow-elev-3 hover:bg-tint/60 px-5 py-3.5 text-sm font-semibold text-ink transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-primary">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#064789" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 15V3m0 0L7 8m5-5 5 5"></path><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"></path></svg>
                Импорт из PDF
            </button>
            <button type="button" role="menuitem" data-fab="add"
                    class="flex items-center gap-3 whitespace-nowrap text-left bg-white rounded shadow-elev-2 hover:shadow-elev-3 hover:bg-tint/60 px-5 py-3.5 text-sm font-semibold text-ink transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-primary">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#679436" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"></path></svg>
                Добавить событие
            </button>
            <button type="button" role="menuitem" data-fab="edit"
                    class="flex items-center gap-3 whitespace-nowrap text-left bg-white rounded shadow-elev-2 hover:shadow-elev-3 hover:bg-tint/60 px-5 py-3.5 text-sm font-semibold text-ink transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-primary">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#427AA1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path></svg>
                Обновить событие
            </button>
        </div>
        <button type="button" id="fab-toggle" aria-expanded="false" aria-controls="fab-menu" aria-label="Действия со событиями"
                class="w-14 h-14 rounded bg-moss text-white shadow-elev-2 hover:bg-moss-btn hover:shadow-elev-3 hover:-translate-y-0.5 transition-all flex items-center justify-center focus:outline-none focus-visible:ring-2 focus-visible:ring-moss focus-visible:ring-offset-2">
            <svg id="fab-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="transition-transform duration-200" aria-hidden="true"><path d="M12 5v14M5 12h14"></path></svg>
        </button>`;
    document.body.appendChild(wrap);

    wrap.querySelector('#fab-toggle').addEventListener('click', () => {
        fabIsOpen() ? closeFabMenu() : openFabMenu();
    });

    wrap.querySelectorAll('[data-fab]').forEach(btn =>
        btn.addEventListener('click', () => {
            closeFabMenu();
            if (btn.dataset.fab === 'pdf') openPdfModal(fabRefresh);
            else if (btn.dataset.fab === 'add') openAddEventModal(fabRefresh);
            else openUpdateEventModal(fabRefresh);
        }));

    /* Клик вне FAB и ESC закрывают меню */
    document.addEventListener('click', e => { if (!wrap.contains(e.target)) closeFabMenu(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeFabMenu(); });
}

function fabIsOpen() {
    const t = document.getElementById('fab-toggle');
    return !!t && t.getAttribute('aria-expanded') === 'true';
}

function openFabMenu() {
    const menu = document.getElementById('fab-menu');
    const toggle = document.getElementById('fab-toggle');
    const icon = document.getElementById('fab-icon');
    if (!menu || !toggle) return;
    menu.classList.remove('opacity-0', 'translate-y-2', 'pointer-events-none');
    menu.classList.add('opacity-100', 'translate-y-0', 'pointer-events-auto');
    toggle.setAttribute('aria-expanded', 'true');
    if (icon) icon.classList.add('rotate-45');
    const first = menu.querySelector('[data-fab]');
    if (first) first.focus();
}

function closeFabMenu() {
    const menu = document.getElementById('fab-menu');
    const toggle = document.getElementById('fab-toggle');
    const icon = document.getElementById('fab-icon');
    if (!menu || !toggle) return;
    menu.classList.remove('opacity-100', 'translate-y-0', 'pointer-events-auto');
    menu.classList.add('opacity-0', 'translate-y-2', 'pointer-events-none');
    toggle.setAttribute('aria-expanded', 'false');
    if (icon) icon.classList.remove('rotate-45');
}

/* Обновление текущей страницы после действий из FAB */
function fabRefresh() {
    if (getRoute() === '/my-events') { renderMyEvents(); return; }
    (async () => {
        try { await loadDashboardData(); }
        catch (err) { console.error('[fab] ошибка обновления:', err); }
        drawDashboard();
    })();
}

/* ---------- Шапка и навигация ---------- */

function navLinkClass(active) {
    const base = 'px-4 py-2 rounded text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-navy';
    return active
        ? `${base} bg-tint text-primary font-semibold`
        : `${base} text-ink/60 hover:text-ink hover:bg-tint/60`;
}

function renderHeader() {
    const nav = document.getElementById('nav');
    if (!nav) return;
    if (!store.user) { nav.innerHTML = ''; return; }

    const links = [
        { href: '#/', route: '/', label: 'Олимпиады' },
        { href: '#/my-events', route: '/my-events', label: 'Мои события' },
        { href: '#/profile', route: '/profile', label: 'Профиль' },
    ];
    if (store.isAdmin()) links.push({ href: '#/admin', route: '/admin', label: 'Админ' });

    nav.innerHTML = links.map(l =>
        `<a href="${l.href}" data-route="${l.route}" class="${navLinkClass(false)}">${l.label}</a>`
    ).join('') + `<button id="btn-logout" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall} ml-2">Выйти</button>`;

    document.getElementById('btn-logout').addEventListener('click', logout);
    highlightNav(getRoute());
}

function highlightNav(path) {
    const current = path.startsWith('/event/') ? '/' : path;
    document.querySelectorAll('#nav a[data-route]').forEach(a => {
        const active = a.dataset.route === current;
        a.setAttribute('aria-current', active ? 'page' : 'false');
        a.className = navLinkClass(active);
    });
}

/* ---------- Bootstrap сессии ---------- */
async function bootstrap() {
    try {
        const res = await api.getDashboard();
        if (res.ok && res.data && res.data.user_id) {
            store.setUser(userFromDashboard(res.data));
            store.setEvents(res.data.events);
        } else if (!getRoute().startsWith('/auth')) {
            navigate('#/auth');
        }
    } catch (err) {
        console.error('[bootstrap] ошибка проверки сессии:', err);
        if (!getRoute().startsWith('/auth')) navigate('#/auth');
    }
    renderHeader();
}

async function logout() {
    try { await api.logout(); } catch { /* сессия истечёт сама */ }
    store.clear();
    renderHeader();
    navigate('#/auth');
}

/* ---------- Запуск приложения ---------- */
(async function init() {
    await bootstrap();
    router();
})();