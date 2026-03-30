SHELL := /bin/bash

.PHONY: up down restart logs test migrate connect-telegram reset-telegram login-opencode reset-data

up:
	docker compose up -d --build --wait --remove-orphans && docker compose exec -it api python -m services.onboarding.ensure_connected

down:
	docker compose down --remove-orphans

restart:
	docker compose up -d --build --force-recreate --remove-orphans

logs:
	docker compose logs -f --tail=200

test:
	docker compose run --rm api pytest -v

migrate:
	docker compose run --rm api python -m services.shared.db.migrations.apply

connect-telegram:
	docker compose exec -it api python -m services.onboarding.wizard

reset-telegram:
	docker compose exec api python -m services.auth.main disconnect --run-id manual

login-opencode:
	docker compose exec -it api opencode providers login

reset-data:
	docker compose down -v --remove-orphans
