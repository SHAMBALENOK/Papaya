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

---

## GET /

Текущий пользователь по cookie-токенам.

| Code | Description | Body |
|------|-------------|------|
| 200 | Профиль текущего пользователя | `{"id", "email", "name", "surname", "role", "university_id", "isActive", "gender", "bday", "bio", "phone", "country", "region", "status", "createdAt", "updatedAt"}` |
| 401 | Access token missing | `{"detail": "Access token missing"}` |
| 403 | Invalid token | `{"detail": "Invalid access token"}` |
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
| 422 | Ошибка валидации | `{"detail": [...]}` |

---

## GET /user/{user_id}

Профиль пользователя по id (страница профиля и запасной путь клиента).

| Code | Description | Body |
|------|-------------|------|
| 200 | Профиль | `UserResponse` |
| 401 / 403 | Токен отсутствует или невалиден | `{"detail": "..."}` |
| 404 | Пользователь не найден | `{"detail": "User not found"}` |

---

## POST /user/{user_id}/edit_info

Изменение собственного профиля. Роль и привязка к университету здесь не
меняются — это делает администратор.

| Code | Description | Body |
|------|-------------|------|
| 200 | Профиль обновлён | `UserResponse` |
| 400 | Пустое тело | `{"detail": "No fields to update"}` |
| 403 | Чужой профиль или занятый email | `{"detail": "You can only edit your own profile"}` |
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
| 200 | Карточка университета | `{"id", "name", "name_norm", "short_name", "description", "website", "image", "createdAt", "updatedAt"}` |
| 404 | Вуз не найден | `{"detail": "University not found"}` |

---

## GET /universities/{university_id}/olympiads

**Query:** `include_pending` (требует входа и прав на этот вуз).

| Code | Description | Body |
|------|-------------|------|
| 200 | Олимпиады с БВИ | `{"olympiads": [OlympiadResponse + "bvi_status"]}` |
| 401 | `include_pending` без входа | `{"detail": "Access token required to view pending requests"}` |
| 403 | Чужие заявки | `{"detail": "You can only view pending requests of your own university"}` |
| 404 | Вуз не найден | `{"detail": "University not found"}` |

Публично видны только подтверждённые (`CONFIRMED`) связи.

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

## POST /universities/{university_id}/bvi

Заявка: «этот университет даёт БВИ за эту олимпиаду». Связь создаётся в
статусе `PENDING`; повторная заявка возвращает существующую связь.

Заявка возможна только по актуальной олимпиаде: архивная запись сохраняет
прежние связи, но новых не получает. Уже подтверждённые связи при архивации
остаются на месте.

**Request body:** `{"olympiad_id": str}`

| Code | Description | Body |
|------|-------------|------|
| 201 | Заявка создана или уже существует | `{"id", "university_id", "olympiad_id", "status", "createdBy", "confirmedBy", "createdAt", "updatedAt"}` |
| 403 | Не администратор и не представитель этого вуза | `{"detail": "You can only manage your own university"}` |
| 404 | Вуз или олимпиада не найдены | `{"detail": "University not found"}` / `{"detail": "Olympiad not found"}` |
| 409 | Олимпиада архивирована | `{"detail": "Олимпиада архивирована: её нет в актуальном перечне РСОШ, новые заявки БВИ за неё не принимаются. Подтверждённые ранее связи сохраняются."}` |

---

## GET /universities/{university_id}/olympiads, GET /olympiads/{olympiad_id}/universities

Публичные списки связей БВИ. Видны только подтверждённые связи.

| Code | Description | Body |
|------|-------------|------|
| 200 | Список связей | `{"olympiads": [BviOlympiadItem]}` / `{"universities": [BviUniversityItem]}` |
| 401 | Запрошены неподтверждённые заявки без входа | `{"detail": "Access token required to view pending requests"}` |
| 403 | Чужие заявки | `{"detail": "You can only view pending requests of your own university"}` |
| 404 | Университет или олимпиада не найдены | `{"detail": "..."}` |

`BviOlympiadItem`: `id`, `name`, `description`, `official_url`,
`preview_image`, `image`, `source_url`, `status`, `bvi_status`,
`is_historical`.

`BviUniversityItem`: `id`, `name`, `short_name`, `description`, `website`,
`preview_image`, `image`, `bvi_status`, `is_historical`.

`is_historical` — подтверждённая связь с архивной олимпиадой. Такая связь
сохранена (архив не отменяет историю), но интерфейс показывает
«Архивная олимпиада» / «Историческая связь» вместо «БВИ».

---

## POST /universities/{university_id}/bvi/remove

**Request body:** `{"olympiad_id": str}`

| Code | Description | Body |
|------|-------------|------|
| 200 | Связь удалена | `{"status": "removed", "olympiad_id": str}` |
| 403 | Нет прав на этот вуз | `{"detail": "You can only manage your own university"}` |
| 404 | Связи нет | `{"detail": "BVI link not found"}` |

---

## POST /universities/{university_id}/bvi/{olympiad_id}/moderation

Административное действие над заявкой. Произвольной смены статуса нет.

**Request body:** `{"action": "confirm"｜"reject"｜"revoke"}`

| Code | Description | Body |
|------|-------------|------|
| 200 | Подтверждена или удалена | `{"result": "CONFIRMED"｜"removed", "university_id", "olympiad_id", "status"}` |
| 401 | Нет токена | `{"detail": "..."}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Связи нет | `{"detail": "BVI link not found"}` |
| 409 | Действие не применимо к текущему состоянию | `{"detail": "..."}` — например, отклонить уже подтверждённую связь |
| 422 | Неизвестное действие | `{"detail": [...]}` |

- `confirm` — `PENDING` → `CONFIRMED`; поле `confirmedBy` заполняется.
- `reject` — заявка отклонена, связь удаляется.
- `revoke` — подтверждение отозвано, связь удаляется.

Перехода `CONFIRMED → PENDING` не существует: это не состояние заявки, а
отзыв публичного факта.

Модерация: подтверждение или снятие связи.

**Request body:** `{"status": "PENDING" | "CONFIRMED"}`

| Code | Description | Body |
|------|-------------|------|
| 200 | Статус изменён | `BviLinkResponse` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Связи нет | `{"detail": "BVI link not found"}` |
| 422 | Неверный статус | `{"detail": [...]}` |

---

## GET /olympiads

Каталог олимпиад. Публично.

**Query:** `search` (по названию и описанию), `include_archived` (показать
олимпиады вне актуального перечня РСОШ), `limit`.

| Code | Description | Body |
|------|-------------|------|
| 200 | Список олимпиад | `{"olympiads": [{"id", "name", "description", "official_url", "preview_image", "image", "source_url", "status", "is_archived"}]}` |

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
| 200 | Карточка олимпиады | `{"id", "name", "description", "official_url", "preview_image", "image", "source_url", "status"}` |

Публичная модель минимальна: `name_norm`, `source_doc_id`, `createdAt`,
`updatedAt` и `archive_reason` — служебные поля импорта и панели
администратора, наружу они не отдаются. Причина архива пользователю ничего не
объясняет: он видит `status: "ARCHIVED"` и понятный текст в интерфейсе.
| 404 | Олимпиада не найдена | `{"detail": "Olympiad not found"}` |

---

## GET /olympiads/{olympiad_id}/universities

Вузы, дающие БВИ за олимпиаду (обратная сторона связи). Публично, только
подтверждённые связи.

| Code | Description | Body |
|------|-------------|------|
| 200 | Список вузов | `{"universities": [UniversityResponse + "bvi_status"]}` |
| 404 | Олимпиада не найдена | `{"detail": "Olympiad not found"}` |

---

## GET /olympiads/{olympiad_id}/source

Откуда взялась информация об олимпиаде. Публично, без доступа к файлу
документа: ровно два пользовательских поля.

| Code | Description | Body |
|------|-------------|------|
| 200 | Источник данных | `{"title": str, "source_url": str｜null}` |
| 404 | Олимпиада не найдена | `{"detail": "Olympiad not found"}` |

`404` означает только «олимпиады нет». Отсутствие документа РСОШ — нормальное
состояние, а не ошибка:

- импорт из РСОШ → `title` из названия документа (иначе «Перечень олимпиад
  РСОШ»), `source_url` из metadata или поля олимпиады;
- ручное создание → `{"title": "Создано администратором Papaya", "source_url": null}`
  либо с заполненной ссылкой.

Внутренние поля документа (UUID, имя файла, хеш, статус обработки, metadata) в
ответе не участвуют. Сам `source_doc_id` олимпиады в публичных ответах каталога
тоже не отдаётся: он остаётся внутренним идентификатором и доступен
администратору в `GET /admin/olympiads`.

---

## POST /olympiads/add_olympiad

Ручное создание олимпиады (резервный путь; основной — импорт РСОШ).

**Request body:** `{"name": str, "description"?, "official_url"?, "preview_image"?, "image"?, "source_url"?}`

| Code | Description | Body |
|------|-------------|------|
| 201 | Олимпиада создана | `OlympiadResponse` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 409 | Такая олимпиада уже есть | `{"detail": "Olympiad with this name already exists"}` |

---

## POST /olympiads/edit_olympiad/{olympiad_id}

**Request body:** любое подмножество `{"name", "description", "official_url", "image", "source_url", "status"}`.

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

---

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
| 202 | Импорт запущен | `{"id", "name", "type", "status", "state", "summary", "warnings", "error", "execution": "celery"｜"inline"}` |
| 400 | Документ не подходит или импорт не стартует из текущего состояния | `{"detail": "Only RSOSH_LIST documents can be imported"}` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |

В фоновом режиме сразу после ответа `state` = `processing`: состояние нужно
полярно опрашивать до `review` или `failed`.

---

## GET /imports/{import_id}

| Code | Description | Body |
|------|-------------|------|
| 200 | Состояние импорта | `{"state": "processing｜review｜approved｜rejected｜failed", "summary": {"total", "new", "merge", "review"}, "warnings": [...], "error": str｜null}` |
| 404 | Импорт не найден | `{"detail": "Import not found"}` |

---

## GET /imports/{import_id}/preview

Кандидаты импорта: что будет создано, что обновлено, что требует проверки.

| Code | Description | Body |
|------|-------------|------|
| 200 | Preview | `{"import": {...}, "pages": [{"page", "method", "orientation", "tables", "rows", "chars", "confidence", "issues"}], "candidates": [{"name", "name_norm", "description", "action": "create｜merge｜skip", "matched_olympiad_id", "match_score", "confidence": "ok｜review", "page", "issues"}]}` |
| 409 | Импорт ещё обрабатывается | `{"detail": "Import is still processing"}` |

Кандидаты с `confidence: "review"` требуют решения администратора: сомнительное
сопоставление с существующей олимпиадой нельзя принять автоматически.

---

## POST /imports/{import_id}/confirm

**Request body:** `{"skip": [name_norm, ...], "archive_missing": bool}`.

| Code | Description | Body |
|------|-------------|------|
| 200 | Импорт применён | `{"import": {...}, "result": {"created": [...], "updated": [...], "archived": [...], "skipped": [...], "errors": [...]}, "skipped": [name_norm, ...]}` |
| 400 | Импорт нельзя подтвердить или неизвестные `skip` | `{"detail": "Import state approved is not confirmable; start a new import first"}` |

Поле верхнего уровня `skipped` — то, что администратор снял в preview.
Снятый кандидат не пишется в каталог **и не считается отсутствующим** в
перечне: иначе ошибка распознавания одной строки архивировала бы
существующую олимпиаду (у кандидата-merge защищается его `matched_olympiad_id`).

---

## POST /imports/{import_id}/reject

| Code | Description | Body |
|------|-------------|------|
| 200 | Результаты отклонены, в каталог ничего не записано | `{"state": "rejected", ...}` |
| 400 | Отклонить нельзя | `{"detail": "Import state approved is not rejectable"}` |

---

## GET /admin/users, /admin/olympiads, /admin/bvi

**Администратор.** Списки для панели: пользователи (с ролью и привязкой к
вузу), полный каталог олимпиад включая архивные, очередь заявок БВИ.

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

## POST /admin/grant_admin/{user_id}, /admin/demote_admin/{user_id}

Назначение и снятие роли `ADMIN`. **Администратор.**

`grant_admin` сохраняет привязку к университету, если она была: `demote_admin`
тогда возвращает роль представителя (`EDITOR`), а не `USER`.

| Code | Description | Body |
|------|-------------|------|
| 200 | Роль изменена | `UserResponse` |
| 403 | Не администратор | `{"detail": "Permission denied"}` |
| 404 | Пользователь не найден | `{"detail": "User not found"}` |
| 409 | Не ADMIN, либо это последний активный администратор | `{"detail": "User is not ADMIN"}` / `{"detail": "Нельзя снять роль администратора: это последний активный администратор Papaya..."}` |

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

Поля `website`, `official_url`, `preview_image`, `image`, `source_url` проверяются
одинаково при создании и при правке: допустимы только `http://` и `https://` с
хостом. `javascript:`, `data:`, `file:`, `vbscript:`, строки без схемы и с
пробелами отклоняются с 422 — интерфейс вставляет эти значения в `href`/`src`,
поэтому схема проверяется на входе, а не подменяется экранированием на выводе.
Пустая строка считается «ссылки нет» и сохраняется как `null`.
