function renderAuth() {
    const page = document.getElementById('page');
    page.innerHTML = `<div class="auth-container"> <h1>Papaya</h1> <p>Олимпиады для школьников в одном месте</p> <div class="auth-tabs"> <button class="auth-tab active" data-tab="login">Вход</button> <button class="auth-tab" data-tab="register">Регистрация</button> </div> <div id="auth-alert"></div> <form id="auth-form"> <div class="form-group reg-only hidden"> <label>Имя</label> <input type="text" name="name" placeholder="Иван"> </div> <div class="form-group reg-only hidden"> <label>Фамилия</label> <input type="text" name="surname" placeholder="Иванов"> </div> <div class="form-group"> <label>Email</label> <input type="email" name="email" placeholder="you@example.com" required> </div> <div class="form-group"> <label>Пароль</label> <input type="password" name="password" placeholder="Мин. 8 символов" required> </div> <button type="submit" class="btn btn-primary btn-block" id="auth-submit">Войти</button> </form> </div>`;

    let mode = 'login';
    const tabs = page.querySelectorAll('.auth-tab');
    const regFields = page.querySelectorAll('.reg-only');
    const submitBtn = document.getElementById('auth-submit');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            mode = tab.dataset.tab;
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            regFields.forEach(f => f.classList.toggle('hidden', mode === 'login'));
            submitBtn.textContent = mode === 'login' ? 'Войти' : 'Зарегистрироваться';
            document.getElementById('auth-alert').innerHTML = '';
        });
    });

    document.getElementById('auth-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const alertEl = document.getElementById('auth-alert');
        submitBtn.disabled = true;

        try {
            let res;
            if (mode === 'login') {
                res = await api.login({
                    name: '',
                    surname: '',
                    email: fd.get('email'),
                    password: fd.get('password'),
                    isActive: true,
                });
            } else {
                res = await api.register({
                    name: fd.get('name'),
                    surname: fd.get('surname'),
                    email: fd.get('email'),
                    password: fd.get('password'),
                    isActive: true,
                });
            }

            if (res.ok) {
                store.setUser(res.data);
                navigate('#/');
            } else {
                const d = res.data?.detail;
                let msg = 'Ошибка';
                if (Array.isArray(d)) {
                    msg = d.map(e => e.msg).join('; ');
                } else if (typeof d === 'string') {
                    msg = d;
                }
                alertEl.innerHTML = `<div class="alert alert-error">${msg}</div>`;
            }
        } catch (err) {
            alertEl.innerHTML = `<div class="alert alert-error">Сетевая ошибка</div>`;
        }

        submitBtn.disabled = false;
    });
}