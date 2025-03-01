FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu20.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive

# Install python
RUN apt-get update \
    && apt-get purge -y python3.8 \
    && apt-get autoremove -y \
    && apt-get clean \
    && apt-get install -y software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y python3.10 \
    && apt install -y python3-pip

RUN apt update && apt install -y figlet

# Set the working directory to /app
WORKDIR /app

COPY pyproject.toml /app/

# Install any needed packages specified in requirements.txt
RUN pip install --upgrade pip
RUN pip install poetry
RUN poetry install --no-root

# Copy the current directory contents into the container at /app
COPY calliope /app/calliope