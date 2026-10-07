.PHONY: install lint test migrate run frontend-build

install:
	python -m pip install -e ".[test]"

lint:
	ruff check backend

test:
	pytest -q

migrate:
	alembic upgrade head

run:
	uvicorn app.main:app --app-dir backend --reload

frontend-build:
	cd frontend && npm install && npm run build
