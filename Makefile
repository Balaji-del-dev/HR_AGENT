# Everyday commands. Local Postgres (5432) and Redis (6379) only: no Docker.
# Run `make db-setup` once, then `make migrate seed run`.

OWNER_ENV = DB_USER=hr_owner DB_PASSWORD=$${DB_OWNER_PASSWORD:-hr_owner_dev}
QUEUES    = default,documents,agents,integrations,notifications

.PHONY: help db-setup migrate makemigrations seed seed-users seed-candidates reset-users run worker beat test evals lint check schema api fe-install fe-dev fe-build fe-test fe-preview

help:
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

db-setup: ## One-time: create roles hr_owner/hr_app and database hr_platform (asks for sudo)
	sudo -u postgres psql < scripts/setup_local_db.sql

migrate: ## Apply migrations and create the LangGraph checkpoint schema, as the owner role
	cd backend && $(OWNER_ENV) uv run python manage.py migrate
	cd backend && $(OWNER_ENV) uv run python manage.py setup_agent_checkpoints

makemigrations: ## Generate migrations; tenant tables then need EnableRowLevelSecurity added by hand
	cd backend && $(OWNER_ENV) uv run python manage.py makemigrations

seed: ## Demo tenants, people, requisitions, candidates with parsed resumes, a paused matching run (password demo-pass-2026)
	cd backend && uv run python manage.py seed_demo

seed-users: ## Tenants and users only (several per role, password demo-pass-2026), no hiring data
	cd backend && uv run python manage.py seed_users

seed-candidates: ## 100 fictional candidates with resumes, parsed by the running worker (no jobs)
	cd backend && uv run python manage.py seed_candidates --wait

reset-users: ## DELETE all hiring data (jobs, candidates, runs, logs, files) and keep only tenants, users and roles
	cd backend && $(OWNER_ENV) uv run python manage.py reset_data --yes
	cd backend && uv run python manage.py seed_users

run: ## Django on Uvicorn (HTTP + WebSockets) at http://127.0.0.1:8050
	cd backend && uv run uvicorn config.asgi:application --reload --host 127.0.0.1 --port 8050

worker: ## Celery worker for every queue (documents, agents, integrations, notifications)
	cd backend && uv run celery -A config worker -Q $(QUEUES) --concurrency 2 -l info

beat: ## Celery beat: retention purge, ATS sync, nightly evals, stuck-run sweep
	cd backend && uv run celery -A config beat -l info

test: ## Backend tests (runs as hr_app so Row-Level Security applies)
	cd backend && uv run pytest

evals: ## LLM eval gate against the configured provider (fails on regression)
	cd backend && uv run python manage.py run_evals

lint: ## ruff + mypy
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy .

schema: ## Validate the OpenAPI schema and write it for the frontend client
	cd backend && $(OWNER_ENV) uv run python manage.py spectacular --validate --fail-on-warn --file ../frontend/openapi.yaml

api: schema ## Regenerate the typed React client (orval) from the OpenAPI schema
	cd frontend && npm run api

check: lint test schema fe-build fe-test ## Everything CI runs
	cd backend && $(OWNER_ENV) uv run python manage.py makemigrations --check --dry-run
	cd backend && uv run python manage.py run_evals --no-store

fe-install: ## Install frontend packages
	cd frontend && npm install

fe-dev: ## React dev server at http://127.0.0.1:5180 (proxies the API to 8050)
	cd frontend && npm run dev

fe-build: ## Type-check and build the frontend
	cd frontend && npm run build

fe-test: ## Frontend component tests (Vitest)
	cd frontend && npm test

fe-preview: ## Serve the production build at http://127.0.0.1:5180 (same API proxy as dev)
	cd frontend && npx vite preview
