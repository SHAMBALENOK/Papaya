/* ==========================================================================
 * pages/welcome.js — публичная визитка Papaya.
 * Содержит только сведения о возможностях, которые уже есть в проекте.
 * ========================================================================== */

function renderWelcome() {
    const page = document.getElementById('page');

    page.innerHTML = `
    <div class="pb-8 md:pb-12">
        <header class="flex items-center justify-between gap-6 pb-16 md:pb-24" aria-label="Шапка визитки">
            <a href="#/welcome" class="text-2xl font-extrabold tracking-tight text-ink rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">
                Papaya<span class="text-ember" aria-hidden="true">.</span>
            </a>
            <a href="#/auth" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Войти</a>
        </header>

        <section class="grid gap-12 lg:grid-cols-[minmax(0,1.35fr)_minmax(18rem,0.65fr)] lg:items-center pb-24 md:pb-32">
            <div>
                <p class="${UI.eyebrow}">Сервис для школьников</p>
                <h1 class="mt-6 text-5xl md:text-7xl font-black tracking-tight leading-[1.02] max-w-4xl">
                    Олимпиады —<br>
                    <span class="text-ember">в одном месте.</span>
                </h1>
                <p class="mt-8 text-lg md:text-xl text-ink-soft leading-relaxed max-w-2xl">
                    Papaya — веб-сервис, где собрана информация о всероссийских и региональных олимпиадах для школьников.
                </p>
                <div class="mt-10 flex flex-wrap gap-3">
                    <a href="#/auth" class="${UI.btn} ${UI.btnPrimary}">Войти или зарегистрироваться</a>
                    <button type="button" data-welcome-about class="${UI.btn} ${UI.btnSecondary}">О сервисе</button>
                </div>
            </div>

            <div class="bg-white shadow-elev-2 p-8 md:p-10" aria-label="Основные разделы Papaya">
                <p class="text-xs font-semibold text-ink-soft uppercase tracking-[0.14em]">Papaya</p>
                <div class="mt-8 space-y-6">
                    <div class="flex items-start gap-4">
                        <span class="mt-1 w-3 h-3 rounded bg-ember shrink-0" aria-hidden="true"></span>
                        <div>
                            <h2 class="font-bold text-lg">Каталог олимпиад</h2>
                            <p class="mt-2 text-sm text-ink-soft leading-relaxed">Всероссийские и региональные мероприятия.</p>
                        </div>
                    </div>
                    <div class="flex items-start gap-4">
                        <span class="mt-1 w-3 h-3 rounded bg-sage shrink-0" aria-hidden="true"></span>
                        <div>
                            <h2 class="font-bold text-lg">Личный профиль</h2>
                            <p class="mt-2 text-sm text-ink-soft leading-relaxed">Регистрация, вход и управление данными профиля.</p>
                        </div>
                    </div>
                    <div class="flex items-start gap-4">
                        <span class="mt-1 w-3 h-3 rounded bg-sand shrink-0" aria-hidden="true"></span>
                        <div>
                            <h2 class="font-bold text-lg">Работа с событиями</h2>
                            <p class="mt-2 text-sm text-ink-soft leading-relaxed">Добавление, изменение и импорт данных из PDF-таблиц.</p>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <section id="welcome-about" class="py-20 md:py-28 scroll-mt-8" aria-labelledby="welcome-about-title">
            <div class="max-w-2xl">
                <p class="${UI.eyebrow}">Возможности</p>
                <h2 id="welcome-about-title" class="mt-5 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">Что есть в Papaya</h2>
                <p class="mt-6 text-lg text-ink-soft leading-relaxed">
                    Возможности сервиса, доступные после авторизации.
                </p>
            </div>

            <div class="mt-14 grid gap-8 md:grid-cols-3">
                <article class="bg-white shadow-elev-1 p-8 md:p-10">
                    <p class="text-sm font-extrabold text-ember">01</p>
                    <h3 class="mt-6 text-2xl font-bold tracking-tight">Просмотр олимпиад</h3>
                    <p class="mt-4 text-ink-soft leading-relaxed">
                        Каталог активных мероприятий и отдельные страницы с информацией об олимпиадах.
                    </p>
                </article>
                <article class="bg-white shadow-elev-1 p-8 md:p-10">
                    <p class="text-sm font-extrabold text-ember">02</p>
                    <h3 class="mt-6 text-2xl font-bold tracking-tight">Управление профилем</h3>
                    <p class="mt-4 text-ink-soft leading-relaxed">
                        Пользователь может зарегистрироваться, войти в сервис и изменить данные своего профиля.
                    </p>
                </article>
                <article class="bg-white shadow-elev-1 p-8 md:p-10">
                    <p class="text-sm font-extrabold text-ember">03</p>
                    <h3 class="mt-6 text-2xl font-bold tracking-tight">Управление событиями</h3>
                    <p class="mt-4 text-ink-soft leading-relaxed">
                        Пользователи с соответствующими правами могут добавлять и изменять события, а также импортировать данные из PDF-таблиц.
                    </p>
                </article>
            </div>
        </section>

        <section class="mt-12 bg-ink text-white px-8 py-14 md:px-14 md:py-16 flex flex-col md:flex-row md:items-center md:justify-between gap-8" aria-labelledby="welcome-start-title">
            <div class="max-w-2xl">
                <p class="text-xs font-semibold text-white/60 uppercase tracking-[0.18em]">Начало работы</p>
                <h2 id="welcome-start-title" class="mt-4 text-3xl md:text-4xl font-extrabold tracking-tight">Перейдите к авторизации</h2>
                <p class="mt-5 text-white/70 leading-relaxed">
                    Войдите в существующий аккаунт или зарегистрируйтесь, чтобы открыть каталог и остальные разделы сервиса.
                </p>
            </div>
            <a href="#/auth" class="${UI.btn} bg-ember text-ink px-6 py-3 shadow-elev-1 hover:brightness-95 shrink-0">Войти или зарегистрироваться</a>
        </section>

        <footer class="pt-16 flex items-center justify-between gap-6 text-sm text-ink-soft">
            <span class="font-bold text-ink">Papaya<span class="text-ember" aria-hidden="true">.</span></span>
            <a href="#/auth" class="font-semibold text-ink hover:text-black rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">Авторизация</a>
        </footer>
    </div>`;

    page.querySelector('[data-welcome-about]').addEventListener('click', () => {
        document.getElementById('welcome-about').scrollIntoView({ behavior: 'smooth' });
    });
}