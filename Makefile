.PHONY: install placeholder refresh test dev build

install:
	python3 -m pip install -r sitegen/requirements.txt
	npm install

placeholder:
	python3 -m sitegen.build --mode placeholder

refresh:
	python3 -m sitegen.build --mode live --require-live

test:
	python3 -m pytest -q sitegen/tests
	npm run typecheck:web
	npm run lint:web

dev:
	npm run dev:web

build:
	NEXT_PUBLIC_BASE_PATH=/zhuqing-sunshine npm run build:web
