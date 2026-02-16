# Используем легкий образ Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файл зависимостей и устанавливаем их
COPY requirements.txt .
RUN pip3 install psycopg2-binary
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код проекта
COPY . .

# Открываем порт 5000
EXPOSE 5000

# Запускаем приложение через Gunicorn
# main:app означает: файл main.py, объект app внутри него
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app"]