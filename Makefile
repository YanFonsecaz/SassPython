.PHONY: help infra up down migrate seed dev build lint test logs worker scheduler

help: ## Mostra esta ajuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

infra: ## Sobe PostgreSQL + Redis
	docker compose up -d postgres redis

down: ## Para todos os containers
	docker compose down

up: ## Sobe tudo (infra + backend)
	docker compose up -d

migrate: ## Roda migrations
	cd backend && python -m alembic upgrade head

seed: ## Roda seed data (migration 0004)
	cd backend && python -m alembic upgrade head

dev: ## Inicia backend em dev (com reload)
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker: ## Inicia ARQ worker
	cd backend && arq app.worker.WorkerSettings

scheduler: ## Inicia scheduler
	cd backend && python -c "import asyncio; from app.scheduler import criar_scheduler; s = criar_scheduler(); asyncio.run(s.start())"

build: ## Build do frontend
	cd frontend && npm run build

lint: ## Lint backend
	cd backend && ruff check app/

test: ## Roda testes
	cd backend && pytest

logs: ## Logs do backend
	docker compose logs -f backend

logs-infra: ## Logs do postgres + redis
	docker compose logs -f postgres redis

reset-db: ## Reseta banco (cuidado!)
	docker compose down -v
	docker compose up -d postgres redis
	@echo "Aguardando PostgreSQL..."
	@sleep 3
	cd backend && python -m alembic upgrade head
