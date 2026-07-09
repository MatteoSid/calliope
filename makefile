.PHONY: run sync lock lint format check build up down logs stop docker-run

# --- Sviluppo locale (venv uv) ---------------------------------------------
run:              ## Avvia il bot in locale
	uv run calliope

sync:             ## Installa/aggiorna le dipendenze dal lockfile
	uv sync

lock:             ## Rigenera uv.lock
	uv lock

lint:             ## Controlli statici (ruff + mypy)
	uv run ruff check calliope/
	uv run mypy calliope/

format:           ## Formatta il codice
	uv run ruff format calliope/

check: lint       ## Alias di lint

# --- Docker / compose (ambiente completo con Mongo) ------------------------
build:            ## Build dell'immagine via compose
	docker compose build

up:               ## Avvia lo stack (bot + Mongo) in background
	docker compose up -d

down:             ## Ferma e rimuove lo stack
	docker compose down

logs:             ## Segue i log del bot
	docker compose logs -f calliope

stop:             ## Ferma i container senza rimuoverli
	docker compose stop

# Avvio standalone dell'immagine (senza compose), con GPU e variabili da .env.
docker-run:       ## Esegue l'immagine calliope:dev da sola
	docker run --rm --gpus all --env-file .env calliope:dev
