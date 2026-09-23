/* ==========================================================================
 * pages/imports.js — статус и предпросмотр RSOSH-импорта с подтверждением.
 * Бэкенд: app/routers/imports.py (#/imports/{import_id}).
 * ========================================================================== */

const IMP_STATE_LABELS = {
    processing: 'Обработка…',
    review: 'Ожидает подтверждения',
    approved: 'Подтверждён',
    rejected: 'Отклонён',
    failed: 'Ошибка',
};

function impSummaryHtml(summary) {
    if (!summary) return '';
    return `
    <div class="grid grid-cols-2 sm:grid-cols-5 gap-3">
        ${[['Найдено', summary.total], ['Новые', summary.new], ['Объединить', summary.merge],
           ['Дубликаты', summary.duplicate], ['Требуют проверки', summary.review]].map(([label, value]) => `
            <div class="bg-mist rounded p-3 text-center">
                <p class="text-xl font-bold">${escHtml(String(value))}</p>
                <p class="text-xs text-ink-soft">${escHtml(label)}</p>
            </div>`).join('')}
    </div>`;
}

function actionBadge(action) {
    const map = { create: [UI.badgeSuccess, 'Создать'],
                  merge: [UI.badgeNeutral, 'Объединить'],
                  skip: [UI.badgeDanger, 'Пропустить'] };
    const [cls, label] = map[action] || [UI.badgeNeutral, action || '—'];
    return `<span class="${UI.badge} ${cls}">${escHtml(label)}</span>`;
}

function confidenceBadge(conf) {
    return conf === 'review'
        ? `<span class="${UI.badge} ${UI.badgeDanger}">проверка</span>`
        : `<span class="${UI.badge} ${UI.badgeSuccess}">ok</span>`;
}

function candidateRow(cand) {
    const reviews = Array.isArray(cand.reviews) && cand.reviews.length
        ? `<p class="text-xs text-crimson">${cand.reviews.map(escHtml).join('; ')}</p>` : '';
    return `
    <tr class="border-b border-mist align-top">
        <td class="py-3 pr-3 min-w-0">
            <p class="font-medium">${escHtml(cand.name || '—')}</p>
            <p class="text-xs text-ink-soft break-all">${escHtml(cand.name_norm || '')}</p>
        </td>
        <td class="py-3 pr-3 text-sm">${escHtml((cand.subjects || []).join(', '))}</td>
        <td class="py-3 pr-3 text-sm">${escHtml((cand.levels || []).join(', '))}</td>
        <td class="py-3 pr-3 text-sm whitespace-nowrap">${escHtml((cand.years || []).join(', '))}</td>
        <td class="py-3 pr-3 whitespace-nowrap">${actionBadge(cand.action)}</td>
        <td class="py-3 whitespace-nowrap">${confidenceBadge(cand.confidence)}${reviews}</td>
    </tr>`;
}

async function renderImport(importId) {
    const page = document.getElementById('page');
    if (!store.user) { navigate('#/auth'); return; }
    page.innerHTML = loadingHtml('Загружаем импорт…');

    const [statusRes, previewRes] = await Promise.all([
        api.getImportStatus(importId).catch(() => null),
        api.getImportPreview(importId).catch(() => null),
    ]);
    if (!statusRes || !statusRes.ok) {
        page.innerHTML = `${alertHtml(statusRes ? errorText(statusRes) : 'Сетевая ошибка', 'error')}
            <button id="imp-back" class="${UI.btn} ${UI.btnPrimary} mt-4">← Документы</button>`;
        page.querySelector('#imp-back').addEventListener('click', () => navigate('#/docs'));
        return;
    }

    const status = statusRes.data;
    const state = status.status;
    const preview = previewRes && previewRes.ok ? previewRes.data : null;
    const candidates = preview ? preview.candidates : [];
    const canConfirm = state === 'review';

    page.innerHTML = `
    <section class="max-w-5xl mx-auto px-4 py-8">
        <nav class="mb-4"><a href="#/docs" class="text-sm text-ember">← Документы</a></nav>
        <header class="flex flex-wrap items-start justify-between gap-4 mb-6">
            <div>
                <h1 class="text-2xl font-bold">RSOSH-импорт</h1>
                <p class="text-sm text-ink-soft mt-1">${escHtml(IMP_STATE_LABELS[state] || state)}</p>
                ${status.error ? `<p class="mt-2 text-sm text-crimson">${escHtml(status.error)}</p>` : ''}
            </div>
            <div class="flex gap-2">
                <button id="imp-refresh" class="${UI.btn} ${UI.btnGhost} ${UI.btnSmall}">Обновить</button>
                ${canConfirm ? `
                <button id="imp-confirm" class="${UI.btn} ${UI.btnPrimary} ${UI.btnSmall}">Подтвердить импорт</button>
                <button id="imp-reject" class="${UI.btn} ${UI.btnDanger} ${UI.btnSmall}">Отклонить</button>` : ''}
            </div>
        </header>
        ${preview ? impSummaryHtml(preview.summary) : ''}
        ${state === 'processing'
            ? `<div class="mt-6">${alertHtml('Импорт выполняется в фоне. Обновите страницу через несколько секунд.', 'info')}</div>`
            : ''}
        ${candidates.length
            ? `
        <div class="mt-6 overflow-x-auto">
            <table class="w-full min-w-[720px] text-left">
                <thead>
                    <tr class="text-xs text-ink-soft uppercase">
                        <th class="py-2 pr-3">Олимпиада</th>
                        <th class="py-2 pr-3">Предметы</th>
                        <th class="py-2 pr-3">Уровни</th>
                        <th class="py-2 pr-3">Годы</th>
                        <th class="py-2 pr-3">Действие</th>
                        <th class="py-2">Проверка</th>
                    </tr>
                </thead>
                <tbody>${candidates.slice(0, 500).map(candidateRow).join('')}</tbody>
            </table>
            ${candidates.length > 500 ? `<p class="text-xs text-ink-soft mt-2">Показаны первые 500 из ${candidates.length}</p>` : ''}
        </div>` : ''}
    </section>`;

    page.querySelector('#imp-refresh').addEventListener('click', () => renderImport(importId));

    const confirmBtn = page.querySelector('#imp-confirm');
    if (confirmBtn) confirmBtn.addEventListener('click', async () => {
        if (!window.confirm(`Подтвердить импорт и создать ${(preview && preview.summary && preview.summary.new) || 0} новых олимпиад?`)) return;
        confirmBtn.disabled = true;
        const res = await api.confirmImport(importId).catch(() => null);
        if (res && res.ok) {
            showToast('Импорт подтверждён и применён', 'success');
            renderImport(importId);
        } else {
            showToast(res ? errorText(res) : 'Сетевая ошибка', 'error');
            confirmBtn.disabled = false;
        }
    });

    const rejectBtn = page.querySelector('#imp-reject');
    if (rejectBtn) rejectBtn.addEventListener('click', async () => {
        if (!window.confirm('Отклонить импорт? Ничего не будет создано.')) return;
        rejectBtn.disabled = true;
        const res = await api.rejectImport(importId).catch(() => null);
        if (res && res.ok) {
            showToast('Импорт отклонён', 'info');
            renderImport(importId);
        } else {
            showToast(res ? errorText(res) : 'Сетевая ошибка', 'error');
            rejectBtn.disabled = false;
        }
    });
}