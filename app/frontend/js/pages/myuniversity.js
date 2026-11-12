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

    const [uniRes, olyRes, benRes, docRes, srcRes] = await Promise.all([
        api.getUniversity(universityId),
        api.getUniversityOlympiads(universityId, true),
        api.listUniversityBenefitRulesManage(universityId).catch(() => ({ ok: false, data: null })),
        api.listUniversityDocs(universityId).catch(() => ({ ok: false, data: null })),
        api.listUniversitySources(universityId).catch(() => ({ ok: false, data: null })),
    ]);
    if (!uniRes.ok || !uniRes.data) {
        page.innerHTML = emptyHtml('Университет не найден',
            'Обратитесь к администратору: привязка представителя, возможно, потеряна.');
        return;
    }

    const university = uniRes.data;
    const linked = (olyRes.ok && olyRes.data && olyRes.data.olympiads) || [];
    const linkedIds = new Set(linked.map(item => String(item.id)));
    const benefits = (benRes.ok && benRes.data && benRes.data.rules) || [];
    const docs = (docRes.ok && docRes.data && docRes.data.docs) || [];
    /* Справочник источников ведёт администратор: представителю доступны общие
       источники (перечень РСОШ) и источники своего вуза. */
    const sources = (srcRes.ok && srcRes.data && srcRes.data.sources) || [];

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
            Выберите олимпиады из каталога, за которые университет даёт БВИ,
            ведите правила льгот и загружайте документы-основания.
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

    <section class="mb-16 md:mb-24" aria-labelledby="my-benefits-title">
        <div class="flex flex-wrap items-center justify-between gap-6">
            <h2 id="my-benefits-title" class="text-2xl font-extrabold tracking-tight">Правила льгот (${benefits.length})</h2>
            <button type="button" id="benefit-add" class="${UI.btn} ${UI.btnPrimary}">Добавить правило</button>
        </div>
        <p class="mt-4 text-sm text-ink-soft leading-relaxed max-w-2xl">
            Правило появится в публичном каталоге после проверки администратором Papaya.
            Изменение содержания проверенного правила снова отправляет его на проверку.
        </p>
        <div id="my-benefits-list" class="mt-10"></div>
    </section>

    <section class="mb-16 md:mb-24" aria-labelledby="my-docs-title">
        <div class="flex flex-wrap items-center justify-between gap-6">
            <h2 id="my-docs-title" class="text-2xl font-extrabold tracking-tight">Документы университета (${docs.length})</h2>
            <button type="button" id="doc-add" class="${UI.btn} ${UI.btnPrimary}">Загрузить документ</button>
        </div>
        <p class="mt-4 text-sm text-ink-soft leading-relaxed max-w-2xl">
            Приказ или положение университета можно приложить к правилу льготы как основание.
        </p>
        <div id="my-docs-list" class="mt-10"></div>
    </section>`;

    drawMyBviList(linked, universityId, linkedIds);
    drawMyBenefitsList(benefits, universityId, docs, sources);
    drawMyDocsList(docs, universityId);

    document.getElementById('bvi-add').addEventListener('click', () => openBviPickerModal(universityId, linkedIds));
    document.getElementById('benefit-add').addEventListener('click', () =>
        openBenefitFormModal(universityId, null, docs, sources, () => renderMyUniversity()));
    document.getElementById('doc-add').addEventListener('click', () =>
        openDocUploadModal(universityId, () => renderMyUniversity()));
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

/* ----------------------------- Правила льгот ------------------------------ */

const BENEFIT_TYPE_LABELS = {
    BVI: 'БВИ',
    EGE_100: '100 баллов ЕГЭ',
    DVI_100: '100 баллов ДВИ',
    OTHER: 'Другая льгота',
};

const BENEFIT_RESULT_LABELS = {
    WINNER: 'Победитель',
    PRIZE: 'Призёр',
    SCORE: 'Балл',
    OTHER: 'Другое',
};

function benefitTypeLabel(type) {
    return BENEFIT_TYPE_LABELS[type] || type || 'Льгота';
}

function benefitResultText(rule) {
    if (rule.required_result_type) {
        const label = BENEFIT_RESULT_LABELS[rule.required_result_type] || rule.required_result_type;
        return rule.required_result_value ? `${label}: ${rule.required_result_value}` : label;
    }
    return rule.required_result || '';
}

/** Бейдж публикации: правило видно в каталоге только при `verified` + `is_published`. */
function benefitPublishedBadge(rule) {
    if (rule.is_published) {
        return `<span class="${UI.badge} ${UI.badgeSuccess}">Опубликовано</span>`;
    }
    return `<span class="${UI.badge} ${UI.badgeNeutral}">Скрыто из каталога</span>`;
}

function drawMyBenefitsList(rules, universityId, docs, sources) {
    const box = document.getElementById('my-benefits-list');
    if (!box) return;

    if (!rules.length) {
        box.innerHTML = emptyHtml('Правил льгот пока нет',
            'Добавьте правило: олимпиада, условия и документ-основание. '
            + 'После проверки администратором оно появится в публичном каталоге.');
        return;
    }

    const docNames = new Map((docs || []).map(item => [String(item.id), item.name]));
    const sourceNames = new Map((sources || []).map(item => [String(item.id), item.name]));
    box.innerHTML = `<div class="space-y-6">` + rules.map(item => {
        const result = benefitResultText(item);
        const docName = item.doc_id ? docNames.get(String(item.doc_id)) : '';
        const sourceName = item.source_id ? sourceNames.get(String(item.source_id)) : '';
        /* Публикация не меняет содержание правила, поэтому проверка при
           переключении не снимается — но версия меняется, её и передаём. */
        const publishLabel = item.is_published ? 'Скрыть из каталога' : 'Опубликовать';
        return `
        <article class="${UI.card} px-8 py-7">
            <div class="flex flex-col lg:flex-row lg:items-start gap-6">
                <div class="flex-1 min-w-0">
                    <p class="font-bold text-ink leading-snug">
                        ${escHtml(benefitTypeLabel(item.benefit_type))}${item.subject ? ` · ${escHtml(item.subject)}` : ''}
                    </p>
                    <div class="mt-3 flex items-center gap-3 flex-wrap">
                        ${benefitStatusBadge(item.verification_status)}
                        ${benefitPublishedBadge(item)}
                        <span class="${UI.badge} ${UI.badgeNeutral}">Версия ${escHtml(item.version)}</span>
                    </div>
                    ${result ? `<p class="mt-4 text-sm text-ink-soft">Условие: ${escHtml(result)}</p>` : ''}
                    ${item.additional_requirements ? `<p class="mt-2 text-sm text-ink-soft">Дополнительно: ${escHtml(item.additional_requirements)}</p>` : ''}
                    ${item.rejection_reason ? `<p class="mt-3 text-sm text-crimson">Причина отказа: ${escHtml(item.rejection_reason)}</p>` : ''}
                    ${sourceName ? `<p class="mt-3 text-sm text-ink-soft">Источник: ${escHtml(sourceName)}</p>` : ''}
                    ${item.source_url ? `<p class="mt-3 text-sm"><a href="${escAttr(item.source_url)}" target="_blank" rel="noopener noreferrer" class="underline">Источник правила</a></p>` : ''}
                    ${docName ? `<p class="mt-2 text-sm text-ink-faint">Документ: ${escHtml(docName)}</p>` : ''}
                    ${!item.is_published && item.verification_status === 'verified'
                        ? '<p class="mt-2 text-sm text-ink-faint">Правило проверено, но скрыто из публичного каталога.</p>'
                        : ''}
                </div>
                <div class="flex flex-wrap lg:flex-col gap-3 shrink-0">
                    <button type="button" data-benefit-edit="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Редактировать</button>
                    <button type="button" data-benefit-publish="${escAttr(item.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">${publishLabel}</button>
                    <button type="button" data-benefit-history="${escAttr(item.id)}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">История версий</button>
                </div>
            </div>
        </article>`;
    }).join('') + `</div>`;

    const byId = new Map(rules.map(item => [String(item.id), item]));
    box.querySelectorAll('[data-benefit-edit]').forEach(btn => {
        btn.addEventListener('click', () => {
            const rule = byId.get(String(btn.dataset.benefitEdit));
            if (rule) openBenefitFormModal(universityId, rule, docs, sources, () => renderMyUniversity());
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

async function openBenefitFormModal(universityId, rule, docs, sources, onDone) {
    const [olyRes, progRes] = await Promise.all([
        api.listOlympiads(''),
        api.listPrograms(universityId),
    ]);
    if (!olyRes.ok) {
        showToast(errorText(olyRes), 'error');
        return;
    }

    const olympiads = (olyRes.data.olympiads || []).slice();
    if (rule && rule.olympiad_id && !olympiads.some(item => String(item.id) === String(rule.olympiad_id))) {
        olympiads.unshift({ id: rule.olympiad_id, name: 'Текущая олимпиада (нет в актуальном перечне)' });
    }
    const programs = (progRes.ok && progRes.data && progRes.data.programs) || [];
    const documents = docs || [];
    const availableSources = sources || [];
    const isEdit = !!rule;

    let seasons = [];
    if (rule && rule.olympiad_id) {
        const res = await api.listSeasons(rule.olympiad_id);
        seasons = (res.ok && res.data && res.data.seasons) || [];
    } else if (olympiads.length) {
        // Для нового правила олимпиада уже выбрана в форме, поэтому сезоны
        // нужны сразу. Раньше они подгружались только по событию change:
        // пока администратор не переключит олимпиаду, сезон выбрать нельзя.
        const res = await api.listSeasons(olympiads[0].id);
        seasons = (res.ok && res.data && res.data.seasons) || [];
    }
    let profiles = [];
    if (rule && rule.season_id) {
        const res = await api.listProfiles(rule.season_id);
        profiles = (res.ok && res.data && res.data.profiles) || [];
    }

    const body = `
        <div id="modal-alert"></div>
        <form id="benefit-form">
            ${selectField({
                id: 'benefit-olympiad',
                name: 'olympiad_id',
                label: 'Олимпиада',
                options: olympiads.map(item => ({ value: item.id, label: item.name })),
                value: rule ? rule.olympiad_id : (olympiads[0] || {}).id,
            })}
            ${selectField({
                id: 'benefit-season',
                name: 'season_id',
                label: 'Сезон (необязательно)',
                options: [{ value: '', label: 'Не выбран' }, ...seasons.map(item => ({ value: item.id, label: item.season_label }))],
                value: rule ? (rule.season_id || '') : '',
            })}
            ${selectField({
                id: 'benefit-profile',
                name: 'profile_id',
                label: 'Профиль (необязательно)',
                options: [{ value: '', label: 'Не выбран' }, ...profiles.map(item => ({ value: item.id, label: item.profile_name || item.subject || 'Профиль' }))],
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
                label: 'Тип результата',
                options: [{ value: '', label: 'Не указан' }, ...Object.entries(BENEFIT_RESULT_LABELS).map(([value, label]) => ({ value, label }))],
                value: rule ? (rule.required_result_type || '') : '',
            })}
            ${inputField({ id: 'benefit-result-value', name: 'required_result_value', label: 'Значение результата', value: rule ? (rule.required_result_value || '') : '', placeholder: 'например, 75' })}
            ${inputField({ id: 'benefit-result', name: 'required_result', label: 'Условие словами', value: rule ? (rule.required_result || '') : '', placeholder: 'Победитель или призёр заключительного этапа' })}
            ${inputField({ id: 'benefit-subject', name: 'subject', label: 'Предмет / профиль', value: rule ? (rule.subject || '') : '', placeholder: 'Физика' })}
            ${textareaField({ id: 'benefit-extra', name: 'additional_requirements', label: 'Дополнительные требования', value: rule ? (rule.additional_requirements || '') : '' })}
            ${selectField({
                id: 'benefit-source-id',
                name: 'source_id',
                label: 'Источник из справочника (необязательно)',
                options: [
                    { value: '', label: 'Без источника' },
                    ...availableSources.map(item => ({ value: item.id, label: item.name })),
                ],
                value: rule ? (rule.source_id || '') : '',
            })}
            ${inputField({ id: 'benefit-source', name: 'source_url', label: 'Ссылка на источник', type: 'url', value: rule ? (rule.source_url || '') : '', placeholder: 'https://…' })}
            ${selectField({
                id: 'benefit-doc',
                name: 'doc_id',
                label: 'Документ-основание',
                options: [{ value: '', label: 'Без документа' }, ...documents.map(item => ({ value: item.id, label: item.name }))],
                value: rule ? (rule.doc_id || '') : '',
            })}
            <div class="${UI.field}">
                <p class="${UI.label}">Образовательные программы</p>
                ${programs.length
                    ? `<div class="grid sm:grid-cols-2 gap-2 mt-2">${programs.map(item => `
                        <label class="flex items-start gap-3 text-sm text-ink leading-snug">
                            <input type="checkbox" name="program_ids" value="${escAttr(item.id)}"
                                   ${rule && (rule.program_ids || []).some(id => String(id) === String(item.id)) ? 'checked' : ''}
                                   class="mt-0.5">
                            <span>${escHtml(item.name)}</span>
                        </label>`).join('')}</div>`
                    : '<p class="mt-2 text-sm text-ink-soft">Программы не заведены. Правило можно сохранить без привязки.</p>'}
            </div>
            <div class="flex flex-wrap justify-end gap-3 mt-10">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">${isEdit ? 'Сохранить' : 'Добавить правило'}</button>
            </div>
        </form>`;

    const { overlay, close } = openModal(
        isEdit ? 'Редактирование правила льготы' : 'Новое правило льготы',
        body,
        { wide: true }
    );
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    const olympiadSelect = overlay.querySelector('#benefit-olympiad');
    const seasonSelect = overlay.querySelector('#benefit-season');
    const profileSelect = overlay.querySelector('#benefit-profile');
    if (isEdit && olympiadSelect) olympiadSelect.disabled = true;

    const seasonOption = (value, label) => ({ value, label });
    async function loadSeasons(olympiadId, selected) {
        const options = [seasonOption('', 'Не выбран')];
        if (olympiadId) {
            const res = await api.listSeasons(olympiadId);
            if (res.ok) {
                ((res.data || {}).seasons || []).forEach(item =>
                    options.push(seasonOption(item.id, item.season_label)));
            }
        }
        setSelectOptions(seasonSelect, options, selected || '');
    }
    async function loadProfiles(seasonId, selected) {
        const options = [seasonOption('', 'Не выбран')];
        if (seasonId) {
            const res = await api.listProfiles(seasonId);
            if (res.ok) {
                ((res.data || {}).profiles || []).forEach(item =>
                    options.push(seasonOption(item.id, item.profile_name || item.subject || 'Профиль')));
            }
        }
        setSelectOptions(profileSelect, options, selected || '');
    }

    olympiadSelect.addEventListener('change', async () => {
        await loadSeasons(olympiadSelect.value, '');
        await loadProfiles('', '');
    });
    seasonSelect.addEventListener('change', () => loadProfiles(seasonSelect.value, ''));

    overlay.querySelector('#benefit-form').addEventListener('submit', async e => {
        e.preventDefault();
        const form = e.target;
        const fd = new FormData(form);
        const olympiadId = (fd.get('olympiad_id') || '').trim();
        if (!olympiadId) {
            showModalError(overlay, { data: { detail: 'Выберите олимпиаду' } });
            return;
        }
        const payload = {
            season_id: (fd.get('season_id') || '') || null,
            profile_id: (fd.get('profile_id') || '') || null,
            benefit_type: fd.get('benefit_type') || 'BVI',
            required_result_type: (fd.get('required_result_type') || '') || null,
            required_result_value: (fd.get('required_result_value') || '').trim() || null,
            required_result: (fd.get('required_result') || '').trim() || null,
            subject: (fd.get('subject') || '').trim() || null,
            additional_requirements: (fd.get('additional_requirements') || '').trim() || null,
            source_id: (fd.get('source_id') || '') || null,
            source_url: (fd.get('source_url') || '').trim() || null,
            doc_id: (fd.get('doc_id') || '') || null,
            program_ids: fd.getAll('program_ids'),
        };
        if (isEdit) {
            payload.version = rule.version;
            payload.change_reason = 'Правка представителя университета';
        } else {
            payload.olympiad_id = olympiadId;
        }

        const btn = form.querySelector('button[type="submit"]');
        btn.disabled = true;
        btn.textContent = 'Сохраняем…';
        const res = isEdit
            ? await api.updateBenefit(rule.id, payload)
            : await api.createBenefit(universityId, payload);
        if (res.ok) {
            close();
            showToast(isEdit ? 'Правило обновлено' : 'Правило добавлено', 'success');
            if (onDone) onDone();
            return;
        }
        showModalError(overlay, res);
        btn.disabled = false;
        btn.textContent = isEdit ? 'Сохранить' : 'Добавить правило';
    });
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
                        return `<div class="${UI.card} px-6 py-5 flex flex-col sm:flex-row sm:items-center gap-4">
                            <div class="flex-1 min-w-0">
                                <p class="font-semibold text-ink">Версия ${escHtml(item.version_number)}</p>
                                <p class="mt-1 text-sm text-ink-soft">${escHtml(snap.subject || benefitTypeLabel(snap.benefit_type))}${snap.required_result ? ` · ${escHtml(snap.required_result)}` : ''}</p>
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
            const res = await api.rollbackBenefit(rule.id, version);
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

const DOC_TYPE_LABELS = {
    RSOSH_LIST: 'Перечень РСОШ',
    UNIVERSITY_ORDER: 'Приказ университета',
    OTHER: 'Другой документ',
};

function docTypeLabel(type) {
    return DOC_TYPE_LABELS[type] || type || 'Документ';
}

function drawMyDocsList(docs, universityId) {
    const box = document.getElementById('my-docs-list');
    if (!box) return;
    if (!docs.length) {
        box.innerHTML = emptyHtml('Документов пока нет',
            'Загрузите приказ или положение университета — его можно приложить к правилу льготы.');
        return;
    }
    box.innerHTML = `<div class="space-y-4">` + docs.map(item => `
        <article class="${UI.card} px-8 py-6 flex flex-col lg:flex-row lg:items-center gap-5">
            <div class="flex-1 min-w-0">
                <p class="font-bold text-ink leading-snug">${escHtml(item.name)}</p>
                <p class="mt-2 text-sm text-ink-soft">${escHtml(docTypeLabel(item.type))} · ${escHtml(item.status || 'UPLOADED')}</p>
                ${item.createdAt ? `<p class="mt-1 text-xs text-ink-faint">Загружен: ${escHtml(formatDate(item.createdAt))}</p>` : ''}
            </div>
            <div class="flex flex-wrap gap-3 shrink-0">
                <a href="${escAttr(api.docFileUrl(item.id))}" target="_blank" rel="noopener noreferrer" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Скачать</a>
                <button type="button" data-doc-edit="${escAttr(item.id)}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">Переименовать</button>
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
                <label for="doc-file" class="${UI.label}">Файл <span class="text-crimson" aria-hidden="true">*</span></label>
                <input id="doc-file" name="file" type="file" required accept=".pdf,.xlsx,.png,.jpg,.jpeg"
                       class="block w-full cursor-pointer text-sm text-ink-soft file:mr-4 file:rounded file:px-5 file:py-2.5 file:text-sm file:font-semibold file:bg-ink file:text-white hover:file:bg-ink-deep">
                <p class="mt-2 text-sm text-ink-soft">Поддерживаются PDF, XLSX и изображения PNG/JPG/JPEG.</p>
            </div>
            ${inputField({ id: 'doc-name', name: 'name', label: 'Название документа', placeholder: 'Приказ о льготах 2026' })}
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
