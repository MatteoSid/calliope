FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04

# Base -runtime con cuDNN 9: richiesto da ctranslate2 >= 4.5 (CTranslate2 usa
# cuDNN 9 / cuBLAS 12 a runtime; le wheel sono precompilate, niente toolkit
# devel). Non serve quindi uno stage builder separato: l'immagine non contiene
# compilatori né header di sviluppo.

# Binario uv dall'immagine ufficiale (nessun pip/poetry da installare).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/home/calliope \
    # uv crea la venv in /app/.venv e scarica un Python standalone sotto la home
    # dell'utente non-root (così sync gira senza permessi di root).
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_PYTHON_INSTALL_DIR=/home/calliope/.local/uv/python \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # Cache dei modelli scaricati a runtime da faster-whisper/huggingface.
    HF_HOME=/home/calliope/.cache/huggingface

# Dipendenze di sistema audio/video:
# libsndfile1: librosa; ffmpeg: estrazione audio (media/extract.py) + av.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libsndfile1 \
        ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Utente non-root dedicato (S6): nessun processo gira come root nel container.
# /app e la home sono di sua proprietà PRIMA di uv sync, così la venv nasce già
# con i permessi giusti (niente chown -R della venv, che gonfierebbe l'immagine).
RUN useradd --create-home --uid 10001 calliope \
    && mkdir -p /app /home/calliope/.cache/huggingface \
    && chown -R calliope:calliope /app /home/calliope

USER calliope
WORKDIR /app

# Fase 1: installa SOLO le dipendenze dal lockfile (layer cache-abile),
# senza il progetto. --frozen: usa uv.lock così com'è.
COPY --chown=calliope:calliope pyproject.toml uv.lock .python-version README.md /app/
RUN uv sync --frozen --no-install-project --no-dev

# Fase 2: copia il codice e installa il progetto (crea lo script `calliope`).
COPY --chown=calliope:calliope calliope /app/calliope
RUN uv sync --frozen --no-dev

# La venv diventa il Python di default: lo script `calliope` è in /app/.venv/bin.
ENV PATH="/app/.venv/bin:$PATH"

CMD ["calliope"]
