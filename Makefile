.DEFAULT_GOAL := help
.PHONY: help init sync sync-frontend generate-api check-api install-browser build-frontend dev-frontend lint-frontend lint-docs test-frontend audit-frontend lint lint-python lint-shell build-websites check-websites build-bash-tests format typecheck test test-bash test-integration test-all coverage-report check check-unit audit

WEBSITES_IMAGE := goit-cs-hw-02-websites
export NEXT_TELEMETRY_DISABLED := 1
BASH_TEST_IMAGE := goit-cs-hw-02-bash-tests
BASH_TEST_RUN = docker run --rm --network none --read-only \
	--tmpfs /tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777 \
	--cap-drop ALL --security-opt no-new-privileges $(BASH_TEST_IMAGE)

help: ## Показати доступні команди (також типова ціль make).
	@awk 'BEGIN { print "Використання: make <команда>\n" } /^[a-zA-Z0-9_-]+:.*## / { split($$0, parts, ":"); sub(/^.*## /, "", $$0); printf "  %-20s %s\n", parts[1], $$0 }' $(MAKEFILE_LIST)

init: ## Створити відсутні .env і паролі; зберегти наявні файли.
	@command -v uv >/dev/null 2>&1 || { echo 'Error: install uv before running make init.' >&2; exit 1; }
	@uv run --locked python -m scripts.init_local

sync: sync-frontend ## Встановити Python і frontend залежності з lockfiles.
	uv sync --locked

sync-frontend: ## Встановити frontend залежності через pnpm.
	pnpm --dir frontend install --frozen-lockfile

install-browser: sync-frontend ## Встановити Chromium, Firefox та WebKit для Playwright.
	pnpm --dir frontend exec playwright install chromium firefox webkit

generate-api: sync-frontend ## Оновити OpenAPI snapshot, клієнт і Zod-схеми.
	uv run --locked python -m scripts.export_openapi
	pnpm --dir frontend generate

check-api: ## Перевірити актуальність OpenAPI snapshot.
	uv run --locked python -m scripts.export_openapi --check

build-frontend: sync-frontend check-api ## Зібрати frontend, перевірити TypeScript та HTML.
	pnpm --dir frontend run build

dev-frontend: sync-frontend check-api ## Запустити Next.js dev на 127.0.0.1:3000.
	pnpm --dir frontend run dev

lint-frontend: sync-frontend ## ESLint, SonarJS і перевірка форматування Prettier.
	pnpm --dir frontend run lint

lint-docs: sync-frontend ## Перевірити Markdown через спільну з VS Code конфігурацію.
	pnpm --dir frontend run lint:docs

test-frontend: build-frontend install-browser ## Запустити браузерні тести та axe.
	pnpm --dir frontend test

audit-frontend: sync-frontend ## Перевірити frontend залежності через pnpm audit.
	pnpm --dir frontend audit

lint: lint-python lint-shell lint-frontend lint-docs ## Запустити Ruff, ShellCheck у Rocky, ESLint, Prettier і markdownlint.

lint-python: ## Перевірити Python і форматування через Ruff.
	uv run --locked ruff check .
	uv run --locked ruff format --check .

build-websites: ## Зібрати Rocky-образ для ручного запуску Bash-скрипту.
	docker build --file docker/websites.Dockerfile --target runner --tag $(WEBSITES_IMAGE) .

check-websites: build-websites ## Перевірити справжні сайти у Rocky, лог в artifacts/websites/.
	mkdir -p artifacts/websites
	docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
		--user "$$(id -u):$$(id -g)" \
		--volume "$(CURDIR)/artifacts/websites:/output:Z" $(WEBSITES_IMAGE)

build-bash-tests: ## Зібрати Rocky-образ з інструментами Bash-тестів.
	docker build --file docker/websites.Dockerfile --target tests --tag $(BASH_TEST_IMAGE) .

lint-shell: build-bash-tests ## Перевірити синтаксис Bash і ShellCheck у Rocky.
	$(BASH_TEST_RUN) bash -c 'bash -n check_websites.sh && bash -n docker/init-app-role.sh && shellcheck --norc --shell=bash check_websites.sh docker/init-app-role.sh'

format: sync-frontend ## Застосувати Ruff, Prettier та автоматичні виправлення ESLint.
	uv run --locked ruff format .
	pnpm --dir frontend run format

typecheck: ## Запустити строгий mypy для Python.
	uv run --locked mypy

test: build-frontend ## Запустити Python-тести без Docker та звіт coverage.
	uv run --locked coverage run -m pytest
	$(MAKE) coverage-report

test-bash: build-bash-tests ## Запустити ізольовані Bash/curl тести у Rocky.
	$(BASH_TEST_RUN)

test-integration: build-frontend install-browser ## Перевірити API і Percona в тимчасових Docker-контейнерах.
	uv run --locked pytest --integration tests/integration

test-all: test-bash test-frontend ## Запустити всі тести та Python coverage.
	uv run --locked coverage run -m pytest --integration
	$(MAKE) coverage-report

coverage-report: ## Оновити текстовий, HTML та XML звіти coverage.
	uv run --locked coverage report
	uv run --locked coverage html
	uv run --locked coverage xml

check: lint typecheck test-all ## Запустити всі перевірки, включно з Docker і трьома браузерами.

check-unit: lint-python typecheck test ## Ruff, mypy, frontend build і Python-тести без Docker.

audit: ## Перевірити Python-залежності через pip-audit.
	mkdir -p artifacts
	uv export --locked --all-groups --format requirements-txt --output-file artifacts/audit-requirements.txt --quiet
	uv run --locked pip-audit --require-hashes --disable-pip --progress-spinner off -r artifacts/audit-requirements.txt
