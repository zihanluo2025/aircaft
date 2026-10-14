.PHONY: backend-install backend-dev frontend-install frontend-dev test seed up down logs

backend-install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

backend-dev:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/pytest
	cd frontend && npm test

# Local demo data and a login (demo / demo-password-1) for development
seed:
	cd backend && .venv/bin/python -m scripts.seed_demo && .venv/bin/python -m scripts.create_user demo demo-password-1 --name "Demo"

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f
