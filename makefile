run:
	poetry run env PYTHONPATH=. python -m calliope

docker-build:
	docker build -t calliope .

docker-run:
	docker run --gpus all calliope