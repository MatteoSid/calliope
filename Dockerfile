FROM nvidia/cuda:12.1.0-base-ubuntu20.04

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

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY calliope /app/calliope
COPY utils /app/utils
COPY pyproject.toml /app/
COPY TOKEN.txt /app/
COPY TOKEN_CHAT_ID.txt /app/

# TODO stats.json must to be saved outside the container
COPY stast.json /app/

# Install any needed packages specified in requirements.txt
RUN pip install --upgrade pip
RUN pip install poetry
RUN poetry install

# Run the command to start the service
CMD poetry run env PYTHONPATH=. python -m calliope