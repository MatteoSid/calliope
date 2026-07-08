FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# Set environment variables
# (base -runtime invece di -devel: le dipendenze sono wheel precompilate, il CUDA
# toolkit di sviluppo non serve a runtime. cuDNN 8 + CUDA 12 restano disponibili a
# livello di sistema per CTranslate2.)
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Install python and audio dependencies
# (python 3.10 di sistema: deadsnakes non pubblica più pacchetti per basi EOL
# e il progetto richiede solo ^3.10)
# figlet: banner ASCII a runtime; libsndfile1: librosa; ffmpeg: moviepy.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-pip \
        figlet \
        libsndfile1 \
        ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory to /app
WORKDIR /app

COPY pyproject.toml poetry.lock /app/

# Install only le dipendenze di produzione (niente gruppo dev) e ripulisci la cache
# di poetry nello stesso layer per non lasciarla nell'immagine.
RUN pip install --upgrade pip "poetry==2.1.1" \
    && poetry install --no-root --only main \
    && rm -rf "$POETRY_CACHE_DIR"

# Copy the current directory contents into the container at /app
COPY calliope /app/calliope
