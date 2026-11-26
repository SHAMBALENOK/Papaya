# Тесты

[← Документация](README.md) · [К README проекта](../README.md) · [English](en/testing.md)

Тесты идут в изолированном контейнере профиля `testing`: рабочая БД не
затрагивается (создаётся отдельная база `papaya_test`, накатываются миграции,
Redis очищается). Перед каждым тестом каталоги, документы и пользователи пусты —
тесты не зависят от порядка.

```bash
docker compose --profile testing run --rm test
```

Подмножество тестов:

```bash
docker compose --profile testing run --rm --entrypoint sh test -c \
  "pip install --no-cache-dir -q -r /app/requirements-dev.txt && pytest -q tests/test_rsosh_import.py"
```

## Что покрыто

| Файл | Сценарии |
|------|----------|
| `tests/test_auth.py` | регистрация, вход, выход, cookie-флаги, пароли |
| `tests/test_security_hardening.py` | защитные заголовки, запрет JWT-заглушки, loopback-порты, самопроверка заявок и защита роли администратора |
| `tests/test_health.py` | liveness, readiness, JSON-404 для не-API путей |
| `tests/test_catalog.py` | публичные каталоги, поиск, дубли, архив, единый поиск |
| `tests/test_mvp.py` | каноническая модель: сезоны, профили с уровнем РСОШ, правила льгот, БВИ как тип льготы, требование ЕГЭ, документы вуза |
| `tests/test_invariants.py` | инварианты модели: уникальность, ссылочная целостность, отсутствие legacy-сущностей |
| `tests/test_catalog_integrity.py` | гонки, блокировки строк, версии и откат, целостность при ошибках импорта |
| `tests/test_durability.py` | «не удалять», атомарность архива, сохранение правил при импорте |
| `tests/test_roles.py` | границы ролей: школьник / представитель / администратор |
| `tests/test_rsosh_import.py` | XLSX, PDF с текстовым слоем, скан, повороты 90/180/270, PNG/JPEG, многострочные и объединённые ячейки, повторный импорт, архивирование, ошибки, права |

См. также: [запуск и настройка](getting-started.md) · [импорт РСОШ](rsosh-import.md).
