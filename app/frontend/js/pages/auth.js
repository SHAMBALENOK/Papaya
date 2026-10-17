/* ==========================================================================
 * pages/auth.js — экраны входа и регистрации.
 * Активная вкладка — чёрная (bg-ink), поля — подложка mist.
 * ========================================================================== */

const TAB_ACTIVE = 'auth-tab flex-1 sm:flex-none sm:min-w-[10rem] px-6 py-3 rounded text-sm font-semibold bg-ink text-white shadow-elev-1 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60';
const TAB_IDLE = 'auth-tab flex-1 sm:flex-none sm:min-w-[10rem] px-6 py-3 rounded text-sm font-semibold text-ink-soft hover:text-ink transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60';

/* Требования к паролю — зеркало серверной проверки
   (app/middlewares/re_check.py). Список показывается заранее, а не всплывает
   по одной ошибке за раз: пользователь видит все условия до ввода и следит
   за ними по мере набора. Порядок совпадает с порядком проверок на сервере. */
const PASSWORD_RULES = [
    { id: 'length', label: 'Минимум 8 символов', test: p => p.length >= 8 },
    { id: 'bytes', label: 'Не длиннее 72 байт', test: p => new TextEncoder().encode(p).length <= 72 },
    { id: 'upper', label: 'Хотя бы одна заглавная буква', test: p => /[A-ZА-ЯЁ]/.test(p) },
    { id: 'lower', label: 'Хотя бы одна строчная буква', test: p => /[a-zа-яё]/.test(p) },
    { id: 'digit', label: 'Хотя бы одна цифра', test: p => /\d/.test(p) },
    { id: 'special', label: 'Хотя бы один спецсимвол (!@#$%^&* и др.)', test: p => /[!@#$%^&*()_+\-=\[\]{};:"\\|,.<>/?]/.test(p) },
    { id: 'nospace', label: 'Без пробелов', test: p => !/\s/.test(p) },
    { id: 'repeat', label: 'Без 4 одинаковых символов подряд', test: p => !/(.)\1{3,}/.test(p) },
    { id: 'sequence', label: 'Без слабых последовательностей (1234, qwerty…)', test: p => !['1234', 'abcd', 'qwerty', 'asdf', 'zxcv'].some(s => p.toLowerCase().includes(s)) },
];

function passwordRulesHtml() {
    return `<div id="reg-password-rules" class="mt-3" aria-live="polite">
        <p class="text-sm font-medium text-ink-soft mb-2">Пароль должен содержать:</p>
        <ul class="grid sm:grid-cols-2 gap-x-4 gap-y-1 text-sm">
            ${PASSWORD_RULES.map(r => `<li data-rule="${r.id}" class="flex items-start gap-2 text-ink-faint">
                <span data-rule-mark class="shrink-0 leading-6" aria-hidden="true">○</span>
                <span>${r.label}</span>
            </li>`).join('')}
        </ul>
    </div>`;
}

function renderAuth() {
    if (store.user) { navigate('#/'); return; }

    const page = document.getElementById('page');
    page.innerHTML = `
    <div class="max-w-narrow mx-auto py-12 md:py-24">

        <div class="mb-16 md:mb-20">
            <p class="${UI.eyebrow}">Олимпиады и поступление</p>
            <h1 class="mt-5 text-5xl md:text-6xl font-extrabold tracking-tight leading-[1.05] text-ink">Papaya<span class="text-ember" aria-hidden="true">.</span></h1>
            <p class="mt-7 text-lg text-ink-soft leading-relaxed max-w-md">
                Какие олимпиады дают БВИ в вашем университете — в одном месте.
            </p>
        </div>

        <div class="flex sm:inline-flex flex-wrap gap-2 bg-mist rounded p-2 mb-12" role="tablist" aria-label="Вход или регистрация">
            <button class="${TAB_ACTIVE}" role="tab" aria-selected="true" data-tab="login">Вход</button>
            <button class="${TAB_IDLE}" role="tab" aria-selected="false" data-tab="register">Регистрация</button>
        </div>

        <div id="auth-alert"></div>

        <form id="login-form" class="max-w-md">
            ${inputField({ id: 'login-email', name: 'email', label: 'Email', type: 'email', required: true, placeholder: 'you@example.com', autocomplete: 'email' })}
            ${passwordField({ id: 'login-password', name: 'password', label: 'Пароль', required: true, placeholder: 'Ваш пароль', autocomplete: 'current-password' })}
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
            ${passwordField({ id: 'reg-password', name: 'password', label: 'Пароль', required: true, placeholder: 'Минимум 8 символов', autocomplete: 'new-password' })}
            ${passwordRulesHtml()}
            ${passwordField({ id: 'reg-password2', name: 'password2', label: 'Подтвердите пароль', required: true, placeholder: 'Повторите пароль', autocomplete: 'new-password' })}
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

    // Показ пароля: кнопка переключает тип поля и не отправляет форму
    // (type="button"). Значение и имя поля при этом не меняются, поэтому
    // автозаполнение браузера продолжает работать.
    page.querySelectorAll('[data-toggle-password]').forEach(btn => {
        btn.addEventListener('click', () => {
            const field = document.getElementById(btn.dataset.togglePassword);
            if (!field) return;
            const reveal = field.type === 'password';
            field.type = reveal ? 'text' : 'password';
            btn.textContent = reveal ? 'Скрыть' : 'Показать';
            btn.setAttribute('aria-pressed', String(reveal));
        });
    });

    function showErr(msg) { alertEl.innerHTML = alertHtml(msg, 'error'); }

    // Живые индикаторы требований к паролю: каждая строка списка меняет
    // отметку «○ / ✓» и цвет по мере ввода. Пустое поле — всё нейтрально,
    // чтобы список читался как условия, а не как уже нарушенные правила.
    const regPassword = document.getElementById('reg-password');
    const rulesList = page.querySelector('#reg-password-rules');
    function updatePasswordRules() {
        if (!rulesList) return;
        const pw = regPassword ? regPassword.value : '';
        PASSWORD_RULES.forEach(rule => {
            const li = rulesList.querySelector(`[data-rule="${rule.id}"]`);
            if (!li) return;
            const ok = !!pw && rule.test(pw);
            li.classList.toggle('text-sage', ok);
            li.classList.toggle('text-ink-faint', !ok);
            const mark = li.querySelector('[data-rule-mark]');
            if (mark) mark.textContent = ok ? '✓' : '○';
        });
    }
    if (regPassword) regPassword.addEventListener('input', updatePasswordRules);
    updatePasswordRules();

    function enterApp(userData) {
        store.setUser({
            id: userData && userData.id,
            name: userData && userData.name,
            surname: userData && userData.surname,
            email: userData && userData.email,
            role: (userData && userData.role) || 'USER',
            university_id: (userData && userData.university_id) || null,
        });
        renderHeader();
        navigate('#/');
    }

    loginForm.addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(loginForm);
        const btn = loginForm.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
            const res = await api.login({
                email: fd.get('email'),
                password: fd.get('password'),
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