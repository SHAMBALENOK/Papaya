/* ==========================================================================
 * pages/olympiads.js — каталог и детальная карточка олимпиад.
 * Создаёт/правит орг-админ своей организации или ADMIN.
 * Бэкенд: app/routers/olympiads.py (#/olympiads, #/olympiads/{id}).
 *
 * Фаза 2 «Этапы и даты»:
 *   — в карточке: вычисленный статус олимпиады + ближайший дедлайн;
 *   — на странице: timeline этапов (season, даты, статус каждого этапа);
 *   — в модалке: визуальный конструктор одного или нескольких этапов.
 *   Расписание хранится в JSONB-поле schedule; статусы считает сервер.
 * ========================================================================== */

const STAGE_TYPE_LABELS = {
    REGISTRATION: 'Регистрация',
    QUALIFICATION: 'Отборочный этап',
    FINAL: 'Заключительный этап',
    RESULTS: 'Результаты',
};

function statusBadge(status) {
    const map = { PUBLISHED: [UI.badgeSuccess, 'Опубликована'],
                  DRAFT: [UI.badgeNeutral, 'Черновик'],
                  ARCHIVED: [UI.badgeDanger, 'Архив'] };
    const [cls, label] = map[status] || [UI.badgeNeutral, status || '—'];
    return `<span class="${UI.badge} ${cls}">${escHtml(label)}</span>`;
}

function phaseStatusBadge(status) {
    const map = {
        UPCOMING: [UI.badgeNeutral, 'Ещё не началась'],
        REGISTRATION_OPEN: [UI.badgeSuccess, 'Регистрация открыта'],
        REGISTRATION_CLOSED: [UI.badgeNeutral, 'Регистрация закрыта'],
        QUALIFICATION: [UI.badgeSuccess, 'Отборочный этап'],
        FINAL: [UI.badgeSuccess, 'Заключительный этап'],
        RESULTS: [UI.badgeSuccess, 'Результаты'],
        FINISHED: [UI.badgeDanger, 'Завершена'],
    };
    const [cls, label] = map[status] || [UI.badgeNeutral, status || '—'];
    return `<span class="${UI.badge} ${cls}">${escHtml(label)}</span>`;
}

function stageStatusBadge(status) {
    const map = {
        UPCOMING: [UI.badgeNeutral, 'Предстоит'],
        ACTIVE: [UI.badgeSuccess, 'Идёт сейчас'],
        FINISHED: [UI.badgeDanger, 'Завершён'],
    };
    const [cls, label] = map[status] || [UI.badgeNeutral, status || '—'];
    return `<span class="${UI.badge} ${cls}">${escHtml(label)}</span>`;
}

function formatDateTime(iso) {
    if (!iso) return 'Н/Д';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return 'Н/Д';
    return d.toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
    });
}

/* datetime-local ("YYYY-MM-DDTHH:MM", локальное время) → ISO с таймзоной. */
function toLocalIso(inputValue) {
    if (!inputValue) return null;
    const d = new Date(inputValue);
    if (isNaN(d.getTime())) return null;
    const offset = -d.getTimezoneOffset();
    const sign = offset >= 0 ? '+' : '-';
    const pad = n => String(Math.abs(n)).padStart(2, '0');
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
        + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes())
        + ':00' + sign + pad(Math.floor(Math.abs(offset) / 60)) + ':' + pad(Math.abs(offset) % 60);
}

/* ISO с таймзоной → значение для input[type="datetime-local"]. */
function toLocalInput(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0')
        + 'T' + String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
}

function scheduleTimelineHtml(oly) {
    const sch = oly.schedule;
    if (!sch || !Array.isArray(sch.stages) || sch.stages.length === 0) {
        return `<div class="${UI.card} p-8 mt-6"><p class="text-sm text-ink-soft">Даты пока не указаны.</p></div>`;
    }
    const items = sch.stages.map(stage => {
        const label = STAGE_TYPE_LABELS[stage.type] || stage.type;
        const start = formatDateTime(stage.start_at);
        const end = stage.end_at ? ' — ' + formatDateTime(stage.end_at) : '';
        const dot = stage.status === 'ACTIVE'
            ? 'bg-sage border-ink'
            : stage.status === 'FINISHED'
                ? 'bg-mist border-ink/40'
                : 'bg-white border-ink/40';
        return `
        <li class="relative pl-9 pb-6 last:pb-0">
            <span class="absolute left-0 top-1 w-4 h-4 rounded-full border-2 ${dot}" aria-hidden="true"></span>
            <div class="flex flex-wrap items-center gap-2">
                <h3 class="font-semibold text-ink">${escHtml(stage.name)}</h3>
                <span class="text-xs font-semibold text-ink-soft">${escHtml(label)}</span>
                ${stageStatusBadge(stage.status)}
            </div>
            <p class="mt-1 text-sm text-ink-soft">${escHtml(start)}${escHtml(end)}</p>
        </li>`;
    }).join('');
    return `
    <div class="${UI.card} p-8 mt-6">
        ${sch.season ? `<p class="${UI.eyebrow} mb-6">Сезон ${escHtml(sch.season)}</p>` : ''}
        <ol class="list-none">${items}</ol>
    </div>`;
}

function splitList(text) {
    return text.split(/[;,]/).map(s => s.trim()).filter(Boolean);
}

function olympiadCard(oly) {
    const subjects = (Array.isArray(oly.subjects) ? oly.subjects : []).slice(0, 3);
    const levels = (Array.isArray(oly.levels) ? oly.levels : []).join('‑');
    const years = (Array.isArray(oly.years) ? oly.years : []).slice(0, 3).join(', ');
    const accent = oly.status === 'ARCHIVED' ? 'bg-crimson'
        : oly.status === 'DRAFT' ? 'bg-sand'
        : 'bg-sage';
    const phaseInfo = (oly.current_status || oly.next_deadline)
        ? `<div class="mt-3 flex flex-wrap items-center gap-2">
            ${oly.current_status ? phaseStatusBadge(oly.current_status) : ''}
            ${oly.next_deadline ? `<span class="text-xs font-semibold text-ink">Дедлайн ${escHtml(formatDateTime(oly.next_deadline))}</span>` : ''}
        </div>`
        : '';
    return `
    <a href="#/olympiads/${oly.id}"
       title="${escAttr(oly.name)}"
       class="group flex flex-col bg-white shadow-elev-1 hover:shadow-elev-2 hover:-translate-y-0.5 transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/60">
        <div class="h-1 ${accent}" aria-hidden="true"></div>
        <div class="p-5 flex flex-col grow">
            <div class="flex items-start justify-between gap-2">
                <h2 class="font-bold text-ink leading-snug line-clamp-2">${escHtml(oly.name)}</h2>
                ${statusBadge(oly.status)}
            </div>
            ${oly.description ? `<p class="mt-2 text-sm text-ink-soft leading-relaxed line-clamp-2">${escHtml(oly.description)}</p>` : ''}
            ${phaseInfo}
            ${subjects.length ? `
            <div class="mt-3 flex flex-wrap gap-1.5">
                ${subjects.map(s => `<span class="${UI.badge} ${UI.badgeNeutral}">${escHtml(s)}</span>`).join('')}
            </div>` : ''}
            <div class="mt-auto pt-4 flex items-center justify-between gap-3 text-xs">
                ${levels ? `<span class="font-semibold text-ink">уровень ${escHtml(levels)}</span>` : '<span></span>'}
                ${years ? `<span class="text-ink-soft">${escHtml(years)}</span>` : ''}
            </div>
            <p class="mt-3 text-sm font-semibold text-ink group-hover:text-black transition-colors">Подробнее →</p>
        </div>
    </a>`;
}

function stagesEditorHtml(stages, season, error) {
    const rows = (stages || []).map((s, i) => `
        <div class="grid gap-3 bg-mist/60 rounded p-3 stage-row" data-stage-row="${i}">
            <div class="flex items-center justify-between gap-2">
                <span class="text-xs font-bold text-ink-soft uppercase tracking-wide">Этап ${i + 1}</span>
                <button type="button" data-stage-remove="${i}" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall} text-crimson hover:text-crimson stage-remove">Удалить</button>
            </div>
            <input class="${UI.input}" data-stage-field="name" value="${escAttr(s.name || '')}" placeholder="Название, напр. «Отборочный тур»">
            <select class="${UI.input}" data-stage-field="type">
                ${Object.entries(STAGE_TYPE_LABELS).map(([val, lab]) => `<option value="${val}" ${s.type === val ? 'selected' : ''}>${escHtml(lab)}</option>`).join('')}
            </select>
            <div class="grid grid-cols-2 gap-3">
                <label class="block">
                    <span class="text-xs font-semibold text-ink-soft">Начало</span>
                    <input type="datetime-local" class="${UI.input} mt-1" data-stage-field="start_at" value="${escAttr(toLocalInput(s.start_at || ''))}">
                </label>
                <label class="block">
                    <span class="text-xs font-semibold text-ink-soft">Конец (необязательно)</span>
                    <input type="datetime-local" class="${UI.input} mt-1" data-stage-field="end_at" value="${escAttr(toLocalInput(s.end_at || ''))}">
                </label>
            </div>
        </div>`).join('');
    return `
    <div class="rounded border border-mist p-4">
        <div class="flex items-center justify-between mb-3">
            <p class="text-sm font-semibold text-ink">Этапы и даты</p>
            <button type="button" id="stage-add" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">+ Добавить этап</button>
        </div>
        <input id="oly-season" class="${UI.input} mb-3" placeholder="Сезон, напр. 2026/27" value="${escAttr(season || '')}">
        <p class="text-xs text-ink-faint mb-3">Даты появятся на странице олимпиады (timeline). Оставьте поле пустым, если даты пока неизвестны.</p>
        <div class="space-y-3">${rows || '<p class="text-sm text-ink-faint">Этапов пока нет.</p>'}</div>
        ${error ? `<p class="mt-3 text-sm text-crimson">${escHtml(error)}</p>` : ''}
    </div>`;
}

/* Собрать этапы из DOM редактора и провалидировать их клиентски. */
function collectStagesFromEditor(overlay) {
    const out = [];
    overlay.querySelectorAll('.stage-row').forEach((row, i) => {
        const name = row.querySelector('[data-stage-field="name"]').value.trim();
        const type = row.querySelector('[data-stage-field="type"]').value;
        const start = toLocalIso(row.querySelector('[data-stage-field="start_at"]').value);
        const end = toLocalIso(row.querySelector('[data-stage-field="end_at"]').value);
        if (!name && !start && !end) return;
        if (!name) throw new Error('У одного из этапов не указано название');
        if (!start) throw new Error(`У этапа «${name}» не указано время начала`);
        if (end && new Date(end) < new Date(start)) throw new Error(`У этапа «${name}» начало позже конца`);
        out.push({
            /* Сервер требует уникальный id; генерируем по типу + номеру. */
            id: `${type.toLowerCase()}_${i + 1}`,
            name,
            type,
            start_at: start,
            end_at: end || null,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
        });
    });
    return out;
}

function openOlympiadModal(onDone, oly = null, orgs = []) {
    const isOrgAdmin = store.user.role === 'ORGANIZATION_ADMIN';
    const data = oly || {};
    const orgOptions = orgs.length
        ? orgs.map(o => ({ value: o.id, label: o.name }))
        : [];
    const body = `
    <form id="oly-form" class="space-y-4">
        <div id="modal-alert"></div>
        ${inputField({ id: 'oly-name', name: 'name', label: 'Название', value: data.name || '', required: true })}
        ${isOrgAdmin
            ? `<input type="hidden" id="oly-org" value="${escAttr(store.user.organization_id || '')}">`
            : selectField({ id: 'oly-org', name: 'organizer', label: 'Организатор', value: data.organizer_ids && data.organizer_ids[0], options: orgOptions })}
        ${inputField({ id: 'oly-subjects', name: 'subjects', label: 'Предметы (через запятую)', value: (data.subjects || []).join(', ') })}
        ${inputField({ id: 'oly-levels', name: 'levels', label: 'Уровни РСОШ (1, 2, 3)', value: (data.levels || []).join(', ') })}
        ${inputField({ id: 'oly-years', name: 'years', label: 'Годы (2000, 2001…)', value: (data.years || []).join(', ') })}
        ${textareaField({ id: 'oly-desc', name: 'description', label: 'Описание', value: data.description || '' })}
        ${oly ? selectField({
            id: 'oly-status', name: 'status', label: 'Статус', value: data.status || 'DRAFT',
            options: [
                { value: 'DRAFT', label: 'Черновик' },
                { value: 'PUBLISHED', label: 'Опубликована' },
                { value: 'ARCHIVED', label: 'Архив' },
            ],
        }) : ''}
        <div id="stage-editor-root" class="${UI.field} mt-8"></div>
        <button type="submit" class="${UI.btn} ${UI.btnPrimary} w-full">${oly ? 'Сохранить' : 'Создать'}</button>
    </form>`;
    const { overlay, close } = openModal(oly ? 'Редактирование олимпиады' : 'Новая олимпиада', body, { wide: true });

    /* ----- Конструктор этапов ----- */
    const stages = (data.schedule && Array.isArray(data.schedule.stages))
        ? data.schedule.stages.map(s => ({
            id: s.id || '',
            name: s.name || '',
            type: s.type || 'QUALIFICATION',
            start_at: s.start_at || '',
            end_at: s.end_at || '',
        }))
        : [];
    let seasonValue = data.schedule && data.schedule.season ? data.schedule.season : '';
    let stageError = '';

    function renderStageEditor() {
        const root = overlay.querySelector('#stage-editor-root');
        if (!root) return;
        root.innerHTML = stagesEditorHtml(stages, seasonValue, stageError);
        const addBtn = root.querySelector('#stage-add');
        if (addBtn) addBtn.addEventListener('click', () => {
            stages.push({ id: '', name: '', type: 'QUALIFICATION', start_at: '', end_at: '' });
            stageError = '';
            renderStageEditor();
        });
        root.querySelectorAll('.stage-remove').forEach(btn => {
            btn.addEventListener('click', () => {
                stages.splice(Number(btn.dataset.stageRemove), 1);
                stageError = '';
                renderStageEditor();
            });
        });
        const season = root.querySelector('#oly-season');
        if (season) season.addEventListener('input', e => { seasonValue = e.target.value; });
        /* Держим in-memory массив в синхроне с DOM для перерисовки. */
        root.querySelectorAll('.stage-row').forEach(row => {
            const idx = Number(row.dataset.stageRow);
            row.querySelectorAll('[data-stage-field]').forEach(field => {
                field.addEventListener('input', () => {
                    stages[idx][field.dataset.stageField] =
                        (field.dataset.stageField === 'start_at' || field.dataset.stageField === 'end_at')
                            ? toLocalIso(field.value)
                            : field.value;
                });
            });
        });
    }
    renderStageEditor();

    overlay.querySelector('#oly-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = overlay.querySelector('button[type="submit"]');
        btn.disabled = true;
        const orgId = overlay.querySelector('#oly-org').value;
        const payload = {
            name: overlay.querySelector('#oly-name').value.trim(),
            subjects: splitList(overlay.querySelector('#oly-subjects').value),
            levels: splitList(overlay.querySelector('#oly-levels').value),
            years: splitList(overlay.querySelector('#oly-years').value),
            description: overlay.querySelector('#oly-desc').value.trim() || null,
            organizer_ids: orgId ? [orgId] : (data.organizer_ids || []),
        };
        if (oly) payload.status = overlay.querySelector('#oly-status').value;

        /* Этапы: валидация до запроса; пустой список = «даты пока не указаны». */
        try {
            const collected = collectStagesFromEditor(overlay);
            const season = seasonValue.trim() || null;
            if (season && !collected.length) throw new Error('Указан сезон, но нет ни одного этапа');
            payload.schedule = collected.length
                ? { season: season, stages: collected }
                : null;
        } catch (err) {
            showModalError(overlay, { data: { detail: err.message || 'Ошибка в расписании' } });
            btn.disabled = false;
            return;
        }

        try {
            const res = oly
                ? await api.updateOlympiad(oly.id, payload)
                : await api.createOlympiad(payload);
            if (res.ok) {
                close();
                showToast(oly ? 'Олимпиада обновлена' : 'Олимпиада создана', 'success');
                if (onDone) onDone();
            } else {
                showModalError(overlay, res);
                btn.disabled = false;
            }
        } catch {
            showModalError(overlay, { data: { detail: 'Сетевая ошибка' } });
            btn.disabled = false;
        }
    });
}

async function renderOlympiads() {
    const page = document.getElementById('page');
    if (!store.user) { navigate('#/auth'); return; }
    page.innerHTML = loadingHtml('Загружаем олимпиады…');

    const [listRes, orgRes] = await Promise.all([
        api.getOlympiads().catch(() => null),
        store.isAdmin() ? api.getOrganizations().catch(() => null) : Promise.resolve(null),
    ]);
    if (!listRes || !listRes.ok) {
        page.innerHTML = `${alertHtml(listRes ? errorText(listRes) : 'Сетевая ошибка', 'error')}
            <button id="oly-retry" class="${UI.btn} ${UI.btnPrimary} mt-4">Повторить</button>`;
        page.querySelector('#oly-retry').addEventListener('click', renderOlympiads);
        return;
    }

    const olympiads = Array.isArray(listRes.data) ? listRes.data : [];
    const orgs = orgRes && orgRes.ok && Array.isArray(orgRes.data) ? orgRes.data : [];
    const canManage = store.isAdmin() || store.user.role === 'ORGANIZATION_ADMIN';

    page.innerHTML = `
    <section class="pt-4 pb-16 md:pb-20">
        <div class="flex flex-wrap items-end justify-between gap-6">
            <div class="max-w-2xl">
                <p class="${UI.eyebrow}">Каталог</p>
                <h1 class="mt-4 text-4xl md:text-5xl font-extrabold tracking-tight leading-[1.08]">Олимпиады</h1>
                <p class="mt-6 text-lg text-ink-soft leading-relaxed">Перечень РСОШ и другие олимпиады для школьников. Откройте карточку, чтобы узнать подробности.</p>
            </div>
            ${canManage ? `<button id="oly-create" class="${UI.btn} ${UI.btnPrimary}">Создать</button>` : ''}
        </div>
        ${olympiads.length === 0
            ? `<div class="mt-16">${alertHtml('Олимпиад пока нет', 'error')}</div>`
            : `<div class="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">${olympiads.map(olympiadCard).join('')}</div>`}
    </section>`;

    const createBtn = page.querySelector('#oly-create');
    if (createBtn) createBtn.addEventListener('click', () => openOlympiadModal(renderOlympiads, null, orgs));
}

async function renderOlympiad(olyId) {
    const page = document.getElementById('page');
    if (!store.user) { navigate('#/auth'); return; }
    page.innerHTML = loadingHtml('Загружаем олимпиаду…');

    const [olyRes, orgRes] = await Promise.all([
        api.getOlympiad(olyId).catch(() => null),
        store.isAdmin() ? api.getOrganizations().catch(() => null) : Promise.resolve(null),
    ]);
    if (!olyRes || !olyRes.ok) {
        page.innerHTML = `${alertHtml(olyRes ? errorText(olyRes) : 'Сетевая ошибка', 'error')}
            <button id="oly-back" class="${UI.btn} ${UI.btnPrimary} mt-4">Назад</button>`;
        page.querySelector('#oly-back').addEventListener('click', () => navigate('#/olympiads'));
        return;
    }
    const oly = olyRes.data;
    const orgs = orgRes && orgRes.ok && Array.isArray(orgRes.data) ? orgRes.data : [];
    const orgIndex = Object.fromEntries(orgs.map(o => [o.id, o.name]));
    const canManage = store.isAdmin() || store.user.role === 'ORGANIZATION_ADMIN';

    const rows = [
        ['Статус', statusBadge(oly.status)],
        ['Предметы', (oly.subjects || []).join(', ')],
        ['Уровни', (oly.levels || []).join(', ')],
        ['Годы', (oly.years || []).join(', ')],
        ['Организаторы', (oly.organizer_ids || []).map(id => orgIndex[id] || id).join(', ')],
        ['Описание', oly.description],
        ['Регистрация', oly.registration_url ? `<a class="text-ember" href="${escAttr(oly.registration_url)}" target="_blank" rel="noopener">${escHtml(oly.registration_url)}</a>` : null],
        ['Официальный сайт', oly.official_url ? `<a class="text-ember" href="${escAttr(oly.official_url)}" target="_blank" rel="noopener">${escHtml(oly.official_url)}</a>` : null],
    ];
    if (oly.current_status) rows.push(['Текущий статус', phaseStatusBadge(oly.current_status)]);
    if (oly.next_deadline) rows.push(['Ближайший дедлайн', formatDateTime(oly.next_deadline)]);

    page.innerHTML = `
    <section class="max-w-3xl mx-auto px-4 py-8">
        <nav class="mb-4"><a href="#/olympiads" class="text-sm text-ember">← Все олимпиады</a></nav>
        <div class="flex items-start justify-between gap-4 mb-6">
            <h1 class="text-2xl font-bold">${escHtml(oly.name)}</h1>
            ${canManage ? `
            <div class="flex gap-2 shrink-0">
                <button id="oly-edit" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Редактировать</button>
                <button id="oly-delete" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}">Удалить</button>
            </div>` : ''}
        </div>
        <div class="${UI.card} divide-y divide-mist">
            ${rows.filter(([, v]) => v !== null && v !== '').map(([label, value]) => `
                <div class="flex justify-between gap-4 py-3">
                    <dt class="text-sm text-ink-soft shrink-0">${escHtml(label)}</dt>
                    <dd class="text-sm text-right">${value}</dd>
                </div>`).join('')}
        </div>
        ${scheduleTimelineHtml(oly)}
    </section>`;

    const editBtn = page.querySelector('#oly-edit');
    if (editBtn) editBtn.addEventListener('click', () => openOlympiadModal(renderOlympiad.bind(null, oly.id), oly, orgs));

    const deleteBtn = page.querySelector('#oly-delete');
    if (deleteBtn) deleteBtn.addEventListener('click', async () => {
        if (!window.confirm(`Удалить олимпиаду «${oly.name}»?`)) return;
        deleteBtn.disabled = true;
        const res = await api.deleteOlympiad(oly.id).catch(() => null);
        if (res && res.ok) {
            showToast('Олимпиада удалена', 'success');
            navigate('#/olympiads');
        } else {
            showToast(res ? errorText(res) : 'Сетевая ошибка', 'error');
            deleteBtn.disabled = false;
        }
    });
}