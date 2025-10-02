PYTHON ?= python3
PLAYWRIGHT_BROWSERS_PATH ?= .playwright

.PHONY: dev build api ui smoke-docker threat-scan stop reset e2e-ui setup

api:
	cd app && uvicorn app.main:app --reload

ui:
	cd ui && npm run dev

dev:
	./scripts/dev.sh

test:
	python3 -m unittest discover -s app/tests

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

setup:
	./scripts/quickstart.sh

e2e-ui:
	bash -lc "source ./scripts/e2e_env.sh && \
	  npm --prefix ui install && \
	  PLAYWRIGHT_BROWSERS_PATH=$(PLAYWRIGHT_BROWSERS_PATH) npm --prefix ui exec -- playwright install --with-deps chromium && \
	  ENABLE_CI_E2E_UI=1 PLAYWRIGHT_BROWSERS_PATH=$(PLAYWRIGHT_BROWSERS_PATH) npm --prefix ui run test:e2e"
