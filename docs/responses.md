# Papaya API — справочник ответов

> Базовый путь: `/api/v1`. Полная интерактивная схема: http://localhost:5000/docs
>
> Документ описывает фактические ответы API: состав полей, коды и смысл.
> Примеры сокращены до существенных полей.

## Общие правила

- Ошибка всегда в формате `{"detail": ...}`; внутренние детали исключений
  наружу не отдаются.
- Неизвестный путь под `/api/v1/` → `404 {"detail": "Not found"}` (не HTML SPA).
- Каталоги и поиск публичные: авторизация не требуется.
- Авторизация — JWT в HttpOnly-cookies (`access_jwt`, `refresh_jwt`).
- Роль читается из актуальной версии пользователя (кэш с версионированием),
  поэтому понижение прав действует сразу.
- Заблокированный пользователь (`isActive=false`) в авторизованных маршрутах
  получает `403 {"detail": "Account is blocked"}` (действующая сессия
  перестаёт работать сразу при блокировке) и не может войти заново.

---

## GET /

Текущий пользователь по cookie-токенам.

| Code | Description | Body |
|------|-------------|------|
| 200 | Профиль текущего пользователя | `{"id", "email", "name", "surname", "role", "university_id", "isActive", "gender", "bday", "bio", "phone", "country", "region", "status", "createdAt", "updatedAt"}` |
| 401 | Access token missing | `{"detail": "Access token missing"}` |
| 403 | Невалидный токен или аккаунт заблокирован | `{"detail": "Invalid access token"}` / `{"detail": "Account is blocked"}` |
| 404 | Пользователь не найден | `{"detail": "User not found"}` |
| 500 | Внутренняя ошибка | `{"detail": "Internal server error"}` |

---

## POST /auth/register

**Request body:** `{"name": str, "surname": str, "email": str, "password": str}`

| Code | Description | Body |
|------|-------------|------|
| 201 | Пользователь создан, cookies установлены | `UserResponse` (см. `GET /`) |
| 400 | Пароль не проходит проверку | `{"detail": "Пароль должен содержать минимум 8 символов"}` |
| 409 | Email уже занят | `{"detail": "You already have account"}` |
| 422 | Ошибка валидации | `{"detail": [...]}` |

---

## POST /auth/login

**Request body:** `{"email": str, "password": str}`

| Code | Description | Body |
|------|-------------|------|
| 200 | Вход выполнен, cookies установлены | `UserResponse` |
| 401 | Неверный email или пароль | `{"detail": "Invalid email or password"}` |
| 403 | Аккаунт заблокирован | `{"detail": "Account is blocked"}` |
| 422 | Ошибка валидации | `{"detail": [...]}` |

---

## GET /user/{user_id}

Профиль пользователя по id (страница профиля и запасной путь клиента).

| Code | Description | Body |
|------|-------------|------|
| 200 | Профиль | `UserResponse` |
| 401 / 403 | Токен отсутствует, невалиден или аккаунт заблокирован | `{"detail": "..."}` |
| 404 | Пользователь не найден | `{"detail": "User not found"}` |

---

## POST /user/{user_id}/edit_info

Изменение собственного профиля. Роль и привязка к университету здесь не
меняются — это делает администратор.

| Code | Description | Body |
|------|-------------|------|
| 200 | Профиль обновлён | `UserResponse` |
| 400 | Пустое тело | `{"detail": "No fields to update"}` |
| 403 | Чужой профиль, занятый email, невалидный токен или блокировка | `{"detail": "You can only edit your own profile"}` |
| 404 | Пользователь не найден | `{"detail": "User not found"}` |
| 409 | Email занят другим пользователем | `{"detail": "Email is already taken by another user"}` |

---

## POST /auth/logout

| Code | Description | Body |
|------|-------------|------|
| 200 | Cookies удалены | `null` |
| 401 / 403 | Токен отсутствует или невалиден | `{"detail": "..."}` |

---

## GET /universities

Каталог университетов. Публично.

**Query:** `search` (по названию, краткому названию, описанию), `limit`.

| Code | Description | Body |
|------|-------------|------|
| 200 | Список вузов | `{"universities": [{"id", "name", "short_name", "description", "website", "image"}]}` |
| 500 | Внутренняя ошибка | `{"detail": "Internal server error"}` |

---

## GET /universities/{university_id}

| Code | Description | Body |
|------|-------------|------|
| 200 | Карточка университета | `{"id", "name", "short_name", "description", "website", "image", "preview_image"}` |
| 404 | Вуз не найден | `{"detail": "University not found"}` |

Публичная карточка отдаёт только то, что нужно читателю: без `name_norm`,
`createdAt`, `updatedAt` и прочих служебных полей. Админский маршрут правки
возвращает полный `UniversityResponse`.

---

## GET/POST /universities/{university_id}/programs

**GET — публично.** Образовательные программы университета: самостоятельный
справочник вуза, не привязанный к правилам льгот.

| Code | Description | Body |
|------|-------------|------|
| 200 | Список программ | `{"programs": [{"id", "university_id", "name", "code", "description", "is_archived", "version"}]}` |
| 404 | Вуз не найден | `{"detail": "University not found"}` |

**POST — представитель своего вуза или администратор.**

**Request body:** `{"name": str, "code"?, "description"?}`

| Code | Description | Body |
|------|-------------|------|
| 200/201 | Программа создана | `{"id", "university_id", "name", "code", "description", "is_archived", "version"}` |
| 403 | Чужой вуз | `{"detail": "You can only manage your own university"}` |
| 404 | Вуз не найден | `{"detail": "University not found"}` |
| 409 | Программа с таким названием уже есть | `{"detail": "Program already exists"}` |

`PUT /programs/{program_id}` обновляет программу и требует актуальную
`version` (иначе `409`). `POST /universities/{university_id}/programs/{program_id}/archive?archived=true|false`
переводит программу в архив и обратно; физического удаления нет.

---

## POST /universities/add_university

**Request body:** `{"name": str, "short_name"?, "description"?, "website"?, "image"?}`

| Code | Description | Body |
|------|-------------|------|
| 201 | Вуз создан | `UniversityResponse` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 409 | Такой вуз уже есть | `{"detail": "University with this name already exists"}` |
| 422 | Ошибка валидации | `{"detail": [...]}` |

---

## POST /universities/edit_university/{university_id}

**Request body:** любое подмножество `{"name", "short_name", "description", "website", "image"}`.

| Code | Description | Body |
|------|-------------|------|
| 200 | Вуз обновлён | `UniversityResponse` |
| 400 | Пустое тело | `{"detail": "No fields to update"}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Вуз не найден | `{"detail": "University not found"}` |
| 409 | Название занято другим вузом | `{"detail": "University with this name already exists"}` |

---

## GET/POST /olympiads/{olympiad_id}/seasons

Сезон — это олимпиада и метка года (`season_label`). Дат регистрации и
проведения, уровня РСОШ и флага доступности у сезона нет: уровень относится к
профилю конкретного сезона, а состояние приёмной кампании Papaya не хранит.

**GET — публично.** Query: `include_archived` (показать архивные сезоны),
`profiles` (вложить профили в ответ одним запросом).

| Code | Description | Body |
|------|-------------|------|
| 200 | Список сезонов | `{"seasons": [{"id", "olympiad_id", "season_label", "is_archived", "version", "profiles"?}]}` |
| 404 | Олимпиада не найдена | `{"detail": "Olympiad not found"}` |

**POST — администратор.** **Request body:** `{"season_label": str}`

| Code | Description | Body |
|------|-------------|------|
| 200/201 | Сезон создан | `{"id", "olympiad_id", "season_label", "is_archived", "version"}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Олимпиада не найдена | `{"detail": "Olympiad not found"}` |
| 409 | Сезон с такой меткой у олимпиады уже есть | `{"detail": "..."}` |

## GET/PUT/DELETE /seasons/{season_id}

| Code | Description | Body |
|------|-------------|------|
| 200 | Сезон | `{"id", "olympiad_id", "season_label", "is_archived", "version"}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Сезон не найден | `{"detail": "Season not found"}` |
| 409 | Конфликт версий или у сезона есть правила | `{"detail": "Version conflict"}` / `{"detail": "Season has benefit rules; archive it instead of deleting"}` |

**PUT** принимает `{"version", "season_label"?, "is_archived"?}`. `version`
обязательна при правке: устаревшая версия — `409`, данные не перезаписываются.
**DELETE** физически удаляет только сезон без правил; сезон с историей
архивируется (`is_archived: true`) и сохраняет профили и правила.

## GET/POST /seasons/{season_id}/profiles, PUT/DELETE /profiles/{profile_id}

Профиль принадлежит конкретному сезону. Уровень РСОШ (`1`, `2`, `3` или `null`)
— свойство профиля сезона, а не олимпиады: в перечне могут быть только
отдельные профили, и в следующем сезоне их набор и уровни меняются.

**Request body:** `{"name": str, "rsosh_level"?: "1"｜"2"｜"3"｜null, "description"?}`

| Code | Description | Body |
|------|-------------|------|
| 200/201 | Профиль создан или обновлён | `{"id", "season_id", "name", "rsosh_level", "description", "version"}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Сезон или профиль не найден | `{"detail": "Season not found"}` / `{"detail": "Profile not found"}` |
| 409 | Дубль профиля в сезоне или конфликт версий | `{"detail": "..."}` |
| 422 | Уровень не `1`, `2`, `3` и не пустой | `{"detail": [...]}` |

`PUT /profiles/{profile_id}` принимает `version` и те же поля; устаревшая
версия — `409`. Профиль с правилами не удаляется: `409` с требованием
архивировать сезон.

## GET/POST /universities/{university_id}/entity-requests

**Представитель своего вуза.** Запрос на отсутствующую в каталоге сущность:
олимпиаду, сезон или профиль. Представитель не создаёт их напрямую.

**Request body:** `{"entity_type": "OLYMPIAD"｜"SEASON"｜"PROFILE", "name": str, "parent_id"?: str, "comment"?}`

- `OLYMPIAD` — `parent_id` не нужен;
- `SEASON` — `parent_id` = id олимпиады;
- `PROFILE` — `parent_id` = id сезона.

| Code | Description | Body |
|------|-------------|------|
| 201 | Запрос создан | `{"id", "university_id", "entity_type", "name", "parent_id", "status": "PENDING", "createdAt"}` |
| 403 | Чужой вуз | `{"detail": "You can only manage your own university"}` |
| 404 | Родительская сущность не найдена | `{"detail": "..."}` |
| 409 | Такой запрос уже есть | `{"detail": "..."}` |

Администратор видит очередь в `GET /admin/entity-requests` (фильтры `status`,
`limit`, `offset`, `total`), одобряет
`POST /admin/entity-requests/{request_id}/approve` и отклоняет
`POST /admin/entity-requests/{request_id}/reject` с обязательным
`{"reason"}`. Одобрение создаёт сущность один раз: повторное одобрение — `409`.
При создании проверяется дубль по имени, чтобы в каталоге не появилось две
одинаковые олимпиады, сезона или профиля.

---

## GET /olympiads

Каталог олимпиад. Публично.

**Query:** `search` (по названию и описанию), `include_archived` (показать
олимпиады вне актуального перечня РСОШ), `limit`.

| Code | Description | Body |
|------|-------------|------|
| 200 | Список олимпиад | `{"olympiads": [{"id", "name", "description", "official_url", "preview_image", "image", "organizer", "status", "is_archived"}]}` |

`status`: `PUBLISHED` — в актуальном перечне РСОШ, `ARCHIVED` — больше нет
в перечне (запись сохранена исторически).

`archive_reason`: причина архива — `RSOSH_ABSENT` (нет в перечне РСОШ,
вернёт импорт) или `MANUAL` (исключил администратор, можно вернуть руками);
`null`, пока олимпиада актуальна.

`preview_image` — картинка для карточки, `image` — для страницы. Оба
необязательны; интерфейс берёт второе, если первое не заполнено.

---

## GET /olympiads/{olympiad_id}

| Code | Description | Body |
|------|-------------|------|
| 200 | Карточка олимпиады | `{"id", "name", "description", "official_url", "preview_image", "image", "organizer", "status", "is_archived": bool}` |
| 404 | Олимпиада не найдена | `{"detail": "Olympiad not found"}` |

Публичная модель минимальна: `name_norm`, `source_doc_id`, `createdAt`,
`updatedAt` и `archive_reason` — служебные поля импорта и панели
администратора, наружу они не отдаются. Причина архива пользователю ничего не
объясняет: он видит `status: "ARCHIVED"` и понятный текст в интерфейсе.

`is_archived` — производное от `status` поле для интерфейса: карточка не
разбирает статус сама. Значение всегда согласовано со `status`.

`organizer` — организатор олимпиады (вуз, министерство или иная организация).
Поле свободное: в перечне РСОШ формулировки разные, поэтому справочника нет.

---

## GET /olympiads/{olympiad_id}/universities

Вузы, у которых есть опубликованные правила льгот по этой олимпиаде. Список
строится по правилам, поэтому не может разойтись с каталогом.

| Code | Description | Body |
|------|-------------|------|
| 200 | Список вузов | `{"universities": [{"id", "name", "short_name", "description", "website", "preview_image", "image"}]}` |
| 404 | Олимпиада не найдена | `{"detail": "Olympiad not found"}` |

Если олимпиада архивная, её правила остаются доступными в истории: архив
меняет актуальность, а не удаляет данные.

---

## GET /olympiads/{olympiad_id}/source

Откуда взялась информация об олимпиаде. Публично.

| Code | Description | Body |
|------|-------------|------|
| 200 | Источник данных | `{"title": str, "has_file": bool}` |
| 404 | Олимпиада не найдена | `{"detail": "Olympiad not found"}` |

- импорт РСОШ → `title` = название документа-источника, `has_file` = есть ли у документа локальная копия;
- ручное создание → `{"title": "Создано администратором Papaya", "has_file": false}`.

Файл документа-источника можно скачать по публичному маршруту
`GET /api/v1/olympiads/{olympiad_id}/source/file` (только если олимпиада
опубликована и у неё есть документ-источник с локальной копией).

Внутренние поля документа (UUID, имя файла, хеш, статус обработки, metadata) в
ответе не участвуют. Сам `source_doc_id` олимпиады в публичных ответах каталога
тоже не отдаётся: он остаётся внутренним идентификатором и доступен
администратору в `GET /admin/olympiads`.

---

## POST /olympiads/add_olympiad

Ручное создание олимпиады (резервный путь; основной — импорт РСОШ).

**Request body:** `{"name": str, "description"?, "official_url"?, "preview_image"?, "image"?, "organizer"?}`

| Code | Description | Body |
|------|-------------|------|
| 201 | Олимпиада создана | `OlympiadResponse` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 409 | Такая олимпиада уже есть | `{"detail": "Olympiad with this name already exists"}` |

---

## POST /olympiads/edit_olympiad/{olympiad_id}

**Request body:** любое подмножество `{"name", "description", "official_url", "preview_image", "image", "organizer", "status"}`.

| Code | Description | Body |
|------|-------------|------|
| 200 | Олимпиада обновлена | `OlympiadResponse` |
| 400 | Пустое тело | `{"detail": "No fields to update"}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Олимпиада не найдена | `{"detail": "Olympiad not found"}` |
| 409 | Название занято | `{"detail": "Olympiad with this name already exists"}` |

---

## GET /search

Единый поиск по обоим каталогам.

**Query:** `q` (обязательный смысл поиска), `limit`.

| Code | Description | Body |
|------|-------------|------|
| 200 | Найденные сущности | `{"query": str, "universities": [...], "olympiads": [...], "programs": [{"id", "university_id", "name", "code"}]}` |
| 200 (пустой `q`) | Ничего не искали | `{"query": "", "universities": [], "olympiads": [], "programs": []}` |

Олимпиады в поиске не содержат `source_url`. Программы ищутся только по
актуальным (неархивным) записям.

---

## GET /olympiads/{olympiad_id}/source/file

Скачать файл документа-источника опубликованной олимпиады. Публично.

| Code | Description | Body |
|------|-------------|------|
| 200 | Файл документа | `application/pdf` и др. |
| 404 | Олимпиада, документ или файл не найдены | `{"detail": "Document not found"}` |

Доступ только к опубликованной олимпиаде (`status === PUBLISHED`), у которой есть `source_doc_id` с локальным файлом. Имя скачиваемого файла — название документа (с корректным расширением).

## POST /docs/upload

Загрузка документа-источника. **Администратор.**

**Form data:** `file` (PDF/XLSX/PNG/JPG/JPEG), `type`
(`RSOSH_LIST` | `UNIVERSITY_ORDER` | `OTHER`), `name?`.

| Code | Description | Body |
|------|-------------|------|
| 201 | Документ загружен | `{"id", "name", "type", "status", "storage_key", "mime_type", "checksum", "createdAt", ...}` |
| 400 | Формат не поддерживается или содержимое не совпадает с расширением | `{"detail": "Unsupported file format. Allowed: ..."}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 413 | Файл больше лимита | `{"detail": "File exceeds the 30 MB limit"}` |
| 422 | Неверный тип документа | `{"detail": "Invalid document type. Allowed: ..."}` |

---

## GET/POST /universities/{university_id}/docs, PATCH /universities/{university_id}/docs/{doc_id}

Документы-основания своего университета. **Представитель этого вуза или
администратор.**

- `GET` возвращает `{"docs": [...]}` — только документы указанного вуза.
- `POST` принимает form data `file`, `type` (`UNIVERSITY_ORDER` | `OTHER`),
  `name?`; документ получает `university_id` и `uploaded_by`.
- `PATCH` меняет `name`, `type`, `note`; сменить владельца нельзя.

| Code | Description | Body |
|------|-------------|------|
| 200/201 | Список или изменённый документ | `DocResponse` |
| 400 | Пустое тело, формат файла или пустой файл | `{"detail": "..."}` |
| 403 | Чужой университет или чужой документ | `{"detail": "Document belongs to another university"}` |
| 404 | Документ не найден | `{"detail": "Document not found"}` |
| 413 | Файл больше лимита | `{"detail": "File exceeds the ... limit"}` |

`GET /docs/{doc_id}/file` доступен администратору и представителю университета,
которому принадлежит документ. Общие документы (например, перечень РСОШ)
скачивает только администратор.

---

## POST /imports/rsosh

Запуск импорта РСОШ. **Администратор.**

**Request body:** `{"doc_id": str}`

| Code | Description | Body |
|------|-------------|------|
| 202 | Импорт запущен | `{"id", "name", "type", "status", "state", "progress", "summary", "warnings", "error", "execution": "celery"｜"inline"}` |
| 400 | Документ не подходит или импорт не стартует из текущего состояния | `{"detail": "Only RSOSH_LIST documents can be imported"}` |
| 401 | Нет токена | `{"detail": "..."}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 409 | Импорт уже обрабатывается | `{"detail": "Импорт этого документа уже запущен: дождитесь окончания обработки"}` |

В фоновом режиме сразу после ответа `state` = `processing`: состояние нужно
полярно опрашивать до `review` или `failed`.

Если скан распознан как официальный перечень РСОШ, поле `mode` в состоянии
импорта равно `official_list`: документ проходит через таблицу, план и
`POST /imports/{import_id}/apply`, а не через `preview` + `confirm`.

---

## GET /imports/{import_id}

| Code | Description | Body |
|------|-------------|------|
| 200 | Состояние импорта | `{"id", "name", "type", "status", "state": "processing｜paused｜review｜approved｜rejected｜failed", "progress": {"stage": "starting｜extracting｜matching｜done｜failed"}, "started_at", "finished_at", "error": str｜null, "summary": {"total", "new", "merge", "review"}, "warnings": [...], "confirm": object｜null}` |
| 404 | Импорт не найден | `{"detail": "Import not found"}` |

Поле `confirm` — итог применения (тело ответа `confirm` в разделе confirm
ниже). Оно хранится в метаданных документа, поэтому `archive_skipped_reason`
виден и при повторном открытии импорта, а не только в момент подтверждения.

Поле `progress` показывает текущий этап обработки, поэтому панель отвечает
«что сейчас происходит», а не только «обрабатывается». У завершённого прогона
этап — `done` (или `failed`). Состояние `paused` означает, что обработка
остановлена по запросу администратора; её можно возобновить (см. раздел pause
и resume ниже).

---

## GET /imports/{import_id}/preview

Кандидаты импорта: что будет создано, что обновлено, что требует проверки.

| Code | Description | Body |
|------|-------------|------|
| 200 | Preview | `{"import": {...}, "pages": [{"page", "method", "orientation", "tables", "rows", "chars", "confidence", "issues"}], "candidates": [{"name", "name_norm", "description", "action": "create｜merge｜skip", "matched_olympiad_id", "match_score", "confidence": "ok｜review", "page", "issues"}], "selection": object｜null}` |
| 409 | Импорт ещё обрабатывается | `{"detail": "Import is still processing"}` |

Кандидаты с `confidence: "review"` требуют решения администратора: сомнительное
сопоставление с существующей олимпиадой нельзя принять автоматически.

Поле `selection` — сохранённый ранее выбор администратора (подтверждённые и
снятые строки, переименования, описания, принудительные объединения). Оно
возвращается, чтобы открытая заново страница проверки восстановила решения;
`null` — выбор ещё не сохранялся. Сохраняется через `PUT …/selection`
(см. ниже).

Кандидаты, добавленные вручную (`manual_candidates`), в этом ответе не
разделяются по отдельному полю, а присоединяются к `candidates` и показываются
в едином перечне для предпросмотра.

---

## POST /imports/{import_id}/confirm

**Request body:** `{"skip": [name_norm, ...], "rename": {...}, "descriptions": {...}, "merge": {...}, "archive_missing": bool}`.
Пустое тело (`{}`) — подтвердить всё; `archive_missing` по умолчанию `true`.

Если тело запроса не передано вовсе, применяется ранее сохранённый выбор
администратора (тот, что вернул `preview` в поле `selection`). Это делает
подтверждение идемпотентным: интерфейс может отправить пустой запрос, и
решения не потеряются.

Способа применить устаревший перечень нет: поля вроде `allow_outdated` не
существует ни в схеме, ни в интерфейсе.

| Code | Description | Body |
|------|-------------|------|
| 200 | Импорт применён | `{"import": {...}, "result": {"created": [...], "updated": [...], "archived": [...], "skipped": [...], "errors": [...], "archive_skipped_reason": str｜null}, "skipped": [name_norm, ...]}` |
| 400 | Неизвестные `skip` или документ не `RSOSH_LIST` | `{"detail": "Unknown candidates in skip: ..."}` |
| 401 | Нет токена | `{"detail": "..."}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Импорт не найден | `{"detail": "Import not found"}` |
| 409 | Перечень устарел или уже применён | `{"detail": "Этот перечень устарел: он загружен раньше уже подтверждённого документа ..."}` |

Если документ обработан конвейером официального перечня (`mode: "official_list"`),
подтверждение кандидатов не применяется: ответ 409 с указанием применить план
через `POST /imports/{import_id}/apply`.

Поле верхнего уровня `skipped` — то, что администратор снял в preview.
Снятый кандидат не пишется в каталог **и не считается отсутствующим** в
перечне: иначе ошибка распознавания одной строки архивировала бы
существующую олимпиаду (у кандидата-merge защищается его `matched_olympiad_id`).

### Порядок подтверждения перечней

Перечень — снимок состояния на момент загрузки. Подтверждение документа,
загруженного **раньше** уже подтверждённого, откатило бы каталог назад,
поэтому такой импорт отклоняется с 409 — без исключений и без флага.
Актуальный каталог определяется последним подтверждённым перечнем РСОШ;
чтобы вернуть каталог к предыдущей редакции, нужно загрузить и подтвердить
тот перечень заново.

Проверка актуальности и запись каталога выполняются в одной транзакции под
блокировкой применения перечней, поэтому два параллельных подтверждения
разных перечней не могут разойтись по времени: второй увидит уже
подтверждённый более новый перечень и получит 409.

Один перечень применяется один раз: повторное подтверждение возвращает 409,
даже если перечень применён минуту назад.

### Когда архивирование не происходит

`archive_skipped_reason` объясняет, почему пропавшие из перечня олимпиады не
архивированы. Пустое значение — архивирование отработало штатно либо его не
запрашивали. Причины отказа:

| Причина | Что означает |
|---------|--------------|
| строки перечня не распознаны или сопоставление подозрительно | каталог нельзя считать полным: олимпиада могла просто не распознаться |
| в `errors` есть хотя бы одна строка | часть перечня не записана, судить по нему о «ком больше нет» нельзя |
| `archive_missing=false` | администратор сознательно оставил каталог без архивирования |

---

## Официальный перечень: план, применение, история

Скан официального перечня РСОШ обрабатывается отдельным конвейером: из PDF
строится таблица (XLSX), по ней — план импорта, и только утверждённый план
пишется в каталог. Признак этого режима — `mode: "official_list"` в состоянии
импорта; прежний конвейер (`preview` + `confirm`) работает как раньше для
остальных документов.

Порядок шагов:

```text
PDF сохраняется в docs (UUID-имя)
    ↓ фоновая задача Celery (RSOSH_EXECUTION=auto|celery|inline)
Распознавание перечня (OCR, ориентация страниц, шапка года)
    ↓
Таблица XLSX (лист «Перечень <сезон>» + лист «Сводка») и HTML-версия
    ↓ производные документы RSOSH_TABLE / RSOSH_HTML, серверные файлы
План импорта: создать / использовать / требует решения / пропустить
    ↓ правка плана администратором (PATCH …/plan)
Применение одной транзакцией (POST …/apply)
    ↓
Записи ImportJob/ImportRecord и история решений в docs.metadata['rsosh']
```

Производные таблицы создаёт только сервер: типы `RSOSH_TABLE` и `RSOSH_HTML`
нельзя выбрать при загрузке документа, они не принимаются и в
`POST /docs/upload`. Файлы лежат рядом с исходным PDF под именем
`<doc_id>.xlsx` / `<doc_id>.html`, отдаются через `GET /docs/{doc_id}/file` и
скачиваются только администратором. Повторный разбор того же PDF переиспользует
существующие записи, а не создаёт вторые.

### GET /imports/{import_id}/plan

План импорта официального перечня. **Администратор.**

| Code | Description | Body |
|------|-------------|------|
| 200 | План | `{"import": {...}, "plan": {"season_label", "complete", "olympiads": [{"name", "name_norm", "organizer", "page", "source_rows", "match": {"action": "create｜use｜review｜skip", "confidence", "olympiad_id", "candidates"}, "season": {"season_label", "action", "season_id"}, "profiles": [{"source_row", "name", "level", "match", "issues"}], "issues", "duplicate"}], "missing", "missing_pool", "missing_allowed", "duplicates", "summary", "warnings", "errors"}}` |
| 401 | Нет токена | `{"detail": "..."}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Импорт не найден | `{"detail": "Import not found"}` |
| 409 | План ещё не построен | `{"detail": "План импорта ещё не построен: документ не разобран"}` |

План отдаётся целиком вместе со строками исходного документа: администратор
должен видеть каждую строку, иначе потерянную при OCR олимпиаду не заметить.

`match.action`: `create` — новой олимпиады в каталоге нет; `use` — точное
совпадение с существующей; `review` — есть похожие записи, но автоматически
объединять нельзя, решение принимает администратор; `skip` — строку не
переносить. Нечёткие совпадения никогда не применяются сами.

`summary` считает строки плана: олимпиады (`create`/`use`/`review`/`skip`),
профили (`profiles_create`/`profiles_update`/`profiles_skip`), отсутствующие
(`missing`) и число нерешённых `errors`.

`missing` заполняется только для полного перечня: если `complete=false`, в
документе нет сезона или остались ошибки, список отсутствующих пуст, а
`missing_allowed=false`. `missing_pool` — кандидаты на «олимпиады нет в этом
перечне».

### PATCH /imports/{import_id}/plan

Исправить план, не применяя его. **Администратор.**

**Request body:** `{"season_label"?, "olympiads": [{"name_norm", "name"?, "organizer"?, "action"?, "olympiad_id"?}], "profiles": [{"olympiad", "source_row", "action"?, "name"?, "level"?}]}`

| Code | Description | Body |
|------|-------------|------|
| 200 | План обновлён | `{"import": {...}, "plan": {...}}` |
| 400 | Некорректная правка | `{"detail": "..."}` |
| 401 | Нет токена | `{"detail": "..."}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Импорт не найден | `{"detail": "Import not found"}` |
| 409 | План не построен или импорт уже применён | `{"detail": "Импорт уже применён: план больше не редактируется"}` |

Правки меняют только план, каталог не затрагивается. Строка, которую OCR не
прочитал, остаётся ошибкой и блокирует применение; пропустить её можно лишь
явным действием `action: "skip"` для профиля — это решение администратора, а не
молчаливая потеря данных.

### POST /imports/{import_id}/apply

Применить утверждённый план. **Администратор.**

**Request body:** `{"mark_missing": bool}` (по умолчанию `false`).

| Code | Description | Body |
|------|-------------|------|
| 200 | Применено | `{"import": {...}, "result": {"created", "used", "profiles_created", "profiles_updated", "profiles_absent", "archived", "missing"}, "records": [...], "history": [...], "missing_profiles": [...]}` |
| 400 | План неполон или документ не `official_list` | `{"detail": "Строка 25: профиль не распознан — укажите название и уровень"}` |
| 401 | Нет токена | `{"detail": "..."}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Импорт не найден | `{"detail": "Import not found"}` |
| 409 | Импорт уже применён | `{"detail": "..."}` |

Запись идёт одной транзакцией под блокировкой применения перечней: частично
применённого перечня не бывает, при ошибке откатывается всё. Один документ
применяется один раз; повторный вызов возвращает 409, а не создаёт дубли.

Сезон берётся из документа (`season_label`), а не из года запуска. Олимпиада не
дублируется между сезонами: профили и уровни принадлежат сезону, изменение
уровня записывается в историю.

`mark_missing=true` фиксирует отсутствие: профили, которых нет в перечне,
получают `rsosh_level = null`, а олимпиады уходят в архив с причиной
`RSOSH_ABSENT`. Это возможно только при `missing_allowed=true` — отсутствие
нельзя зафиксировать по неполному или непрочитанному перечню.

### GET /imports/{import_id}/history

История решений по документу. **Администратор.**

| Code | Description | Body |
|------|-------------|------|
| 200 | История | `{"import": {...}, "history": [{"action", "name", "source_row", "before", "after", "at"}], "confirm", "jobs": [...]}` |
| 401 | Нет токена | `{"detail": "..."}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Импорт не найден | `{"detail": "Import not found"}` |

Необязательный параметр `limit` (1–1000, по умолчанию 100) ограничивает
размер ответа. История описывает решения по этому перечню (создание,
переименование, смена уровня, отсутствие), а не общий журнал аудита.

### GET /imports/{import_id}/table

Постраничный просмотр таблицы перечня. **Администратор.**

| Code | Description | Body |
|------|-------------|------|
| 200 | Страница таблицы | `{"sheet": "list｜summary", "title", "headers": [...], "rows": [[...]], "total", "offset", "limit"}` |
| 401 | Нет токена | `{"detail": "..."}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Импорт не найден | `{"detail": "Import not found"}` |
| 409 | Таблица ещё не собрана | `{"detail": "..."}` |

Параметры: `sheet` (`list`|`summary`), `offset` (от 0), `limit` (1–200, по
умолчанию 50), `search` (до 100 символов, фильтр по всем колонкам). Пагинация
серверная: в перечне бывает 300+ строк.

---

## POST /imports/{import_id}/pause

Остановить идущий импорт. **Администратор.**

Остановка выполняется на границе этапа: запрос лишь помечает прогон, а
обработчик завершает текущий этап и переходит в ``paused``, сохранив
распознанные строки. Поэтому импорт никогда не обрывается на середине записи
состояния, а возобновление может продолжить с сохранённого этапа.

| Code | Description | Body |
|------|-------------|------|
| 200 | Остановка принята или уже произошла | `{"id", "state": "processing｜paused", "progress", ...}` |
| 401 | Нет токена | `{"detail": "..."}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Импорт не найден | `{"detail": "Import not found"}` |
| 409 | Прогон не обрабатывается | `{"detail": "..."}` — приостановить можно только ``processing`` |

---

## POST /imports/{import_id}/resume

Возобновить приостановленный импорт. **Администратор.**

Если распознавание уже завершилось до остановки, повторного чтения документа
не будет: прогон продолжает с сохранённых строк и сразу переходит к
сопоставлению. Иначе обработка идёт с начала.

| Code | Description | Body |
|------|-------------|------|
| 200 | Импорт возобновлён | `{"id", "state": "processing｜review", "progress", "execution": "celery"｜"inline", ...}` |
| 401 | Нет токена | `{"detail": "..."}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Импорт не найден | `{"detail": "Import not found"}` |
| 409 | Прогон не приостановлен | `{"detail": "..."}` |

---

## PUT /imports/{import_id}/selection

Сохранить выбор администратора в окне проверки, не применяя перечень.
**Администратор.**

Тело совпадает с телом `confirm`. Выбор хранится вместе с прогоном и
возвращается в `preview` (поле `selection`), поэтому перезагрузка страницы не
теряет подтверждённые и снятые строки, переименования, описания и
принудительные объединения. При подтверждении без тела запроса применяется
именно этот сохранённый выбор.

| Code | Description | Body |
|------|-------------|------|
| 200 | Выбор сохранён | `{"state": "review", ...}` |
| 400 | Неизвестные кандидаты в выборе | `{"detail": "Unknown candidates in selection: ..."}` |
| 401 | Нет токена | `{"detail": "..."}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Импорт не найден | `{"detail": "Import not found"}` |
| 409 | Прогон не в состоянии `review`/`paused`/`processing` | `{"detail": "..."}` |

## POST /imports/{import_id}/candidates

Добавить олимпиаду в документ РСОШ вручную. **Администратор.**

**Request body:** `{"name": str, "description"?: str}`

| Code | Description | Body |
|------|-------------|------|
| 200 | Кандидат добавлен | `{"state": "review"|..., "manual_candidates": [...]}` |
| 400 | Пустое название | `{"detail": "Название олимпиады не может быть пустым"}` |
| 401 | Нет токена | `{"detail": "..."}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Импорт не найден | `{"detail": "Import not found"}` |
| 409 | Прогон подтверждён/отклонён или кандидат уже есть | `{"detail": "..."}` |

## POST /imports/{import_id}/candidates/remove

Убрать вручную добавленную олимпиаду. **Администратор.**

**Request body:** `{"name_norm": str}`

| Code | Description | Body |
|------|-------------|------|
| 200 | Кандидат удалён | `{"state": "review"|..., "manual_candidates": [...]}` |
| 400 | Кандидат не найден | `{"detail": "Такой олимпиады нет среди добавленных вручную"}` |
| 401 | Нет токена | `{"detail": "..."}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Импорт не найден | `{"detail": "Import not found"}` |
| 409 | Прогон подтверждён/отклонён | `{"detail": "..."}` |

---

## POST /imports/{import_id}/reject

| Code | Description | Body |
|------|-------------|------|
| 200 | Результаты отклонены, в каталог ничего не записано | `{"state": "rejected", ...}` |
| 401 | Нет токена | `{"detail": "..."}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Импорт не найден | `{"detail": "Import not found"}` |
| 409 | Прогон уже вне ``review`` | `{"detail": "Импорт ещё обрабатывается: дождитесь окончания обработки"}` — импорт в обработке; `{"detail": "Импорт в состоянии approved уже применён или не может быть отклонён"}` — уже применён или отклонён |

Отклонять можно и приостановленный импорт (``paused``): решение администратора
не зависит от того, ждёт прогон или остановлен.

---

## GET /admin/users, /admin/olympiads, /admin/benefits, /admin/entity-requests

**Администратор.** Списки для панели: пользователи (с ролью и привязкой к
вузу), полный каталог олимпиад включая архивные, очередь модерации правил
льгот и запросы представителей.

`/admin/users`, `/admin/olympiads`, `/admin/benefits` и
`/admin/entity-requests` поддерживают `search`, `limit` и `offset`. В ответе
есть `total` — сколько записей под фильтром всего, чтобы панель показывала
«Показано N из M» и догружала следующую страницу. Без `limit` возвращается
весь список.

---

## Правила льгот

**Публичная выдача:** `GET /benefits`, `GET /benefits/{id}`,
`GET /benefits/{id}/versions`, `GET /benefits/{id}/status-history`,
`GET /universities/{university_id}/benefits`,
`GET /benefits/olympiad/{olympiad_id}`.

Публично отдаются опубликованные правила: `is_published: true` и
`verification_status != "rejected"`. Непроверенное правило видно с честным
статусом `unverified` и предупреждением «Не проверено Papaya». Черновики
(`is_published: false`) и отклонённые записи не видны даже по прямому id.
Список поддерживает `university_id`, `olympiad_id`, `season_id`,
`profile_id`, `benefit_type`, `level` (уровень РСОШ профиля), `search`,
`limit` и `offset`; в ответе есть `total` под фильтром.

```json
{"rules": [...], "total": 12, "limit": 50, "offset": 0}
```

Правило описывает: университет, олимпиаду, сезон, профиль, тип льготы
(`BVI`｜`EGE_100`｜`DVI_100`｜`OTHER`), требуемый результат (`WINNER`｜
`PRIZE`｜`WINNER_OR_PRIZE`), документ университета-основание и необязательное
требование ЕГЭ (`{"subject", "min_score"}`). Предмет ЕГЭ — отдельная
структура и не смешивается с профилем олимпиады.

Поля правила в ответе: `id`, `university_id`, `olympiad_id`, `season_id`,
`profile_id`, `benefit_type`, `required_result_type`, `ege_requirement`,
`doc_id`, `needs_review`, `verification_status`, `is_published`, `version`.

**Кабинет представителя** (только свой вуз):

- `GET /universities/{university_id}/benefit-rules/manage` — черновики,
  отклонённые и проверенные правила с фильтрами `verification_status`,
  `search`, `limit`, `offset` и `total`;
- `GET /benefits/{id}/manage` — правило до проверки;
- `GET /benefits/{id}/versions/manage`,
  `GET /benefits/{id}/status-history/manage` — история;
- `POST /universities/{university_id}/benefits`,
  `PUT|PATCH /benefits/{id}`,
  `POST /benefits/{id}/rollback`.

Созданное правило всегда `unverified`: `verification_status` из клиента
игнорируется. Сезон обязан принадлежать олимпиаде, профиль — сезону, документ
— тому же университету; иначе `422`. Любая содержательная правка проверенного
правила снова делает его `unverified`. Параллельная правка со старой `version`
возвращает `409 {"detail": "Version conflict"}`.

`POST /benefits/{id}/rollback` принимает `{"version": int, "expected_version": int}`.
Откат атомарен (строка блокируется `FOR UPDATE`), при несовпадении текущей
версии — `409`, при успехе создаётся новая версия, правило становится
`unverified`, а изменение попадает в историю статусов.

`is_published` — не содержание правила: представитель может скрыть правило из
каталога и вернуть его, не теряя `verified`. Версия при этом растёт, поэтому
переключение тоже передаёт актуальную `version`.

**Проверка — только администратор.** `POST /benefits/{id}/verify` требует
приложенный документ типа `UNIVERSITY_ORDER` того же университета.
`POST /benefits/{id}/reject` принимает непустой `{"reason"}` и снимает правило
с публикации. Администратору доступны `GET /admin/benefits`,
`GET /admin/benefits/{id}` и `GET /admin/benefits/{id}/versions`; фильтр
`needs_review=true` показывает правила, которым не хватает сезона или профиля.

| Code | Description | Body |
|------|-------------|------|
| 200/201 | Успех | правило или `{"rules", "total", "limit", "offset"}` |
| 400 | Пустая причина отклонения | `{"detail": "..."}` |
| 403 | Чужой вуз, попытка подтвердить правило | `{"detail": "..."}` |
| 404 | Правило, сезон, профиль или документ не найдены | `{"detail": "..."}` |
| 409 | Конфликт версий | `{"detail": "Version conflict"}` |
| 422 | Ссылки не согласованы, нет сезона/профиля, архивная олимпиада | `{"detail": "..."}` |

---

## GET /admin/stats, /admin/universities, /admin/programs, /admin/seasons, /admin/docs, /admin/imports

**Администратор.** Сводка и полные списки для панели: `total` есть у
университетов, программ и сезонов; `include_archived` по умолчанию `true`.
Архивирование и восстановление:

- `POST /admin/universities/{id}/archive?archived=true|false`
- `POST /admin/programs/{id}/archive?archived=true|false`
- `POST /admin/seasons/{id}/archive?archived=true|false`

Архив не удаляет данные: правила, история и связи сохраняются, публичный
каталог просто перестаёт показывать запись. `/admin/imports` отдаёт журнал
прогонов РСОШ (кто и когда запустил, статус, итог).

`/admin/docs` поддерживает `search` (подстрока по названию), `type`
(`RSOSH_LIST`｜`UNIVERSITY_ORDER`｜`OTHER`), `status` (`UPLOADED`｜`PROCESSING`｜
`PROCESSED`｜`NEEDS_REVIEW`｜`FAILED`｜`REJECTED`), `limit` и `offset`; в ответе
есть `total`.

`/admin/imports` принимает `doc_id`, `limit` и `offset`.

---

## GET /admin/imports/{job_id}

**Администратор.** Один прогон импорта вместе с построчными результатами.

| Code | Description | Body |
|------|-------------|------|
| 200 | Прогон найден | `{"id", "doc_id", "kind", "status", "started_by", "started_at", "finished_at", "summary", "error", "records": [{"id", "job_id", "name", "action", "status", "payload", "createdAt"}]}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Прогон не найден | `{"detail": "Import job not found"}` |

`status` прогона: `PROCESSING`, `APPLIED` или `REJECTED`. `records` — что именно
произошло с каждой олимпиадой (`action`/`status`); `payload` хранит исходную
строку импорта.

---

## Документы: РСОШ и университета

Отдельной сущности «Источник» нет. Есть два вида документов:

- **документ РСОШ** — `type: "RSOSH_LIST"`, загружается администратором в
  `POST /docs/upload` и привязывается к импорту (`docs.source_url` — ссылка на
  оригинал);
- **документ университета** — `type: "UNIVERSITY_ORDER"｜"OTHER"`, загружается
  представителем своего вуза в `POST /universities/{university_id}/docs` и
  служит основанием правила льготы.

`GET /docs`, `GET /docs/{doc_id}`, `GET /docs/{doc_id}/file` — администратор.
`GET /universities/{university_id}/docs`,
`POST /universities/{university_id}/docs`,
`PATCH /universities/{university_id}/docs/{doc_id}` — представитель своего вуза
или администратор. Скачивание проверяет права и отдаёт файл только владельцу
или администратору.

Удаления документов нет: документ-основание подтверждённого правила должно
оставаться доступным.

## GET /admin/audit

**Администратор.** Журнал действий с фильтрами.

**Query:** `entity_type`, `entity_id`, `action`, `limit` (по умолчанию 100), `offset`.

| Code | Description | Body |
|------|-------------|------|
| 200 | Записи журнала | `{"logs": [{"id", "entity_type", "entity_id", "action", "user_id", "before", "after", "request_id", "createdAt"}], "total"}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |

Типовые `entity_type`: `benefit_rule`, `university`, `olympiad_season`,
`program`, `source`, `doc`, `import`, `representative_application`. Типовые
`action`: `create`, `update`, `delete`, `verify`, `reject`, `status_change`,
`rollback`, `archive`, `restore`, `upload`, `start`, `confirm`, `review`.

---

## POST /admin/role/{user_id}

Единственный способ изменить роль и привязку к университету. **Администратор.**

**Request body:** `{"role": "USER"｜"EDITOR"｜"ADMIN", "university_id": str｜null}`

| Code | Description | Body |
|------|-------------|------|
| 200 | Роль применена | `UserResponse` |
| 400 | Нарушен инвариант роли | `{"detail": "..."}` — например, `EDITOR` без университета или `USER` с привязкой |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Пользователь или университет не найден | `{"detail": "User not found"}` |
| 409 | Это последний активный ADMIN — понизить или заблокировать нельзя | `{"detail": "..."}` |
| 422 | Неизвестная роль | `{"detail": [...]}` |

Отдельного маршрута «привязать университет» не существует: представитель — это
«роль + вуз», поэтому роль и привязка меняются вместе.

Отдельных маршрутов `grant_admin` / `demote_admin` тоже нет: они меняли роль,
не трогая привязку, то есть давали второй путь, на котором инварианты роли могли
разойтись с проверяемыми в `/role`. Повысить до `ADMIN` и снять роль можно
только здесь, целевая роль задаётся в теле запроса:

```json
{"role": "ADMIN",                       "university_id": null}
{"role": "EDITOR", "university_id": "…"}  // представитель
{"role": "USER",   "university_id": null}  // обычный пользователь
```

Инварианты проверяются сервером: `EDITOR` без университета — 400, `USER` с
привязкой — 400 (привязку нужно снять явно), `ADMIN` может сохранять
привязку.

---

## POST /admin/ban/{user_id}, /admin/unban/{user_id}

Блокировка и разблокировка пользователя. **Администратор.**

| Code | Description | Body |
|------|-------------|------|
| 200 | Статус изменён | `UserResponse` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Пользователь не найден | `{"detail": "User not found"}` |
| 409 | Блокируется последний активный администратор | `{"detail": "Нельзя заблокировать: это последний активный администратор Papaya. Сначала назначьте другого администратора."}` |

Заблокированный пользователь не может войти; `unban` это отменяет.

---

## POST /admin/archive_olympiad/{olympiad_id}?archived=true|false

Архивирование или возврат олимпиады в каталог. **Администратор.**

| Code | Description | Body |
|------|-------------|------|
| 200 | Статус изменён | `OlympiadResponse` со `status: "ARCHIVED"｜"PUBLISHED"` и `archive_reason: "MANUAL"｜null` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Олимпиада не найдена | `{"detail": "Olympiad not found"}` |
| 409 | Вернуть из архива РСОШ вручную нельзя | `{"detail": "Олимпиада архивирована, потому что её нет в актуальном перечне РСОШ..."}` |

`archived=true` ставит причину `MANUAL` (исключил администратор — вернуть
можно). Олимпиада, исчезнувшая из перечня РСОШ, помечена `RSOSH_ABSENT` и
возвращается только подтверждением импорта, где она снова встретилась.

---

## POST /representative-applications, GET /applications/my

**Пользователь.** Заявка на роль представителя университета. Пока заявка
`pending`, повторная отправка на тот же вуз возвращает существующую запись, а не
создаёт дубль. `GET /applications/my` отдаёт свои заявки с названием вуза и
датой — по ним профиль показывает статус рассмотрения.

**Request body:** `{"university_id": "...", "justification": "..."}`

| Code | Description | Body |
|------|-------------|------|
| 200/201 | Заявка создана или уже существует | заявка |
| 401 | Нет авторизации | `{"detail": "..."}` |
| 404 | Университет не найден | `{"detail": "University not found"}` |

Администратор рассматривает заявки через
`GET /admin/representative-applications?status=` (в ответе есть `user_name`,
`user_email`, `university_name`) и
`POST /admin/representative-applications/{id}/review` с телом
`{"status": "approved"｜"rejected", "rejection_reason": "..."}`. Одобрение
назначает роль `EDITOR` и привязку к вузу; отклонение сохраняет причину.

---

## Удаление каталога

Маршрутов удаления олимпиады или университета нет, и в слое данных нет
соответствующих функций. Единственный способ убрать олимпиаду из актуальных —
`POST /admin/archive_olympiad/{id}?archived=true`: запись сохраняется вместе с
подтверждёнными связями, документом-источником и историей актуальности.

---

## GET /health, GET /ready

| Code | Description | Body |
|------|-------------|------|
| 200 | Сервис жив / готов | `{"status": "ok"}` / `{"status": "ready"}` |
| 503 | Зависимость недоступна | `{"status": "degraded", "component": "database"｜"redis"}` |

---

## Проверка ссылок

Поля `website`, `official_url`, `preview_image`, `image` проверяются
одинаково при создании и при правке: допустимы только `http://` и `https://` с
хостом. `javascript:`, `data:`, `file:`, `vbscript:`, строки без схемы и с
пробелами отклоняются с 422 — интерфейс вставляет эти значения в `href`/`src`,
поэтому схема проверяется на входе, а не подменяется экранированием на выводе.
Пустая строка считается «ссылки нет» и сохраняется как `null`.
