# Common tasks. `make help` lists them.

.DEFAULT_GOAL := help
PY := ./venv/bin/python
PIP := ./venv/bin/pip

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

db-up: ## Start the local PostgreSQL container
	docker compose up -d db

db-down: ## Stop the local PostgreSQL container
	docker compose down

install: ## Install Python and Node dependencies
	$(PIP) install -r requirements/dev.txt
	npm install

css: ## Build the stylesheet once
	npx tailwindcss -i ./assets/css/app.css -o ./static/dist/app.css --minify

css-watch: ## Rebuild the stylesheet on change
	npx tailwindcss -i ./assets/css/app.css -o ./static/dist/app.css --watch

migrations: ## Create migrations
	$(PY) manage.py makemigrations

migrate: ## Apply migrations and ensure the cache table exists
	$(PY) manage.py migrate
	$(PY) manage.py createcachetable

check: ## Run Django system checks
	$(PY) manage.py check
	$(PY) manage.py check --deploy --settings=config.settings.prod

test: ## Run the test suite
	./venv/bin/pytest

lint: ## Lint and format-check
	./venv/bin/ruff check .

run: ## Start the development server
	$(PY) manage.py runserver

.PHONY: help db-up db-down install css css-watch migrations migrate check test lint run
