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
# figlet: banner ASCII a runtime; libsndfile1: librosa; ffmpeg: moviepy/av.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        figlet \
        libsndfile1 \
        ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installa SOLO le dipendenze di produzione dal lockfile (layer cache-abile).
# --frozen: usa uv.lock così com'è, senza ri-risolvere.
COPY pyproject.toml uv.lock .python-version /app/
RUN uv sync --frozen --no-dev

# Copia il codice dell'applicazione.
COPY calliope /app/calliope

# La venv diventa il Python di default: `python -m calliope` usa /app/.venv.
ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "-m", "calliope"]
