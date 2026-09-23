FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Europe/Berlin \
    PYTHONPATH=/app/scraper:/app/api

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        tzdata \
        xvfb \
        fonts-liberation \
        fonts-dejavu-core \
        fonts-freefont-ttf \
        fonts-gfs-artemisia \
    && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
        | gpg --dearmor -o /usr/share/keyrings/google-linux.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-linux.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
        > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY scraper/requirements.txt /app/scraper/requirements.txt
RUN pip install --no-cache-dir -r /app/scraper/requirements.txt

COPY scraper /app/scraper
COPY api/app /app/api/app

RUN useradd --create-home --uid 10001 scraper \
    && chown -R scraper:scraper /app
USER scraper

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--app-dir", "/app/scraper", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
