/* ==========================================================================
 * pages/event.js — страница события (GET /api/v1/events/{id}).
 * Узкая колонка max-w-narrow, крупные заголовки, dl-сетка без линий —
 * строки разделены только gap-y-9 («воздух»).
 * ========================================================================== */
async function renderEvent(eventId) {
    const page = document.getElementById('page');
    page.innerHTML = loadingHtml();

    const errorState = (msg) => `
    <div class="max-w-narrow mx-auto py-24 text-center">
        <h1 class="text-3xl font-extrabold tracking-tight">${escHtml(msg)}</h1>
        <p class="mt-5 text-lg text-ink-soft leading-relaxed">Возможно, событие было удалено или ссылка неверна.</p>
        <a href="#/" class="${UI.btn} ${UI.btnSecondary} mt-10">К списку олимпиад</a>
    </div>`;

    let res;
    try { res = await api.getEvent(eventId); }
    catch { page.innerHTML = errorState('Ошибка загрузки'); return; }

    if (!res.ok || !res.data) { page.innerHTML = errorState('Событие не найдено'); return; }

    const ev = res.data;
    const imgSrc = ev.picture || ev.preview_picture || null;
    const active = ev.isActive !== false;

    const statusBadge = active
        ? `<span class="${UI.badge} ${UI.badgeSuccess}"><span class="w-2 h-2 rounded-full bg-ink/60" aria-hidden="true"></span>Активно</span>`
        : `<span class="${UI.badge} ${UI.badgeNeutral}">Архив</span>`;

    page.innerHTML = `
    <article class="max-w-narrow mx-auto py-4">
        <a href="#/" class="inline-flex items-center gap-2 text-ink-soft font-semibold hover:text-ink transition-colors rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5M12 19l-7-7 7-7"></path></svg>
            К списку олимпиад
        </a>

        ${imgSrc ? `
        <div class="mt-12 bg-mist shadow-elev-1">
            <img src="${escAttr(imgSrc)}" alt="${escAttr(ev.name)}" class="w-full max-h-[26rem] object-cover"
                 onerror="this.onerror=null;this.parentElement.style.display='none'">
        </div>` : ''}

        <!-- Заголовок: увеличенные вертикальные разрывы вокруг -->
        <header class="mt-14">
            ${statusBadge}
            <h1 class="mt-7 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">${escHtml(ev.name)}</h1>
        </header>

        ${ev.disc ? `
        <section class="mt-16" aria-labelledby="event-disc-title">
            <h2 id="event-disc-title" class="${UI.eyebrow}">Описание</h2>
            <p class="mt-7 text-lg text-ink leading-[1.8] whitespace-pre-wrap">${escHtml(ev.disc)}</p>
        </section>` : ''}

        <!-- Информация: dl-сетка, строки разделены только отступами gap-y-9 -->
        <section class="mt-16 mb-8" aria-labelledby="event-info-title">
            <h2 id="event-info-title" class="${UI.eyebrow}">Информация</h2>
            <dl class="mt-8 grid sm:grid-cols-2 gap-x-12 gap-y-9">
                <div>
                    <dt class="text-sm font-medium text-ink-faint">Статус</dt>
                    <dd class="mt-2">${statusBadge}</dd>
                </div>
                <div>
                    <dt class="text-sm font-medium text-ink-faint">Создано</dt>
                    <dd class="mt-2 text-base">${formatDate(ev.createdAt)}</dd>
                </div>
                <div>
                    <dt class="text-sm font-medium text-ink-faint">Обновлено</dt>
                    <dd class="mt-2 text-base">${formatDate(ev.updatedAt)}</dd>
                </div>
                <div>
                    <dt class="text-sm font-medium text-ink-faint">ID события</dt>
                    <dd class="mt-2 text-sm text-ink-soft break-all">${escHtml(ev.id)}</dd>
                </div>
            </dl>
        </section>
    </article>`;
}