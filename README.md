# [Papaya]((https://papaya-poxq.onrender.com/)
Сервис для школьников, содержащий все олимпиады в одном удобном месте

## Самостоятельный Запуск *(ИСПОЛЬУЙТЕ ФОРК DOCKER!!!)*
Для начала вам понадобится завести в вашей проектной папке файл `.env` следующего содержания:
```
FLASK_SECRET_KEY=
DB_USER=postgres
DB_PASSWORD=     # Рекомендуется: postgres
DB_HOST=     # Рекомендуется: postgres
DB_PORT=     # Рекомендуется: 5432
DB_NAME=     # Рекомендуется: testdb

INIT_EVENT_ID=     # Рекомендуется: 111
INIT_EVENT_NAME=     # Рекомендуется: my_event
INIT_EVENT_PLACE=     # Рекомендуется: my_place
INIT_EVENT_MIN_GRADE=     # Рекомендуется: 1
INIT_EVENT_MAX_GRADE=     # Рекомендуется: 11
INIT_EVENT_MIN_AGE=     # Рекомендуется: 6
INIT_EVENT_MAX_AGE=     # Рекомендуется: 17
```
*FLASK_SECRET_KEY создается с помощью `bash python -c "import secrets; print('FLASK_SECRET_KEY=' + secrets.token_urlsafe(48))"`*

Затем нужно установить и зайти в Docker Desktop и запустить приложение следующими командами:
```bash
$ cd путь до вашей папки
```
*путь до вашей папки должен соответсвовать путю к папке содержание которой соответствует содержанию этого репозитория*
```bash
$ docker-compose up -d --build
```

Сайт находится по пути localhost:5000

### Для выключения используйте:
```bash
$ docker-compose down -v
```
