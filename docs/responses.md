# Papaya API — Responses Reference

> Branch: `patch-0.7` | Base path: `/api/v1`
>
> Разделы ниже описывают исторические (patch 0.5) endpoints auth/user/event.
> Доменные ресурсы и RSOSH-импорт (patch 0.7) — в конце документа.

---

## GET /

**Суть:** Главная страница приложения. Проверяет авторизацию пользователя через JWT-токены (access + refresh в cookies), извлекает профиль из БД и возвращает данные пользователя вместе со списком случайных событий (до 10 записей из таблицы `event`). Служит точкой входа в приложение после авторизации.

| Code | Description | Body |
|------|-------------|------|
| 200 | OK | `{"user_id": str, "user_name": str, "user_surname": str, "user_email": str, "events": [{"id": str, "name": str, "disc": str|null, "preview_picture": str|null, "picture": str|null, "isActive": bool}, ...]}` |
| 401 | Access or refresh token missing | `{"detail": "..."}` |
| 403 | Invalid refresh or access token | `{"detail": "..."}` |
| 500 | Something has broken | `{"detail": "App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯"}` |

---

## GET /auth/

**Суть:** Страница авторизации/регистрации. Проверяет, есть ли у пользователя валидные JWT-токены. Если пользователь уже авторизован — возвращает 403 (повторный вход не требуется). Если токены отсутствуют или невалидны — страница доступна для ввода данных. По сути это gate-маршрут, определяющий, показывать ли форму входа или редиректить в приложение.

| Code | Description | Body |
|------|-------------|------|
| 200 | OK (пользователь не авторизован — страница доступна) | `null` |
| 403 | Already signed in | `{"detail": "Already signed in"}` |
| 401 | Access or refresh token missing | `{"detail": "..."}` |
| 500 | Something has broken | `{"detail": "App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯"}` |

---

## POST /auth/register

**Суть:** Регистрация нового пользователя. Принимает данные профиля и пароль, валидирует пароль через регулярное выражение (`re_check`), хеширует его, создаёт запись в таблице `user` в PostgreSQL. При успехе генерирует пару JWT-токенов (access — 600s, refresh — 1209600s / 14 дней) и устанавливает их в httpOnly cookies. Возвращает полный профиль пользователя.

**Request body:** `UserCreate`
```json
{
  "id": "str",
  "name": "str",
  "surname": "str",
  "email": "str",
  "isActive": true,
  "password": "str"
}
```
| Code | Description | Body |
|------|-------------|------|
| 200 | Успешная регистрация, токены установлены в cookies | `UserResponse`: `{"id": str, "name": str, "surname": str, "email": str, "isActive": bool, "gender": str|null, "bday": str|null, "bio": str|null, "phone": str|null, "country": str|null, "region": str|null, "status": str|null}` |
| 400 | Пароль не соответствует требованиям (длина, символы и т.д.) | `{"detail": "<reason from re_check>"}` |
| 409 | Пользователь с таким email уже существует | `{"detail": "You already have account"}` |
| 500 | Something has broken | `{"detail": "App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯"}` |

---

## POST /auth/login

**Суть:** Вход в систему. Принимает email и пароль, ищет пользователя в БД по email, сравнивает хеш пароля. При успехе генерирует пару JWT-токенов и устанавливает их в httpOnly cookies. Возвращает полный профиль пользователя. Не создаёт нового пользователя — только аутентифицирует существующего.

**Request body:** `UserCreate`
```json
{
  "id": "str",
  "name": "str",
  "surname": "str",
  "email": "str",
  "isActive": true,
  "password": "str"
}
```

| Code | Description | Body |
|------|-------------|------|
| 200 | Успешный вход, токены установлены в cookies | `UserResponse`: `{"id": str, "name": str, "surname": str, "email": str, "isActive": bool, "gender": str|null, ...}` |
| 404 | Email не найден в базе данных | `{"detail": "your email is not in database, try to register"}` |
| 401 | Неверный пароль | `{"detail": "incorrect email or password"}` |
| 500 | Something has broken | `{"detail": "App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯"}` |

---

## GET /auth/logout

**Суть:** Выход из системы. Валидирует текущие JWT-токены, после чего удаляет cookies `access_jwt` и `refresh_jwt`, завершая сессию. Не инвалидирует токены на стороне сервера (stateless JWT) — просто убирает их из браузера.

| Code | Description | Body |
|------|-------------|------|
| 200 | Успешный выход, cookies удалены | `null` |
| 403 | Invalid refresh or access token | `{"detail": "..."}` |
| 401 | Access or refresh token missing | `{"detail": "..."}` |
| 500 | Something has broken | `{"detail": "App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯"}` |

---

## GET /event/{event_id}

**Суть:** Получение информации о конкретном событии по его ID. Извлекает запись из таблицы `event` в PostgreSQL. Возвращает название, описание, изображения и статус активности события. Используется для просмотра деталей мероприятия.

| Code | Description | Body |
|------|-------------|------|
| 200 | OK | `EventResponse`: `{"id": str, "name": str, "disc": str|null, "preview_picture": str|null, "picture": str|null, "isActive": bool}` |
| 401 | Access or refresh token missing | `{"detail": "..."}` |
| 403 | Invalid refresh or access token | `{"detail": "..."}` |
| 404 | Событие с таким ID не найдено | `{"detail": "Page is missing"}` |
| 500 | Something has broken | `{"detail": "App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯"}` |

---

## POST /event/add_event

**Суть:** Создание нового события. Принимает данные пользователя (для проверки прав) и данные события. Проверяет, что запрос делает владелец профиля (сверяет user_id из токена с user_id в теле). Создаёт запись в таблице `event` с привязкой к владельцу. Возвращает созданное событие.

**Request body:** `UserBase` + `EventCreate`
```json
{
  "user": {"id": "str", "name": "str", "surname": "str", "email": "str", "isActive": true},
  "event": {
    "id": "str",
    "name": "str",
    "disc": "str|null",
    "preview_picture": "str|null",
    "picture": "str|null",
    "isActive": true,
    "owner": "str",
    "createdAt": "datetime",
    "updatedAt": "datetime"
  }
}
```

| Code | Description | Body |
|------|-------------|------|
| 200 | Событие создано | `EventResponse`: `{"id": str, "name": str, "disc": str|null, "preview_picture": str|null, "picture": str|null, "isActive": bool}` |
| 401 | Access or refresh token missing | `{"detail": "..."}` |
| 403 | Invalid token / попытка создать событие от чужого имени | `{"detail": "..."}` |
| 500 | Something has broken | `{"detail": "App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯"}` |

---

## POST /event/edit_event

**Суть:** Редактирование существующего события. Принимает обновлённые данные; поля со значением `"null"` (строка) игнорируются — сохраняется прежнее значение. Проверяет права владельца. Обновляет запись в таблице `event`. Возвращает обновлённое событие.

**Request body:** `UserBase` + `EventCreate` (аналогично add_event)

| Code | Description | Body |
|------|-------------|------|
| 200 | Событие обновлено | `EventResponse`: `{"id": str, "name": str, "disc": str|null, "preview_picture": str|null, "picture": str|null, "isActive": bool}` |
| 401 | Access or refresh token missing | `{"detail": "..."}` |
| 403 | Invalid token / не ваш профиль | `{"detail": "..."}` |
| 404 | Событие не найдено в БД | `{"detail": "Event not found"}` |
| 500 | Something has broken | `{"detail": "App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯"}` |

---

## POST /event/add_events_via_pdf_tables

**Суть:** Массовое добавление событий через загрузку PDF-файла, содержащего таблицы с данными. Парсит PDF, извлекает табличные строки и создаёт события в БД. Проверяет, что загрузку выполняет владелец профиля. Возвращает профиль пользователя после обработки.

**Request body:** `multipart/form-data`
- `user` — JSON (UserBase)
- `event` — JSON (EventCreate)
- `file` — PDF-файл

| Code | Description | Body |
|------|-------------|------|
| 200 | События из PDF добавлены | `UserResponse`: `{"id": str, "name": str, "surname": str, "email": str, "isActive": bool, ...}` |
| 401 | Access or refresh token missing | `{"detail": "..."}` |
| 403 | Попытка загрузить от чужого профиля | `{"detail": "It looks like you are trying to use not your profile"}` |
| 500 | Something has broken | `{"detail": "App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯"}` |

---

## GET /user/{user_id}

**Суть:** Получение полного профиля пользователя по ID. Доступ строго ограничен: пользователь может просматривать только свой собственный профиль (user_id из токена должен совпадать с user_id в пути). Возвращает все поля профиля, включая необязательные (gender, bday, bio, phone, country, region, status).

| Code | Description | Body |
|------|-------------|------|
| 200 | OK | `UserResponse`: `{"id": str, "name": str, "surname": str, "email": str, "isActive": bool, "gender": str|null, "bday": str|null, "bio": str|null, "phone": str|null, "country": str|null, "region": str|null, "status": str|null}` |
| 401 | Access or refresh token missing | `{"detail": "..."}` |
| 403 | Попытка просмотра чужого профиля | `{"detail": "It looks like you are trying to look on not your profile"}` |
| 500 | Something has broken | `{"detail": "App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯"}` |

---

## POST /user/{user_id}/edit_info

**Суть:** Редактирование профиля пользователя. Принимает объект `UserUpdate`; поля со значением `null` игнорируются (сохраняется текущее значение). Проверяет, что редактируется собственный профиль. Обновляет запись в таблице `user`. Возвращает обновлённый профиль.

**Request body:** `UserUpdate`
```json
{
  "id": "str",
  "name": "str",
  "surname": "str",
  "email": "str",
  "isActive": true,
  "gender": "str|null",
  "bday": "str|null",
  "bio": "str|null",
  "phone": "str|null",
  "country": "str|null",
  "region": "str|null",
  "status": "str|null",
  "role": "str"
}
```

| Code | Description | Body |
|------|-------------|------|
| 200 | Профиль обновлён | `UserResponse`: `{"id": str, "name": str, "surname": str, "email": str, "isActive": bool, ...}` |
| 401 | Access or refresh token missing | `{"detail": "..."}` |
| 403 | Попытка редактирования чужого профиля | `{"detail": "It looks like you are trying to change not your profile"}` |
| 404 | Пользователь не найден в БД | `{"detail": "Cannot find this user in database, try something else)"}` |
| 500 | Something has broken | `{"detail": "App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯"}` |

---

## Сводка кодов ответов

| Code | Значение |
|------|----------|
| 200 | Успех |
| 400 | Неверный формат данных (валидация пароля) |
| 401 | Отсутствует access/refresh токен в cookies |
| 403 | Невалидный токен / чужой профиль / уже авторизован |
| 404 | Ресурс не найден в БД |
| 409 | Конфликт (аккаунт с таким email уже существует) |
| 500 | Внутренняя ошибка сервера |

---

## Сводка маршрутов

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/` | Главная: профиль + случайные события |
| GET | `/auth/` | Gate авторизации |
| POST | `/auth/register` | Регистрация |
| POST | `/auth/login` | Вход |
| GET | `/auth/logout` | Выход |
| GET | `/event/{event_id}` | Просмотр события |
| POST | `/event/add_event` | Создание события |
| POST | `/event/edit_event` | Редактирование события |
| POST | `/event/add_events_via_pdf_tables` | Импорт событий из PDF |
| GET | `/user/{user_id}` | Просмотр профиля |
| POST | `/user/{user_id}/edit_info` | Редактирование профиля |

---

# Доменные ресурсы (`patch-0.7`)

Все маршруты требуют авторизации (JWT в cookies). Создание/изменение — ADMIN или ORGANIZATION_ADMIN своей организации; списки для ORGANIZATION_ADMIN фильтруются на сервере.

## Organizations

| Метод | Путь | Доступ | Успешно | Назначение |
|-------|------|--------|---------|------------|
| GET | `/organizations` | авторизован | 200 | Список (`?type=&limit=`) |
| POST | `/organizations` | ADMIN | 201 | Создать организацию |
| GET | `/organizations/{id}` | авторизован | 200 | Детали организации |
| PATCH | `/organizations/{id}` | ADMIN / своя | 200 | Обновить |
| DELETE | `/organizations/{id}` | ADMIN / своя | 204 | Удалить |

**Organization:** `{"id", "name", "short_name", "type": "UNIVERSITY|ORGANIZER|SCHOOL|OTHER", "website", "description", "contact_email", "contact_phone", "metadata": {}, "createdAt", "updatedAt"}`

## Olympiads

| Метод | Путь | Доступ | Успешно | Назначение |
|-------|------|--------|---------|------------|
| GET | `/olympiads` | авторизован | 200 | Список (`?status=&organizer_id=&limit=`) |
| POST | `/olympiads` | ADMIN / орг-админ | 201 | Создать олимпиаду |
| GET | `/olympiads/{id}` | авторизован | 200 | Детали олимпиады |
| PATCH | `/olympiads/{id}` | ADMIN / своя | 200 | Обновить |
| DELETE | `/olympiads/{id}` | ADMIN / своя | 204 | Удалить |

**Olympiad:** `{"id", "name", "description", "status": "REGISTRATION_OPEN|...", "subjects": [...], "levels": [...], "years": [...], "grades": [...], "profiles": [...], "organizer_ids": [...], "bvi_organizations": [...], "official_url", "registration_url", "region", "metadata": {}, ...}` — связи хранятся в JSONB-массивах.

## Docs

| Метод | Путь | Доступ | Успешно | Назначение |
|-------|------|--------|---------|------------|
| GET | `/docs` | авторизован | 200 | Список (`?type=&status=&organization_id=&olympiad_id=`) |
| POST | `/docs` | ADMIN / орг-админ | 201 | Загрузка файла (`multipart`: `file` + query `type`, `organization_id`) |
| GET | `/docs/{id}` | авторизован (object-level) | 200 | Детали документа |
| GET | `/docs/{id}/file` | авторизован (object-level) | 200 | Скачивание файла |
| PATCH | `/docs/{id}` | ADMIN / своя | 200 | Обновить метаданные |
| DELETE | `/docs/{id}` | ADMIN / своя | 204 | Удалить запись |

**Errors:** 400 неподдерживаемый формат файла, 403 чужая организация, 413 больше `MAX_UPLOAD_MB`. **Doc:** `{"id", "name", "type": "RSOSH_LIST|OLYMPIAD_REGULATION|UNIVERSITY_DOCUMENT|OTHER", "status": "UPLOADED|PROCESSING|NEEDS_REVIEW|PROCESSED|FAILED", "organization_id", "olympiad_id", "uploaded_by", "checksum", "metadata": {}, ...}`

---

# RSOSH-импорт (`patch-0.7`)

Пайплайн: загрузить документ типа `RSOSH_LIST` → `POST /imports/rsosh` → Celery извлекает таблицы (PDF → OCR, XLSX напрямую), нормализует и сопоставляет олимпиады → админ подтверждает. **В БД олимпиады не пишутся до `confirm`.**

Состояния (`docs.metadata["rsosh"].state`): `processing → review → approved|rejected|failed`.

| Метод | Путь | Доступ | Успешно | Назначение |
|-------|------|--------|---------|------------|
| GET | `/imports` | ADMIN / орг-админ (свои) | 200 | Список импортов (state, error, summary) |
| POST | `/imports/rsosh` | ADMIN / орг-админ | 202 | Старт импорта, `{"doc_id"}` |
| GET | `/imports/{id}` | ADMIN / орг-админ | 200 | `{"import_id", "status", "doc_status", "error", "summary"}` |
| GET | `/imports/{id}/preview` | ADMIN / орг-админ | 200 | `{"candidates": [{name, name_norm, subjects, levels, years, action: "create|merge|skip", confidence, reviews}]}` |
| POST | `/imports/{id}/confirm` | ADMIN / орг-админ | 200 | Применить: создать/объединить олимпиады, кэш инвалидирован; идемпотентно |
| POST | `/imports/{id}/reject` | ADMIN / орг-админ | 200 | Отклонить, ничего не пишется |

**Errors:** 400 не `RSOSH_LIST` / недопустимый статус старта, 409 документ/импорт не в подходящем состоянии (`preview` ещё `processing`), 404 нет документа, 403 чужая организация, 503 очередь недоступна (импорт откатывается).