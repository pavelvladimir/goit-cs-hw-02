# Розробка та перевірки

[До README](../README.md)

Підготовка локального середовища, налаштування редактора й повний перелік перевірок.
Усі команди виконуються з кореня репозиторію.

## Версії та встановлення

Для локальної розробки потрібні uv, Node.js **22.22+ у межах major 22**
та pnpm; `packageManager` фіксує pnpm 12.11.2. TypeScript зафіксовано на
**6.0.3**: Hey API 0.99.0 використовує JavaScript compiler API, несумісне
з TypeScript 7.0.2 (`SyntaxKind.AnyKeyword` під час генерації).
`pnpm-workspace.yaml` містить вузький override `js-yaml` 4.3.2 для parser
Hey API: він виправляє знайдені аудитом YAML CPU exhaustion вразливості.
Override можна прибрати після оновлення залежності upstream і чистого аудиту.

Кореневий `.nvmrc` фіксує перевірений Node.js **22.22.2**. Якщо встановлено nvm,
виконайте з кореня репозиторію:

```bash
nvm install
nvm use
make sync
```

У `frontend/package.json` є `preinstall: npx --yes only-allow@1.2.1 pnpm`:
звичайна установка через npm або Yarn завершується підказкою використовувати pnpm.
Версію pnpm задає `packageManager`; `only-allow` перевіряє назву менеджера.
Перший запуск hook може завантажити пакет у кеш npx і потребує інтернету.
Цей hook працює також у Docker builder; runtime застосунку його не використовує.

## Налаштування редактора

`.editorconfig` задає UTF-8, LF, кінцевий newline, два пробіли для frontend
та конфігурації, чотири для Python/Bash, табуляцію для Makefile. Для Python
довжина рядка — 88, для frontend — 120. Кінцеві пробіли Markdown збережено.

У VS Code відкрийте корінь репозиторію та встановіть рекомендовані розширення
з `.vscode/extensions.json`. Після `make sync` налаштування використовують
`.venv`, локальні Ruff/Prettier/TypeScript і ESLint із робочим каталогом `frontend`.
Python форматується Ruff при збереженні, JS/TS — Prettier з автоматичними
виправленнями ESLint, включно з SonarJS. Форматування враховує
`frontend/.prettierignore`, тому generated client та візуальні fixtures пропускаються.
Якщо VS Code вже запам'ятав інший Python interpreter, виберіть `.venv`
через **Python: Select Interpreter**; для TypeScript підтвердьте використання
workspace version.

Додатково рекомендовано Docker DX для редагування Dockerfile/Compose,
Container Tools для перегляду контейнерів і журналів, DotENV для підсвічування
`.env`/`.env.example` та markdownlint для перевірки документації.
Це рекомендації редактора; встановлення розширень виконує користувач.

Для зручності роботи додано GitLens, Better Comments, TODO Tree та Code Spell Checker
з українським словником. `cSpell.language: "en,uk"` вмикає англійську й українську
перевірку після встановлення обох розширень Code Spell Checker. Ігноруються файли
з `.gitignore`, lockfiles, `AGENTS.md`, OpenAPI snapshot та тестові fixtures.

Markdownlint у VS Code та CLI читає одну кореневу `.markdownlint-cli2.jsonc`.
`make lint-docs` перевіряє всі `.md` і `.markdown` у проєкті; він також входить
до `make lint` та `make check`. CLI `markdownlint-cli2` 0.23.3 зафіксовано
як dev-залежність у frontend pnpm lockfile, глобальна установка не потрібна.
Типові правила ввімкнено; довжина текстового рядка — до 120 символів,
код і таблиці не обмежуються цим лімітом. Файли з `.gitignore` та
`frontend/AGENTS.md`, який генерує Next.js, пропускаються.
Для нових залежностей лінтера задано вузькі security overrides:
`smol-toml` 1.9.0 ([GHSA-r4xh-jqrq-34v2](https://github.com/advisories/GHSA-r4xh-jqrq-34v2))
і `katex` 0.18.2 ([GHSA-238p-pmpm-9mq7](https://github.com/advisories/GHSA-238p-pmpm-9mq7)).
Їх можна прибрати після виправлення відповідних залежностей upstream і чистої перевірки аудиту.

**Tasks: Run Task** пропонує `make init`, `make lint`, `make build-frontend`
і `make check`. Build task за замовчуванням збирає static export; test task
запускає всі перевірки з Docker. Python Test Explorer виконує звичайний pytest
без `--integration`; для нього спочатку потрібен `make build-frontend`.
Bash/ShellCheck залишаються в Rocky через Make-команди. Особисті файли у
`.vscode/` ігноруються Git, спільні settings/extensions/tasks зберігаються.

## Команди та тести

Потрібні `make`, Node.js 22.22.2 (major 22), pnpm та
[uv](https://docs.astral.sh/uv/getting-started/installation/).
Для повного набору запустіть Docker Engine / Docker Desktop із Compose 2.24.4+,
після чого виконайте:

```bash
make sync
make check
```

Проєкт використовує Python 3.13 (`.python-version`); uv завантажить його,
якщо відповідної версії немає на комп'ютері, та створить `.venv`.
`psycopg2-binary` встановлюється з готового wheel на перевірених платформах
macOS ARM64 та Linux ARM64, тому локально не потрібен `pg_config`.
ShellCheck 0.11.0 постачається пакетом `shellcheck-py==0.11.0.1`,
зафіксованим у `uv.lock`. Група `bash-test` містить pytest і ShellCheck;
`dev` включає цю групу, а тестовий образ встановлює лише її через
`uv sync --locked --only-group bash-test`. ShellCheck і перевірка синтаксису
обох `.sh` виконуються через `make lint-shell` у Linux-контейнері.
Локальні Bash, curl чи глобальний ShellCheck для автоматичних перевірок не потрібні.

| Команда | Що перевіряє | Потрібен Docker |
| --- | --- | --- |
| `make check` | Ruff, ShellCheck, ESLint/SonarJS, Prettier, markdownlint, TypeScript, mypy, усі тести та Python coverage | Так |
| `make help` або `make` | Стислий перелік команд без виконання підготовки | Ні |
| `make init` | Створити лише відсутні .env і secrets із правильними правами | Ні |
| `make check-unit` | Ruff, mypy, frontend build, 77 Python-тестів без контейнерів та coverage | Ні |
| `make test` | Frontend build, 77 Python-тестів та coverage | Ні |
| `make build-frontend` | Frozen pnpm install, перевірка OpenAPI, Hey API, TypeScript і static export Next.js | Ні |
| `make dev-frontend` | Next.js на порту 3000 із development rewrite до API | Ні |
| `make lint-frontend` | ESLint/SonarJS для TypeScript/React, тестів і конфігурації; Prettier | Ні |
| `make lint-docs` | Markdownlint для документації; спільна конфігурація з VS Code | Ні |
| `make test-frontend` | 117 перевірок у Chromium/Firefox/WebKit: API, axe, клавіатура, адаптивність, вигляд | Ні |
| `make generate-api` | Експорт OpenAPI з FastAPI та генерація клієнта й Zod | Ні |
| `make check-api` | Відхилення застарілого OpenAPI snapshot | Ні |
| `make audit-frontend` | pnpm audit; потрібен інтернет | Ні |
| `make lint-python` | Ruff: правила та форматування | Ні |
| `make check-websites` | Ручна перевірка справжніх сайтів у Rocky; це не тестовий набір | Так |
| `make build-websites` | Лише збірка Rocky-образу для ручного запуску | Так |
| `make lint-shell` | Синтаксис Bash і ShellCheck для обох `.sh` у Rocky | Так |
| `make test-bash` | 17 сценаріїв Bash/curl і HTTP-сервер у Rocky-контейнері | Так |
| `make test-integration` | Інтеграційні тести з реальною Percona та трьома браузерами | Так |
| `make test-all` | Bash у Rocky, React у Chromium/Firefox/WebKit, Python та інтеграційні тести; Python coverage | Так |
| `make audit` | Перевірка зафіксованих Python-залежностей через pip-audit; потрібен інтернет | Ні |

`make check` запускає такі перевірки. Shell-команди нижче делегують виконання
контейнеру; host pytest виконує лише Python/API-тести:

```bash
uv run --locked ruff check .
uv run --locked ruff format --check .
make lint-frontend
make lint-docs
make lint-shell
uv run --locked mypy
make test-bash
make test-frontend
uv run --locked coverage run -m pytest --integration
uv run --locked coverage report
uv run --locked coverage html
uv run --locked coverage xml
```

- Ruff перевіряє стиль, імпорти, типові помилки та форматування; `make format`
  застосовує форматування.
- ShellCheck аналізує `check_websites.sh` і `docker/init-app-role.sh`, зокрема
  роботу з лапками, змінними та умовами. `--norc` забезпечує незалежність від
  користувацької конфігурації; жодні діагностики не вимкнені.
- mypy працює у строгому режимі для `main.py`, `conf/`, `scripts/` і `tests/`.
- TypeScript перевіряє frontend і тести через `tsc --noEmit`; ESLint/SonarJS —
  якість коду, Next.js, доступність та тести; Prettier — форматування.
  Початкові візуальні еталони не форматуються.
- Markdownlint перевіряє заголовки, списки, посилання, блоки коду та оформлення
  Markdown за кореневою `.markdownlint-cli2.jsonc`.
- pytest трактує попередження як помилки: застарілі виклики бібліотек
  не можна приховати успішним результатом тестів.
- coverage вимірює виконання рядків та гілок Python-коду застосунку;
  мінімальний поріг — 90%. Код запуску сервера під `if __name__ == "__main__"`
  виключено з вимірювання, оскільки тести викликають застосунок через TestClient.
- HTML-звіт створюється у `htmlcov/index.html`, XML-звіт — у `coverage.xml`.
  Ці файли, кеші та `.venv` не входять до Git або Docker-контексту.

**Швидкі тести** перевіряють головну сторінку, статичні файли, документацію,
контракт відповідей API, обробку помилки БД та порожнього результату. Замість
SQL-з'єднання вони використовують mock сесії; SQLite не використовується.
Тести конфігурації працюють із тимчасовими файлами та ізольованим середовищем:
перевіряють обов'язкові поля, неправильні значення, пріоритет змінних,
спеціальні символи в паролях, читання secret-файлів та приховування значень.
Тести логування перевіряють JSON, фільтрацію рівнів, єдиний запис запиту,
приховування даних, кореляцію помилок, ізоляцію ID паралельних запитів
і обірвану відповідь. Окремо перевіряється конфігурація запуску Uvicorn.
17 сценаріїв `tests/test_init_local.py` перевіряють першу, повторну,
часткову та паралельну ініціалізацію, випадкові паролі, права, незмінність
файлів, власні шляхи й overrides, помилки конфігурації та відсутність
паролів у виводі. Вони використовують лише тимчасові каталоги.
Після `make build-frontend` звичайний `uv run --locked pytest` запускає
лише ці 77 Python-тестів без Docker.
Bash-сценарії з `tests/bash/test_websites.py` запускає тільки `make test-bash`
у спеціальному Linux-контейнері. Навіть `pytest --integration` на хості не
додає Bash-сценарії; `make test-all` об'єднує обидва запуски без дублювання.

**Інтеграційні тести** в `tests/integration/` запускаються явно через
`--integration`. Вони використовують основний `docker-compose.yaml`, реальний
Dockerfile distroless, образ Percona 17.11 та той самий скрипт ініціалізації.
`compose.test.yaml` додає випадкові порти лише на `127.0.0.1` і окремий тег
образу застосунку. Набір тестів перевіряє:

- реальний HTTP-виклик `/healthchecker` та відповідність прикладу OpenAPI;
- React у Chromium/Firefox/WebKit: завантаження з distroless, натискання кнопки, реальна
  відповідь від Percona та успішний результат без JavaScript-помилок;
- JSON логів запущеного контейнера, кореляцію `X-Request-ID`, відсутність
  дублювання access log і переданих чутливих значень;
- версію Percona 17 і виконання SQL через PostgreSQL-драйвер;
- вхід застосунку та адміністратора, відмову з неправильним паролем;
- мінімальні права ролі та відмову у створенні таблиць, тимчасових таблиць,
  ролей і читанні системних хешів паролів;
- повернення справжнього з'єднання до пулу після успіху й винятку;
- реальну зупинку тестової Percona, своєчасну помилку API та автоматичне
  відновлення після запуску БД без перезапуску застосунку;
- SIGTERM під час активного HTTP-запиту, його успішне завершення, закриття
  з'єднань БД до виходу PID 1 та завершення без SIGKILL;
- non-root запуск і відсутність доступу застосунку до секрету адміністратора;
- нульові capabilities, `NoNewPrivs=1` у сервера та його потоків, read-only
  root mount і відмову запису з `EROFS`; роботу HTML, Swagger та статичних файлів;
- повторне застосування ініціалізації без порушення підключення.

Усі перевірки використовують єдину конфігурацію secrets з основного Compose.
Паролі читаються з приватних тимчасових файлів; тимчасовий `.env` містить
налаштування та шляхи, але не значення паролів. pytest генерує окремий проєкт
`hw02-test-<random>`, нові паролі та порожній том. Сценарій SIGTERM має ще один
окремий проєкт, оскільки навмисно завершує процес застосунку.
Локальний `.env` розробника не читається, успадковані DB/Compose overrides
відкидаються. Перша збірка може завантажувати образи й пакети; наступні
використовують Docker build cache. За відсутності Docker інтеграційний запуск
завершується помилкою, а не успішним пропуском перевірок.

Блок `finally` прибирає тестові контейнери, мережу, том, тег образу та тимчасові
секрети після успіху або помилки. Робочий Compose-проєкт і його дані не
використовуються. Після примусового завершення процесу через SIGKILL або збою
Docker залишки можна знайти за префіксом `hw02-test-`; автоматичний глобальний
`docker prune` не виконується.

**Випадок реального збою БД** описаний у
`tests/integration/test_database_recovery.py`. Перед зупинкою тест викликає
API, щоб у пулі були живі з'єднання, та перевіряє ефективний `connect_timeout`
безпосередньо в libpq усередині distroless: типові 3 секунди з основного Compose.
Далі він виконує `stop db` лише в тимчасовому проєкті та перевіряє:

- дві послідовні відповіді `500` із безпечним JSON
  `{"detail":"Error connecting to the database"}` за час менший за
  `DB_CONNECT_TIMEOUT + 2` секунди для кожної відповіді;
- для кожного `X-Request-ID` — один JSON-запис `Database health check failed`
  з типом `OperationalError` та один access log, обидва рівня `ERROR`,
  без паролів у журналі;
- доступність Swagger під час відмови БД;
- після `start --wait db` — успіх уже першого запиту `/healthchecker`
  і ще двох послідовних запитів без повторних спроб на клієнті;
- незмінні ID контейнера та час старту PID 1 із `/proc/1/stat`, що підтверджує
  відсутність перезапуску процесу застосунку під час усього сценарію.

Блок `finally` запускає тестову БД навіть при падінні перевірки; зовнішня
fixture прибирає весь тимчасовий проєкт. Зупинка БД зазвичай дає відмову
з'єднання швидше за timeout: цей сценарій не симулює завислий SQL-запит
або мережу, яка мовчки відкидає пакети. Часовий бюджет тесту стосується
саме цього ізольованого середовища, а не універсального SLA.
Наявний `pool_pre_ping=True` виявляє непридатні з'єднання при отриманні з пулу
та дозволяє наступним запитам підключитися після відновлення БД.
Операції, що вже перервалися, автоматично не повторюються.
Довідка: [SQLAlchemy: disconnect handling](https://docs.sqlalchemy.org/en/21/core/pooling.html#disconnect-handling-pessimistic).

Окремий запуск сценарію:

```bash
uv run --locked pytest --integration tests/integration/test_database_recovery.py -v
```

Coverage вимірює Python-код у процесі pytest. Виконання API в окремому
контейнері не додається до цього звіту; його поведінка перевіряється HTTP-
та SQL-assertions. Bash і JavaScript coverage не вимірює.

Для зміни залежностей використовуйте `uv add PACKAGE` або `uv add --dev PACKAGE`.
Після зміни залежностей оновіть сумісний експорт:

```bash
uv export --locked --no-dev --format requirements-txt --output-file requirements.txt
```

## Оновлення та аудит залежностей

11 жовтня 2026 року перевірено всі прямі, транзитивні та розробницькі
Python-залежності. Після вилучення Jinja2 і MarkupSafe залишився 61 сторонній
пакет у `uv.lock`; їхні версії відповідають найновішим
стабільним версіям, сумісним із Python 3.13, доступним на PyPI на момент перевірки.
Основні зміни:

| Пакет | До оновлення | Після оновлення |
| --- | --- | --- |
| FastAPI | 0.108.0 | 0.143.0 |
| Starlette (транзитивно) | 0.32.0.post1 | 1.7.0 |
| Uvicorn | 0.25.0 | 0.54.0 |
| Jinja2 | 3.1.2 | вилучено після переходу на React |
| SQLAlchemy | 2.0.54 | 2.1.4 |
| HTTP-клієнт тестів | httpx 0.27.2 | httpx2 2.13.1 |
| pip-audit | не використовувався | 2.10.1 |
| shellcheck-py (dev) | не використовувався | 0.11.0.1 (ShellCheck 0.11.0) |

Pydantic 2.14.0, pydantic-settings 2.15.0, psycopg2-binary 2.9.13,
coverage 7.16.2, mypy 2.4.0, pytest 9.1.1 та Ruff 0.17.0 вже були актуальними.
Builder Docker також оновлено з uv 0.11.6 до 0.13.0; глобальні інструменти
операційної системи розробника цей проєкт не змінює.

Головна сторінка використовує `FileResponse` для готового frontend build.
Тести переведено на `httpx2`, рекомендований новою Starlette, включно
з асинхронним ASGI transport та реальними HTTP-викликами контейнера.
Драйвер БД явно задано як `postgresql+psycopg2`, тому зміна типового драйвера
в SQLAlchemy 2.1 не змінює наш спосіб підключення.
Довідка: [Starlette](https://starlette.dev/release-notes/),
[міграція HTTPX2](https://pydantic.dev/docs/httpx2/get-started/migration/),
[SQLAlchemy 2.1](https://docs.sqlalchemy.org/en/21/changelog/migration_21.html).

`pip-audit` виявив у попередніх версіях 25 відомих проблем у FastAPI,
Jinja2 та Starlette. Після оновлення аудит залежностей застосунку й інструментів
розробки не виявив відомих вразливостей. Це результат перевірки за поточними
даними advisory-сервісу, а не гарантія відсутності всіх можливих проблем.

`make audit` експортує всі групи з `uv.lock` у
`artifacts/audit-requirements.txt` із точними версіями й хешами та запускає
`pip-audit --require-hashes --disable-pip`. Повторне розв'язання залежностей
через pip не виконується. Враховуються platform markers поточного середовища;
системні пакети Debian/Rocky, Python runtime та образ Percona цей аудит не перевіряє.
Аудит має окрему команду, бо потребує мережевого доступу. Каталог `artifacts/`
не входить до Git, Docker-контексту або ZIP.

Для наступного оновлення в межах дозволених діапазонів:

```bash
uv lock --upgrade
uv sync --locked
uv export --locked --no-dev --format requirements-txt --output-file requirements.txt
make check
make audit
```

Pre-release версії заборонені конфігурацією uv. Нові major-версії потребують
окремого перегляду обмежень у `pyproject.toml`, змін API та повторного запуску
перевірок. Звичайні Python-команди використовують `--locked`; pnpm install —
`--frozen-lockfile`.

Python-конфігурація міститься в `pyproject.toml`; frontend-конфігурація —
у `frontend/package.json`, `eslint.config.mjs`, `.prettierrc.json`,
`postcss.config.mjs`, `tsconfig.json` та `playwright.config.ts`.
Довідка: [uv у Docker](https://docs.astral.sh/uv/guides/integration/docker/),
[Ruff](https://docs.astral.sh/ruff/configuration/),
[ShellCheck](https://github.com/koalaman/shellcheck),
[shellcheck-py](https://github.com/shellcheck-py/shellcheck-py),
[mypy](https://mypy.readthedocs.io/en/stable/config_file.html),
[coverage](https://coverage.readthedocs.io/en/latest/config.html).
