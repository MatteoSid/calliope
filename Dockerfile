FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive

# Install python and audio dependencies
# (python 3.10 di sistema: deadsnakes non pubblica più pacchetti per basi EOL
# e il progetto richiede solo ^3.10)
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

# Install any needed packages specified in requirements.txt
RUN pip install --upgrade pip
RUN pip install "poetry==2.1.1"
RUN poetry install --no-root

# Copy the current directory contents into the container at /app
COPY calliope /app/calliope