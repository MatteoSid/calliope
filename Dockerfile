FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04

# Base -runtime con cuDNN 9: richiesto da ctranslate2 >= 4.5 (CTranslate2 usa
# cuDNN 9 / cuBLAS 12 a runtime; le wheel sono precompilate, niente toolkit devel).

# Binario uv dall'immagine ufficiale (nessun pip/poetry da installare).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV DEBIAN_FRONTEND=noninteractive \
    # uv scarica un Python standalone e crea la venv in /app/.venv
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Dipendenze di sistema audio/video:
# libsndfile1: librosa; ffmpeg: estrazione audio (media/extract.py) + av.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libsndfile1 \
        ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Fase 1: installa SOLO le dipendenze dal lockfile (layer cache-abile),
# senza il progetto. --frozen: usa uv.lock così com'è.
COPY pyproject.toml uv.lock .python-version README.md /app/
RUN uv sync --frozen --no-install-project --no-dev

# Fase 2: copia il codice e installa il progetto (crea lo script `calliope`).
COPY calliope /app/calliope
RUN uv sync --frozen --no-dev

# La venv diventa il Python di default: lo script `calliope` è in /app/.venv/bin.
ENV PATH="/app/.venv/bin:$PATH"

CMD ["calliope"]
