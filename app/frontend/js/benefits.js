/* ==========================================================================
 * benefits.js — правило льготы: общие компоненты для всех страниц.
 *
 * Правило льготы — отдельная сущность: университет + олимпиада + (сезон,
 * профиль) + вид льготы + требуемый результат + предмет + программы +
 * документ + источник + проверка Papaya. Один и тот же вид карточки, одна
 * форма редактирования, одна история версий используются на публичных
 * страницах, в кабинете представителя и в панели администратора — иначе
 * три экрана показывали бы одно правило по-разному.
 *
 *   #/benefits/{id}   → GET /api/v1/benefit-rules/{id}   (публичная карточка)
 * ========================================================================== */

const BENEFIT_TYPE_OPTIONS = [
    { value: 'BVI', label: 'БВИ' },
    { value: 'EGE_100', label: '100 баллов ЕГЭ' },
    { value: 'DVI_100', label: '100 баллов ДВИ' },
    { value: 'OTHER', label: 'Иная льгота' },
];

const RULE_STATUS_LABELS = {
    draft: 'Черновик',
    published: 'Опубликовано',
    archived: 'В архиве',
};

/** Человеческая подпись требуемого результата. */
function resultRequirementLabel(value) {
    if (!value) return '';
    const map = { winner: 'победитель', prize: 'призёр', 'winner_or_prize': 'победитель или призёр' };
    return map[String(value).toLowerCase()] || value;
}

/** Бейдж публикационного состояния правила (черновик / опубликовано / архив). */
function ruleStatusBadge(status) {
    if (status === 'published') return `<span class="${UI.badge} ${UI.badgeSuccess}">Опубликовано</span>`;
    if (status === 'archived') return `<span class="${UI.badge} ${UI.badgeNeutral}">В архиве</span>`;
    return `<span class="${UI.badge} ${UI.badgePending}">Черновик</span>`;
}

/** Подпись сезона: «2026» или «2025/2026», если задана метка. */
function seasonLabel(season) {
    if (!season) return '';
    return season.label || (season.year ? String(season.year) : '');
}

/**
 * Историческое ли правило.
 *
 * Единственное место, где это решается во фронтенде: раздел действующих и
 * исторических правил на страницах университета и олимпиады обязан считать
 * одинаково. Историческим правило становится, когда олимпиада ушла из
 * актуального перечня (сервер отдаёт `is_historical`) — или когда само
 * правило архивировано.
 */
function isHistoricalRule(item) {
    return Boolean(item.is_historical)
        || item.status === 'archived'
        || item.olympiad_status === 'ARCHIVED';
}

/** Текстовые строки условий правила (общие для всех карточек). */
function ruleConditionLines(rule) {
    const lines = [];
    if (rule.season && seasonLabel(rule.season)) lines.push(`Сезон: ${escHtml(seasonLabel(rule.season))}`);
    if (rule.profile && rule.profile.name) {
        lines.push(`Профиль: ${escHtml(rule.profile.name)}${rule.profile.subject ? ` (${escHtml(rule.profile.subject)})` : ''}`);
    }
    if (rule.result_requirement) lines.push(`Требуемый результат: ${escHtml(resultRequirementLabel(rule.result_requirement))}`);
    if (rule.subject) lines.push(`Предмет: ${escHtml(rule.subject)}`);
    if (rule.programs && rule.programs.length) {
        lines.push(`Программы: ${escHtml(rule.programs.map(item => item.name || item).join(', '))}`);
    }
    if (rule.extra_requirements) lines.push(`Дополнительно: ${escHtml(rule.extra_requirements)}`);
    if (rule.valid_until) lines.push(`Действует до ${escHtml(formatDate(rule.valid_until))}`);
    return lines;
}

/** Бейджи правила: вид льготы, проверка Papaya, подтверждение вуза. */
function ruleBadgesHtml(rule, { withStatus = false } = {}) {
    const historical = isHistoricalRule(rule);
    return `
        <div class="flex items-center gap-2 flex-wrap">
            ${historical
                ? `<span class="${UI.badge} ${UI.badgeNeutral}">Историческое правило</span>`
                : benefitTypeBadge(rule.benefit_type)}
            ${historical && rule.benefit_type && rule.benefit_type !== 'BVI'
                ? `<span class="${UI.badge} ${UI.badgeNeutral}">${escHtml(benefitTypeLabel(rule.benefit_type))}</span>`
                : ''}
            ${verificationBadge(rule.verification_status)}
            ${rule.university_confirmed
                ? `<span class="${UI.badge} ${UI.badgeNeutral}">Подтверждено вузом</span>`
                : ''}
            ${withStatus ? ruleStatusBadge(rule.status) : ''}
        </div>`;
}

/** Ссылки правила: документ и первоисточник. */
function ruleSourcesHtml(rule, { compact = false } = {}) {
    const doc = rule.document || null;
    const hasFile = !!(doc && doc.has_file) || !!rule.source_doc_id;
    const docUrl = rule.id ? api.publicBenefitRuleDocumentUrl(rule.id) : '';
    const parts = [];
    if (hasFile && docUrl) {
        parts.push(`<a href="${escAttr(docUrl)}" target="_blank" rel="noopener noreferrer"
            class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">${escHtml(compact ? 'Документ' : (doc && doc.name ? `Документ: ${doc.name}` : 'Официальный документ'))}</a>`);
    }
    if (rule.source_url) {
        parts.push(`<a href="${escAttr(rule.source_url)}" target="_blank" rel="noopener noreferrer"
            class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Первоисточник</a>`);
    }
    if (!parts.length) {
        return compact
            ? ''
            : `<p class="text-sm text-ink-faint">Документ и ссылка на источник пока не приложены.</p>`;
    }
    return `<div class="flex flex-wrap items-center gap-3">${parts.join('')}</div>`;
}

/**
 * Компактная карточка правила внутри списка (на странице университета — под
 * олимпиадой, на странице олимпиады — под вузом).
 */
function benefitRuleRowHtml(rule) {
    const lines = ruleConditionLines(rule);
    return `
    <div class="rounded bg-mist px-5 py-4" data-rule-id="${escAttr(rule.id)}">
        ${ruleBadgesHtml(rule)}
        ${lines.length
            ? `<ul class="mt-3 space-y-1 text-sm text-ink-soft">${lines.map(line => `<li>${line}</li>`).join('')}</ul>`
            : `<p class="mt-3 text-sm text-ink-soft">Условия не уточнены: льгота распространяется на олимпиаду в целом.</p>`}
        ${rule.verification_status === 'rejected'
            ? `<p class="mt-3 text-sm text-crimson">Проверка Papaya не пройдена: правило не считается действующим.</p>`
            : ''}
        <div class="mt-4 flex flex-wrap items-center gap-3">
            ${ruleSourcesHtml(rule, { compact: true })}
            <a href="#/benefits/${escAttr(rule.id)}" class="text-sm font-semibold text-ink underline">Подробнее о правиле</a>
        </div>
    </div>`;
}

/**
 * Карточка олимпиады со вложенными правилами (страница университета).
 */
function olympiadWithRulesCardHtml(olympiad) {
    const rules = olympiad.rules || [];
    const historical = Boolean(olympiad.is_historical) || olympiad.status === 'ARCHIVED';
    return `
    <article class="bg-white shadow-elev-1 p-8" data-olympiad-id="${escAttr(olympiad.id)}">
        <div class="flex items-center gap-3 flex-wrap">
            ${historical
                ? `<span class="${UI.badge} ${UI.badgeNeutral}">Архивная олимпиада</span>`
                : olympiadStatusBadge(olympiad.status)}
            <span class="text-sm text-ink-faint">Правил: ${rules.length}</span>
        </div>
        <h3 class="mt-4 text-lg font-bold tracking-tight leading-snug">
            <a href="#/olympiads/${escAttr(olympiad.id)}" class="hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60 rounded">${escHtml(olympiad.name)}</a>
        </h3>
        ${olympiad.organizer ? `<p class="mt-1 text-sm text-ink-soft">${escHtml(olympiad.organizer)}</p>` : ''}
        ${historical
            ? `<p class="mt-3 text-sm text-ink-faint">Олимпиады сейчас нет в актуальном перечне: правила сохранены как история.</p>`
            : ''}
        <div class="mt-5 space-y-3">${rules.map(benefitRuleRowHtml).join('')}</div>
    </article>`;
}

/**
 * Карточка университета со вложенными правилами (страница олимпиады).
 */
function universityWithRulesCardHtml(university) {
    const rules = university.rules || [];
    return `
    <article class="bg-white shadow-elev-1 p-8" data-university-id="${escAttr(university.id)}">
        <a href="#/universities/${escAttr(university.id)}" class="block rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">
            ${entityTitleHtml(university)}
        </a>
        <p class="mt-2 text-sm text-ink-faint">Правил: ${rules.length}</p>
        <div class="mt-5 space-y-3">${rules.map(benefitRuleRowHtml).join('')}</div>
    </article>`;
}

/* ---------------------------- Фильтры каталога ---------------------------- */

/**
 * Комбинируемые фильтры по правилам: вид льготы, предмет, программа, сезон.
 *
 * Варианты предметов, программ и сезонов приходят из фасетов сервера, а не
 * вводятся вслепую: выбрать можно только то, по чему есть хотя бы одно
 * опубликованное правило.
 */
function benefitFiltersHtml(state, facets, { prefix = 'bf', withPrograms = true, withSeasons = true } = {}) {
    facets = facets || {};
    const typeOptions = [{ value: '', label: 'Любая льгота' }].concat(
        BENEFIT_TYPE_OPTIONS.map(item => {
            const facet = (facets.benefit_types || []).find(f => f.value === item.value);
            return { value: item.value, label: facet ? `${item.label} (${facet.count})` : item.label };
        }));
    const subjectOptions = [{ value: '', label: 'Любой предмет' }].concat(
        (facets.subjects || []).filter(item => item.value).map(item => ({
            value: item.value, label: `${item.value} (${item.count})`,
        })));
    const programOptions = [{ value: '', label: 'Любая программа' }].concat(
        (facets.programs || []).filter(item => item.id).map(item => ({
            value: item.id, label: `${item.name} (${item.count})`,
        })));
    const seasonOptions = [{ value: '', label: 'Любой сезон' }].concat(
        (facets.seasons || []).filter(item => item.id).map(item => ({
            value: item.id, label: `${seasonLabel(item)} (${item.count})`,
        })));

    const select = (id, label, options, value) => `
        <div class="flex-1 min-w-[12rem]">
            <label for="${prefix}-${id}" class="${UI.label}">${label}</label>
            <select id="${prefix}-${id}" data-filter="${id}" class="${UI.input}">
                ${options.map(item => `<option value="${escAttr(item.value)}"${String(item.value) === String(value || '') ? ' selected' : ''}>${escHtml(item.label)}</option>`).join('')}
            </select>
        </div>`;

    return `
    <div class="mt-10 flex flex-col sm:flex-row flex-wrap gap-4 sm:items-end" data-benefit-filters="${prefix}">
        ${select('benefitType', 'Вид льготы', typeOptions, state.benefitType)}
        ${select('subject', 'Предмет', subjectOptions, state.subject)}
        ${withPrograms ? select('programId', 'Образовательная программа', programOptions, state.programId) : ''}
        ${withSeasons ? select('seasonId', 'Сезон', seasonOptions, state.seasonId) : ''}
        <button type="button" data-filter-reset class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Сбросить</button>
    </div>`;
}

/** Привязать фильтры: любое изменение вызывает onChange(state). */
function bindBenefitFilters(prefix, state, onChange) {
    const box = document.querySelector(`[data-benefit-filters="${prefix}"]`);
    if (!box) return;
    box.querySelectorAll('[data-filter]').forEach(select => {
        select.addEventListener('change', () => {
            state[select.dataset.filter] = select.value;
            onChange(state);
        });
    });
    const reset = box.querySelector('[data-filter-reset]');
    if (reset) {
        reset.addEventListener('click', () => {
            Object.keys(state).forEach(key => { state[key] = ''; });
            box.querySelectorAll('[data-filter]').forEach(select => { select.value = ''; });
            onChange(state);
        });
    }
}

/* -------------------------- Публичная карточка правила -------------------- */

async function renderBenefitRule(ruleId) {
    const page = document.getElementById('page');
    if (!ruleId) { renderNotFound(); return; }
    page.innerHTML = loadingHtml('Открываем правило…');

    const res = await api.getPublicBenefitRule(ruleId);
    if (!res.ok || !res.data) {
        page.innerHTML = emptyHtml(
            res.status === 404 ? 'Правило не найдено' : 'Не удалось открыть правило',
            res.status === 404
                ? 'Правило могло быть снято с публикации, архивировано или ссылка неверна.'
                : errorText(res),
            '<a href="#/universities" class="' + UI.btn + ' ' + UI.btnSecondary + '">К каталогу университетов</a>');
        return;
    }
    const rule = res.data;
    const lines = ruleConditionLines(rule);
    const historical = isHistoricalRule(rule);
    const canManage = store.isAdmin()
        || (store.isUniversityRep() && String(store.user.university_id) === String(rule.university_id));

    page.innerHTML = `
    <article class="max-w-narrow mx-auto pb-16 md:pb-24">
        <a href="#/universities/${escAttr(rule.university_id)}" class="inline-flex items-center gap-2 text-ink-soft font-semibold hover:text-ink transition-colors rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5M12 19l-7-7 7-7"></path></svg>
            ${escHtml(rule.university_short_name || rule.university_name || 'Университет')}
        </a>

        <header class="mt-12">
            <p class="${UI.eyebrow}">Правило льготы</p>
            <h1 class="mt-5 text-3xl md:text-4xl font-extrabold tracking-tight leading-[1.1]">
                ${escHtml(benefitTypeLabel(rule.benefit_type))} за «${escHtml(rule.olympiad_name || 'олимпиаду')}»
            </h1>
            <p class="mt-4 text-lg text-ink-soft leading-relaxed">
                ${escHtml(rule.university_name || '')}
            </p>
            <div class="mt-6">${ruleBadgesHtml(rule)}</div>
        </header>

        ${rule.verification_status !== 'verified' ? `
        <div class="mt-8">${alertHtml(
            rule.verification_status === 'rejected'
                ? 'Проверка Papaya не пройдена: правило не считается действующим.' + (rule.verification_note ? ` Причина: ${rule.verification_note}` : '')
                : 'Не проверено Papaya: правило опубликовал представитель университета, модератор ещё не сверил его с документом.',
            rule.verification_status === 'rejected' ? 'error' : 'success')}</div>` : ''}

        ${historical ? `<div class="mt-4">${alertHtml('Правило историческое: олимпиады сейчас нет в актуальном перечне или правило архивировано.', 'error')}</div>` : ''}

        <section class="mt-12">
            <h2 class="${UI.eyebrow}">Условия</h2>
            ${lines.length
                ? `<ul class="mt-6 space-y-3 text-lg text-ink leading-relaxed">${lines.map(line => `<li>${line}</li>`).join('')}</ul>`
                : `<p class="mt-6 text-lg text-ink-soft">Условия не уточнены: льгота распространяется на олимпиаду в целом.</p>`}
        </section>

        <section class="mt-12">
            <h2 class="${UI.eyebrow}">Откуда взялась информация</h2>
            <div class="mt-6">${ruleSourcesHtml(rule)}</div>
            <dl class="mt-8 grid sm:grid-cols-2 gap-x-12 gap-y-6 text-sm">
                <div>
                    <dt class="font-medium text-ink-faint">Проверка Papaya</dt>
                    <dd class="mt-2">${escHtml(rule.verification_status === 'verified' ? `Проверено ${formatDate(rule.verified_at)}` : (rule.verification_status === 'rejected' ? 'Проверка не пройдена' : 'Не проверено'))}</dd>
                </div>
                <div>
                    <dt class="font-medium text-ink-faint">Подтверждение университета</dt>
                    <dd class="mt-2">${rule.university_confirmed ? `Подтверждено вузом ${formatDate(rule.university_confirmed_at)}` : 'Вуз пока не подтверждал'}</dd>
                </div>
                <div>
                    <dt class="font-medium text-ink-faint">Версия правила</dt>
                    <dd class="mt-2">${escHtml(String(rule.version || 1))} · обновлено ${formatDate(rule.updatedAt)}</dd>
                </div>
                <div>
                    <dt class="font-medium text-ink-faint">Олимпиада</dt>
                    <dd class="mt-2"><a href="#/olympiads/${escAttr(rule.olympiad_id)}" class="font-semibold underline">${escHtml(rule.olympiad_name || 'Открыть')}</a></dd>
                </div>
            </dl>
        </section>

        ${canManage ? `
        <section class="mt-12">
            <a href="${store.isAdmin() ? '#/admin/benefit-rules' : '#/my-university'}" class="${UI.btn} ${UI.btnSecondary} ${UI.btnSmall}">
                Управлять правилом
            </a>
        </section>` : ''}
    </article>`;
}

/* --------------------------- Управление правилом -------------------------- */

/**
 * Кнопки действий над правилом для представителя/администратора.
 *
 * Каждая кнопка либо работает, либо не показывается: например, «Удалить»
 * есть только у черновика (опубликованное правило уходит в архив, а не
 * исчезает), «Проверить» — только у администратора.
 */
function ruleManageActionsHtml(rule, { admin = false } = {}) {
    const id = escAttr(rule.id);
    const buttons = [];
    const btn = (act, label, cls = UI.btnSecondary, extra = '') =>
        `<button type="button" data-rule-act="${act}" data-rule-id="${id}" ${extra} class="${UI.btn} ${cls} ${UI.btnSmall}">${label}</button>`;

    if (rule.status !== 'archived') buttons.push(btn('edit', 'Редактировать'));
    if (rule.status === 'draft') buttons.push(btn('publish', 'Опубликовать', UI.btnPrimary));
    if (rule.status === 'published') buttons.push(btn('unpublish', 'Снять с публикации'));
    if (rule.status !== 'archived') buttons.push(btn('document', rule.source_doc_id ? 'Заменить документ' : 'Приложить документ'));
    buttons.push(btn('history', 'История', UI.btnGhost));
    buttons.push(btn('confirm', rule.university_confirmed ? 'Снять подтверждение вуза' : 'Подтвердить от имени вуза', UI.btnGhost));
    if (admin) buttons.push(btn('verify', 'Проверка Papaya', UI.btnPrimary));
    if (rule.status !== 'archived') buttons.push(btn('archive', 'В архив', UI.btnGhost));
    if (rule.status === 'draft') buttons.push(btn('delete', 'Удалить черновик', UI.btnDanger));
    if (rule.status === 'archived') buttons.push(btn('unarchive', 'Вернуть в черновики', UI.btnGhost));
    return `<div class="flex flex-wrap gap-2">${buttons.join('')}</div>`;
}

/** Полная карточка правила в кабинете / панели. */
function benefitRuleManageCardHtml(rule, { admin = false } = {}) {
    const lines = ruleConditionLines(rule);
    return `
    <div class="${UI.card} px-8 py-7" data-rule-card="${escAttr(rule.id)}">
        <div class="flex flex-col lg:flex-row lg:items-start gap-6">
            <div class="flex-1 min-w-0">
                <p class="font-bold text-ink leading-snug">
                    <a href="#/olympiads/${escAttr(rule.olympiad_id)}" class="hover:underline">${escHtml(rule.olympiad_name || 'Олимпиада')}</a>
                </p>
                ${admin && rule.university_name
                    ? `<p class="mt-1 text-sm text-ink-soft">${escHtml(rule.university_short_name || rule.university_name)}</p>`
                    : ''}
                <div class="mt-3">${ruleBadgesHtml(rule, { withStatus: true })}</div>
                ${lines.length
                    ? `<ul class="mt-4 space-y-1 text-sm text-ink-soft">${lines.map(line => `<li>${line}</li>`).join('')}</ul>`
                    : `<p class="mt-4 text-sm text-ink-soft">Условия не уточнены.</p>`}
                ${rule.verification_note
                    ? `<p class="mt-3 text-sm ${rule.verification_status === 'rejected' ? 'text-crimson' : 'text-ink-soft'}">Комментарий проверки: ${escHtml(rule.verification_note)}</p>`
                    : ''}
                <div class="mt-4">${ruleSourcesHtml(rule)}</div>
                <p class="mt-3 text-xs text-ink-faint">
                    Версия ${escHtml(String(rule.version || 1))} · обновлено ${formatDate(rule.updatedAt)}
                    · <a href="#/benefits/${escAttr(rule.id)}" class="underline">публичная карточка</a>
                </p>
            </div>
            <div class="shrink-0 lg:max-w-[18rem]">${ruleManageActionsHtml(rule, { admin })}</div>
        </div>
    </div>`;
}

/**
 * Обработчик действий над правилом (делегирование с контейнера).
 *
 * `rules` — текущий список, чтобы не перезапрашивать правило перед каждой
 * модалкой; `reload` — перерисовка после успешного действия.
 */
function bindRuleManageActions(container, getRules, reload, { admin = false } = {}) {
    if (!container) return;
    container.addEventListener('click', async e => {
        const btn = e.target.closest('[data-rule-act]');
        if (!btn || btn.disabled) return;
        const rule = (getRules() || []).find(item => String(item.id) === String(btn.dataset.ruleId));
        if (!rule) return;
        const universityId = rule.university_id;
        const act = btn.dataset.ruleAct;

        if (act === 'edit') { openBenefitRuleEditor({ universityId, rule, onDone: reload, admin }); return; }
        if (act === 'history') { openBenefitRuleHistoryModal(universityId, rule, reload); return; }
        if (act === 'document') { openBenefitRuleDocumentModal(universityId, rule, reload); return; }
        if (act === 'verify') { openBenefitRuleVerificationModal(universityId, rule, reload); return; }

        let promise = null;
        let message = '';
        if (act === 'publish' || act === 'unpublish' || act === 'archive' || act === 'unarchive') {
            const status = act === 'publish' ? 'published' : (act === 'archive' ? 'archived' : 'draft');
            if (act === 'archive' && !window.confirm('Отправить правило в архив? Оно исчезнет из каталога, история сохранится.')) return;
            const reason = act === 'archive' ? (window.prompt('Причина архивирования (попадёт в историю):', '') || null) : null;
            promise = api.setBenefitRuleStatus(universityId, rule.id, {
                status, reason, expected_version: rule.version || undefined,
            });
            message = { publish: 'Правило опубликовано', unpublish: 'Правило снято с публикации',
                archive: 'Правило архивировано', unarchive: 'Правило возвращено в черновики' }[act];
        } else if (act === 'delete') {
            if (!window.confirm('Удалить черновик без возможности восстановления?')) return;
            promise = api.deleteBenefitRule(universityId, rule.id);
            message = 'Черновик удалён';
        } else if (act === 'confirm') {
            promise = api.confirmBenefitRuleByUniversity(universityId, rule.id, !rule.university_confirmed);
            message = rule.university_confirmed ? 'Подтверждение вуза снято' : 'Правило подтверждено от имени вуза';
        } else {
            return;
        }

        btn.disabled = true;
        try {
            const res = await promise;
            if (res.ok) {
                showToast(message, 'success');
                await reload();
                return;
            }
            showToast(res.status === 409 ? `${errorText(res)}` : errorText(res), 'error');
        } catch {
            showToast('Сетевая ошибка', 'error');
        }
        btn.disabled = false;
    });
}

/* ------------------------------ Форма правила ----------------------------- */

/**
 * Создание и правка правила льготы.
 *
 * Зависимые списки: олимпиада → сезоны этой олимпиады → профили выбранного
 * сезона; программы — из каталога программ университета. При правке уходит
 * `expected_version`: если правило параллельно изменил кто-то ещё, сервер
 * ответит 409, и форма попросит перезагрузить данные, а не перезапишет
 * чужие правки.
 */
async function openBenefitRuleEditor({ universityId, rule = null, onDone, admin = false, olympiad = null }) {
    const isEdit = !!(rule && rule.id);
    const programsRes = await api.listUniversityPrograms(universityId);
    const programs = (programsRes.ok && programsRes.data && programsRes.data.programs) || [];
    const selectedPrograms = new Set((rule && rule.program_ids) || []);
    let dirty = false;

    const olympiadId = (rule && rule.olympiad_id) || (olympiad && olympiad.id) || '';
    const olympiadName = (rule && rule.olympiad_name) || (olympiad && olympiad.name) || '';

    const body = `
        <div id="modal-alert"></div>
        <form id="benefit-rule-form" novalidate>
            <div class="${UI.field}">
                <label for="rule-olympiad-query" class="${UI.label}">Олимпиада <span class="text-crimson" aria-hidden="true">*</span></label>
                ${isEdit
                    ? `<p class="px-4 py-3 bg-mist rounded text-ink">${escHtml(olympiadName)}</p>
                       <p class="mt-2 text-xs text-ink-faint">Олимпиаду у существующего правила сменить нельзя — заведите новое правило.</p>`
                    : `<input id="rule-olympiad-query" type="search" class="${UI.input}" autocomplete="off"
                              placeholder="Начните вводить название" value="${escAttr(olympiadName)}">
                       <input type="hidden" name="olympiad_id" id="rule-olympiad-id" value="${escAttr(olympiadId)}">
                       <div id="rule-olympiad-results" class="mt-2 space-y-1 max-h-48 overflow-y-auto modal-scroll"></div>
                       <p id="rule-olympiad-picked" class="mt-2 text-sm ${olympiadId ? 'text-ink' : 'text-ink-faint'}">
                           ${olympiadId ? `Выбрано: ${escHtml(olympiadName)}` : 'Олимпиада не выбрана'}
                       </p>`}
            </div>
            <div class="grid sm:grid-cols-2 gap-x-4">
                <div class="${UI.field}">
                    <label for="rule-season" class="${UI.label}">Сезон</label>
                    <select id="rule-season" name="season_id" class="${UI.input}" ${olympiadId ? '' : 'disabled'}>
                        <option value="">Все сезоны</option>
                    </select>
                </div>
                <div class="${UI.field}">
                    <label for="rule-profile" class="${UI.label}">Профиль</label>
                    <select id="rule-profile" name="profile_id" class="${UI.input}" disabled>
                        <option value="">Любой профиль</option>
                    </select>
                </div>
            </div>
            <div class="grid sm:grid-cols-2 gap-x-4">
                ${selectField({
                    id: 'rule-benefit-type', name: 'benefit_type', label: 'Вид льготы',
                    value: (rule && rule.benefit_type) || 'BVI', options: BENEFIT_TYPE_OPTIONS,
                })}
                ${selectField({
                    id: 'rule-result', name: 'result_requirement', label: 'Требуемый результат',
                    value: (rule && rule.result_requirement) || '',
                    options: [
                        { value: '', label: 'Не уточнён' },
                        { value: 'winner', label: 'Победитель' },
                        { value: 'prize', label: 'Призёр' },
                        { value: 'winner_or_prize', label: 'Победитель или призёр' },
                    ],
                })}
            </div>
            ${inputField({ id: 'rule-subject', name: 'subject', label: 'Предмет', value: (rule && rule.subject) || '', placeholder: 'например: математика' })}
            <div class="${UI.field}">
                <p class="${UI.label}">Образовательные программы</p>
                ${programs.length
                    ? `<div class="grid sm:grid-cols-2 gap-2 max-h-48 overflow-y-auto modal-scroll bg-mist rounded p-4" id="rule-programs">
                        ${programs.map(item => `
                        <label class="flex items-start gap-2 text-sm leading-snug">
                            <input type="checkbox" name="program_ids" value="${escAttr(item.id)}" class="mt-0.5" ${selectedPrograms.has(String(item.id)) ? 'checked' : ''}>
                            <span>${escHtml(item.name)}</span>
                        </label>`).join('')}
                       </div>
                       <p class="mt-2 text-xs text-ink-faint">Ничего не отмечено — правило действует на все программы.</p>`
                    : `<p class="text-sm text-ink-soft">У университета пока нет программ в каталоге. Добавьте их в разделе «Образовательные программы» — тогда правило можно будет привязать к направлениям.</p>`}
            </div>
            ${textareaField({ id: 'rule-extra', name: 'extra_requirements', rows: 2, label: 'Дополнительные условия', value: (rule && rule.extra_requirements) || '' })}
            <div class="grid sm:grid-cols-2 gap-x-4">
                ${inputField({ id: 'rule-source-url', name: 'source_url', type: 'url', label: 'Ссылка на первоисточник', value: (rule && rule.source_url) || '', placeholder: 'https://…' })}
                ${inputField({ id: 'rule-valid-until', name: 'valid_until', type: 'date', label: 'Действует до', value: ((rule && rule.valid_until) || '').slice(0, 10) })}
            </div>
            ${inputField({ id: 'rule-reason', name: 'reason', label: 'Комментарий к изменению (попадёт в историю)', value: '', placeholder: isEdit ? 'например: уточнён профиль по приказу 2026 года' : 'например: по приказу о приёме 2026' })}
            ${isEdit ? '' : `
            <label class="flex items-center gap-3 text-sm text-ink mb-6">
                <input type="checkbox" name="publish" class="w-4 h-4">
                Сразу опубликовать (иначе правило останется черновиком и не попадёт в каталог)
            </label>`}
            <div class="flex flex-wrap justify-end gap-3 mt-6">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">${isEdit ? 'Сохранить изменения' : 'Создать правило'}</button>
            </div>
        </form>`;

    const { overlay, close } = openModal(
        isEdit ? 'Правка правила льготы' : 'Новое правило льготы', body, { wide: true, isDirty: () => dirty });
    ['input', 'change'].forEach(ev => overlay.addEventListener(ev, () => { dirty = true; }));
    overlay.querySelector('[data-cancel]').addEventListener('click', close);

    const seasonSelect = overlay.querySelector('#rule-season');
    const profileSelect = overlay.querySelector('#rule-profile');
    let seasons = [];

    async function loadSeasons(oid, seasonId, profileId) {
        seasonSelect.innerHTML = '<option value="">Все сезоны</option>';
        profileSelect.innerHTML = '<option value="">Любой профиль</option>';
        profileSelect.disabled = true;
        if (!oid) { seasonSelect.disabled = true; return; }
        const res = await api.listOlympiadSeasons(oid).catch(() => ({ ok: false }));
        seasons = (res.ok && res.data && res.data.seasons) || [];
        seasonSelect.disabled = false;
        seasonSelect.innerHTML = '<option value="">Все сезоны</option>' + seasons.map(season =>
            `<option value="${escAttr(season.id)}" ${String(season.id) === String(seasonId || '') ? 'selected' : ''}>${escHtml(seasonLabel(season))} · ${escHtml(seasonStateLabel(season.state))}</option>`).join('');
        if (!seasons.length) {
            seasonSelect.innerHTML = '<option value="">Сезоны не заведены</option>';
            seasonSelect.disabled = true;
        }
        fillProfiles(seasonId, profileId);
    }
    function fillProfiles(seasonId, profileId) {
        const season = seasons.find(item => String(item.id) === String(seasonId || ''));
        const profiles = (season && season.profiles) || [];
        profileSelect.innerHTML = '<option value="">Любой профиль</option>' + profiles.map(profile =>
            `<option value="${escAttr(profile.id)}" ${String(profile.id) === String(profileId || '') ? 'selected' : ''}>${escHtml(profile.name)}${profile.subject ? ` · ${escHtml(profile.subject)}` : ''}</option>`).join('');
        profileSelect.disabled = !season || !profiles.length;
        if (season && !profiles.length) profileSelect.innerHTML = '<option value="">У сезона нет профилей</option>';
    }
    seasonSelect.addEventListener('change', () => fillProfiles(seasonSelect.value, null));
    if (olympiadId) loadSeasons(olympiadId, rule && rule.season_id, rule && rule.profile_id);

    if (!isEdit) {
        const queryInput = overlay.querySelector('#rule-olympiad-query');
        const hidden = overlay.querySelector('#rule-olympiad-id');
        const results = overlay.querySelector('#rule-olympiad-results');
        const picked = overlay.querySelector('#rule-olympiad-picked');
        let timer = null;
        async function search(q) {
            if (!q) { results.innerHTML = ''; return; }
            const res = await api.listOlympiads(q);
            const items = (res.ok && res.data && res.data.olympiads) || [];
            results.innerHTML = items.length
                ? items.slice(0, 20).map(item => `
                    <button type="button" data-pick-olympiad="${escAttr(item.id)}" data-name="${escAttr(item.name)}"
                            class="w-full text-left px-4 py-2 rounded hover:bg-mist text-sm">${escHtml(item.name)}</button>`).join('')
                : `<p class="px-4 py-2 text-sm text-ink-faint">Ничего не найдено. Если олимпиады нет в каталоге, отправьте заявку на пополнение.</p>`;
        }
        queryInput.addEventListener('input', () => {
            clearTimeout(timer);
            timer = setTimeout(() => search(queryInput.value.trim()), 300);
        });
        results.addEventListener('click', e => {
            const btn = e.target.closest('[data-pick-olympiad]');
            if (!btn) return;
            hidden.value = btn.dataset.pickOlympiad;
            queryInput.value = btn.dataset.name;
            picked.textContent = `Выбрано: ${btn.dataset.name}`;
            picked.className = 'mt-2 text-sm text-ink';
            results.innerHTML = '';
            loadSeasons(hidden.value, null, null);
        });
    }

    overlay.querySelector('#benefit-rule-form').addEventListener('submit', async e => {
        e.preventDefault();
        const form = e.target;
        const fd = new FormData(form);
        const programIds = fd.getAll('program_ids');
        const payload = {
            season_id: fd.get('season_id') || null,
            profile_id: fd.get('profile_id') || null,
            benefit_type: fd.get('benefit_type'),
            result_requirement: (fd.get('result_requirement') || '').trim() || null,
            subject: (fd.get('subject') || '').trim() || null,
            program_ids: programIds,
            extra_requirements: (fd.get('extra_requirements') || '').trim() || null,
            source_url: (fd.get('source_url') || '').trim() || null,
            valid_until: fd.get('valid_until') || null,
            reason: (fd.get('reason') || '').trim() || null,
        };
        const submit = form.querySelector('button[type="submit"]');
        submit.disabled = true;
        try {
            let res;
            if (isEdit) {
                payload.expected_version = rule.version || undefined;
                res = await api.updateBenefitRule(universityId, rule.id, payload);
            } else {
                payload.olympiad_id = fd.get('olympiad_id');
                payload.publish = !!fd.get('publish');
                if (!payload.olympiad_id) {
                    showModalError(overlay, { data: { detail: 'Выберите олимпиаду из каталога' } });
                    submit.disabled = false;
                    return;
                }
                res = await api.createBenefitRule(universityId, payload);
            }
            if (res.ok) {
                dirty = false;
                close();
                showToast(isEdit ? 'Правило сохранено (новая версия)' : (payload.publish ? 'Правило создано и опубликовано' : 'Черновик правила создан'), 'success');
                if (onDone) await onDone(res.data);
                return;
            }
            if (res.status === 409 && isEdit) {
                showModalError(overlay, { data: { detail: `${errorText(res)} Закройте окно и откройте правило заново, чтобы увидеть актуальную версию.` } });
            } else {
                showModalError(overlay, res);
            }
        } catch {
            showModalError(overlay, { data: { detail: 'Сетевая ошибка' } });
        }
        submit.disabled = false;
    });
}

/* ------------------------------ История версий ---------------------------- */

const SNAPSHOT_LABELS = {
    benefit_type: 'Вид льготы',
    result_requirement: 'Результат',
    subject: 'Предмет',
    programs: 'Программы',
    extra_requirements: 'Дополнительно',
    source_url: 'Источник',
    valid_until: 'Действует до',
    status: 'Статус',
    verification_status: 'Проверка',
    season_id: 'Сезон',
    profile_id: 'Профиль',
    source_doc_id: 'Документ',
};

function snapshotValueText(key, value) {
    if (value === null || value === undefined || value === '') return '—';
    if (key === 'benefit_type') return benefitTypeLabel(value);
    if (key === 'result_requirement') return resultRequirementLabel(value);
    if (key === 'status') return RULE_STATUS_LABELS[value] || value;
    if (key === 'verification_status') {
        return { verified: 'проверено', rejected: 'не пройдена', unverified: 'не проверено' }[value] || value;
    }
    if (Array.isArray(value)) return value.length ? value.join(', ') : '—';
    return String(value);
}

/** Что изменилось между двумя снимками — только отличающиеся поля. */
function snapshotDiffHtml(prev, current) {
    const keys = Object.keys(SNAPSHOT_LABELS).filter(key => {
        const a = JSON.stringify((prev || {})[key] ?? null);
        const b = JSON.stringify((current || {})[key] ?? null);
        return a !== b;
    });
    if (!keys.length) return '<p class="mt-2 text-xs text-ink-faint">Содержимое не отличается от предыдущей версии.</p>';
    return `<ul class="mt-2 space-y-1 text-xs text-ink-soft">${keys.map(key => `
        <li><span class="font-semibold">${escHtml(SNAPSHOT_LABELS[key])}:</span>
            ${prev ? `<s>${escHtml(snapshotValueText(key, (prev || {})[key]))}</s> → ` : ''}${escHtml(snapshotValueText(key, (current || {})[key]))}</li>`).join('')}</ul>`;
}

async function openBenefitRuleHistoryModal(universityId, rule, onDone) {
    const res = await api.benefitRuleVersions(universityId, rule.id);
    if (!res.ok) { showToast(errorText(res), 'error'); return; }
    const versions = (res.data && res.data.versions) || [];
    const currentVersion = (res.data && res.data.current_version) || rule.version;

    const rows = versions.slice().reverse().map((version, index, arr) => {
        const prev = arr[index + 1];
        const isCurrent = Number(version.version) === Number(currentVersion);
        return `
        <li class="rounded bg-mist px-5 py-4">
            <div class="flex flex-wrap items-center gap-3">
                <span class="text-sm font-bold">Версия ${escHtml(String(version.version))}</span>
                ${isCurrent ? `<span class="${UI.badge} ${UI.badgeSuccess}">Текущая</span>` : ''}
                ${version.is_rollback ? `<span class="${UI.badge} ${UI.badgeNeutral}">Откат</span>` : ''}
                <span class="text-sm text-ink-soft">${formatDate(version.changed_at)}${version.changed_by_name ? ` · ${escHtml(version.changed_by_name)}` : ''}</span>
                ${isCurrent ? '' : `<button type="button" data-rollback="${escAttr(String(version.version))}"
                        class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall} ml-auto">Откатить к этой версии</button>`}
            </div>
            ${version.reason ? `<p class="mt-2 text-sm text-ink">${escHtml(version.reason)}</p>` : ''}
            ${snapshotDiffHtml(prev ? prev.snapshot : null, version.snapshot)}
        </li>`;
    }).join('');

    const body = `
        <div id="modal-alert"></div>
        <p class="text-sm text-ink-soft leading-relaxed">
            Каждое изменение — отдельная версия. Откат не стирает историю: он создаёт
            новую версию с прежним содержимым, и такое правило снова считается
            непроверенным, пока модератор не сверит его заново.
        </p>
        ${versions.length ? `<ul class="mt-6 space-y-3">${rows}</ul>` : '<p class="mt-6 text-sm text-ink-soft">История пуста.</p>'}`;

    const { overlay, close } = openModal(`История правила: ${rule.olympiad_name || ''}`, body, { wide: true });
    overlay.addEventListener('click', async e => {
        const btn = e.target.closest('[data-rollback]');
        if (!btn) return;
        const version = Number(btn.dataset.rollback);
        if (!window.confirm(`Откатить правило к версии ${version}? Будет создана новая версия ${currentVersion + 1}.`)) return;
        const reason = window.prompt('Причина отката (попадёт в историю):', '') || null;
        btn.disabled = true;
        const rolled = await api.rollbackBenefitRule(universityId, rule.id, {
            version, reason, expected_version: currentVersion,
        });
        if (rolled.ok) {
            close();
            showToast(`Правило откатано к версии ${version}`, 'success');
            if (onDone) await onDone();
            return;
        }
        btn.disabled = false;
        showModalError(overlay, rolled);
    });
}

/* --------------------------- Документ правила ----------------------------- */

function openBenefitRuleDocumentModal(universityId, rule, onDone) {
    const body = `
        <div id="modal-alert"></div>
        <form id="rule-doc-form">
            <p class="text-sm text-ink-soft leading-relaxed mb-6">
                Приложите официальный документ университета (приказ, правила приёма),
                подтверждающий льготу. Допустимы PDF, XLSX, XLS, PNG, JPG. После
                замены документа правило снова считается непроверенным.
            </p>
            ${inputField({ id: 'rule-doc-name', name: 'name', label: 'Название документа', placeholder: 'Приказ о приёме 2026' })}
            <div class="${UI.field}">
                <label for="rule-doc-file" class="${UI.label}">Файл <span class="text-crimson" aria-hidden="true">*</span></label>
                <input id="rule-doc-file" name="file" type="file" required accept=".pdf,.xlsx,.xls,.png,.jpg,.jpeg" class="${UI.input}">
            </div>
            <div class="flex flex-wrap justify-end gap-3 mt-8">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Загрузить</button>
            </div>
        </form>`;
    const { overlay, close } = openModal('Документ правила', body);
    overlay.querySelector('[data-cancel]').addEventListener('click', close);
    overlay.querySelector('#rule-doc-form').addEventListener('submit', async e => {
        e.preventDefault();
        const form = e.target;
        const fileInput = form.querySelector('#rule-doc-file');
        if (!fileInput.files.length) {
            showModalError(overlay, { data: { detail: 'Выберите файл' } });
            return;
        }
        const fd = new FormData();
        fd.append('file', fileInput.files[0]);
        const name = form.querySelector('#rule-doc-name').value.trim();
        if (name) fd.append('name', name);
        const submit = form.querySelector('button[type="submit"]');
        submit.disabled = true;
        const res = await api.uploadBenefitRuleDocument(universityId, rule.id, fd);
        if (res.ok) {
            close();
            showToast('Документ приложен к правилу', 'success');
            if (onDone) await onDone();
            return;
        }
        submit.disabled = false;
        showModalError(overlay, res);
    });
}

/* --------------------------- Проверка Papaya ------------------------------ */

/**
 * Решение модератора по правилу (ТЗ §7).
 *
 * «Проверено» ставится только при документе и ссылке на источник — сервер
 * откажет без них, а форма говорит об этом заранее. «Проверка не пройдена»
 * требует причины: без неё представитель не поймёт, что исправить.
 */
function openBenefitRuleVerificationModal(universityId, rule, onDone) {
    const hasDoc = !!rule.source_doc_id;
    const hasUrl = !!rule.source_url;
    const canVerify = hasDoc && hasUrl;
    const body = `
        <div id="modal-alert"></div>
        <div class="rounded bg-mist px-5 py-4 text-sm leading-relaxed mb-6">
            <p>Документ: ${hasDoc ? 'приложен' : '<span class="text-crimson">отсутствует</span>'}</p>
            <p>Ссылка на источник: ${hasUrl ? 'указана' : '<span class="text-crimson">отсутствует</span>'}</p>
            ${canVerify ? '' : '<p class="mt-2 text-ink-soft">Отметить «Проверено» нельзя, пока у правила нет документа и ссылки на источник.</p>'}
        </div>
        <form id="rule-verify-form">
            ${selectField({
                id: 'verify-status', name: 'status', label: 'Решение', value: rule.verification_status || 'unverified',
                options: [
                    { value: 'unverified', label: 'Не проверено (снять отметку)' },
                    { value: 'verified', label: canVerify ? 'Проверено Papaya' : 'Проверено Papaya — недоступно без документа и ссылки' },
                    { value: 'rejected', label: 'Проверка не пройдена' },
                ],
            })}
            ${textareaField({ id: 'verify-note', name: 'note', rows: 3, label: 'Комментарий (обязателен при отказе)', value: rule.verification_note || '' })}
            <div class="flex flex-wrap justify-end gap-3 mt-8">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Сохранить решение</button>
            </div>
        </form>`;
    const { overlay, close } = openModal(`Проверка Papaya: ${rule.olympiad_name || ''}`, body);
    overlay.querySelector('[data-cancel]').addEventListener('click', close);
    const statusSelect = overlay.querySelector('#verify-status');
    if (!canVerify) statusSelect.querySelector('option[value="verified"]').disabled = true;

    overlay.querySelector('#rule-verify-form').addEventListener('submit', async e => {
        e.preventDefault();
        const status = statusSelect.value;
        const note = overlay.querySelector('#verify-note').value.trim();
        if (status === 'rejected' && !note) {
            showModalError(overlay, { data: { detail: 'Укажите причину: без неё представитель не поймёт, что исправить' } });
            return;
        }
        const res = await api.verifyBenefitRule(universityId, rule.id, {
            status, note: note || null, expected_version: rule.version || undefined,
        });
        if (res.ok) {
            close();
            showToast({ verified: 'Правило проверено', rejected: 'Проверка не пройдена — правило скрыто из действующих', unverified: 'Отметка проверки снята' }[status], 'success');
            if (onDone) await onDone();
            return;
        }
        showModalError(overlay, res);
    });
}

/* ------------------------ Заявка на пополнение каталога -------------------- */

function openCatalogRequestModal(universityId, onDone) {
    const body = `
        <div id="modal-alert"></div>
        <form id="catalog-request-form">
            <p class="text-sm text-ink-soft leading-relaxed mb-6">
                Каталог олимпиад наполняется из перечня РСОШ, и представитель не
                создаёт олимпиады сам. Если нужной олимпиады или сезона нет —
                опишите, что добавить; администратор получит заявку.
            </p>
            ${selectField({
                id: 'cr-kind', name: 'kind', label: 'Что не хватает', value: 'olympiad',
                options: [
                    { value: 'olympiad', label: 'Олимпиады нет в каталоге' },
                    { value: 'season', label: 'Нет нужного сезона или профиля' },
                    { value: 'other', label: 'Другое' },
                ],
            })}
            ${textareaField({ id: 'cr-text', name: 'text', rows: 4, required: true, label: 'Описание', placeholder: 'Название олимпиады, организатор, ссылка на сайт, год сезона…' })}
            <div class="flex flex-wrap justify-end gap-3 mt-8">
                <button type="button" data-cancel class="${UI.btn} ${UI.btnGhost}">Отмена</button>
                <button type="submit" class="${UI.btn} ${UI.btnPrimary}">Отправить заявку</button>
            </div>
        </form>`;
    const { overlay, close } = openModal('Заявка на пополнение каталога', body);
    overlay.querySelector('[data-cancel]').addEventListener('click', close);
    overlay.querySelector('#catalog-request-form').addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const text = (fd.get('text') || '').trim();
        if (!text) { showModalError(overlay, { data: { detail: 'Опишите, что нужно добавить' } }); return; }
        const res = await api.createCatalogRequest(universityId, { kind: fd.get('kind'), text });
        if (res.ok) {
            close();
            showToast('Заявка отправлена администратору', 'success');
            if (onDone) await onDone();
            return;
        }
        showModalError(overlay, res);
    });
}
