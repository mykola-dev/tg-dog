SHELL := /bin/bash

.PHONY: up down restart logs test migrate connect-telegram reset-telegram reset-data

up:
	docker compose up -d --build --wait && docker compose exec -it app python -m services.onboarding.ensure_connected

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f --tail=200

test:
	docker compose run --rm app pytest -v

migrate:
	docker compose run --rm app python -m services.shared.db.migrations.apply

connect-telegram:
	docker compose exec -it app python -m services.onboarding.wizard

reset-telegram:
	docker compose exec app python -m services.auth.main disconnect --run-id manual

reset-data:
	docker compose down -v --remove-orphans
