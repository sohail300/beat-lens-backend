FROM python:3.12-slim

# ffmpeg decodes uploaded audio (mp3, m4a, browser webm/opus, ...)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENV=production \
    PORT=5000 \
    WEB_CONCURRENCY=2

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries 5 -r requirements.txt

COPY . .
RUN useradd --create-home --uid 10001 app \
    && mkdir -p tmp \
    && chown -R app:app /app \
    && chmod +x start.sh
USER app

EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health', timeout=4)"

CMD ["./start.sh"]
