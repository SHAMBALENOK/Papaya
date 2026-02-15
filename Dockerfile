# Dockerfile
# Используем официальный образ Python 3.11 (slim для меньшего размера)
FROM python:3.11-slim

# Устанавливаем переменные окружения
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=main.py \
    FLASK_ENV=production

# Устанавливаем системные зависимости для компиляции psycopg2 и PostgreSQL клиента
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Создаем непривилегированного пользователя для безопасности
RUN useradd -m -u 1000 appuser

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл зависимостей и устанавливаем их (для кэширования слоя)
COPY requirements.txt .
RUN pip3 install psycopg2-binary
RUN pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache

# Копируем ВЕСЬ проект внутрь контейнера
# Это включает main.py, templates/, static/, database/, middlewares/, .env и т.д.
COPY . .

# Устанавливаем владельца файлов для безопасности
RUN chown -R appuser:appuser /app

# Переключаемся на непривилегированного пользователя
USER appuser

# Открываем порт 5000
EXPOSE 5000

# Запускаем приложение
# Обязательно измените в main.py: app.run(host='0.0.0.0', port=5000, debug=False)
CMD ["python", "main.py"]