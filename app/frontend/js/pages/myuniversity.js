/* ==========================================================================
 * pages/myuniversity.js — кабинет представителя университета.
 *
 * Одна сущность льготы — правило: олимпиада + сезон + профиль + тип льготы +
 * результат + документ университета. Отдельной заявки БВИ больше нет: БВИ —
 * это значение benefit_type. Требование ЕГЭ — необязательная часть правила.
 *
 * Представитель управляет только своим университетом. Олимпиады, сезоны и
 * профили он не создаёт, а запрашивает у администратора через очередь запросов.
 * ========================================================================== */

async function renderMyUniversity() {
    const page = document.getElementById('page');

    if (!store.canManageUniversity()) {
        renderForbidden('Нет доступа к управлению университетом',
            'Правила своего университета ведёт представитель, назначенный администратором.');
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
            'Администратор управляет всеми университетами в разделе «Администрирование».',
            `<a href="#/admin/universities" class="${UI.btn} ${UI.btnSecondary}">Университеты</a>`);
        return;
    }

    const [uniRes, benRes, docRes, progRes, reqRes] = await Promise.all([
        api.getUniversity(universityId),
        api.listUniversityBenefitRulesManage(universityId, { limit: 200 }).catch(() => ({ ok: false, data: null })),
        api.listUniversityDocs(universityId).catch(() => ({ ok: false, data: null })),
        api.listPrograms(universityId).catch(() => ({ ok: false, data: null })),
        api.listEntityRequests(universityId, { limit: 50 }).catch(() => ({ ok: false, data: null })),
    ]);
    if (!uniRes.ok || !uniRes.data) {
        page.innerHTML = emptyHtml('Университет не найден',
            'Обратитесь к администратору: привязка представителя, возможно, потеряна.');
        return;
    }

    const university = uniRes.data;
    const benefits = (benRes.ok && benRes.data && benRes.data.rules) || [];
    const docs = (docRes.ok && docRes.data && docRes.data.docs) || [];
    const programs = (progRes.ok && progRes.data && progRes.data.programs) || [];
    const requests = (reqRes.ok && reqRes.data && reqRes.data.requests) || [];

    page.innerHTML = `
    <section class="pt-2 pb-10 md:pb-12">
        <p class="${UI.eyebrow}">Представитель университета</p>
        <h1 class="mt-3 text-3xl md:text-4xl font-extrabold tracking-tight leading-[1.1]">
            ${escHtml(university.short_name || university.name)}
        </h1>
        ${university.short_name && university.short_name !== university.name
            ? `<p class="mt-3 text-lg text-ink-soft leading-snug">${escHtml(university.name)}</p>`
            : ''}
        <p class="mt-6 text-lg text-ink-soft leading-relaxed max-w-2xl">
            Ведите правила льгот: олимпиада, сезон, профиль, тип льготы и документ-основание.
            Непроверенные правила видны в каталоге с пометкой «Не проверено Papaya».
        </p>
        <p class="mt-6"><a href="#/universities/${escAttr(university.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Открыть страницу университета</a></p>
    </section>

    <section class="mb-16 md:mb-24" aria-labelledby="my-benefits-title">
        <div class="flex flex-wrap items-center justify-between gap-6">
            <h2 id="my-benefits-title" class="text-2xl font-extrabold tracking-tight">Правила льгот (${benefits.length})</h2>
            <div class="flex flex-wrap gap-3">
                <button type="button" id="benefit-bulk" class="${UI.btn} ${UI.btnSecondary}">Привязать ко всем РСОШ</button>
                <button type="button" id="benefit-add" class="${UI.btn} ${UI.btnPrimary}">Добавить правило</button>
            </div>
        </div>
        <div id="my-benefits-list" class="mt-10"></div>
    </section>

    <section class="mb-16 md:mb-24" aria-labelledby="my-docs-title">
        <div class="flex flex-wrap items-center justify-between gap-6">
            <h2 id="my-docs-title" class="text-2xl font-extrabold tracking-tight">Документы университета (${docs.length})</h2>
            <button type="button" id="doc-add" class="${UI.btn} ${UI.btnPrimary}">Загрузить документ</button>
        </div>
        <p class="mt-4 text-sm text-ink-soft leading-relaxed max-w-2xl">
            Приказ или положение университета — основание льготы. Подтвердить правило
            можно только по документу типа «Приказ университета».
        </p>
        <div id="my-docs-list" class="mt-10"></div>
    </section>

    <section class="mb-16 md:mb-24" aria-labelledby="my-programs-title">
        <div class="flex flex-wrap items-center justify-between gap-6">
            <h2 id="my-programs-title" class="text-2xl font-extrabold tracking-tight">Образовательные программы (${programs.length})</h2>
            <button type="button" id="program-add" class="${UI.btn} ${UI.btnPrimary}">Добавить программу</button>
        </div>
        <div id="my-programs-list" class="mt-10"></div>
    </section>

    <section class="mb-16 md:mb-24" aria-labelledby="my-requests-title">
        <div class="flex flex-wrap items-center justify-between gap-6">
            <h2 id="my-requests-title" class="text-2xl font-extrabold tracking-tight">Запросы в каталог (${requests.length})</h2>
            <button type="button" id="request-add" class="${UI.btn} ${UI.btnSecondary}">Запросить добавление</button>
        </div>
        <p class="mt-4 text-sm text-ink-soft leading-relaxed max-w-2xl">
            Если олимпиады, сезона или профиля нет в каталоге, опишите их здесь.
            Администратор проверит дубли и создаст сущность.
        </p>
        <div id="my-requests-list" class="mt-10"></div>
    </section>`;

    drawMyBenefitsList(benefits, universityId, docs);
    drawMyDocsList(docs, universityId);
    drawMyProgramsList(programs, universityId);
    drawMyRequestsList(requests);

    document.getElementById('benefit-add').addEventListener('click', () =>
        openBenefitFormModal(universityId, null, docs, () => renderMyUniversity()));
    document.getElementById('benefit-bulk').addEventListener('click', () =>
        openBulkBenefitModal(universityId, docs, () => renderMyUniversity()));
    document.getElementById('doc-add').addEventListener('click', () =>
        openDocUploadModal(universityId, () => renderMyUniversity()));
    document.getElementById('program-add').addEventListener('click', () =>
        openProgramFormModal(universityId, null, () => renderMyUniversity()));
    document.getElementById('request-add').addEventListener('click', () =>
        openEntityRequestModal(universityId, () => renderMyUniversity()));
}

/* ----------------------------- Правила льгот ------------------------------ */

function benefitPublishedBadge(rule) {
    if (rule.is_published) {
        return `<span class="${UI.badge} ${UI.badgeSuccess}">Опубликовано</span>`;
    }
    return `<span class="${UI.badge} ${UI.badgeNeutral}">Скрыто из каталога</span>`;
}

function ruleContextLine(rule) {
    const parts = [];
    if (rule.olympiad_name) parts.push(rule.olympiad_name);
    if (rule.season_label) parts.push(rule.season_label);
    if (rule.profile_name) {
        parts.push(rule.profile_rsosh_level
            ? `${rule.profile_name} · уровень РСОШ ${rule.profile_rsosh_level}`
            : rule.profile_name);
    }
    return parts.join(' · ');
}

function drawMyBenefitsList(rules, universityId, docs) {
    const box = document.getElementById('my-benefits-list');
    if (!box) return;

    if (!rules.length) {
        box.innerHTML = emptyHtml('Правил льгот пока нет',
            'Добавьте правило: олимпиада, сезон, профиль, условия и документ-основание.');
        return;
    }

    const docNames = new Map((docs || []).map(item => [String(item.id), item.name]));
    box.innerHTML = `<div class="space-y-6">` + rules.map(item => {
        const docName = item.doc_id ? docNames.get(String(item.doc_id)) : '';
        const ege = item.ege_requirement
            ? `ЕГЭ: ${item.ege_requirement.subject}${item.ege_requirement.min_score != null ? `, от ${item.ege_requirement.min_score}` : ''}`
            : '';
        return `
        <article class="${UI.card} rounded-lg px-8 py-7">
            <div class="flex flex-col lg:flex-row lg:items-start gap-6">
                <div class="flex-1 min-w-0">
                    <p class="font-bold text-ink leading-snug">
                        ${escHtml(benefitTypeLabel(item.benefit_type))} · ${escHtml(benefitResultText(item.required_result_type))}
                    </p>
                    <p class="mt-2 text-sm text-ink-soft leading-relaxed">${escHtml(ruleContextLine(item))}</p>
                    <div class="mt-3 flex items-center gap-3 flex-wrap">
                        ${benefitStatusBadge(item.verification_status)}
                        ${benefitPublishedBadge(item)}
                        ${item.needs_review ? `<span class="${UI.badge} ${UI.badgeDanger}">Нужно заполнить</span>` : ''}
                        <span class="${UI.badge} ${UI.badgeNeutral}">Версия ${escHtml(item.version)}</span>
                    </div>
                    ${ege ? `<p class="mt-4 text-sm text-ink-soft">${escHtml(ege)}</p>` : ''}
                    ${item.rejection_reason ? `<p class="mt-3 text-sm text-danger">Причина отказа: ${escHtml(item.rejection_reason)}</p>` : ''}
                    ${docName ? `<p class="mt-3 text-sm text-ink-faint">Документ: ${escHtml(docName)}</p>` : ''}
                    ${!item.doc_id ? '<p class="mt-3 text-sm text-danger">Не выбран документ-основание: подтверждение невозможно.</p>' : ''}
                </div>
                <div class="flex flex-wrap lg:flex-col gap-3 shrink-0">
                    <button type="button" data-benefit-edit="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Редактировать</button>
                    <button type="button" data-benefit-publish="${escAttr(item.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">${item.is_published ? 'Скрыть из каталога' : 'Опубликовать'}</button>
                    <button type="button" data-benefit-history="${escAttr(item.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">История версий</button>
                </div>
            </div>
        </article>`;
    }).join('') + `</div>`;

    const byId = new Map(rules.map(item => [String(item.id), item]));
    box.querySelectorAll('[data-benefit-edit]').forEach(btn => {
        btn.addEventListener('click', () => {
            const rule = byId.get(String(btn.dataset.benefitEdit));
            if (rule) openBenefitFormModal(universityId, rule, docs, () => renderMyUniversity());
        });
    });
    box.querySelectorAll('[data-benefit-publish]').forEach(btn => {
        btn.addEventListener('click', async () => {
            const rule = byId.get(String(btn.dataset.benefitPublish));
            if (!rule) return;
            btn.disabled = true;
            const res = await api.updateBenefit(rule.id, {
                is_published: !rule.is_published,
                version: rule.version,
            });
            if (res.ok) {
                showToast(rule.is_published ? 'Правило скрыто из каталога' : 'Правило опубликовано', 'success');
                renderMyUniversity();
                return;
            }
            btn.disabled = false;
            showToast(errorText(res), 'error');
        });
    });
    box.querySelectorAll('[data-benefit-history]').forEach(btn => {
        btn.addEventListener('click', () => {
            const rule = byId.get(String(btn.dataset.benefitHistory));
            if (rule) openBenefitHistoryModal(rule, () => renderMyUniversity());
        });
    });
}

function setSelectOptions(select, options, selected) {
    if (!select) return;
    select.innerHTML = options.map(item => `
        <option value="${escAttr(item.value)}" ${String(item.value) === String(selected || '') ? 'selected' : ''}>
            ${escHtml(item.label)}
        </option>`).join('');
}

function universityOrderDocs(docs) {
    return (docs || []).filter(item => item.type === 'UNIVERSITY_ORDER');
}

async function openBenefitFormModal(universityId, rule, docs, onDone, options = {}) {
    // Администратор создаёт правило для любого вуза: в форме появляется выбор
    // университета, а документы-основания подгружаются для выбранного вуза.
    const adminMode = !!options.admin;
    const isEdit = !!rule;
    const universities = adminMode
        ? await loadAdminUniversityOptions()
        : [];
    if (adminMode && isEdit && rule.university_id
        && !universities.some(item => String(item.id) === String(rule.university_id))) {
        universities.unshift({
            id: rule.university_id,
            name: rule.university_name || 'Текущий университет',
            short_name: rule.university_short_name || '',
        });
    }
    let selectedUniversityId = rule ? rule.university_id : universityId;
    if (!selectedUniversityId && adminMode) {
        selectedUniversityId = (universities[0] || {}).id || '';
    }
    if (adminMode && !selectedUniversityId) {
        showToast('Сначала создайте университет', 'error');
        return;
    }

    const loadOrderDocs = async id => {
        if (!id) return [];
        const res = await api.listUniversityDocs(id).catch(() => null);
        return universityOrderDocs((res && res.ok && res.data && res.data.docs) || []);
    };
    let documents = adminMode ? await loadOrderDocs(selectedUniversityId) : universityOrderDocs(docs);

    const [olyRes, progRes] = await Promise.all([
        api.listOlympiads(''),
        selectedUniversityId
            ? api.listPrograms(selectedUniversityId)
            : Promise.resolve({ ok: false, data: null }),
    ]);
    if (!olyRes.ok) {
        showToast(errorText(olyRes), 'error');
        return;
    }

    const olympiads = (olyRes.data.olympiads || []).slice();
    if (rule && rule.olympiad_id && !olympiads.some(item => String(item.id) === String(rule.olympiad_id))) {
        olympiads.unshift({ id: rule.olympiad_id, name: rule.olympiad_name || 'Текущая олимпиада' });
    }
    let programs = (progRes.ok && progRes.data && progRes.data.programs) || [];
    const isEditMode = isEdit;

    const initialOlympiad = rule ? rule.olympiad_id : (olympiads[0] || {}).id;
    let seasons = [];
    let profiles = [];
    if (initialOlympiad) {
        const res = await api.listSeasons(initialOlympiad, { include_archived: true });
        seasons = (res.ok && res.data && res.data.seasons) || [];
    }
    // Профили грузим сразу для того сезона, который будет выбран в форме:
    // иначе при создании правила сезон уже выбран, а список профилей пуст.
    const initialSeason = rule
        ? rule.season_id
        : ((seasons[0] || {}).id || '');
    if (initialSeason) {
        const res = await api.listProfiles(initialSeason);
        profiles = (res.ok && res.data && res.data.profiles) || [];
    }

    const docOptions = () => documents.map(item => ({ value: item.id, label: item.name }));
    const programsHtml = () => programs.length
        ? `<div class="grid sm:grid-cols-2 gap-2 mt-2">${programs.map(item => `
            <p class="text-sm text-ink leading-snug">${escHtml(item.name)}</p>`).join('')}</div>
            <p class="mt-3 text-xs text-ink-faint">Программы — самостоятельный справочник вуза; правило на них не ссылается.</p>`
        : '<p class="mt-2 text-sm text-ink-soft">Программы не заведены. Их можно добавить на странице университета.</p>';
    const docHintHtml = () => documents.length
        ? ''
        : '<p class="mb-6 text-sm text-danger">У выбранного вуза нет приказа UNIVERSITY_ORDER: без него правило нельзя подтвердить.</p>';
    const universityName = adminMode
        ? (universities.find(item => String(item.id) === String(selectedUniversityId)) || {})
        : {};
    const universityField = adminMode
        ? (isEditMode
            ? `<p class="mb-6 text-sm text-ink-soft">Университет: <span class="font-semibold text-ink">${escHtml(universityName.short_name || universityName.name || rule.university_name || 'текущий')}</span></p>`
            : selectField({
                id: 'benefit-university',
                name: 'university_id',
                label: 'Университет',
                options: universities.map(item => ({
                    value: item.id,
                    label: item.short_name || item.name,
                })),
                value: selectedUniversityId,
            }))
        : '';

    const body = `
        <div id="modal-alert"></div>
        <form id="benefit-form">
            ${universityField}
            ${selectField({
                id: 'benefit-olympiad',
                name: 'olympiad_id',
                label: 'Олимпиада',
                options: olympiads.map(item => ({ value: item.id, label: item.name })),
                value: initialOlympiad,
            })}
            ${selectField({
                id: 'benefit-season',
                name: 'season_id',
                label: 'Сезон',
                options: seasons.map(item => ({
                    value: item.id,
                    label: `${item.season_label}${item.is_archived ? ' (архив)' : ''}`,
                })),
                value: initialSeason,
            })}
            ${selectField({
                id: 'benefit-profile',
                name: 'profile_id',
                label: 'Профиль сезона',
                options: profiles.map(item => ({
                    value: item.id,
                    label: item.rsosh_level ? `${item.name} · уровень ${item.rsosh_level}` : item.name,
                })),
                value: rule ? (rule.profile_id || '') : '',
            })}
            ${selectField({
                id: 'benefit-type',
                name: 'benefit_type',
                label: 'Тип льготы',
                options: Object.entries(BENEFIT_TYPE_LABELS).map(([value, label]) => ({ value, label })),
                value: rule ? rule.benefit_type : 'BVI',
            })}
            ${selectField({
                id: 'benefit-result-type',
                name: 'required_result_type',
                label: 'Требуемый результат',
                options: Object.entries(BENEFIT_RESULT_LABELS).map(([value, label]) => ({ value, label })),
                value: rule ? (rule.required_result_type || 'WINNER_OR_PRIZE') : 'WINNER_OR_PRIZE',
            })}
            ${selectField({
                id: 'benefit-doc',
                name: 'doc_id',
                label: 'Документ-основание (приказ университета)',
                options: docOptions(),
                value: rule ? (rule.doc_id || '') : '',
            })}
            <div id="benefit-doc-hint">${docHintHtml()}</div>
            <fieldset class="mb-6 rounded border border-lineStrong px-5 py-5">
                <legend class="px-2 text-sm font-semibold text-ink">Требование ЕГЭ (необязательно)</legend>
                <div class="grid sm:grid-cols-2 gap-4">
                    ${inputField({ id: 'benefit-ege-subject', name: 'ege_subject', label: 'Предмет ЕГЭ', value: rule && rule.ege_requirement ? rule.ege_requirement.subject : '', placeholder: 'Математика' })}
                    ${inputField({ id: 'benefit-ege-score', name: 'ege_min_score', label: 'Минимальный балл', type: 'number', value: rule && rule.ege_requirement && rule.ege_requirement.min_score != null ? rule.ege_requirement.min_score : '', placeholder: '75' })}
                </div>
            </fieldset>
            <div class="${UI.field}">
                <p class="${UI.label}">Образовательные программы</p>
                <div id="benefit-programs">${programsHtml()}</div>
            </div>
            <label class="flex items-start gap-3 text-sm text-ink mb-6">
                <input type="checkbox" name="is_published" class="mt-0.5" ${!rule || rule.is_published ? 'checked' : ''}>
                <span>Показывать в каталоге</span>
            </label>
            ${isEditMode ? inputField({ id: 'benefit-reason', name: 'change_reason', label: 'Причина изменения', value: adminMode ? 'Правка администратора' : 'Правка представителя университета' }) : ''}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">${isEditMode ? 'Сохранить' : 'Добавить правило'}</button>
            </div>
        </form>`;

    const { overlay, close } = openModal(
        isEditMode ? 'Редактирование правила льготы' : 'Новое правило льготы',
        body,
        { wide: true }
    );
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    const olympiadSelect = overlay.querySelector('#benefit-olympiad');
    const seasonSelect = overlay.querySelector('#benefit-season');
    const profileSelect = overlay.querySelector('#benefit-profile');
    const docSelect = overlay.querySelector('#benefit-doc');
    const universitySelect = overlay.querySelector('#benefit-university');

    async function loadSeasons(olympiadId, selected) {
        const res = await api.listSeasons(olympiadId, { include_archived: true });
        const options = ((res.ok && res.data && res.data.seasons) || []).map(item => ({
            value: item.id,
            label: `${item.season_label}${item.is_archived ? ' (архив)' : ''}`,
        }));
        // Сезон без явного выбора — первый в списке: профили должны появиться
        // сразу, а не после ручного переключения.
        const effective = selected && options.some(item => String(item.value) === String(selected))
            ? selected
            : ((options[0] || {}).value || '');
        setSelectOptions(seasonSelect, options, effective);
        await loadProfiles(effective, '');
    }
    async function loadProfiles(seasonId, selected) {
        let options = [];
        if (seasonId) {
            const res = await api.listProfiles(seasonId);
            options = ((res.ok && res.data && res.data.profiles) || []).map(item => ({
                value: item.id,
                label: item.rsosh_level ? `${item.name} · уровень ${item.rsosh_level}` : item.name,
            }));
        }
        setSelectOptions(profileSelect, options, selected || '');
    }

    olympiadSelect.addEventListener('change', () => loadSeasons(olympiadSelect.value, ''));
    seasonSelect.addEventListener('change', () => loadProfiles(seasonSelect.value, ''));

    if (universitySelect) {
        universitySelect.addEventListener('change', async () => {
            selectedUniversityId = universitySelect.value;
            documents = await loadOrderDocs(selectedUniversityId);
            setSelectOptions(docSelect, docOptions(), '');
            const hint = overlay.querySelector('#benefit-doc-hint');
            if (hint) hint.innerHTML = docHintHtml();
            const res = await api.listPrograms(selectedUniversityId);
            programs = (res.ok && res.data && res.data.programs) || [];
            const box = overlay.querySelector('#benefit-programs');
            if (box) box.innerHTML = programsHtml();
        });
    }

    overlay.querySelector('#benefit-form').addEventListener('submit', async e => {
        e.preventDefault();
        const form = e.target;
        const fd = new FormData(form);
        const seasonId = (fd.get('season_id') || '').trim();
        const profileId = (fd.get('profile_id') || '').trim();
        const docId = (fd.get('doc_id') || '').trim();
        if (!seasonId || !profileId) {
            showModalError(overlay, { data: { detail: 'Выберите сезон и профиль сезона' } });
            return;
        }
        if (!docId) {
            showModalError(overlay, { data: { detail: 'Выберите документ-основание' } });
            return;
        }
        const egeSubject = (fd.get('ege_subject') || '').trim();
        const egeScore = (fd.get('ege_min_score') || '').trim();
        const payload = {
            season_id: seasonId,
            profile_id: profileId,
            benefit_type: fd.get('benefit_type') || 'BVI',
            required_result_type: fd.get('required_result_type'),
            doc_id: docId,
            ege_requirement: egeSubject
                ? { subject: egeSubject, min_score: egeScore ? Number(egeScore) : null }
                : null,
            is_published: fd.get('is_published') === 'on',
        };
        if (isEditMode) {
            payload.version = rule.version;
            payload.change_reason = (fd.get('change_reason') || '').trim() || null;
        } else {
            payload.olympiad_id = olympiadSelect.value;
        }

        const btn = form.querySelector('button[type="submit"]');
        btn.disabled = true;
        btn.textContent = 'Сохраняем…';
        const targetUniversityId = adminMode ? (universitySelect ? universitySelect.value : selectedUniversityId) : universityId;
        const res = isEditMode
            ? await api.updateBenefit(rule.id, payload)
            : await api.createBenefit(targetUniversityId, payload);
        if (res.ok) {
            close();
            showToast(isEditMode ? 'Правило обновлено' : 'Правило добавлено', 'success');
            if (onDone) onDone();
            return;
        }
        showModalError(overlay, res);
        btn.disabled = false;
        btn.textContent = isEditMode ? 'Сохранить' : 'Добавить правило';
    });
}

/** Массовая привязка: одно правило для всех олимпиад РСОШ сезона. */
async function openBulkBenefitModal(universityId, docs, onDone) {
    const orderDocs = universityOrderDocs(docs);
    if (!orderDocs.length) {
        showToast('Сначала загрузите приказ университета', 'error');
        return;
    }
    const initial = await api.bulkBenefitOptions(universityId);
    if (!initial.ok) {
        showToast(errorText(initial), 'error');
        return;
    }
    const labels = (initial.data && initial.data.season_labels) || [];
    if (!labels.length) {
        showToast('В каталоге пока нет сезонов олимпиад', 'error');
        return;
    }

    const body = `
        <div id="modal-alert"></div>
        <form id="bulk-benefit-form">
            <p class="text-sm text-ink-soft leading-relaxed">
                Одно правило будет создано для каждой олимпиады РСОШ выбранного
                сезона и уровня, у которой есть отмеченный профиль. Уже существующие
                правила не дублируются.
            </p>
            <div class="grid gap-4 sm:grid-cols-2 mt-6">
                ${selectField({
                    id: 'bulk-season',
                    name: 'season_label',
                    label: 'Учебный год',
                    options: labels.map(label => ({ value: label, label })),
                    value: labels[0],
                })}
                ${selectField({
                    id: 'bulk-level',
                    name: 'rsosh_level',
                    label: 'Уровень РСОШ',
                    options: [
                        { value: '', label: 'Все уровни' },
                        { value: '1', label: '1 уровень' },
                        { value: '2', label: '2 уровень' },
                        { value: '3', label: '3 уровень' },
                    ],
                    value: '',
                })}
                ${selectField({
                    id: 'bulk-doc',
                    name: 'doc_id',
                    label: 'Документ-основание',
                    options: orderDocs.map(item => ({ value: item.id, label: item.name })),
                    value: orderDocs[0] ? orderDocs[0].id : '',
                })}
                ${selectField({
                    id: 'bulk-type',
                    name: 'benefit_type',
                    label: 'Тип льготы',
                    options: Object.entries(BENEFIT_TYPE_LABELS).map(([value, label]) => ({ value, label })),
                    value: 'BVI',
                })}
                ${selectField({
                    id: 'bulk-result',
                    name: 'required_result_type',
                    label: 'Требуемый результат',
                    options: Object.entries(BENEFIT_RESULT_LABELS).map(([value, label]) => ({ value, label })),
                    value: 'WINNER_OR_PRIZE',
                })}
            </div>
            <div class="mt-6 flex flex-wrap items-center justify-between gap-3">
                <h3 class="text-lg font-bold tracking-tight text-ink">Профили сезона</h3>
                <button type="button" id="bulk-toggle-all" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Снять все</button>
            </div>
            <div id="bulk-profiles" class="mt-4">${loadingHtml('Загружаем профили…')}</div>
            <label class="flex items-start gap-3 text-sm text-ink mt-6">
                <input type="checkbox" name="is_published" checked class="mt-0.5">
                <span>Показывать в каталоге</span>
            </label>
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Привязать</button>
            </div>
        </form>`;
    const { overlay, close } = openModal(
        'Привязать льготу ко всем РСОШ',
        body,
        { size: 'xl' }
    );
    const seasonSelect = overlay.querySelector('#bulk-season');
    const levelSelect = overlay.querySelector('#bulk-level');
    const profilesBox = overlay.querySelector('#bulk-profiles');
    let profiles = [];

    const renderProfiles = () => {
        if (!profiles.length) {
            profilesBox.innerHTML = '<p class="text-sm text-ink-soft">В этом сезоне и уровне нет олимпиад с профилями.</p>';
            return;
        }
        profilesBox.innerHTML = `
            <div class="overflow-x-auto">
            <table class="w-full text-sm">
                <thead>
                    <tr class="text-left text-xs uppercase tracking-wide text-ink-faint border-b border-line">
                        <th class="py-2 pr-3">Профиль</th>
                        <th class="py-2 pr-3">Олимпиад</th>
                        <th class="py-2 pr-3">ЕГЭ: предмет</th>
                        <th class="py-2">Мин. балл</th>
                    </tr>
                </thead>
                <tbody>
                    ${profiles.map((item, index) => `
                    <tr class="border-b border-line/60 align-top">
                        <td class="py-3 pr-3">
                            <label class="flex items-start gap-2">
                                <input type="checkbox" data-bulk-profile="${index}" checked class="mt-1">
                                <span>
                                    <span class="font-semibold text-ink">${escHtml(item.name)}</span>
                                    ${item.levels && item.levels.length
                                        ? `<span class="block text-xs text-ink-faint">уровень РСОШ: ${escHtml(item.levels.join(', '))}</span>`
                                        : ''}
                                    ${item.existing
                                        ? `<span class="block text-xs text-ink-faint">уже есть правил: ${item.existing}</span>`
                                        : ''}
                                </span>
                            </label>
                        </td>
                        <td class="py-3 pr-3 text-ink-soft">${item.olympiads.length}</td>
                        <td class="py-3 pr-3">
                            <input data-bulk-ege-subject="${index}" class="${UI.input} !py-2" placeholder="Математика">
                        </td>
                        <td class="py-3">
                            <input data-bulk-ege-score="${index}" type="number" min="0" max="100" class="${UI.input} !py-2" placeholder="75">
                        </td>
                    </tr>`).join('')}
                </tbody>
            </table>
            </div>
            <p class="mt-3 text-xs text-ink-soft leading-relaxed">
                Предмет ЕГЭ заполняется отдельно для каждого профиля. Пустой
                предмет означает правило без требования ЕГЭ.
            </p>`;
    };

    let allChecked = true;
    const toggleAll = overlay.querySelector('#bulk-toggle-all');
    toggleAll.addEventListener('click', () => {
        allChecked = !allChecked;
        overlay.querySelectorAll('[data-bulk-profile]').forEach(box => {
            box.checked = allChecked;
        });
        toggleAll.textContent = allChecked ? 'Снять все' : 'Выбрать все';
    });

    const loadProfiles = async () => {
        profilesBox.innerHTML = loadingHtml('Загружаем профили…');
        const res = await api.bulkBenefitOptions(universityId, seasonSelect.value);
        if (!res.ok) {
            profilesBox.innerHTML = alertHtml(errorText(res), 'error');
            return;
        }
        profiles = (res.data && res.data.profiles) || [];
        renderProfiles();
    };
    seasonSelect.addEventListener('change', loadProfiles);
    await loadProfiles();

    overlay.querySelector('[data-cancel]').addEventListener('click', close);
    overlay.querySelector('#bulk-benefit-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const docId = (fd.get('doc_id') || '').trim();
        if (!docId) {
            showModalError(overlay, { data: { detail: 'Выберите документ-основание' } });
            return;
        }
        const items = [];
        profiles.forEach((item, index) => {
            const box = overlay.querySelector(`[data-bulk-profile="${index}"]`);
            if (!box || !box.checked) return;
            const subject = (overlay.querySelector(`[data-bulk-ege-subject="${index}"]`).value || '').trim();
            const score = (overlay.querySelector(`[data-bulk-ege-score="${index}"]`).value || '').trim();
            items.push({
                name: item.name,
                name_norm: item.name_norm,
                benefit_type: fd.get('benefit_type') || 'BVI',
                required_result_type: fd.get('required_result_type') || 'WINNER_OR_PRIZE',
                ege_requirement: subject
                    ? { subject, min_score: score ? Number(score) : null }
                    : null,
            });
        });
        if (!items.length) {
            showModalError(overlay, { data: { detail: 'Отметьте хотя бы один профиль' } });
            return;
        }
        const btn = e.target.querySelector('button[type="submit"]');
        btn.disabled = true;
        btn.textContent = 'Создаём…';
        const res = await api.bulkCreateBenefits(universityId, {
            season_label: fd.get('season_label'),
            doc_id: docId,
            is_published: fd.get('is_published') === 'on',
            items,
        });
        if (res.ok) {
            close();
            const created = (res.data && res.data.created ? res.data.created.length : 0);
            const skipped = (res.data && res.data.skipped) || 0;
            showToast(`Создано правил: ${created}. Пропущено уже существующих: ${skipped}.`, 'success', 6000);
            if (onDone) onDone();
            return;
        }
        showModalError(overlay, res);
        btn.disabled = false;
        btn.textContent = 'Привязать';
    });
}

/** Университеты для административной формы правила. */
async function loadAdminUniversityOptions() {
    const res = await api.adminUniversities({ limit: 200 });
    if (!res.ok) {
        showToast(errorText(res), 'error');
        return [];
    }
    return ((res.data && res.data.universities) || []).slice().map(item => ({
        id: item.id,
        name: item.name,
        short_name: item.short_name || '',
    }));
}

async function openBenefitHistoryModal(rule, onDone) {
    const [versionsRes, historyRes] = await Promise.all([
        api.benefitVersionsManage(rule.id),
        api.benefitStatusHistoryManage(rule.id).catch(() => ({ ok: false, data: null })),
    ]);
    if (!versionsRes.ok) {
        showToast(errorText(versionsRes), 'error');
        return;
    }

    const versions = (versionsRes.data.versions || []).slice().reverse();
    const history = (historyRes.ok && historyRes.data && historyRes.data.history) || [];
    const historyHtml = history.length
        ? history.slice().reverse().map(item => `
            <li class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-mist pb-3">
                <span class="text-sm text-ink">${escHtml(item.from_status || '—')} → ${escHtml(item.to_status)}</span>
                <span class="text-xs text-ink-faint">${escHtml(formatDate(item.changed_at))}${item.reason ? ` · ${escHtml(item.reason)}` : ''}</span>
            </li>`).join('')
        : '<li class="text-sm text-ink-soft">История статусов пока пуста.</li>';

    const body = `
        <div class="space-y-8">
            <div>
                <p class="${UI.eyebrow}">Версии правила</p>
                <div class="mt-4 space-y-4">
                    ${versions.length ? versions.map(item => {
                        const snap = item.snapshot || {};
                        const changed = (item.changed_fields || []).join(', ');
                        return `<div class="${UI.card} rounded px-6 py-5 flex flex-col sm:flex-row sm:items-center gap-4">
                            <div class="flex-1 min-w-0">
                                <p class="font-semibold text-ink">Версия ${escHtml(item.version_number)}</p>
                                <p class="mt-1 text-sm text-ink-soft">${escHtml(benefitTypeLabel(snap.benefit_type))}${snap.required_result_type ? ` · ${escHtml(benefitResultText(snap))}` : ''}</p>
                                <p class="mt-1 text-xs text-ink-faint">${escHtml(formatDate(item.changed_at))}${changed ? ` · изменено: ${escHtml(changed)}` : ''}</p>
                            </div>
                            <button type="button" data-rollback="${escAttr(item.version_number)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Восстановить</button>
                        </div>`;
                    }).join('') : '<p class="text-sm text-ink-soft">Версий пока нет.</p>'}
                </div>
            </div>
            <div>
                <p class="${UI.eyebrow}">История проверки</p>
                <ul class="mt-4 space-y-3">${historyHtml}</ul>
            </div>
            <div class="flex justify-end">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Закрыть</button>
            </div>
        </div>`;
    const { overlay, close } = openModal('История правила льготы', body, { wide: true });
    overlay.querySelector('[data-cancel]').addEventListener('click', close);
    overlay.querySelectorAll('[data-rollback]').forEach(btn => {
        btn.addEventListener('click', async () => {
            const version = Number(btn.dataset.rollback);
            if (!window.confirm(`Восстановить версию ${version}? Текущая редакция сохранится в истории, а правило снова потребует проверки.`)) {
                return;
            }
            btn.disabled = true;
            const res = await api.rollbackBenefit(rule.id, version, rule.version);
            if (res.ok) {
                close();
                showToast('Версия восстановлена', 'success');
                if (onDone) onDone();
                return;
            }
            btn.disabled = false;
            showToast(errorText(res), 'error');
        });
    });
}

/* ------------------------- Документы университета ------------------------- */

function drawMyDocsList(docs, universityId) {
    const box = document.getElementById('my-docs-list');
    if (!box) return;
    if (!docs.length) {
        box.innerHTML = emptyHtml('Документов пока нет',
            'Загрузите приказ или положение университета — его можно приложить к правилу льготы.');
        return;
    }
    box.innerHTML = `<div class="space-y-4">` + docs.map(item => `
        <article class="${UI.card} rounded px-8 py-6 flex flex-col lg:flex-row lg:items-center gap-5">
            <div class="flex-1 min-w-0">
                <p class="font-bold text-ink leading-snug">${escHtml(item.name)}</p>
                <p class="mt-2 text-sm text-ink-soft">${escHtml(docTypeLabel(item.type))} · ${escHtml(item.status || 'UPLOADED')}</p>
                ${item.source_url ? `<p class="mt-1 text-sm"><a href="${escAttr(item.source_url)}" target="_blank" rel="noopener noreferrer" class="underline text-brand-strong">Оригинал</a></p>` : ''}
            </div>
            <div class="flex flex-wrap gap-3 shrink-0">
                <a href="${escAttr(api.docFileUrl(item.id))}" target="_blank" rel="noopener noreferrer" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Скачать</a>
                <button type="button" data-doc-edit="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Изменить</button>
            </div>
        </article>`).join('') + `</div>`;

    const byId = new Map(docs.map(item => [String(item.id), item]));
    box.querySelectorAll('[data-doc-edit]').forEach(btn => {
        btn.addEventListener('click', () => {
            const doc = byId.get(String(btn.dataset.docEdit));
            if (doc) openDocEditModal(universityId, doc, () => renderMyUniversity());
        });
    });
}

function openDocUploadModal(universityId, onDone) {
    let dirty = false;
    const body = `
        <div id="modal-alert"></div>
        <form id="doc-upload-form">
            <div class="${UI.field}">
                <label for="doc-file" class="${UI.label}">Файл <span class="text-danger" aria-hidden="true">*</span></label>
                <input id="doc-file" name="file" type="file" required accept=".pdf,.xlsx,.png,.jpg,.jpeg"
                       class="block w-full cursor-pointer text-sm text-ink-soft file:mr-4 file:rounded file:px-5 file:py-2.5 file:text-sm file:font-semibold file:bg-brand file:text-white hover:file:bg-brand-strong">
                <p class="mt-2 text-sm text-ink-soft">PDF, XLSX, PNG или JPG.</p>
            </div>
            ${inputField({ id: 'doc-name', name: 'name', label: 'Название документа', placeholder: 'Приказ о льготах 2026', required: true })}
            ${selectField({
                id: 'doc-type',
                name: 'type',
                label: 'Тип документа',
                options: [
                    { value: 'UNIVERSITY_ORDER', label: 'Приказ университета' },
                    { value: 'OTHER', label: 'Другой документ' },
                ],
                value: 'UNIVERSITY_ORDER',
            })}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Загрузить</button>
            </div>
        </form>`;
    const { overlay, close } = openModal('Документ университета', body, { isDirty: () => dirty });
    ['input', 'change'].forEach(ev => overlay.addEventListener(ev, () => { dirty = true; }));
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    overlay.querySelector('#doc-upload-form').addEventListener('submit', async e => {
        e.preventDefault();
        const form = e.target;
        const fd = new FormData(form);
        if (!fd.get('name')) fd.set('name', (fd.get('file') || {}).name || 'Документ');
        const btn = form.querySelector('button[type="submit"]');
        btn.disabled = true;
        btn.textContent = 'Загружаем…';
        const res = await api.uploadUniversityDoc(universityId, fd);
        if (res.ok) {
            dirty = false;
            close();
            showToast('Документ загружен', 'success');
            if (onDone) onDone();
            return;
        }
        showModalError(overlay, res);
        btn.disabled = false;
        btn.textContent = 'Загрузить';
    });
}

function openDocEditModal(universityId, doc, onDone) {
    const body = `
        <div id="modal-alert"></div>
        <form id="doc-edit-form">
            ${inputField({ id: 'doc-edit-name', name: 'name', label: 'Название документа', required: true, value: doc.name || '' })}
            ${selectField({
                id: 'doc-edit-type',
                name: 'type',
                label: 'Тип документа',
                options: [
                    { value: 'UNIVERSITY_ORDER', label: 'Приказ университета' },
                    { value: 'OTHER', label: 'Другой документ' },
                ],
                value: doc.type === 'OTHER' ? 'OTHER' : 'UNIVERSITY_ORDER',
            })}
            ${textareaField({ id: 'doc-edit-note', name: 'note', label: 'Заметка', value: doc.note || '' })}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Сохранить</button>
            </div>
        </form>`;
    const { overlay, close } = openModal('Редактирование документа', body);
    overlay.querySelector('[data-cancel]').addEventListener('click', close);
    overlay.querySelector('#doc-edit-form').addEventListener('submit', async e => {
        e.preventDefault();
        const form = e.target;
        const fd = new FormData(form);
        const payload = {
            name: (fd.get('name') || '').trim(),
            type: fd.get('type') || 'OTHER',
            note: (fd.get('note') || '').trim() || null,
        };
        const btn = form.querySelector('button[type="submit"]');
        btn.disabled = true;
        btn.textContent = 'Сохраняем…';
        const res = await api.updateUniversityDoc(universityId, doc.id, payload);
        if (res.ok) {
            close();
            showToast('Документ обновлён', 'success');
            if (onDone) onDone();
            return;
        }
        showModalError(overlay, res);
        btn.disabled = false;
        btn.textContent = 'Сохранить';
    });
}

/* ------------------------------- Программы -------------------------------- */

function drawMyProgramsList(programs, universityId) {
    const box = document.getElementById('my-programs-list');
    if (!box) return;
    if (!programs.length) {
        box.innerHTML = emptyHtml('Программ пока нет',
            'Добавьте направления вуза: они помогают школьнику понять, куда действует льгота.');
        return;
    }
    box.innerHTML = `<div class="space-y-4">` + programs.map(item => `
        <article class="${UI.card} rounded px-8 py-5 flex flex-col lg:flex-row lg:items-center gap-4">
            <div class="flex-1 min-w-0">
                <p class="font-semibold text-ink leading-snug">${escHtml(item.name)}</p>
                <p class="mt-1 text-sm text-ink-soft">${escHtml(item.code || 'Код не указан')}${item.is_archived ? ' · архив' : ''}</p>
            </div>
            <div class="flex flex-wrap gap-3 shrink-0">
                <button type="button" data-program-edit="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Изменить</button>
                <button type="button" data-program-archive="${escAttr(item.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">${item.is_archived ? 'Вернуть' : 'В архив'}</button>
            </div>
        </article>`).join('') + `</div>`;

    const byId = new Map(programs.map(item => [String(item.id), item]));
    box.querySelectorAll('[data-program-edit]').forEach(btn => {
        btn.addEventListener('click', () => {
            const program = byId.get(String(btn.dataset.programEdit));
            if (program) openProgramFormModal(universityId, program, () => renderMyUniversity());
        });
    });
    box.querySelectorAll('[data-program-archive]').forEach(btn => {
        btn.addEventListener('click', async () => {
            const program = byId.get(String(btn.dataset.programArchive));
            if (!program) return;
            btn.disabled = true;
            const res = await api.archiveUniversityProgram(universityId, program.id, !program.is_archived);
            if (res.ok) {
                showToast(program.is_archived ? 'Программа возвращена' : 'Программа в архиве', 'success');
                renderMyUniversity();
                return;
            }
            btn.disabled = false;
            showToast(errorText(res), 'error');
        });
    });
}

function openProgramFormModal(universityId, program, onDone) {
    const isEdit = !!program;
    const body = `
        <div id="modal-alert"></div>
        <form id="program-form">
            ${inputField({ id: 'program-name', name: 'name', label: 'Название программы', required: true, value: program ? program.name : '', placeholder: 'Прикладная математика и информатика' })}
            ${inputField({ id: 'program-code', name: 'code', label: 'Код', value: program ? (program.code || '') : '', placeholder: '01.03.02' })}
            ${textareaField({ id: 'program-description', name: 'description', label: 'Описание', value: program ? (program.description || '') : '' })}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">${isEdit ? 'Сохранить' : 'Добавить'}</button>
            </div>
        </form>`;
    const { overlay, close } = openModal(isEdit ? 'Редактирование программы' : 'Новая программа', body);
    overlay.querySelector('[data-cancel]').addEventListener('click', close);
    overlay.querySelector('#program-form').addEventListener('submit', async e => {
        e.preventDefault();
        const form = e.target;
        const fd = new FormData(form);
        const payload = {
            name: (fd.get('name') || '').trim(),
            code: (fd.get('code') || '').trim() || null,
            description: (fd.get('description') || '').trim() || null,
        };
        if (isEdit) payload.version = program.version;
        const btn = form.querySelector('button[type="submit"]');
        btn.disabled = true;
        btn.textContent = 'Сохраняем…';
        const res = isEdit
            ? await api.updateProgram(program.id, payload)
            : await api.createProgram(universityId, payload);
        if (res.ok) {
            close();
            showToast(isEdit ? 'Программа обновлена' : 'Программа добавлена', 'success');
            if (onDone) onDone();
            return;
        }
        showModalError(overlay, res);
        btn.disabled = false;
        btn.textContent = isEdit ? 'Сохранить' : 'Добавить';
    });
}

/* ------------------------- Запросы в каталог ------------------------------ */

const REQUEST_STATUS_LABELS = {
    pending: 'Ждёт проверки',
    approved: 'Одобрен',
    rejected: 'Отклонён',
};

const ENTITY_TYPE_LABELS = {
    OLYMPIAD: 'Олимпиада',
    SEASON: 'Сезон',
    PROFILE: 'Профиль',
};

function drawMyRequestsList(requests) {
    const box = document.getElementById('my-requests-list');
    if (!box) return;
    if (!requests.length) {
        box.innerHTML = emptyHtml('Запросов нет',
            'Если нужной олимпиады, сезона или профиля нет — запросите добавление.');
        return;
    }
    box.innerHTML = `<div class="space-y-4">` + requests.map(item => `
        <article class="${UI.card} rounded px-8 py-5">
            <div class="flex flex-col lg:flex-row lg:items-start gap-4">
                <div class="flex-1 min-w-0">
                    <p class="font-semibold text-ink">${escHtml(item.name)}</p>
                    <p class="mt-1 text-sm text-ink-soft">${escHtml(ENTITY_TYPE_LABELS[item.entity_type] || item.entity_type)}</p>
                    ${item.description ? `<p class="mt-2 text-sm text-ink-soft">${escHtml(item.description)}</p>` : ''}
                    ${item.rejection_reason ? `<p class="mt-2 text-sm text-danger">Причина отказа: ${escHtml(item.rejection_reason)}</p>` : ''}
                </div>
                <span class="${UI.badge} ${item.status === 'approved' ? UI.badgeSuccess : (item.status === 'rejected' ? UI.badgeDanger : UI.badgePending)}">
                    ${escHtml(REQUEST_STATUS_LABELS[item.status] || item.status)}
                </span>
            </div>
        </article>`).join('') + `</div>`;
}

async function openEntityRequestModal(universityId, onDone) {
    const olyRes = await api.listOlympiads('');
    const olympiads = (olyRes.ok && olyRes.data && olyRes.data.olympiads) || [];

    const body = `
        <div id="modal-alert"></div>
        <form id="request-form">
            ${selectField({
                id: 'request-type',
                name: 'entity_type',
                label: 'Что добавить',
                options: Object.entries(ENTITY_TYPE_LABELS).map(([value, label]) => ({ value, label })),
                value: 'OLYMPIAD',
            })}
            ${inputField({ id: 'request-name', name: 'name', label: 'Название', required: true, placeholder: 'Олимпиада «…» / 2026/2027 / Профиль «…»' })}
            <div id="request-parent-wrap" class="hidden">
                ${selectField({
                    id: 'request-parent',
                    name: 'parent_id',
                    label: 'Родительская сущность',
                    options: olympiads.map(item => ({ value: item.id, label: item.name })),
                    value: '',
                })}
            </div>
            <div id="request-season-wrap" class="hidden">
                ${selectField({
                    id: 'request-season',
                    name: 'season_for_profile',
                    label: 'Сезон',
                    options: [],
                    value: '',
                })}
            </div>
            ${inputField({ id: 'request-level', name: 'rsosh_level', label: 'Уровень РСОШ профиля (если известен)', placeholder: '1, 2, 3' })}
            ${textareaField({ id: 'request-description', name: 'description', label: 'Пояснение', placeholder: 'Ссылка на официальный документ или страницу' })}
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Отправить запрос</button>
            </div>
        </form>`;

    const { overlay, close } = openModal('Запрос на добавление в каталог', body);
    overlay.querySelector('[data-cancel]').addEventListener('click', close);
    const typeSelect = overlay.querySelector('#request-type');
    const parentWrap = overlay.querySelector('#request-parent-wrap');
    const parentSelect = overlay.querySelector('#request-parent');
    const seasonWrap = overlay.querySelector('#request-season-wrap');
    const seasonSelect = overlay.querySelector('#request-season');
    const levelInput = overlay.querySelector('#request-level');

    async function refreshType() {
        const type = typeSelect.value;
        parentWrap.classList.toggle('hidden', type !== 'SEASON');
        seasonWrap.classList.toggle('hidden', type !== 'PROFILE');
        levelInput.parentElement.classList.toggle('hidden', type !== 'PROFILE');
        if (type === 'PROFILE' && parentSelect.value) {
            const res = await api.listSeasons(parentSelect.value, { include_archived: true });
            const seasons = (res.ok && res.data && res.data.seasons) || [];
            setSelectOptions(seasonSelect,
                seasons.map(item => ({ value: item.id, label: item.season_label })), '');
        }
    }
    typeSelect.addEventListener('change', refreshType);
    parentSelect.addEventListener('change', refreshType);
    refreshType();

    overlay.querySelector('#request-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const type = fd.get('entity_type');
        let parentId = null;
        if (type === 'SEASON') parentId = parentSelect.value || null;
        if (type === 'PROFILE') {
            parentId = seasonSelect.value || null;
            const olympiadId = parentSelect.value;
            if (olympiadId) {
                await api.listSeasons(olympiadId, { include_archived: true });
            }
        }
        const payload = {
            entity_type: type,
            name: (fd.get('name') || '').trim(),
            description: (fd.get('description') || '').trim() || null,
            parent_id: parentId,
            payload: {},
        };
        const level = (fd.get('rsosh_level') || '').trim();
        if (type === 'PROFILE' && level) payload.payload.rsosh_level = level;
        const btn = e.target.querySelector('button[type="submit"]');
        btn.disabled = true;
        btn.textContent = 'Отправляем…';
        const res = await api.createEntityRequest(universityId, payload);
        if (res.ok) {
            close();
            showToast('Запрос отправлен администратору', 'success');
            if (onDone) onDone();
            return;
        }
        showModalError(overlay, res);
        btn.disabled = false;
        btn.textContent = 'Отправить запрос';
    });
}
