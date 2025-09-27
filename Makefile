PYTHON ?= python3

.PHONY: dev build api ui smoke-docker threat-scan stop reset

api:
	cd app && uvicorn app.main:app --reload

ui:
	cd ui && npm run dev

dev:
	./scripts/dev.sh

build:
	(cd app && $(PYTHON) -m compileall .)
	(cd ui && npm run build)

smoke-docker:
	$(PYTHON) scripts/test_docker_path.py --disable-docker

threat-scan:
	$(PYTHON) scripts/threat_scan.py

stop:
	./scripts/stop.sh

reset:
	./scripts/reset.sh
