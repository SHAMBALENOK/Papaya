/* ==========================================================================
 * router.js — hash-роутер SPA.
 * Каждому пользовательскому маршруту соответствует страница.
 * ========================================================================== */

function navigate(hash) {
    if (window.location.hash === hash) {
        router();
        return;
    }
    window.location.hash = hash;
}

function getRoute() { return (window.location.hash || '#/').slice(1); }

function renderNotFound() {
    const page = document.getElementById('page');
    page.innerHTML = `
    <div class="max-w-narrow mx-auto py-24 text-center">
        <p class="${UI.eyebrow}">404</p>
        <h1 class="mt-5 text-3xl md:text-4xl font-extrabold tracking-tight">Страница не найдена</h1>
        <p class="mt-5 text-lg text-ink-soft leading-relaxed">Такого маршрута в приложении нет.</p>
        <a href="#/" class="${UI.btn} ${UI.btnPrimary} mt-10">К каталогу</a>
    </div>`;
}

function router() {
    const path = getRoute() || '/';
    const page = document.getElementById('page');

    try {
        /* Визитка публична, но из авторизованной части на неё не ведём. */
        if (path === '/welcome' || ((path === '/' || path === '') && !store.user)) {
            setChrome(false);
            if (store.user) {
                navigate('#/');
                return;
            }
            renderWelcome();
            return;
        }

        if (path === '/auth') {
            setChrome(false);
            renderAuth();
            highlightNav(path);
            return;
        }

        /* Все маршруты дашборда требуют активной сессии. */
        if (!store.user) {
            setChrome(false);
            navigate('#/auth');
            return;
        }

        setChrome(true);

        if (path === '/') {
            renderOlympiads();
        } else if (path === '/profile') {
            renderProfile();
        } else if (path === '/users') {
            renderUsers();
        } else if (path.startsWith('/users/') && path.split('/users/')[1]) {
            renderUserPublic(path.split('/users/')[1]);
        } else if (path === '/organizations') {
            renderOrganizations();
        } else if (path.startsWith('/organizations/') && path.split('/organizations/')[1]) {
            renderOrganization(path.split('/organizations/')[1]);
        } else if (path === '/olympiads') {
            renderOlympiads();
        } else if (path.startsWith('/olympiads/') && path.split('/olympiads/')[1]) {
            renderOlympiad(path.split('/olympiads/')[1]);
        } else if (path === '/docs') {
            renderDocs();
        } else if (path.startsWith('/imports/') && path.split('/imports/')[1]) {
            renderImport(path.split('/imports/')[1]);
        } else if (path === '/admin' || path === '/admin/users') {
            renderAdmin('users');
        } else if (path === '/admin/imports') {
            renderAdmin('imports');
        } else {
            renderNotFound();
        }

        highlightNav(path);
    } catch (err) {
        console.error('[router] ошибка рендера:', err);
        if (page) {
            page.innerHTML = `
            <div class="max-w-narrow mx-auto py-24 text-center">
                <h1 class="text-3xl font-extrabold tracking-tight">Не удалось открыть страницу</h1>
                <p class="mt-5 text-ink-soft leading-relaxed">Внутренняя ошибка: ${escHtml(String((err && err.message) || err))}</p>
                <p class="mt-3 text-sm text-ink-faint">Если файлы недавно обновлялись — перезагрузите страницу с очисткой кэша (Ctrl+Shift+R).</p>
                <button type="button" onclick="location.reload()" class="${UI.btn} ${UI.btnPrimary} mt-10">Перезагрузить</button>
            </div>`;
        }
    }
}

window.addEventListener('hashchange', router);