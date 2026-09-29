# Базовый образ python:3.11-slim-bookworm (@digest — зафиксированный образ).
# В образ ставится Tesseract OCR: без него не читаются сканы документов РСОШ.
FROM python:3.11-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84

WORKDIR /app

RUN apt-get update -o Acquire::Retries=10 -o Acquire::http::Timeout="60" -o Acquire::https::Timeout="60" && \
    apt-get install -y --fix-missing --no-install-recommends \
    ca-certificates curl wget unzip libgl1 libglib2.0-0 libgomp1 \
    tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng tesseract-ocr-osd \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# pip не использует apt, поэтому отдельного «сборочного» пакета здесь нет и
# удалять нечего. Ранье здесь стоял `apt-get purge -y --auto-remove` без списка
# пакетов: команда без аргументов вычищает всё, что apt считает ненужным, и
# вместе со списками пакетов задевает runtime-часть образа — в том числе
# tesseract и его языковые данные, на которых держится весь импорт РСОШ.
# Очищаем только кэш apt.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /var/lib/apt/lists/* /root/.cache /tmp/*

COPY . .

# setup.sh — точка входа, и она обязана быть исполняемой. В рабочем дереве файл
# может прийти с CRLF (checkout на Windows), и тогда shebang превращается в
# `#!/bin/sh\r`: ядро не находит интерпретатор и контейнер падает с
# "exec /setup.sh: no such file or directory". Приводим к LF в образе, чтобы
# сборка не зависела от настроек git на машине разработчика.
COPY setup.sh /setup.sh
RUN chmod +x /setup.sh && \
    sed -i 's/\r$//' /setup.sh && \
    head -1 /setup.sh | grep -q '^#!/bin/sh'

ENTRYPOINT ["/setup.sh"]
EXPOSE 5000
CMD ["gunicorn", "app.main:app", "--preload", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:5000"]
