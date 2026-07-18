FROM python:3.11-slim-bookworm

WORKDIR /app

# Настройка системных зависимостей с повышенной устойчивостью к сетевым сбоям
RUN apt-get update -o Acquire::Retries=10 -o Acquire::http::Timeout="60" -o Acquire::https::Timeout="60" && \
    apt-get install -y --fix-missing --no-install-recommends \
        ca-certificates \
        curl \
        wget \
        unzip \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        gcc \
        python3-dev \
        tesseract-ocr \
        tesseract-ocr-rus \
        tesseract-ocr-eng \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        torch==2.2.2+cpu \
        torchvision==0.17.2+cpu \
        --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# 3. Очистка сборочных пакетов для уменьшения веса образа
RUN apt-get purge -y --auto-remove gcc python3-dev && \
    rm -rf /root/.cache /tmp/*

# 4. Копирование кода и настройка запуска
COPY . .

COPY setup.sh /setup.sh
RUN chmod +x /setup.sh

ENTRYPOINT ["/setup.sh"]

EXPOSE 5000

CMD ["gunicorn", "app.main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:5000"]
