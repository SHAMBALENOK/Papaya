/* ==========================================================================
 * pages/myuniversity.js — управление БВИ своего университета.
 *
 *   #/my-university → GET /api/v1/user/ (профиль)
 *                     GET /api/v1/universities/{id}/olympiads?include_pending=true
 *                     GET /api/v1/olympiads (поиск олимпиады)
 *
 * Представитель университета не создаёт олимпиады: он выбирает
 * существующие олимпиады из каталога и заявляет, что вуз даёт за них БВИ.
 * Заявка уходит администратору на подтверждение.
 * ========================================================================== */

async function renderMyUniversity() {
    const page = document.getElementById('page');

    if (!store.canManageUniversity()) {
        renderForbidden('Нет доступа к управлению университетом',
            'Связи своего университета может вести представитель университета,'
            + ' назначенный администратором.');
        return;
    }

    page.innerHTML = loadingHtml('Открываем университет…');

    const me = await api.getMe();
    if (!me.ok || !me.data) { navigate('#/auth'); return; }
    store.setUser({
        id: me.data.id,
        name: me.data.name,
        surname: me.data.surname,
        email: me.data.email,
        role: me.data.role || 'USER',
        university_id: me.data.university_id || null,
    });
    renderHeader();

    const universityId = store.isAdmin() ? null : store.user.university_id;
    if (!universityId) {
        page.innerHTML = emptyHtml('Выберите университет',
            'Администратор управляет каталогом всех университетов в разделе «Администрирование».',
            '<a href="#/admin/universities" class="' + UI.btn + ' ' + UI.btnSecondary + '">Университеты</a>');
        return;
    }

    const [uniRes, olyRes, rulesRes, programsRes] = await Promise.all([
        api.getUniversity(universityId),
        api.getUniversityOlympiads(universityId, true),
        api.listBenefitRules(universityId, { include_pending: true }),
        api.listUniversityPrograms(universityId),
    ]);
    if (!uniRes.ok || !uniRes.data) {
        page.innerHTML = emptyHtml('Университет не найден',
            'Обратитесь к администратору: привязка представителя, возможно, потеряна.');
        return;
    }

    const university = uniRes.data;
    const linked = (olyRes.ok && olyRes.data && olyRes.data.olympiads) || [];
    const linkedIds = new Set(linked.map(item => String(item.id)));
    const rules = (rulesRes.ok && rulesRes.data && rulesRes.data.rules) || [];
    const programs = (programsRes.ok && programsRes.data && programsRes.data.programs) || [];

    page.innerHTML = `
    <section class="pt-4 pb-12 md:pb-16">
        <p class="${UI.eyebrow}">Представитель университета</p>
        <h1 class="mt-4 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">
            ${escHtml(university.short_name || university.name)}
        </h1>
        ${university.short_name && university.short_name !== university.name
            ? `<p class="mt-3 text-lg text-ink-soft leading-snug">${escHtml(university.name)}</p>`
            : ''}
        <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Выберите олимпиады из каталога, за которые университет даёт БВИ.
            Связь появится на странице университета после подтверждения администратором.
        </p>
        <p class="mt-6"><a href="#/universities/${escAttr(university.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Открыть страницу университета</a></p>
    </section>

    <section class="mb-16 md:mb-24" aria-labelledby="my-bvi-title">
        <div class="flex flex-wrap items-center justify-between gap-6">
            <h2 id="my-bvi-title" class="text-2xl font-extrabold tracking-tight">Олимпиады с БВИ (${linked.length})</h2>
            <button type="button" id="bvi-add" class="${UI.btn} ${UI.btnPrimary}">Добавить олимпиаду</button>
        </div>
        <div id="my-bvi-list" class="mt-10">${loadingHtml()}</div>
    </section>

    <section class="mb-16 md:mb-24" aria-labelledby="my-rules-title">
        <h2 id="my-rules-title" class="text-2xl font-extrabold tracking-tight">Правила льгот (${rules.length})</h2>
        <p class="mt-4 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Условия по каждой олимпиаде: вид льготы, предмет и требования.
            Правила заполняет администратор Papaya, а вы подтверждаете их со
            стороны вуза — это две независимые отметки.
        </p>
        <div class="mt-10" id="my-rules-list">${myRulesHtml(rules)}</div>
    </section>

    <section class="mb-16 md:mb-24" aria-labelledby="my-programs-title">
        <h2 id="my-programs-title" class="text-2xl font-extrabold tracking-tight">Образовательные программы (${programs.length})</h2>
        <p class="mt-4 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Направления подготовки, на которые распространяются льготы вуза.
            По одному названию в строке; набор сохраняется целиком.
        </p>
        <div class="mt-8" id="my-programs-box">${myProgramsHtml(programs)}</div>
    </section>`;

    drawMyBviList(linked, universityId, linkedIds);
    wireMyRules(universityId);
    wireMyPrograms(universityId, programs);

    document.getElementById('bvi-add').addEventListener('click', () => openBviPickerModal(universityId, linkedIds));
}

/** Список образовательных программ вуза. */
function myProgramsHtml(programs) {
    const value = programs.map(item => item.name).join('\n');
    return `
    <div class="${UI.card} px-8 py-7">
        <div class="${UI.field}">
            <label for="my-programs" class="${UI.label}">Программы</label>
            <textarea id="my-programs" rows="8" class="${UI.input} resize-y"
                      placeholder="Прикладная математика и информатика&#10;Лингвистика">${escHtml(value)}</textarea>
        </div>
        <div class="flex flex-wrap items-center gap-4">
            <button type="button" id="my-programs-save" class="${UI.btn} ${UI.btnPrimary}">Сохранить программы</button>
            <p class="text-sm text-ink-soft">Пустые и повторяющиеся строки игнорируются.</p>
        </div>
    </div>`;
}

/** Сохранение набора образовательных программ. */
function wireMyPrograms(universityId, programs) {
    const save = document.getElementById('my-programs-save');
    const field = document.getElementById('my-programs');
    if (!save || !field) return;

    save.addEventListener('click', async () => {
        save.disabled = true;
        const names = field.value.split('\n')
            .map(line => line.trim())
            .filter(Boolean);
        const res = await api.saveUniversityPrograms(universityId, names);
        if (res.ok) {
            showToast('Программы сохранены', 'success');
            renderMyUniversity();
            return;
        }
        showToast(errorText(res), 'error');
        save.disabled = false;
    });
}

/** Список правил льгот вузом: вид льготы, проверка Papaya и подтверждение вуза. */
function myRulesHtml(rules) {
    if (!rules.length) {
        return emptyHtml('Правил пока нет',
            'Как только администратор Papaya заполнит условия по олимпиаде, '
            + 'они появятся здесь, и вы сможете подтвердить их от имени вуза.');
    }
    const rows = rules.map(rule => {
        const confirmed = !!rule.university_confirmed;
        return `
        <div class="${UI.card} px-8 py-7">
            <div class="flex flex-col lg:flex-row lg:items-start gap-6">
                <div class="flex-1 min-w-0">
                    <p class="font-bold text-ink leading-snug">${escHtml(rule.olympiad_name || 'Олимпиада')}</p>
                    <div class="mt-3 flex flex-wrap items-center gap-3">
                        ${benefitTypeBadge(rule.benefit_type)}
                        ${verificationBadge(rule.verification_status)}
                        ${rule.subject ? `<span class="${UI.badge} ${UI.badgeNeutral}">${escHtml(rule.subject)}</span>` : ''}
                    </div>
                    ${rule.result_requirement
                        ? `<p class="mt-4 text-base text-ink leading-relaxed">Результат: ${escHtml(rule.result_requirement)}</p>`
                        : ''}
                    ${rule.extra_requirements
                        ? `<p class="mt-2 text-base text-ink-soft leading-relaxed">Дополнительно: ${escHtml(rule.extra_requirements)}</p>`
                        : ''}
                    ${rule.programs && rule.programs.length
                        ? `<p class="mt-2 text-base text-ink-soft leading-relaxed">Программы: ${escHtml(rule.programs.join(', '))}</p>`
                        : ''}
                    ${rule.valid_until
                        ? `<p class="mt-2 text-sm text-ink-faint">Действует до: ${escHtml(String(rule.valid_until).slice(0, 10))}</p>`
                        : ''}
                    ${rule.source_url
                        ? `<a href="${escAttr(rule.source_url)}" target="_blank" rel="noopener noreferrer"
                              class="mt-3 inline-block text-sm font-semibold text-ink underline">Источник условий</a>`
                        : ''}
                </div>
                <div class="shrink-0">
                    <button type="button" data-confirm-rule="${escAttr(rule.olympiad_id)}"
                            data-confirmed="${confirmed ? 'true' : 'false'}"
                            class="${UI.btn} ${confirmed ? UI.btnSecondary : UI.btnPrimary} ${UI.btnSmall}">
                        ${confirmed ? 'Подтверждено вузом ✓' : 'Подтвердить от имени вуза'}
                    </button>
                </div>
            </div>
        </div>`;
    }).join('');
    return `<div class="space-y-6">${rows}</div>`;
}

/** Подтверждение правила со стороны вуза (независимо от проверки Papaya). */
function wireMyRules(universityId) {
    document.querySelectorAll('[data-confirm-rule]').forEach(btn => {
        btn.addEventListener('click', async () => {
            btn.disabled = true;
            const next = btn.dataset.confirmed !== 'true';
            const res = await api.confirmBenefitRuleByUniversity(
                universityId, btn.dataset.confirmRule, next);
            if (res.ok) {
                showToast(next ? 'Правило подтверждено вузом' : 'Подтверждение вуза снято', 'success');
                renderMyUniversity();
                return;
            }
            showToast(errorText(res), 'error');
            btn.disabled = false;
        });
    });
}

function drawMyBviList(linked, universityId, linkedIds) {
    const box = document.getElementById('my-bvi-list');
    if (!box) return;

    if (!linked.length) {
        box.innerHTML = emptyHtml('Пока нет связей',
            'Нажмите «Добавить олимпиаду» и выберите олимпиаду из каталога.');
        return;
    }

    box.innerHTML = `<div class="space-y-6">` + linked.map(item => {
        const confirmed = item.bvi_status === 'CONFIRMED';
        const archived = item.status === 'ARCHIVED' || item.is_historical;
        // Архивная олимпиада не попадает в выбор новых заявок, поэтому по
        // такой связи представителю нечего отзывать: заявка уже подтверждена,
        // а олимпиады нет в актуальном перечне.
        const note = archived
            ? `Связь историческая: олимпиады больше нет в перечне РСОШ.
               Связь сохранена, но новые заявки по ней невозможны.`
            : (confirmed
                ? `Связь подтверждена. Снять подтверждение может администратор Papaya.`
                : `Заявка ждёт подтверждения администратором.`);
        return `
        <div class="${UI.card} px-8 py-7 flex flex-col lg:flex-row lg:items-center gap-6">
            <div class="flex-1 min-w-0">
                <p class="font-bold text-ink leading-snug">${escHtml(item.name)}</p>
                <div class="mt-3 flex items-center gap-3 flex-wrap">
                    ${bviStatusBadge(item.bvi_status)}
                    ${archived
                        ? `<span class="${UI.badge} ${UI.badgeNeutral}">Архивная олимпиада</span>`
                        : ''}
                </div>
            </div>
            <div class="flex flex-col lg:items-end gap-3 shrink-0">
                <a href="#/olympiads/${escAttr(item.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Открыть</a>
                ${confirmed || archived
                    ? `<p class="text-xs text-ink-faint max-w-[18rem] text-right">${escHtml(note)}</p>`
                    : `<button type="button" data-remove="${escAttr(item.id)}" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}">Отозвать заявку</button>`}
            </div>
        </div>`;
    }).join('') + `</div>`;

    box.querySelectorAll('[data-remove]').forEach(btn => {
        btn.addEventListener('click', async () => {
            btn.disabled = true;
            const res = await api.removeBvi(universityId, btn.dataset.remove);
            if (res.ok) {
                showToast('Заявка отозвана', 'success');
                renderMyUniversity();
                return;
            }
            showToast(errorText(res), 'error');
            btn.disabled = false;
        });
    });
}

async function openBviPickerModal(universityId, linkedIds) {
    const body = `
        <div id="modal-alert"></div>
        <div class="${UI.field}">
            <label for="bvi-query" class="${UI.label}">Поиск олимпиады</label>
            <input id="bvi-query" type="search" class="${UI.input}" placeholder="Название олимпиады" autocomplete="off">
        </div>
        <div id="bvi-results" class="space-y-3 max-h-96 overflow-y-auto modal-scroll">${loadingHtml('Загружаем каталог…')}</div>
        <div class="flex flex-wrap justify-end gap-3 mt-10">
            <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Закрыть</button>
        </div>`;
    const { overlay, close } = openModal('Добавить олимпиаду с БВИ', body, { wide: true });
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    const results = overlay.querySelector('#bvi-results');
    const queryInput = overlay.querySelector('#bvi-query');

    async function load(query) {
        results.innerHTML = loadingHtml('Ищем…');
        const res = await api.listOlympiads(query || '');
        if (!res.ok) {
            results.innerHTML = alertHtml(errorText(res), 'error');
            return;
        }
        const items = (res.data.olympiads || []).filter(item => !linkedIds.has(String(item.id)));
        if (!items.length) {
            results.innerHTML = `<p class="py-12 text-center text-ink-soft">Олимпиад не найдено</p>`;
            return;
        }
        results.innerHTML = items.map(item => `
            <div class="${UI.card} px-6 py-5 flex flex-col sm:flex-row sm:items-center gap-4">
                <div class="flex-1 min-w-0">
                    <p class="font-semibold text-ink leading-snug">${escHtml(item.name)}</p>
                    ${item.status === 'ARCHIVED' ? `<div class="mt-2">${olympiadStatusBadge(item.status)}</div>` : ''}
                </div>
                <button type="button" data-pick="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall} shrink-0">Добавить</button>
            </div>`).join('');

        results.querySelectorAll('[data-pick]').forEach(btn => {
            btn.addEventListener('click', async () => {
                btn.disabled = true;
                const res2 = await api.requestBvi(universityId, btn.dataset.pick);
                if (res2.ok) {
                    showToast('Заявка отправлена на подтверждение', 'success');
                    close();
                    renderMyUniversity();
                    return;
                }
                const alertBox = overlay.querySelector('#modal-alert');
                if (alertBox) alertBox.innerHTML = alertHtml(errorText(res2), 'error');
                btn.disabled = false;
            });
        });
    }

    let timer = null;
    queryInput.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => load(queryInput.value.trim()), 300);
    });
    load('');
}
