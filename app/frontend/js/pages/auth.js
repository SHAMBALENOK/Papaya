/* ==========================================================================
 * pages/auth.js — экраны входа и регистрации.
 * Монохром: активная вкладка — чёрная (bg-ink), поля — подложка mist;
 * акцент: точка логотипа — эмбер #FF7F11 (как в шапке).
 * ========================================================================== */

const TAB_ACTIVE = 'auth-tab flex-1 sm:flex-none sm:min-w-[10rem] px-6 py-3 rounded text-sm font-semibold bg-ink text-white shadow-elev-1 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60';
const TAB_IDLE = 'auth-tab flex-1 sm:flex-none sm:min-w-[10rem] px-6 py-3 rounded text-sm font-semibold text-ink-soft hover:text-ink transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60';

function renderAuth() {
    const page = document.getElementById('page');
    page.innerHTML = `
    <div class="max-w-narrow mx-auto py-12 md:py-24">

        <div class="mb-16 md:mb-20">
            <p class="${UI.eyebrow}">Олимпиады для школьников</p>
            <h1 class="mt-5 text-5xl md:text-6xl font-extrabold tracking-tight leading-[1.05] text-ink">Papaya<span class="text-ember" aria-hidden="true">.</span></h1>
            <p class="mt-7 text-lg text-ink-soft leading-relaxed max-w-md">
                Всероссийские и региональные олимпиады — в одном удобном месте.
            </p>
        </div>

        <div class="flex sm:inline-flex flex-wrap gap-2 bg-mist rounded p-2 mb-12" role="tablist" aria-label="Вход или регистрация">
            <button class="${TAB_ACTIVE}" role="tab" aria-selected="true" data-tab="login">Вход</button>
            <button class="${TAB_IDLE}" role="tab" aria-selected="false" data-tab="register">Регистрация</button>
        </div>

        <div id="auth-alert"></div>

        <form id="login-form" class="max-w-md">
            ${inputField({ id: 'login-email', name: 'email', label: 'Email', type: 'email', required: true, placeholder: 'you@example.com', autocomplete: 'email' })}
            ${inputField({ id: 'login-password', name: 'password', label: 'Пароль', type: 'password', required: true, placeholder: 'Ваш пароль', autocomplete: 'current-password' })}
            <button type="submit" class="${UI.btn} ${UI.btnPrimary} w-full mt-4">Войти</button>
            <p class="mt-8 text-sm text-ink-soft">Нет аккаунта?
                <a data-goto="register" class="text-ink font-semibold hover:text-black transition-colors cursor-pointer rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">Зарегистрироваться</a>
            </p>
        </form>

        <form id="register-form" class="max-w-md hidden">
            <div class="grid sm:grid-cols-2 gap-x-4">
                ${inputField({ id: 'reg-name', name: 'name', label: 'Имя', required: true, placeholder: 'Иван', autocomplete: 'given-name' })}
                ${inputField({ id: 'reg-surname', name: 'surname', label: 'Фамилия', required: true, placeholder: 'Иванов', autocomplete: 'family-name' })}
            </div>
            ${inputField({ id: 'reg-email', name: 'email', label: 'Email', type: 'email', required: true, placeholder: 'you@example.com', autocomplete: 'email' })}
            ${inputField({ id: 'reg-password', name: 'password', label: 'Пароль', type: 'password', required: true, placeholder: 'Минимум 8 символов', autocomplete: 'new-password' })}
            ${inputField({ id: 'reg-password2', name: 'password2', label: 'Подтвердите пароль', type: 'password', required: true, placeholder: 'Повторите пароль', autocomplete: 'new-password' })}
            <button type="submit" class="${UI.btn} ${UI.btnPrimary} w-full mt-4">Зарегистрироваться</button>
            <p class="mt-8 text-sm text-ink-soft">Уже есть аккаунт?
                <a data-goto="login" class="text-ink font-semibold hover:text-black transition-colors cursor-pointer rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">Войти</a>
            </p>
        </form>
    </div>`;

    const loginForm = document.getElementById('login-form');
    const regForm = document.getElementById('register-form');
    const tabs = page.querySelectorAll('.auth-tab');
    const alertEl = document.getElementById('auth-alert');

    function switchTab(mode) {
        tabs.forEach(t => {
            const active = t.dataset.tab === mode;
            t.className = active ? TAB_ACTIVE : TAB_IDLE;
            t.setAttribute('aria-selected', String(active));
        });
        loginForm.classList.toggle('hidden', mode !== 'login');
        regForm.classList.toggle('hidden', mode !== 'register');
        alertEl.innerHTML = '';
    }

    tabs.forEach(t => t.addEventListener('click', () => switchTab(t.dataset.tab)));
    page.querySelectorAll('[data-goto]').forEach(a =>
        a.addEventListener('click', () => switchTab(a.dataset.goto)));

    function showErr(msg) { alertEl.innerHTML = alertHtml(msg, 'error'); }

    /* Заполняем store из ответа и ведём пользователя на приветствие
       (#/welcome — страница маршрута GET /api/v1/welcome):
       cookie уже установлены сервером. */
    function enterApp(userData) {
        store.setUser({
            id: userData && userData.id,
            name: userData && userData.name,
            surname: userData && userData.surname,
            email: userData && userData.email,
            role: (userData && userData.role) || 'USER',
        });
        renderHeader();
        navigate('#/welcome');
    }

    loginForm.addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(loginForm);
        const btn = loginForm.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
            const res = await api.login({
                name: '', surname: '',
                email: fd.get('email'),
                password: fd.get('password'),
                isActive: true,
            });
            if (res.ok) { enterApp(res.data); return; }
            console.error('[auth] ошибка входа:', res.status, res.data);
            showErr(errorText(res));
        } catch (err) {
            console.error('[auth] сетевая ошибка входа:', err);
            showErr('Сетевая ошибка. Проверьте подключение.');
        }
        btn.disabled = false;
    });

    regForm.addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(regForm);
        if (fd.get('password') !== fd.get('password2')) {
            showErr('Пароли не совпадают');
            return;
        }
        const btn = regForm.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
            const res = await api.register({
                name: fd.get('name'),
                surname: fd.get('surname'),
                email: fd.get('email'),
                password: fd.get('password'),
                isActive: true,
            });
            if (res.ok) { enterApp(res.data); return; }
            console.error('[auth] ошибка регистрации:', res.status, res.data);
            showErr(errorText(res));
        } catch (err) {
            console.error('[auth] сетевая ошибка регистрации:', err);
            showErr('Сетевая ошибка. Проверьте подключение.');
        }
        btn.disabled = false;
    });
}