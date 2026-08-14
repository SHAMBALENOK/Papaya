/* ==========================================================================
 * pages/welcome.js — страница GET /api/v1/welcome
 * Ответ API: { user_id, user_name, user_surname } либо {} без сессии.
 * На странице выводятся только эти поля.
 * ========================================================================== */

async function renderWelcome() {
    const page = document.getElementById('page');
    if (!store.user) { navigate('#/auth'); return; }
    page.innerHTML = loadingHtml();

    let res;
    try { res = await api.getWelcome(); } catch { res = { ok: false, data: null }; }

    const data = (res.ok && res.data) ? res.data : {};
    if (!data.user_id) {
        navigate('#/auth');
        return;
    }

    const fullName = [data.user_name, data.user_surname].filter(Boolean).join(' ');

    page.innerHTML = `
    <section class="pt-4 pb-8 md:pb-12">
        <p class="${UI.eyebrow}">Добро пожаловать</p>
        <h1 class="mt-5 text-4xl md:text-6xl font-extrabold tracking-tight leading-[1.05] max-w-3xl">
            ${escHtml(fullName || 'Пользователь')}
        </h1>
        <p class="mt-8 text-lg text-ink-soft leading-relaxed max-w-xl">
            Вы вошли в Papaya. Ниже — данные, которые вернул маршрут /api/v1/welcome.
        </p>
    </section>

    <section class="grid gap-6 sm:grid-cols-3 pb-16 md:pb-20" aria-label="Данные приветствия">
        <div class="bg-white shadow-elev-1 p-8">
            <p class="text-xs font-semibold text-ink-soft uppercase tracking-[0.14em]">Имя</p>
            <p class="mt-4 text-2xl font-extrabold tracking-tight break-words">${escHtml(data.user_name || '—')}</p>
        </div>
        <div class="bg-white shadow-elev-1 p-8">
            <p class="text-xs font-semibold text-ink-soft uppercase tracking-[0.14em]">Фамилия</p>
            <p class="mt-4 text-2xl font-extrabold tracking-tight break-words">${escHtml(data.user_surname || '—')}</p>
        </div>
        <div class="bg-white shadow-elev-1 p-8">
            <p class="text-xs font-semibold text-ink-soft uppercase tracking-[0.14em]">ID</p>
            <p class="mt-4 text-sm font-medium text-ink-soft break-all">${escHtml(data.user_id)}</p>
        </div>
    </section>

    <section class="flex flex-wrap gap-3">
        <a href="#/" class="${UI.btn} ${UI.btnPrimary}">К каталогу олимпиад</a>
        <a href="#/profile" class="${UI.btn} ${UI.btnSecondary}">Мой профиль</a>
    </section>`;
}