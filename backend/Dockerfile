# Aapda Awaaz API — portable image.
#   docker build -t aapda-awaaz-api ./backend
#   docker run --rm -p 8000:8000 --env-file .env -v aapda-data:/data aapda-awaaz-api
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    AAPDA_VAR_DIR=/data

WORKDIR /app

# soundfile wheels bundle libsndfile, but the distro package makes it explicit.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data

# Run as an unprivileged user; /data holds the SQLite DB, uploads and TTS audio.
RUN useradd --create-home --uid 10001 aapda \
    && mkdir -p /data \
    && chown -R aapda:aapda /data /app
USER aapda

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
