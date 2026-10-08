/* ==========================================================================
 * router.js — hash-роутер SPA.
 *
 * Публичные маршруты (доступны гостю):
 *   #/                      главная: поиск + каталоги
 *   #/universities          каталог университетов
 *   #/universities/{id}     университет и его БВИ-олимпиады
 *   #/olympiads             каталог олимпиад
 *   #/olympiads/{id}        олимпиада, её сайты и вузы с БВИ
 *   #/search?q=…            результаты поиска
 *   #/auth                  вход и регистрация
 *
 * Маршруты с авторизацией:
 *   #/profile               профиль
 *   #/my-university         управление БВИ своего университета
 *   #/admin/*               администрирование Papaya
 *   #/admin/imports/{id}    просмотр и подтверждение результатов импорта
 * ========================================================================== */

const PUBLIC_PREFIXES = ['/universities', '/olympiads', '/search'];

function navigate(hash) {
    if (window.location.hash === hash) {
        router();
        return;
    }
    window.location.hash = hash;
}

function getRoute() { return (window.location.hash || '#/').slice(1); }
function currentQuery() {
    const raw = getRoute();
    const index = raw.indexOf('?');
    return index === -1 ? '' : raw.slice(index + 1);
}
function routePath() {
    const raw = getRoute();
    const index = raw.indexOf('?');
    return index === -1 ? raw : raw.slice(0, index);
}

function isPublicRoute(path) {
    if (path === '/' || path === '/auth' || path === '') return true;
    return PUBLIC_PREFIXES.some(prefix => path === prefix || path.startsWith(prefix + '/'));
}

function renderNotFound() {
    const page = document.getElementById('page');
    page.innerHTML = `
    <div class="max-w-narrow mx-auto py-24 text-center">
        <p class="${UI.eyebrow}">404</p>
        <h1 class="mt-5 text-3xl md:text-4xl font-extrabold tracking-tight">Страница не найдена</h1>
        <p class="mt-5 text-lg text-ink-soft leading-relaxed">Такого маршрута в приложении нет.</p>
        <a href="#/" class="${UI.btn} ${UI.btnPrimary} mt-10">На главную</a>
    </div>`;
}

function router() {
    const path = routePath() || '/';
    const page = document.getElementById('page');

    try {
        if (!isPublicRoute(path) && !store.user) {
            navigate('#/auth');
            return;
        }

        setChrome(true);

        if (path === '/' || path === '') {
            renderHome();
        } else if (path === '/auth') {
            renderAuth();
        } else if (path === '/universities') {
            renderUniversities();
        } else if (path.startsWith('/universities/')) {
            renderUniversity(path.split('/universities/')[1]);
        } else if (path === '/olympiads') {
            renderOlympiads();
        } else if (path.startsWith('/olympiads/')) {
            renderOlympiad(path.split('/olympiads/')[1]);
        } else if (path === '/search') {
            renderSearch(new URLSearchParams(currentQuery()).get('q') || '');
        } else if (path === '/profile') {
            renderProfile();
        } else if (path === '/my-university') {
            renderMyUniversity();
        } else if (path.startsWith('/admin')) {
            if (!store.isAdmin()) {
                renderForbidden('Администрирование Papaya', 'Этот раздел доступен только администратору платформы.');
                return;
            }
            const tab = path.split('/admin/')[1] || 'users';
            if (tab.startsWith('imports/')) {
                renderImportReview(tab.split('/')[1]);
            } else {
                renderAdmin(tab);
            }
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
                <button type="button" onclick="location.reload()" class="${UI.btn} ${UI.btnPrimary} mt-10">Перезагрузить</button>
            </div>`;
        }
    }
}

window.addEventListener('hashchange', router);
