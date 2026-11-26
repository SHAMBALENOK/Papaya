# API

[← Документация](README.md) · [К README проекта](../README.md) · [English](en/api.md)

Все маршруты — под префиксом `/api/v1`. Авторизация — JWT в HttpOnly-cookies
(`access_jwt`, `refresh_jwt`), защита от CSRF через `SameSite=Lax`, `Secure` в
production. Полная интерактивная схема — http://localhost:5000/docs, подробное
описание ответов — в [responses.md](responses.md).

## Каталоги, поиск и страницы

| Метод | Путь | Назначение | Доступ |
|-------|------|-----------|--------|
| `GET` | `/api/v1/universities?search=` | каталог университетов | Публичный |
| `GET` | `/api/v1/universities/{id}` | страница университета | Публичный |
| `GET` | `/api/v1/universities/{id}/benefits` | опубликованные правила льгот вуза | Публичный |
| `GET` | `/api/v1/universities/{id}/programs` | образовательные программы вуза | Публичный |
| `GET` | `/api/v1/olympiads?search=&include_archived=` | каталог олимпиад | Публичный |
| `GET` | `/api/v1/olympiads/{id}` | страница олимпиады | Публичный |
| `GET` | `/api/v1/olympiads/{id}/source` | источник данных об олимпиаде | Публичный |
| `GET` | `/api/v1/olympiads/{id}/seasons?include_archived=&profiles=` | сезоны олимпиады и профили | Публичный |
| `GET` | `/api/v1/olympiads/{id}/universities` | вузы с опубликованными правилами по олимпиаде | Публичный |
| `GET` | `/api/v1/benefits?search=&benefit_type=&university_id=&olympiad_id=&season_id=&profile_id=&level=&limit=&offset=` | каталог льгот с фильтрами и `total` | Публичный |
| `GET` | `/api/v1/benefits/{id}` | одно опубликованное правило | Публичный |
| `GET` | `/api/v1/benefits/olympiad/{id}` | правила по олимпиаде с фильтром по сезону и профилю | Публичный |
| `GET` | `/api/v1/search?q=` | поиск по обоим каталогам | Публичный |

## Управление каталогом

| Метод | Путь | Назначение | Доступ |
|-------|------|-----------|--------|
| `POST` | `/api/v1/universities/add_university` | создать университет | `ADMIN` |
| `POST` | `/api/v1/universities/edit_university/{id}` | изменить университет | `ADMIN` |
| `POST` | `/api/v1/olympiads/add_olympiad` | создать олимпиаду вручную | `ADMIN` |
| `POST` | `/api/v1/olympiads/edit_olympiad/{id}` | изменить олимпиаду | `ADMIN` |
| `POST` | `/api/v1/olympiads/{id}/seasons` | создать сезон | `ADMIN` |
| `PUT` | `/api/v1/seasons/{id}` | изменить сезон (нужна `version`) | `ADMIN` |
| `POST` | `/api/v1/seasons/{id}/profiles` | создать профиль с уровнем РСОШ | `ADMIN` |
| `PUT` | `/api/v1/profiles/{id}` | изменить профиль | `ADMIN` |
| `POST` | `/api/v1/admin/archive_olympiad/{id}` | архивировать или вернуть олимпиаду | `ADMIN` |
| `GET` | `/api/v1/admin/users` | пользователи и роли | `ADMIN` |
| `POST` | `/api/v1/admin/role/{user_id}` | сменить роль и привязку одним запросом | `ADMIN` |

## Правила льгот

| Метод | Путь | Назначение | Доступ |
|-------|------|-----------|--------|
| `POST` | `/api/v1/universities/{id}/benefits` | создать правило своего вуза | `EDITOR` (свой вуз) / `ADMIN` |
| `PUT` / `PATCH` | `/api/v1/benefits/{id}` | изменить правило (нужна `version`) | `EDITOR` (свой вуз) / `ADMIN` |
| `POST` | `/api/v1/benefits/{id}/rollback` | откатить версию атомарно | `EDITOR` (свой вуз) / `ADMIN` |
| `POST` | `/api/v1/benefits/{id}/verify` | проверить правило по приказу вуза | `ADMIN` |
| `POST` | `/api/v1/benefits/{id}/reject` | отклонить правило с причиной | `ADMIN` |
| `GET` | `/api/v1/admin/benefits` | очередь модерации правил | `ADMIN` |

## Документы и импорт

| Метод | Путь | Назначение | Доступ |
|-------|------|-----------|--------|
| `POST` | `/api/v1/docs/upload` | загрузить документ-источник (`RSOSH_LIST`, `UNIVERSITY_ORDER`, `OTHER`) | `ADMIN` |
| `POST` | `/api/v1/imports/rsosh` | запустить импорт документа | `ADMIN` |
| `GET` | `/api/v1/imports` | список прогонов импорта | `ADMIN` |
| `GET` | `/api/v1/imports/{id}` | состояние, сводка и предупреждения | `ADMIN` |
| `GET` | `/api/v1/imports/{id}/preview` | кандидаты: что будет создано и что требует проверки | `ADMIN` |
| `POST` | `/api/v1/imports/{id}/confirm` | применить импорт (`skip`, `archive_missing`) | `ADMIN` |
| `POST` | `/api/v1/imports/{id}/reject` | отклонить результаты | `ADMIN` |
| `POST` | `/api/v1/imports/{id}/pause` | поставить прогон на паузу | `ADMIN` |
| `POST` | `/api/v1/imports/{id}/resume` | продолжить прогон | `ADMIN` |
| `PUT` | `/api/v1/imports/{id}/selection` | сохранить выбор администратора | `ADMIN` |
| `GET` | `/api/v1/imports/{id}/plan` | план импорта официального перечня | `ADMIN` |
| `PATCH` | `/api/v1/imports/{id}/plan` | исправить сопоставление, название, уровень или действие | `ADMIN` |
| `POST` | `/api/v1/imports/{id}/apply` | применить утверждённый план атомарно | `ADMIN` |
| `GET` | `/api/v1/imports/{id}/history` | что документ изменил в каталоге | `ADMIN` |
| `GET` | `/api/v1/imports/{id}/table` | постраничный просмотр таблицы перечня или сводки | `ADMIN` |
| `GET` | `/api/v1/admin/docs` | список документов (`search`, `type`, `status`, `limit`, `offset`) | `ADMIN` |
| `GET` | `/api/v1/admin/imports` | журнал импортов | `ADMIN` |
| `GET` | `/api/v1/admin/imports/{id}` | прогон импорта с записями по строкам | `ADMIN` |

## Заявки и запросы

| Метод | Путь | Назначение | Доступ |
|-------|------|-----------|--------|
| `GET` | `/api/v1/universities/{id}/entity-requests` | запросы на отсутствующие сущности своего вуза | `EDITOR` (свой вуз) / `ADMIN` |
| `POST` | `/api/v1/universities/{id}/entity-requests` | запросить отсутствующие олимпиаду, сезон или профиль | `EDITOR` (свой вуз) / `ADMIN` |
| `GET` | `/api/v1/admin/entity-requests` | очередь запросов (`status`, `limit`, `offset`, `total`) | `ADMIN` |
| `POST` | `/api/v1/admin/entity-requests/{id}/approve` | одобрить запрос и создать сущность один раз | `ADMIN` |
| `POST` | `/api/v1/admin/entity-requests/{id}/reject` | отклонить запрос с обязательной причиной | `ADMIN` |
| `POST` | `/api/v1/representative-applications` | подать заявку на представительство вуза | Аутентифицированный |
| `GET` | `/api/v1/applications/my` | свои заявки представителя | Аутентифицированный |

## Аутентификация и служебные маршруты

| Метод | Путь | Назначение | Доступ |
|-------|------|-----------|--------|
| `POST` | `/api/v1/auth/register` | регистрация пользователя | Публичный |
| `POST` | `/api/v1/auth/login` | вход и установка JWT-cookies | Публичный |
| `POST` | `/api/v1/auth/logout` | выход и удаление JWT-cookies | Аутентифицированный |
| `POST` | `/api/v1/auth/refresh` | обновить access-токен | Аутентифицированный |
| `GET` | `/api/v1/health` | liveness-проба | Публичный |
| `GET` | `/api/v1/ready` | readiness-проба (PostgreSQL и Redis) | Публичный |
| `GET` | `/api/v1/admin/audit` | журнал аудита (`entity_type`, `entity_id`, `action`, `limit`, `offset`, `total`) | `ADMIN` |

## Особенности API

- неизвестные пути под `/api/v1/` возвращают JSON 404, а не HTML-заглушку SPA;
- ответы об ошибках — единый JSON `{"detail": ...}` без утечки внутренних
  деталей;
- версии оптимистичные: устаревшая `version` при правке или откате даёт `409`.

См. также: [роли и права](roles-and-permissions.md) ·
[импорт документов РСОШ](rsosh-import.md).
