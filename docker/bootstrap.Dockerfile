FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    OMP_NUM_THREADS=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libxcb1 \
        libheif1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY api/requirements.txt /app/requirements.txt
COPY api/requirements-bootstrap.txt /app/requirements-bootstrap.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && pip install --no-cache-dir -r /app/requirements-bootstrap.txt \
        --extra-index-url https://download.pytorch.org/whl/cpu

COPY api/app /app/app
COPY api/bootstrap /app/bootstrap
COPY api/eval /app/eval

COPY extra-cards /extra-cards
ENV EXTRA_CARDS_DIR=/extra-cards

RUN mkdir -p /data
WORKDIR /app

ENTRYPOINT ["python", "-m", "bootstrap"]
