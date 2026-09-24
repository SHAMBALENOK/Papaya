# Papaya API — Responses Reference

> Branch: `patch-0.8` | Base path: `/api/v1`
>
> Разделы ниже описывают endpoints auth/user (patch 0.5—0.8).
> Доменные ресурсы и RSOSH-импорт (patch 0.7—0.8) — в конце документа.
>
> Ошибки авторизации отдают JSON-объект `{"detail": {"code": str, "message": str}}`
> (коды `ACCESS_TOKEN_MISSING|INVALID|EXPIRED`, `REFRESH_TOKEN_MISSING|INVALID|EXPIRED`,
> `ACCOUNT_DISABLED`). Прочие ошибки — прежний строковый `{"detail": str}`.
>
> Живая схема всех маршрутов — Swagger по адресу http://localhost:5000/docs.

---

## GET /

**Суть:** Точка входа для проверки сессии авторизованного пользователя. Валидирует access-cookie (`access_jwt`); при его отсутствии/невалидности отдаёт 401. Извлекает профиль из БД и возвращает полный профиль. Каталог олимпиад и остальные данные SPA получает отдельными доменными маршрутами.

| Code | Description | Body |
|------|-------------|------|
| 200 | OK | `{"id": str, "email": str, "name": str, "surname": str, "gender": str|null, "bday": str|null, "bio": str|null, "phone": str|null, "country": str|null, "region": str|null, "status": str|null, "role": str, "isActive": bool, "createdAt": str, "updatedAt": str, "organization_id": str|null, "metadata": object|null}` |
| 401 | Access token missing/expired | `{"detail": {"code": "ACCESS_TOKEN_MISSING\|ACCESS_TOKEN_EXPIRED", "message": str}}` |
| 403 | Invalid access token / deactivated account | `{"detail": {"code": "ACCESS_TOKEN_INVALID\|ACCOUNT_DISABLED", "message": str}}` |
| 500 | Something has broken | `{"detail": "App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯"}` |

---

## GET /auth/

**Суть:** Gate-маршрут для определения, показывать ли форму входа или редиректить в приложение. Возвращает 403, если валиден access-токен, либо если access отсутствует/истёк, но валиден refresh‑cookie (у пользователя живая сессия — новый access выдаст `POST /auth/refresh`). Невалидный (неподписанный) access вместе с валидным refresh трактуется как «нет сессии» (200): такие токены несовместимы, клиенту проще показать форму входа, чем зациклиться. Refresh-токен сам по себе не даёт доступа к API, но подтверждает наличие живой сессии.

| Code | Description | Body |
|------|-------------|------|
| 200 | OK (пользователь не авторизован — страница доступна) | `null` |
| 403 | Already signed in (валиден access или refresh) | `{"detail": "Already signed in"}` |
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

## POST /auth/logout

**Суть:** Выход из системы. Не валидирует JWT — толерантен к любым (в т.ч. истёкшим и битым) токенам. Удаляет cookies `access_jwt` и `refresh_jwt` (Set-Cookie с `Max-Age=0`), завершая сессию. Токены на сервере не инвалидируются (stateless JWT) — просто убираются из браузера. Всегда отвечает 200.

| Code | Description | Body |
|------|-------------|------|
| 200 | Успешный выход, cookies удалены | `null` |
| 500 | Something has broken | `{"detail": "App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯"}` |

---

## POST /auth/refresh

**Суть:** Продление сессии по refresh-cookie. Декодирует refresh_jwt (тип `refresh`), находит пользователя по `sub`; выдаёт новый access_jwt (10 минут) и возвращает 200. SPA вызывает этот маршрут один раз при `ACCESS_TOKEN_EXPIRED` и повторяет исходный запрос. Деактивированный аккаунт (`isActive = false`) дальше не пускается.

| Code | Description | Body |
|------|-------------|------|
| 200 | Новый access установлен cookie | `null` (кука `access_jwt` обновлена на ответе) |
| 401 | Refresh token missing/expired | `{"detail": {"code": "REFRESH_TOKEN_MISSING\|REFRESH_TOKEN_EXPIRED", "message": str}}` |
| 403 | Invalid signature / пользователь не найден / аккаунт деактивирован | `{"detail": {"code": "REFRESH_TOKEN_INVALID\|ACCOUNT_DISABLED", "message": str}}` |
| 500 | Something has broken | `{"detail": "App has broken caused by error\n{e}\n ¯\\_(ツ)_/¯"}` |

---

> Устаревшие endpoints событий (patch 0.5: `/event/{id}`, `/event/add_event`,
> `/event/edit_event`, `/event/add_events_via_tables`, admin-архивация) удалены в
> `patch-0.7` вместе с таблицей `events` (миграция `0005`). Их место заняли
> доменные ресурсы Organizations / Olympiads / Docs (см. ниже).

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
| 401 | Токен отсутствует или истёк (`ACCESS_*`, `REFRESH_*` EXPIRED/MISSING) |
| 403 | Невалидный токен / деактивированный аккаунт / чужой профиль / уже авторизован |
| 404 | Ресурс не найден в БД |
| 409 | Конфликт (аккаунт с таким email уже существует) |
| 500 | Внутренняя ошибка сервера |

---

## Сводка маршрутов

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/` | Профиль текущего пользователя (проверка сессии) |
| GET | `/auth/` | Gate авторизации |
| POST | `/auth/register` | Регистрация |
| POST | `/auth/login` | Вход |
| POST | `/auth/logout` | Выход (толерантный, всегда 200) |
| POST | `/auth/refresh` | Продление сессии по refresh-cookie |
| GET | `/user/{user_id}` | Просмотр профиля |
| POST | `/user/{user_id}/edit_info` | Редактирование профиля |

---

# Доменные ресурсы (`patch-0.7`)

Все маршруты требуют авторизации (JWT в cookies). Создание/изменение — ADMIN или ORGANIZATION_ADMIN своей организации; список `/organizations` для ORGANIZATION_ADMIN фильтруется на сервере до своей организации.

## Organizations

| Метод | Путь | Доступ | Успешно | Назначение |
|-------|------|--------|---------|------------|
| GET | `/organizations` | авторизован | 200 | Список (`?type=&limit=`) |
| POST | `/organizations` | ADMIN | 201 | Создать организацию |
| GET | `/organizations/{id}` | авторизован | 200 | Детали организации |
| PATCH | `/organizations/{id}` | ADMIN / своя | 200 | Обновить |
| DELETE | `/organizations/{id}` | ADMIN / своя | 200 | Удалить |

**Organization:** `{"id", "name", "short_name", "type": "UNIVERSITY|ORGANIZER|SCHOOL|OTHER", "website", "description", "contacts": {"email": ..., "phone": ..., ...}, "metadata": {}, "createdAt", "updatedAt"}` — `contacts` — JSONB-объект контактов.

## Olympiads

| Метод | Путь | Доступ | Успешно | Назначение |
|-------|------|--------|---------|------------|
| GET | `/olympiads` | авторизован | 200 | Список (`?status=&organizer_id=&limit=`) |
| POST | `/olympiads` | ADMIN / орг-админ | 201 | Создать олимпиаду |
| GET | `/olympiads/{id}` | авторизован | 200 | Детали олимпиады |
| PATCH | `/olympiads/{id}` | ADMIN / своя | 200 | Обновить |
| DELETE | `/olympiads/{id}` | ADMIN / своя | 200 | Удалить |

**Olympiad:** `{"id", "name", "description", "status": "DRAFT|PUBLISHED|ARCHIVED", "subjects": [...], "levels": [...], "years": [...], "grades": [...], "profiles": [...], "organizer_ids": [...], "bvi_organizations": [...], "official_url", "registration_url", "region", "metadata": {}, "schedule": {...}|null, "current_status": "...|null", "current_stage": {...}|null, "next_deadline": "...|null", ...}` — связи хранятся в JSONB-массивах; статус задаётся при обновлении, создание всегда приводит к `PUBLISHED`.

`schedule` (JSONB, этапы/сезон) не хранит готовых статусов — они вычисляются при выдаче и никогда не пишутся в БД/кэш:

```json
{
  "season": "2026/27",
  "stages": [
    {"id": "registration_1", "name": "Регистрация", "type": "REGISTRATION",
     "start_at": "2026-10-01T00:00:00+03:00", "end_at": "2026-10-15T23:59:59+03:00"},
    {"id": "qualification_1", "name": "Отборочный этап", "type": "QUALIFICATION",
     "start_at": "2026-10-20T00:00:00+03:00", "end_at": "2026-11-05T23:59:59+03:00"}
  ]
}
```

- типы этапов: `REGISTRATION | QUALIFICATION | FINAL | RESULTS`; даты только ISO 8601 с таймзоной, `start_at <= end_at`; идентификаторы этапов уникальны;
- `current_stage` — только **фактически активный** этап (его `start_at` наступил, а фактический конец — `end_at` или конец суток публикации для `RESULTS` — не прошёл); если активного этапа нет (ещё не начался, между этапами, всё завершено) — `null`. Ближайшие даты в `next_deadline`: конец активного/предстоящего этапа либо начало следующего этапа. При пересечении активных этапов побеждает «более продвинутый» тип (`FINAL > QUALIFICATION > RESULTS > REGISTRATION`), при равенстве — этап раньше в массиве;
- `current_status` без активного этапа: все этапы ещё впереди → `UPCOMING` («ещё не началась»), все завершены → `FINISHED`, иначе (`между этапами` — регистрация закрылась, следующий этап впереди) → `REGISTRATION_CLOSED`;
- `RESULTS` без `end_at` — событие публикации результатов: активен до конца суток `start_at` (в этот день статус `RESULTS`), затем олимпиада завершается `FINISHED`;
- `current_status` может быть одним из `UPCOMING | REGISTRATION_OPEN | REGISTRATION_CLOSED | QUALIFICATION | FINAL | RESULTS | FINISHED`.

## Docs

| Метод | Путь | Доступ | Успешно | Назначение |
|-------|------|--------|---------|------------|
| GET | `/docs` | авторизован | 200 | Список (`?type=&status=&organization_id=&olympiad_id=`) |
| POST | `/docs` | ADMIN / орг-админ | 201 | Загрузка файла (`multipart`: `file` + query `type`, `organization_id`) |
| GET | `/docs/{id}` | авторизован (object-level) | 200 | Детали документа |
| GET | `/docs/{id}/file` | авторизован (object-level) | 200 | Скачивание файла |
| PATCH | `/docs/{id}` | ADMIN / своя | 200 | Обновить метаданные |
| DELETE | `/docs/{id}` | ADMIN / своя | 200 | Удалить запись |

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