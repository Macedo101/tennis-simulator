# syntax=docker/dockerfile:1

# ---- Stage 1: builder -------------------------------------------------
# Instala as dependências num venv isolado, com o toolchain de build
# completo (gcc, headers) que várias libs científicas (numpy/scipy/
# xgboost) precisam para compilar extensões nativas — este toolchain
# nunca chega à imagem final.
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---- Stage 2: runtime --------------------------------------------------
# Imagem final: só o venv já construído + código da app. Sem
# build-essential, sem cache do pip, sem requirements-dev — a
# superfície de ataque e o tamanho da imagem ficam ao mínimo.
FROM python:3.12-slim AS runtime

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY --chown=app:app app/ ./app/
COPY --chown=app:app alembic/ ./alembic/
COPY --chown=app:app alembic.ini .

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", 8000)}/health')" || exit 1

# `alembic upgrade head` corre sempre antes do servidor arrancar —
# necessário em plataformas de deploy simples (ex.: Render free tier)
# que não têm um passo de "pre-deploy" separado; garante que o schema
# está sempre atualizado antes de aceitar pedidos. `${PORT:-8000}`
# respeita a porta atribuída dinamicamente por essas plataformas,
# com 8000 como valor por omissão em local/Docker Compose.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
