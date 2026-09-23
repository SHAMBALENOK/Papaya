"""Централизованная конфигурация приложения.

Все параметры читаются из переменных окружения один раз при импорте модуля.
Обязательные переменные (``JWT_KEY``, ``DATABASE_URL``) валидируются явно
через :func:`validate_config`: приложение падает на старте с понятным
сообщением вместо поздней и труднодиагностируемой ошибки на первом запросе.
"""

import os

_SCHEME = 'postgresql+asyncpg://'


def _env_bool(name: str, default: bool = False) -> bool:
    """Прочитать булеву переменную окружения."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {'1', 'true', 'yes', 'on'}


def _env_int(name: str, default: int) -> int:
    """Прочитать целочисленную переменную окружения с защитой от мусора."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Окружение: development / test / production. Влияет на часть дефолтов.
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development').strip().casefold()

# --- Обязательные секреты и подключения --------------------------------
JWT_KEY = os.getenv('JWT_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgresql://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql://', _SCHEME, 1)

# --- Redis ---------------------------------------------------------------
REDIS_URL = os.getenv('REDIS_URL')
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = _env_int('REDIS_PORT', 6379)
if not REDIS_URL:
    REDIS_URL = f'redis://{REDIS_HOST}:{REDIS_PORT}/0'

# --- Кэш ------------------------------------------------------------------
CACHE_TTL = _env_int('CACHE_TTL', 600)

# --- Аутентификация / cookies --------------------------------------------
# Secure-флаг ставится только по HTTPS; для локальной разработки — false.
COOKIE_SECURE = _env_bool('COOKIE_SECURE', ENVIRONMENT == 'production')

# --- Импорт таблиц ---------------------------------------------------------
MAX_UPLOAD_MB = _env_int('MAX_UPLOAD_MB', 30)
TABLES_DIR = os.getenv(
    'TABLES_DIR',
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tables')),
)
ALLOWED_TABLE_EXTENSIONS = {'.pdf', '.xlsx'}

# --- Документы-источники -----------------------------------------------------
# Каталог для оригиналов загруженных документов. Приложение пишет сюда
# безопасными именами (storage_key), исходное имя клиента не используется.
DOCS_DIR = os.getenv(
    'DOCS_DIR',
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'documents')),
)
MAX_DOC_MB = _env_int('MAX_DOC_MB', 60)
ALLOWED_DOC_EXTENSIONS = {'.pdf', '.xlsx', '.docx'}

# --- RSOSH-импорт -------------------------------------------------------------
# Рабочий каталог промежуточных файлов импорта (XLSX из PDF и пр.). Лежит
# внутри хранилища документов, чтобы web и celery видели один и тот же путь.
RSOSH_WORK_DIR = os.getenv(
    'RSOSH_WORK_DIR',
    os.path.join(DOCS_DIR, '_import_work'),
)

# --- Значения-заглушки, которые запрещено использовать в production -------
_INSECURE_JWT_DEFAULTS = {'change_this_secret_key', 'secret', 'changeme'}


def validate_config() -> None:
    """Проверить обязательные параметры и упасть с понятным сообщением.

    Вызывается из ``app.main`` при старте приложения. Celery и Alembic не
    зависят от этой проверки, чтобы не блокировать миграции.
    """
    missing = []
    if not JWT_KEY:
        missing.append('JWT_KEY')
    if not DATABASE_URL:
        missing.append('DATABASE_URL')
    if missing:
        raise RuntimeError(
            'Missing required environment variables: ' + ', '.join(missing)
        )
    if DATABASE_URL.startswith('sqlite'):
        raise RuntimeError('SQLite is not supported: Papaya requires PostgreSQL')

    if ENVIRONMENT == 'production' and JWT_KEY in _INSECURE_JWT_DEFAULTS:
        raise RuntimeError(
            'JWT_KEY must be a long random secret in production; '
            'remove the default placeholder value'
        )