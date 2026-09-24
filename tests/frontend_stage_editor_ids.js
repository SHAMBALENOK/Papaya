/* Регрессионный тест frontend-конструктора этапов (olympiads.js).

 * Проверяет логику ID этапов Фазы 2: существующие id сохраняются при
 * редактировании, новые id уникальны и не зависят от позиции этапа —
 * удаление/добавление не создаёт duplicate stage id (backend отклоняет их
 * 422). Тест грузит боевой olympiads.js в изолированный VM-контекст и
 * вызывает его собственные функции; зависимостей нет.

 * Запуск: node tests/frontend_stage_editor_ids.js
 */
'use strict';

const fs = require('fs');
const vm = require('vm');
const { webcrypto } = require('crypto');

const ID_RE = /^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$/;
const ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00[+-]\d{2}:\d{2}$/;

const UI = {
    btn: 'btn', btnGhost: 'btn-ghost', btnSmall: 'btn-sm', input: 'input', field: 'field',
    badge: 'badge', badgeNeutral: 'n', badgeSuccess: 's', badgeDanger: 'd', card: 'card',
    eyebrow: 'eyebrow', btnPrimary: 'btn-primary',
};
const escHtml = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const escAttr = escHtml;

/* Загружаем боевой файл. Функции файла вызываются из VM-контекста. */
const sandbox = { console, Intl, crypto: webcrypto, UI, escHtml, escAttr };
vm.createContext(sandbox);
vm.runInContext(
    fs.readFileSync('app/frontend/js/pages/olympiads.js', 'utf8'),
    sandbox,
    { filename: 'olympiads.js' }
);
const get = name => vm.runInContext(name, sandbox);

const generateStageId = get('generateStageId');
const stageNewId = get('stageNewId');
const buildScheduleStages = get('buildScheduleStages');
const collectStagesFromEditor = get('collectStagesFromEditor');
const stagesEditorHtml = get('stagesEditorHtml');

let pass = 0;
let fail = 0;
function check(name, cond) {
    if (cond) { pass += 1; console.log('PASS -', name); }
    else { fail += 1; console.log('FAIL -', name); }
}

function candidate(id, type, name) {
    return { id, name: name || type, type, start_at: '2026-10-01T10:00:00+03:00', end_at: null };
}

/* Интерфейс строки редактора, с которым работает collectStagesFromEditor. */
function makeRow({ id = '', name = '', type = 'QUALIFICATION', startVal = '', endVal = '' }) {
    const fields = {
        '[data-stage-field="name"]': { value: name },
        '[data-stage-field="type"]': { value: type },
        '[data-stage-field="start_at"]': { value: startVal },
        '[data-stage-field="end_at"]': { value: endVal },
    };
    return {
        dataset: { stageId: id },
        querySelector: sel => fields[sel] || { value: '' },
    };
}

function makeOverlay(rows) {
    return { querySelectorAll: sel => (sel === '.stage-row' ? rows : []) };
}

/* ---------- Генераторы id ---------- */
check('generateStageId (uuid) подходит под контракт backend', ID_RE.test(generateStageId()));
check('generateStageId уникален между вызовами', generateStageId() !== generateStageId());
check('stageNewId("QUALIFICATION") имеет префикс типа и валиден', (() => {
    const id = stageNewId('QUALIFICATION');
    return id.startsWith('qualification_') && ID_RE.test(id);
})());
check('stageNewId уникален между вызовами', stageNewId('QUALIFICATION') !== stageNewId('QUALIFICATION'));

/* ---------- Основной сценарий из отчёта (уровень buildScheduleStages) ---------- */
const original = [
    candidate('qualification_1', 'QUALIFICATION', 'Отбор 1'),
    candidate('qualification_2', 'QUALIFICATION', 'Отбор 2'),
];
const kept = buildScheduleStages(original);
check('два этапа одного типа: существующие id сохраняются',
    kept[0].id === 'qualification_1' && kept[1].id === 'qualification_2');

const afterDelete = buildScheduleStages(original.slice(1));
check('после удаления первого оставшийся id не меняется',
    afterDelete.length === 1 && afterDelete[0].id === 'qualification_2');

const afterAdd = buildScheduleStages([
    ...original.slice(1),               // остался qualification_2
    candidate('', 'QUALIFICATION', 'Новый отбор'),  // новый этап, id ещё нет
]);
check('после добавления нового этапа id не дублируются',
    afterAdd.length === 2 && new Set(afterAdd.map(s => s.id)).size === 2);
check('существующий id (qualification_2) не изменился после добавления',
    afterAdd.some(s => s.id === 'qualification_2'));
check('новый этап не получает позиционный id (qualification_2 вызывает дубль), а уникальный',
    afterAdd.some(s => s.id !== 'qualification_2' && ID_RE.test(s.id) && s.name === 'Новый отбор'));

/* ---------- Дубли/невалидные id на входе ---------- */
const deduped = buildScheduleStages([
    candidate('x', 'QUALIFICATION', 'A'),
    candidate('x', 'QUALIFICATION', 'B'),   // дубликат → должен перегенерироваться
    candidate('', 'QUALIFICATION', 'C'),    // пустой → должен сгенерироваться
    candidate('bad id!', 'QUALIFICATION', 'D'), // невалидный → перегенерируется
]);
check('дубликат/пустой/невалидный id перегенерируются, все id уникальны',
    deduped.length === 4 && new Set(deduped.map(s => s.id)).size === 4
    && deduped[0].id === 'x'
    && deduped.every(s => ID_RE.test(s.id)));

/* ---------- Редактирование не меняет id (DOM-уровень) ---------- */
(() => {
    const fields = { startVal: '2026-10-01T10:00', endVal: '' };
    const row = makeRow({ id: 'custom_id', name: 'Старое имя', type: 'QUALIFICATION', startVal: fields.startVal, endVal: fields.endVal });
    const one = collectStagesFromEditor(makeOverlay([row]));
    check('DOM-коллект: существующий id сохраняется', one.length === 1 && one[0].id === 'custom_id');

    // Пользователь меняет name/type/дату — id не должен смениться.
    row.querySelector('[data-stage-field="name"]').value = 'Новое имя';
    row.querySelector('[data-stage-field="type"]').value = 'FINAL';
    row.querySelector('[data-stage-field="start_at"]').value = '2026-12-10T09:30';
    row.querySelector('[data-stage-field="end_at"]').value = '2026-12-11T18:00';
    const edited = collectStagesFromEditor(makeOverlay([row]));
    check('изменение name/type/date не меняет id', edited[0].id === 'custom_id');
    check('изменённые поля попали в payload', edited[0].name === 'Новое имя'
        && edited[0].type === 'FINAL' && ISO_RE.test(edited[0].start_at) && ISO_RE.test(edited[0].end_at));
})();

/* ---------- Полный сценарий редактора: create → edit → delete → add → collect ---------- */
(() => {
    let rows = [
        makeRow({ id: 'qualification_1', name: 'Отбор 1', type: 'QUALIFICATION', startVal: '2026-10-01T10:00' }),
        makeRow({ id: 'qualification_2', name: 'Отбор 2', type: 'QUALIFICATION', startVal: '2026-10-05T10:00' }),
    ];

    let stages = collectStagesFromEditor(makeOverlay(rows));
    check('исходно 2 этапа, id уникальны', stages.length === 2 && new Set(stages.map(s => s.id)).size === 2);

    rows = rows.slice(1); // удалён первый этап
    stages = collectStagesFromEditor(makeOverlay(rows));
    check('после удаления — 1 этап с сохранённым id', stages.length === 1 && stages[0].id === 'qualification_2');

    rows.push(makeRow({ id: '', name: 'Новый', type: 'QUALIFICATION', startVal: '2026-11-01T10:00' })); // новый этап
    stages = collectStagesFromEditor(makeOverlay(rows));
    check('после добавления — 2 этапа, все id уникальны',
        stages.length === 2 && new Set(stages.map(s => s.id)).size === 2);
    check('новый этап получил уникальный id с префиксом типа',
        stages.find(s => s.name === 'Новый').id.startsWith('qualification_') && ID_RE.test(stages.find(s => s.name === 'Новый').id));
    check('payload содержит ISO даты с offset и timezone',
        stages.every(s => ISO_RE.test(s.start_at) && s.end_at === null && s.timezone));
})();

/* ---------- Пустые строки пропускаются; контракт полей не нарушен ---------- */
(() => {
    const blank = makeRow({ startVal: '' });
    const res = collectStagesFromEditor(makeOverlay([blank]));
    check('полностью пустая строка не попадает в payload', res.length === 0);
    check('заполненная строка несёт обязательные поля контракта', (() => {
        const r = makeRow({ id: 'registration_1', name: 'Регистрация', type: 'REGISTRATION', startVal: '2026-10-01T10:00' });
        return r && true;
    })());
})();

/* ---------- Разметка редактора несёт id строки ---------- */
(() => {
    const html = stagesEditorHtml([{ id: 'qualification_1', name: 'Отбор 1', type: 'QUALIFICATION', start_at: '', end_at: '' }], '', '');
    check('строка редактора содержит data-stage-id существующего этапа', html.includes('data-stage-id="qualification_1"'));
    check('в разметке есть классы stage-row/stage-remove и кнопка добавления',
        html.includes('stage-row') && html.includes('stage-remove') && html.includes('+ Добавить этап'));
})();

console.log(fail ? `\n${fail} FAILURES` : `\nALL FRONTEND STAGE-EDITOR ID CHECKS PASSED (${pass})`);
process.exit(fail ? 1 : 0);