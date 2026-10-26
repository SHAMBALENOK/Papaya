/* ==========================================================================
 * pages/myuniversity.js — кабинет представителя университета.
 *
 *   #/my-university → GET /api/v1/universities/{id}
 *                     GET /api/v1/universities/{id}/benefit-rules?include_drafts=true
 *                     GET /api/v1/universities/{id}/programs
 *                     GET /api/v1/universities/{id}/catalog-requests
 *
 * Представитель не создаёт олимпиады: он выбирает их из каталога и заводит
 * правила льгот своего вуза — черновик → публикация. Загружает документы,
 * смотрит историю версий и откатывает. Проверку Papaya ставит только
 * администратор; подтверждение вуза — отдельная отметка представителя.
 * ========================================================================== */

/** Состояние кабинета: фильтр по статусу правил и загруженные данные. */
let myUniversityState = { statusFilter: '', rules: [], programs: [], requests: [] };

async function renderMyUniversity() {
    const page = document.getElementById('page');

    if (!store.canManageUniversity()) {
        renderForbidden('Нет доступа к управлению университетом',
            'Правила льгот своего университета может вести представитель университета,'
            + ' назначенный администратором. Подать заявку можно в профиле.');
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
        page.innerHTML = emptyHtml('Кабинет представителя не нужен администратору',
            'Администратор ведёт правила всех университетов в разделе «Администрирование → Льготы».',
            '<a href="#/admin/benefit-rules" class="' + UI.btn + ' ' + UI.btnSecondary + '">Открыть реестр правил</a>');
        return;
    }

    const [uniRes, rulesRes, programsRes, requestsRes] = await Promise.all([
        api.getUniversity(universityId),
        api.listBenefitRules(universityId, { includeDrafts: true, limit: 500 }),
        api.listUniversityPrograms(universityId),
        api.listCatalogRequests(universityId).catch(() => ({ ok: false })),
    ]);
    if (!uniRes.ok || !uniRes.data) {
        page.innerHTML = emptyHtml('Университет не найден',
            'Обратитесь к администратору: привязка представителя, возможно, потеряна.');
        return;
    }
    if (!rulesRes.ok) {
        page.innerHTML = alertHtml(errorText(rulesRes), 'error');
        return;
    }

    const university = uniRes.data;
    myUniversityState.rules = (rulesRes.data && rulesRes.data.rules) || [];
    myUniversityState.programs = (programsRes.ok && programsRes.data && programsRes.data.programs) || [];
    myUniversityState.requests = (requestsRes.ok && requestsRes.data && requestsRes.data.requests) || [];
    const rules = myUniversityState.rules;
    const programs = myUniversityState.programs;

    const counts = {
        draft: rules.filter(rule => rule.status === 'draft').length,
        published: rules.filter(rule => rule.status === 'published').length,
        archived: rules.filter(rule => rule.status === 'archived').length,
    };

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
            Заводите правила льгот за олимпиады из каталога, прикладывайте документы
            и публикуйте. Опубликованное правило сразу видно в каталоге с пометкой
            «Не проверено Papaya», пока модератор не сверит его с документом.
        </p>
        <div class="mt-6 flex flex-wrap gap-3">
            <a href="#/universities/${escAttr(university.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Открыть публичную страницу</a>
            <button type="button" id="catalog-request" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Нет нужной олимпиады?</button>
        </div>
    </section>

    <section class="mb-16 md:mb-24" aria-labelledby="my-rules-title">
        <div class="flex flex-wrap items-center justify-between gap-6">
            <h2 id="my-rules-title" class="text-2xl font-extrabold tracking-tight">Правила льгот (${rules.length})</h2>
            <button type="button" id="rule-create" class="${UI.btn} ${UI.btnPrimary}">Новое правило</button>
        </div>
        <div class="mt-6 flex flex-wrap gap-2" role="tablist" aria-label="Фильтр по статусу">
            ${[
                { value: '', label: `Все · ${rules.length}` },
                { value: 'draft', label: `Черновики · ${counts.draft}` },
                { value: 'published', label: `Опубликованные · ${counts.published}` },
                { value: 'archived', label: `Архив · ${counts.archived}` },
            ].map(item => `
            <button type="button" data-status-filter="${item.value}" role="tab" aria-selected="${item.value === myUniversityState.statusFilter}"
                    class="px-4 py-2 rounded text-sm font-semibold ${item.value === myUniversityState.statusFilter ? 'bg-ink text-white' : 'bg-mist text-ink-soft hover:text-ink'}">
                ${item.label}
            </button>`).join('')}
        </div>
        <div id="my-rules-list" class="mt-8">${myRulesListHtml()}</div>
    </section>

    <section class="mb-16 md:mb-24" aria-labelledby="my-programs-title">
        <h2 id="my-programs-title" class="text-2xl font-extrabold tracking-tight">Образовательные программы (${programs.length})</h2>
        <p class="mt-4 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Направления подготовки, к которым привязываются правила. Программу,
            на которую ссылается хотя бы одно правило, удалить нельзя — сначала
            уберите её из правил.
        </p>
        <div class="mt-8" id="my-programs-box">${myProgramsHtml(programs)}</div>
    </section>

    <section class="mb-16 md:mb-24" aria-labelledby="my-requests-title">
        <h2 id="my-requests-title" class="text-2xl font-extrabold tracking-tight">Заявки на пополнение каталога (${myUniversityState.requests.length})</h2>
        <div class="mt-8">${myCatalogRequestsHtml(myUniversityState.requests)}</div>
    </section>`;

    const reload = () => renderMyUniversity();
    document.getElementById('rule-create').addEventListener('click', () =>
        openBenefitRuleEditor({ universityId, onDone: reload }));
    document.getElementById('catalog-request').addEventListener('click', () =>
        openCatalogRequestModal(universityId, reload));
    document.querySelectorAll('[data-status-filter]').forEach(btn => {
        btn.addEventListener('click', () => {
            myUniversityState.statusFilter = btn.dataset.statusFilter;
            renderMyUniversity();
        });
    });
    bindRuleManageActions(document.getElementById('my-rules-list'), () => myUniversityState.rules, reload);
    wireMyPrograms(universityId);
}

/** Список правил кабинета с учётом фильтра по статусу. */
function myRulesListHtml() {
    const filter = myUniversityState.statusFilter;
    const rules = myUniversityState.rules.filter(rule => !filter || rule.status === filter);
    if (!rules.length) {
        if (filter) return emptyHtml('В этом разделе пусто', 'Правил с таким статусом пока нет.');
        return emptyHtml('Правил пока нет',
            'Нажмите «Новое правило», выберите олимпиаду из каталога и опишите условия льготы. '
            + 'Черновик не виден в каталоге, пока вы его не опубликуете.');
    }
    return `<div class="space-y-6">${rules.map(rule => benefitRuleManageCardHtml(rule)).join('')}</div>`;
}

/** Список образовательных программ вуза с добавлением и удалением. */
function myProgramsHtml(programs) {
    const rows = programs.length
        ? `<ul class="space-y-2">${programs.map(item => `
            <li class="flex items-center justify-between gap-4 rounded bg-mist px-4 py-3" data-program-id="${escAttr(item.id)}">
                <span class="text-sm text-ink">${escHtml(item.name)}
                    ${item.rules_count ? `<span class="text-ink-faint"> · в правилах: ${item.rules_count}</span>` : ''}
                </span>
                ${item.rules_count
                    ? `<span class="text-xs text-ink-faint" title="Программа используется в правилах">нельзя удалить</span>`
                    : `<button type="button" data-remove-program="${escAttr(item.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Удалить</button>`}
            </li>`).join('')}</ul>`
        : `<p class="text-sm text-ink-soft">Программ пока нет. Добавьте первую — и правила можно будет привязывать к направлениям.</p>`;
    return `
    <div class="${UI.card} px-8 py-7">
        ${rows}
        <form id="my-program-add" class="mt-6 flex flex-col sm:flex-row gap-3">
            <label for="my-program-name" class="sr-only">Название программы</label>
            <input id="my-program-name" type="text" class="${UI.input} flex-1" placeholder="Прикладная математика и информатика" autocomplete="off" required>
            <button type="submit" class="${UI.btn} ${UI.btnSecondary} shrink-0">Добавить программу</button>
        </form>
    </div>`;
}

/** Добавление/удаление программ по одной. */
function wireMyPrograms(universityId) {
    const form = document.getElementById('my-program-add');
    if (form) {
        form.addEventListener('submit', async e => {
            e.preventDefault();
            const input = document.getElementById('my-program-name');
            const name = input.value.trim();
            if (!name) return;
            const res = await api.addUniversityProgram(universityId, { name });
            if (res.ok) {
                showToast('Программа добавлена', 'success');
                renderMyUniversity();
                return;
            }
            showToast(errorText(res), 'error');
        });
    }
    document.querySelectorAll('[data-remove-program]').forEach(btn => {
        btn.addEventListener('click', async () => {
            if (!window.confirm('Удалить программу из каталога университета?')) return;
            btn.disabled = true;
            const res = await api.deleteUniversityProgram(universityId, btn.dataset.removeProgram);
            if (res.ok) {
                showToast('Программа удалена', 'success');
                renderMyUniversity();
                return;
            }
            showToast(errorText(res), 'error');
            btn.disabled = false;
        });
    });
}

/** Заявки представителя на пополнение каталога и их состояние. */
function myCatalogRequestsHtml(requests) {
    if (!requests.length) {
        return `<p class="text-sm text-ink-soft">Заявок нет. Если в каталоге не хватает олимпиады или сезона — нажмите «Нет нужной олимпиады?».</p>`;
    }
    const statusBadge = status => {
        if (status === 'resolved') return `<span class="${UI.badge} ${UI.badgeSuccess}">Выполнено</span>`;
        if (status === 'rejected') return `<span class="${UI.badge} ${UI.badgeDanger}">Отклонено</span>`;
        return `<span class="${UI.badge} ${UI.badgePending}">Открыта</span>`;
    };
    const kindLabel = kind => ({ olympiad: 'Олимпиада', season: 'Сезон', profile: 'Профиль', other: 'Другое' }[kind] || kind || '');
    return `<div class="space-y-4">${requests.map(item => `
        <div class="${UI.card} px-8 py-6">
            <div class="flex flex-wrap items-center gap-3">
                ${statusBadge(item.status)}
                <span class="text-sm text-ink-faint">${escHtml(kindLabel(item.kind))} · ${formatDate(item.createdAt)}</span>
            </div>
            <p class="mt-3 text-base text-ink leading-relaxed whitespace-pre-wrap">${escHtml(item.text || '')}</p>
            ${item.admin_note ? `<p class="mt-3 text-sm text-ink-soft">Ответ администратора: ${escHtml(item.admin_note)}</p>` : ''}
        </div>`).join('')}</div>`;
}
