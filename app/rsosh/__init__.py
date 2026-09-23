"""RSOSH-импорт: preprocessing -> extraction -> parsing -> matching -> validation.

Представлен в REST-слое как /api/v1/imports/*, состояние хранится на документе
(см. app.rsosh.states), персист выполняется только по явному confirm админа.
"""