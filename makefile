run:
	uv run calliope

sync:
	uv sync

lock:
	uv lock

docker-build:
	docker build -t calliope .

docker-run:
	docker run --gpus all --runtime=nvidia --env-file .env calliope

up:
	docker compose up -d --build

down:
	docker compose down
