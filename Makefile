.PHONY: init up geography worker start status logs down rebuild

init:
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from .env.example"; fi

up:
	docker compose up --build -d db api web

geography:
	docker compose run --rm worker import-geography

worker:
	docker compose --profile jobs up --build -d worker

start: init up geography worker
	@echo ""
	@echo "追晴 MVP 已启动："
	@echo "  Web:      http://localhost:3000"
	@echo "  API Docs: http://localhost:8000/docs"
	@echo "  API:      http://localhost:8000/health"

status:
	docker compose --profile jobs ps

logs:
	docker compose --profile jobs logs -f --tail=100 api web worker

down:
	docker compose --profile jobs down

rebuild:
	docker compose --profile jobs up --build -d
