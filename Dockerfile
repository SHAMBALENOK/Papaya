FROM python:3.11-slim-bookworm

# Добавляем retry для нестабильного соединения
RUN apt-get update -o Acquire::Retries=5 && \
    apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        gcc \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        torch==2.2.2+cpu \
        torchvision==0.17.2+cpu \
        --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y --auto-remove gcc python3-dev 2>/dev/null || true && \
    rm -rf /root/.cache /tmp/*

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app"]