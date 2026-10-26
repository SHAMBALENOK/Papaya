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

## GET /universities/{university_id}/olympiads

Олимпиады, по которым у вуза есть **опубликованные** правила льгот, с самими
правилами внутри каждой олимпиады. Публично.

**Query:** `benefit_type`, `subject`, `program_id`, `season_id` — фильтры
комбинируются (И); `limit`, `offset`; `include_drafts` (требует входа и прав на
этот вуз — добавляет черновики и архив правил).

| Code | Description | Body |
|------|-------------|------|
| 200 | Олимпиады с правилами | `{"olympiads": [{"id", "name", "description", "official_url", "organizer", "preview_image", "image", "status", "is_historical": bool, "rules": [BenefitRuleItem]}], "total": int}` |
| 401 | `include_drafts` без входа | `{"detail": "Access token required to view drafts"}` |
| 403 | Чужие черновики | `{"detail": "Drafts are visible to own university only"}` |
| 404 | Вуз не найден | `{"detail": "University not found"}` |
| 422 | Недопустимое значение фильтра | `{"detail": "benefit_type must be one of ..."}` |

Отклонённые проверкой Papaya правила (`verification_status: "rejected"`) в
публичной выдаче не показываются даже в состоянии `published`.

Публично видны только подтверждённые (`CONFIRMED`) связи.

`is_historical` — олимпиада осталась в перечне РСОШ, но связи с архивной
олимпиадой; такие показываются отдельным историческим блоком.

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

## Правило льготы (`BenefitRuleItem`)

Правило — отдельная сущность: «университет *U* по олимпиаде *O* (сезон *S*,
профиль *P*) даёт льготу *T* при результате *R* по предмету *Subj* на
программы *[…]*». У одной пары «вуз — олимпиада» правил может быть несколько.

Поля: `id`, `university_id`, `university_name`, `university_short_name`,
`olympiad_id`, `olympiad_name`, `olympiad_status`, `is_historical`,
`season_id`, `season: {id, year, label, state}`, `profile_id`,
`profile: {id, name, subject}`, `status` (`draft`｜`published`｜`archived`),
`benefit_type` (`BVI`｜`EGE_100`｜`DVI_100`｜`EXTRA_POINTS`),
`result_requirement`, `subject`, `programs: [{id, name}]`, `program_ids`,
`extra_requirements`, `source_url`, `document: {id, name, has_file,
availability, source_url}`, `valid_until`, `verification_status`
(`unverified`｜`verified`｜`rejected`), `verified_at`, `verification_note`,
`university_confirmed`, `university_confirmed_at`, `version`,
`published_at`, `createdBy`, `createdAt`, `updatedAt`.

Три независимых статуса: `status` — публикация (решает вуз), `verification_status`
— проверка Papaya (решает администратор), `university_confirmed` — подтверждение
вузом. `season.state` — состояние сезона олимпиады, на статус правила не влияет.

---

## GET /universities/{university_id}/benefit-rules

Плоский список правил вуза. Публично — только `published` и не `rejected`.

**Query:** `benefit_type`, `subject`, `program_id`, `season_id`, `olympiad_id`,
`verification_status`, `limit`, `offset`; `include_drafts` — как выше.

| Code | Description | Body |
|------|-------------|------|
| 200 | Правила | `{"rules": [BenefitRuleItem], "total": int}` |
| 401 / 403 / 404 / 422 | См. `GET /universities/{university_id}/olympiads` | |

`GET /universities/{university_id}/benefit-rules/facets` — значения для
фильтров по опубликованным правилам: `{"benefit_types": [{value, count}],
"subjects": [{value, count}], "programs": [{id, name, count}],
"seasons": [{id, year, label, state, count}]}`.

---

## POST /universities/{university_id}/benefit-rules

Создать правило. **Представитель этого вуза или администратор.**

**Request body:** `{"olympiad_id": str, "season_id"?: str, "profile_id"?: str,
"benefit_type": "BVI", "result_requirement"?: str, "subject"?: str,
"program_ids": [str], "extra_requirements"?: str, "source_url"?: str,
"valid_until"?: "YYYY-MM-DD", "publish": false, "reason"?: str}`.
Администратор дополнительно может передать `source_doc_id` и
`verification_status`.

| Code | Description | Body |
|------|-------------|------|
| 201 | Правило создано, записана версия 1 | `BenefitRuleItem` |
| 400 | Профиль из другого сезона / чужая программа | `{"detail": "..."}` |
| 401 | Нет токена | `{"detail": "..."}` |
| 403 | Не администратор и не представитель этого вуза | `{"detail": "You can only manage your own university"}` |
| 404 | Вуз, олимпиада, сезон или профиль не найдены | `{"detail": "Olympiad not found"}` |
| 409 | Олимпиада архивирована или такое правило уже есть | `{"detail": "Олимпиада архивирована: её нет в актуальном перечне РСОШ, новые правила льгот по ней не заводятся. Уже записанные правила сохраняются как исторические."}` |
| 422 | Недопустимый `benefit_type` и т. п. | `{"detail": [...]}` |

Правило возможно только по актуальной олимпиаде: архивная запись сохраняет
прежние правила (как исторические), но новых не получает. Дубликат
определяется по сезону, профилю, виду льготы, результату, предмету и набору
программ; архивные правила в проверке не участвуют.

---

## GET /universities/{university_id}/benefit-rules/{rule_id}, GET /benefit-rules/{rule_id}

Карточка правила. Публично для `published` и не `rejected`; черновик, архив и
отклонённые — представителю своего вуза и администратору (иначе 404: чужой
черновик неотличим от несуществующего).

| Code | Description | Body |
|------|-------------|------|
| 200 | Правило | `BenefitRuleItem` |
| 404 | Нет или недоступно | `{"detail": "Benefit rule not found"}` |

`GET …/benefit-rules/{rule_id}/document` — файл официального документа
(те же правила видимости; 404, если документа нет).

---

## PUT /universities/{university_id}/benefit-rules/{rule_id}

Изменить правило. **Представитель этого вуза или администратор.** Каждая
правка — новая версия.

**Request body:** любые поля из `POST` (кроме `olympiad_id`), плюс
`expected_version` (оптимистичная блокировка) и `reason`. Администратор может
передать `verification_status` и `source_doc_id`.

| Code | Description | Body |
|------|-------------|------|
| 200 | Обновлено, `version` увеличен | `BenefitRuleItem` |
| 400 | Недопустимые связи (профиль/программа) | `{"detail": "..."}` |
| 403 | Нет прав | `{"detail": "You can only manage your own university"}` |
| 404 | Правило не найдено | `{"detail": "Benefit rule not found"}` |
| 409 | `expected_version` устарел или дубликат | `{"detail": "Правило уже изменено (текущая версия N, вы правили версию M). Обновите страницу и повторите правку."}` |
| 422 | Невалидные значения | `{"detail": [...]}` |

Содержательная правка сбрасывает проверку Papaya в `unverified` (кроме
случая, когда администратор в том же запросе явно задал
`verification_status`). Подтверждение вузом не сбрасывается.

---

## POST /universities/{university_id}/benefit-rules/{rule_id}/status

Публикация / снятие с публикации / архив. **Представитель своего вуза или
администратор.**

**Request body:** `{"status": "draft"｜"published"｜"archived", "expected_version"?: int, "reason"?: str}`

| Code | Description | Body |
|------|-------------|------|
| 200 | Состояние изменено (или уже такое) | `BenefitRuleItem` |
| 409 | Версия устарела / олимпиада в архиве / дубликат при возврате из архива | `{"detail": "..."}` |
| 422 | Неизвестное состояние | `{"detail": [...]}` |

`DELETE /universities/{university_id}/benefit-rules/{rule_id}` — удалить
**черновик** (204). Опубликованное правило не удаляется (409): его переводят в
архив, чтобы сохранить историю.

---

## POST /universities/{university_id}/benefit-rules/{rule_id}/verification

Проверка Papaya. **Только администратор.**

**Request body:** `{"status": "verified"｜"rejected"｜"unverified", "note"?: str, "expected_version"?: int}`

| Code | Description | Body |
|------|-------------|------|
| 200 | Решение записано как версия | `BenefitRuleItem` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Правило не найдено | `{"detail": "Benefit rule not found"}` |
| 409 | `verified` без документа или ссылки на источник | `{"detail": "Нельзя отметить правило как проверенное: не хватает — официальный документ, ссылка на источник. ..."}` |
| 422 | `rejected` без `note` / неизвестный статус | `{"detail": [...]}` |

`POST …/university-confirmation` `{"confirmed": bool}` — подтверждение со
стороны вуза (представитель или администратор); на `verification_status` не
влияет.

---

## POST /universities/{university_id}/benefit-rules/{rule_id}/document

Загрузить официальный документ правила (multipart `file`: PDF/XLSX/изображение,
проверяется расширение, сигнатура и размер; имя файла санируется).
**Представитель своего вуза или администратор.** Документ сохраняется как
`UNIVERSITY_ORDER`, привязывается к правилу, проверка Papaya сбрасывается.

| Code | Description | Body |
|------|-------------|------|
| 200 | Документ привязан | `BenefitRuleItem` |
| 400 | Неподдерживаемый формат / пустой файл / подделанное расширение | `{"detail": "Unsupported file format. Allowed: ..."}` |
| 413 | Превышен размер | `{"detail": "..."}` |

---

## GET /universities/{university_id}/benefit-rules/{rule_id}/versions

История версий. **Представитель своего вуза или администратор.**

| Code | Description | Body |
|------|-------------|------|
| 200 | Версии по возрастанию | `{"versions": [{"id", "rule_id", "version", "snapshot", "changed_by", "changed_at", "reason", "verification_status", "source_doc_id", "is_rollback"}], "current_version": int}` |

`POST …/rollback` `{"version": int, "expected_version"?: int, "reason"?: str}`
— восстановить содержимое выбранной версии **новой** версией
(`is_rollback: true`). Восстановленное правило всегда `unverified`; состояние
публикации не меняется. 404, если версии нет; 409 при устаревшей
`expected_version`.

---

## Заявки на пополнение каталога

`POST /universities/{university_id}/catalog-requests`
`{"kind": "olympiad"｜"season"｜"profile"｜"other", "olympiad_id"?: str, "text": str}`
— представитель просит добавить в каталог олимпиаду/сезон/профиль (201,
`CatalogRequestItem`). `GET …/catalog-requests` — свои заявки.

`GET /admin/catalog-requests?status=open|resolved|rejected|all` и
`POST /admin/catalog-requests/{request_id}/resolve`
`{"status": "resolved"｜"rejected", "note"?: str}` — очередь администратора.

---

## GET /olympiads

Каталог олимпиад. Публично.

**Query:** `search` (по названию и описанию), `include_archived` (показать
олимпиады вне актуального перечня РСОШ), `limit`.

| Code | Description | Body |
|------|-------------|------|
| 200 | Список олимпиад | `{"olympiads": [{"id", "name", "description", "official_url", "preview_image", "image", "status", "is_archived"}]}` |

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
| 200 | Карточка олимпиады | `{"id", "name", "description", "official_url", "organizer", "preview_image", "image", "status", "is_archived": bool}` |
| 404 | Олимпиада не найдена | `{"detail": "Olympiad not found"}` |

Публичная модель минимальна: `name_norm`, `source_doc_id`, `createdAt`,
`updatedAt` и `archive_reason` — служебные поля импорта и панели
администратора, наружу они не отдаются. Причина архива пользователю ничего не
объясняет: он видит `status: "ARCHIVED"` и понятный текст в интерфейсе.

`is_archived` — производное от `status` поле для интерфейса: карточка не
разбирает статус сама. Значение всегда согласовано со `status`.

---

## GET /olympiads/{olympiad_id}/universities

Вузы, у которых есть опубликованные правила льгот по олимпиаде, с правилами
внутри. Публично.

**Query:** `benefit_type`, `subject`, `program_id`, `season_id`, `limit`,
`offset`.

| Code | Description | Body |
|------|-------------|------|
| 200 | Список вузов | `{"universities": [{"id", "name", "short_name", "description", "website", "preview_image", "image", "is_historical": bool, "rules": [BenefitRuleItem]}], "total": int}` |
| 404 | Олимпиада не найдена | `{"detail": "Olympiad not found"}` |
| 422 | Недопустимое значение фильтра | `{"detail": "..."}` |

`is_historical` равен `true`, если олимпиада архивная: такие вузы показываются
отдельным историческим блоком. `GET /olympiads/{olympiad_id}/benefit-facets` —
значения фильтров (как у вуза).

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

**Request body:** `{"name": str, "description"?, "official_url"?, "preview_image"?, "image"?}`

| Code | Description | Body |
|------|-------------|------|
| 201 | Олимпиада создана | `OlympiadResponse` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 409 | Такая олимпиада уже есть | `{"detail": "Olympiad with this name already exists"}` |

---

## POST /olympiads/edit_olympiad/{olympiad_id}

**Request body:** любое подмножество `{"name", "description", "official_url", "preview_image", "image", "status"}`.

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
| 200 | Найденные сущности | `{"query": str, "universities": [...], "olympiads": [...]}` |
| 200 (пустой `q`) | Ничего не искали | `{"query": "", "universities": [], "olympiads": []}` |

Олимпиады в поиске не содержат `source_url`.

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

## GET /admin/users, /admin/olympiads, /admin/benefit-rules, /admin/audit

**Администратор.** Списки для панели: пользователи (с ролью и привязкой к
вузу), полный каталог олимпиад включая архивные, реестр правил льгот во всех
состояниях (`status`, `verification_status`, `benefit_type`, `university_id`,
`olympiad_id`, `search`, `order=recent|name`) и журнал критичных действий
(`/admin/audit`: `action`, `actor_id`, `target_id`, `limit`, `offset` →
`{"events": [{"id", "action", "actor_id", "actor_email", "target_type",
"target_id", "details", "ip", "createdAt"}], "total"}`).

`/admin/users` и `/admin/olympiads` поддерживают query-параметры `search`
(подстрока по имени/фамилии/email для пользователей и по названию/описанию для
олимпиад), `limit` и `offset`. В ответе есть `total` — сколько записей под
фильтром всего, чтобы панель показывала «Показано N из M» и догружала
следующую страницу. Без `limit` возвращается весь список.

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
