function renderAuth() {
    const page = document.getElementById('page');
    page.innerHTML = `
    <div class="auth-container">
        <h1>Papaya</h1>
        <p>Олимпиады для школьников в одном месте</p>

        <div class="auth-tabs">
            <button class="auth-tab active" data-tab="login">Вход</button>
            <button class="auth-tab" data-tab="register">Регистрация</button>
        </div>

        <div id="auth-alert"></div>

        <!-- LOGIN -->
        <form id="login-form">
            <div class="form-group">
                <label>Email</label>
                <input name="email" type="email" required placeholder="you@example.com">
            </div>
            <div class="form-group">
                <label>Пароль</label>
                <input name="password" type="password" required placeholder="********">
            </div>
            <button type="submit" class="btn btn-primary btn-block">Войти</button>
            <div class="auth-switch">Нет аккаунта? <a data-goto="register">Зарегистрироваться</a></div>
        </form>

        <!-- REGISTER -->
        <form id="register-form" class="hidden">
            <div class="form-row">
                <div class="form-group">
                    <label>Имя</label>
                    <input name="name" required placeholder="Иван">
                </div>
                <div class="form-group">
                    <label>Фамилия</label>
                    <input name="surname" required placeholder="Иванов">
                </div>
            </div>
            <div class="form-group">
                <label>Email</label>
                <input name="email" type="email" required placeholder="you@example.com">
            </div>
            <div class="form-group">
                <label>Пароль</label>
                <input name="password" type="password" required placeholder="Мин. 8 символов">
            </div>
            <div class="form-group">
                <label>Подтвердите пароль</label>
                <input name="password2" type="password" required placeholder="Повторите пароль">
            </div>
            <button type="submit" class="btn btn-primary btn-block">Зарегистрироваться</button>
            <div class="auth-switch">Уже есть аккаунт? <a data-goto="login">Войти</a></div>
        </form>
    </div>`;

    const loginForm = document.getElementById('login-form');
    const regForm   = document.getElementById('register-form');
    const tabs      = page.querySelectorAll('.auth-tab');
    const alertEl   = document.getElementById('auth-alert');

    function switchTab(mode) {
        tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === mode));
        loginForm.classList.toggle('hidden', mode !== 'login');
        regForm.classList.toggle('hidden', mode !== 'register');
        alertEl.innerHTML = '';
    }

    tabs.forEach(t => t.addEventListener('click', () => switchTab(t.dataset.tab)));
    page.querySelectorAll('[data-goto]').forEach(a =>
        a.addEventListener('click', () => switchTab(a.dataset.goto)));

    function showErr(msg) {
        alertEl.innerHTML = `<div class="alert alert-error">${escHtml(msg)}</div>`;
    }

    loginForm.addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(loginForm);
        const btn = loginForm.querySelector('button[type=submit]');
        btn.disabled = true;
        try {
            const res = await api.login({
                name: '', surname: '',
                email: fd.get('email'),
                password: fd.get('password'),
                isActive: true,
            });
            if (res.ok) { store.setUser(res.data); navigate('#/'); }
            else {
                const d = res.data?.detail;
                showErr(Array.isArray(d) ? d.map(x=>x.msg).join('; ') : (d || 'Ошибка входа'));
            }
        } catch { showErr('Сетевая ошибка'); }
        btn.disabled = false;
    });

    regForm.addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(regForm);
        if (fd.get('password') !== fd.get('password2')) {
            showErr('Пароли не совпадают');
            return;
        }
        const btn = regForm.querySelector('button[type=submit]');
        btn.disabled = true;
        try {
            const res = await api.register({
                name: fd.get('name'),
                surname: fd.get('surname'),
                email: fd.get('email'),
                password: fd.get('password'),
                isActive: true,
            });
            if (res.ok) { store.setUser(res.data); navigate('#/'); }
            else {
                const d = res.data?.detail;
                showErr(Array.isArray(d) ? d.map(x=>x.msg).join('; ') : (d || 'Ошибка регистрации'));
            }
        } catch { showErr('Сетевая ошибка'); }
        btn.disabled = false;
    });
}