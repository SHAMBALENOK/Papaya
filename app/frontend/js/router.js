/* ==========================================================================
 * router.js — hash-роутер SPA.
 * ========================================================================== */

function navigate(hash) {
    /* Страховка: если hash уже равен целевому, hashchange не сработает —
       рендерим вручную. */
    if (window.location.hash === hash) {
        router();
        return;
    }
    window.location.hash = hash;
}

function getRoute() { return (window.location.hash || '#/').slice(1); }

function router() {
    const path = getRoute();
    const header = document.getElementById('header');

    try {
        if (path.startsWith('/event/')) {
            header.classList.remove('hidden');
            renderEvent(path.split('/event/')[1]);
        } else if (path === '/profile') {
            header.classList.remove('hidden');
            renderProfile();
        } else if (path === '/my-events') {
            header.classList.remove('hidden');
            renderMyEvents();
        } else if (path === '/admin') {
            header.classList.remove('hidden');
            renderAdmin();
        } else if (path === '/auth') {
            header.classList.add('hidden');
            renderAuth();
        } else {
            header.classList.remove('hidden');
            renderDashboard();
        }
        highlightNav(path);

        /* FAB «+» живёт только на каталоге и «Моих событиях» */
        setFab(path === '/' || path === '/my-events');
    } catch (err) {
        console.error('[router] ошибка рендера:', err);
        setFab(false);
        document.getElementById('page').innerHTML = `
        <div class="max-w-narrow mx-auto py-24 text-center">
            <h1 class="text-3xl font-extrabold tracking-tight">Не удалось открыть страницу</h1>
            <p class="mt-5 text-ink/60 leading-relaxed">Внутренняя ошибка: ${escHtml(String((err && err.message) || err))}</p>
            <p class="mt-3 text-sm text-ink/45">Если файлы проекта недавно обновлялись — перезагрузите страницу с очисткой кэша (Ctrl+Shift+R).</p>
            <button onclick="location.reload()" class="mt-10 inline-flex items-center justify-center font-semibold rounded bg-primary text-white px-6 py-3 shadow-elev-1">Перезагрузить</button>
        </div>`;
    }
}

window.addEventListener('hashchange', router);