FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu20.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive

# Install python and audio dependencies
RUN apt-get update \
    && apt-get purge -y python3.8 \
    && apt-get autoremove -y \
    && apt-get install -y software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.11 \
        python3-pip \
        figlet \
        libsndfile1 \
        ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory to /app
WORKDIR /app

COPY pyproject.toml /app/

# Install any needed packages specified in requirements.txt
RUN pip install --upgrade pip
RUN pip install poetry
RUN poetry install --no-root

# Copy the current directory contents into the container at /app
COPY calliope /app/calliope