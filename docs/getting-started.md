# Запуск и настройка

[← Документация](README.md) · [К README проекта](../README.md) · [English](en/getting-started.md)

## Требования

- **Git**;
- **Docker Desktop** или Docker Engine;
- **Docker Compose v2** (команда `docker compose`);
- интернет для первой сборки образа и загрузки зависимостей.

Python, PostgreSQL, Redis и Tesseract отдельно ставить не нужно: они работают
внутри контейнеров.

## Быстрый запуск

```bash
git clone https://github.com/SHAMBALENOK/Papaya.git
cd Papaya
cp .env.example .env
# замените JWT_KEY в .env на собственный случайный секрет:
python -c "import secrets; print(secrets.token_hex(32))"
docker compose up -d --build
```

> Приложение не стартует с секретом-заглушкой `JWT_KEY=change_this_secret_key`
> (кроме `ENVIRONMENT=test`): с общеизвестным секретом можно подделать JWT
> любого пользователя, включая администратора.

После запуска доступны:

- приложение — http://localhost:5000
- интерактивная документация API — http://localhost:5000/docs
- pgAdmin — http://localhost:5050 (логин `postgres@postgres.com`, пароль
  `postgres`; хост `postgres`, порт `5432`, база `postgres`)

> Если стандартный порт на хосте уже занят (например, локальным PostgreSQL на
> `5432`), задайте в `.env` свободные `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT`,
> `PGADMIN_HOST_PORT` или `WEB_HOST_PORT`. Внутри Docker-сети порты не
> меняются.

## Переменные окружения

Ключевые переменные (подробности — в `.env.example`):

- `JWT_KEY` — секрет подписи JWT; обязателен, длинная случайная строка
  (`python -c "import secrets; print(secrets.token_hex(32))"`); заглушка
  запрещена везде, кроме `ENVIRONMENT=test`;
- `ENVIRONMENT` — `development` (по умолчанию) или `production` (включает
  `Secure`-флаг cookie и HSTS);
- `DATABASE_URL` — подключение к PostgreSQL; миграции применяются
  автоматически при старте;
- `MAX_UPLOAD_MB` — максимальный размер загружаемого документа (по умолчанию
  `30`);
- `DOCS_DIR` — каталог хранения загруженных документов-источников;
- `RSOSH_EXECUTION` — `auto` (по умолчанию), `celery` или `inline`;
- `RSOSH_PDF_DPI` — разрешение рендеринга страниц PDF для OCR (по умолчанию
  `300`).

## Образ

Образ собирается из `python:3.11-slim-bookworm` и ставит Tesseract (`rus`,
`eng`, `osd`) и Python-зависимости из `requirements.txt`. Пакеты, установленные
исключительно ради сборки, не выделяются: `pip` не использует `apt`, поэтому
чистить нечего, а `apt-get purge --auto-remove` без списка пакетов удалял бы
часть runtime-окружения вместе со списками apt. `setup.sh` приводится к LF в
образе, поэтому контейнер стартует независимо от настроек git на машине
разработчика (checkout с CRLF иначе даёт `exec /setup.sh: no such file or
directory`).

> В режиме разработки `web`, `celery` и `test` монтируют рабочее дерево
> (`./app`, `./migrations`, `./scripts`), поэтому правки в коде подхватываются
> без пересборки образа. Изменение `requirements.txt` требует
> `docker compose build`.

## Логи и остановка

```bash
docker compose logs -f web celery
docker compose down        # данные в volumes сохраняются
docker compose down -v     # полная очистка: БД и Redis удаляются
```

См. также: [тесты](testing.md) · [архитектура](architecture.md) ·
[стек технологий](tech-stack.md).
