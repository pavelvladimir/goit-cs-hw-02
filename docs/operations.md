# Docker, конфігурація та експлуатація

[До README](../README.md)

Підготовка secrets, права процесів, оновлення образів і зупинка сервісів.
Усі команди виконуються з кореня репозиторію.

## Запуск

Потрібні `make`, `uv`, запущений Docker Engine (або Docker Desktop) та
Docker Compose. У каталозі репозиторію на macOS/Linux виконайте:

```bash
make init
docker compose up --build -d --wait
make help
```

`make init` запускає `scripts/init_local.py` через uv із `uv.lock`; перший
запуск може завантажити Python 3.13 і Python-залежності. Node.js, pnpm та
OpenSSL на хості для цього не потрібні. Новий `.env` копіюється з
`.env.example` із правами `0600`. Для двох відсутніх secret-файлів
генеруються незалежні паролі з 32 випадкових байтів (`secrets.token_hex`),
файли отримують `0444`, їхні нові каталоги — `0700`.

Наявні `.env`, паролі, права й час модифікації не змінюються. Повторний
запуск нічого не перезаписує; частково підготовлене середовище отримує
лише відсутні файли. Файли публікуються атомарно без заміни наявного шляху,
тому паралельні запуски також не перезаписують один одного. Паролі не
виводяться на екран. Порожній/пошкоджений secret, однакові паролі або
шляхи, symlink замість файлу чи неправильні права дають зрозумілу помилку
та ненульовий код завершення; наявні файли залишаються недоторканими.

Враховуються `DB_PASSWORD_SECRET_FILE` і `POSTGRES_PASSWORD_SECRET_FILE`
із `.env`; значення цих змінних у середовищі shell мають пріоритет, як у
Compose. Підтримано абсолютні та відносні шляхи, лапки й пробіли. Для init
вкажіть буквальні шляхи: конструкції на кшталт `${SECRET_DIR}/password`
відхиляються, щоб не створити секрет за неправильною адресою. Власний
наявний каталог секретів повинен мати права `0700`.

Шаблон містить шляхи, а не значення паролів. Init готує файли, але не
змінює паролі у вже створеній БД. Якщо її secret-файли втрачено, відновіть
чинні паролі або застосуйте процедуру зміни нижче. `make help` і просто
`make` показують перелік команд без встановлення залежностей або Docker.
Еквівалент запуску з назвою команди з умови завдання після налаштування секретів:

```bash
docker-compose up --build -d --wait
```

Compose запускає два сервіси:

| Сервіс | Призначення |
| --- | --- |
| `app` | FastAPI на Python 3.13 у `gcr.io/distroless/python3:nonroot`, доступний за `http://localhost:8000` |
| `db` | `percona/percona-distribution-postgresql:17.11`, база `hw02`, окремі облікові записи адміністратора й застосунку |

## Конфігурація та секрети

`conf/settings.py` використовує Pydantic Settings: змінні середовища мають
пріоритет над локальним `.env`. Обов'язкові `DB_HOST`, `DB_NAME`, `DB_USER`
та рівно одне джерело пароля: `DB_PASSWORD` або `DB_PASSWORD_FILE`.
Порт `DB_PORT` має бути в межах 1–65535 (типово 5432), назви бази й ролі —
латинськими літерами нижнього регістру, цифрами та `_`, починатися з літери
або `_` і мати не більше 63 символів. Роль застосунку не може бути `postgres`
або починатися з `pg_`. Помилки конфігурації зупиняють запуск, не показуючи
вхідних значень. Пароль приховано в представленні налаштувань і URL;
SQLAlchemy не виводить SQL-параметри в повідомленнях про помилки.
`LOG_LEVEL` приймає `DEBUG`, `INFO` (типово), `WARNING`, `ERROR` або `CRITICAL`;
інше значення зупиняє запуск із JSON-повідомленням про некоректне поле.
`DB_CONNECT_TIMEOUT` задає ціле число секунд від 2 до 30, типово `3`.
SQLAlchemy передає його драйверу psycopg2 як параметр libpq `connect_timeout`.
Нульові, від'ємні та некоректні значення відхиляються під час запуску.
Це обмеження встановлення з'єднання, а не виконання SQL чи всього HTTP-запиту:
воно застосовується окремо до кожного хоста/IP, а DNS, очікування в пулі та
вже відкриті з'єднання потребують окремих обмежень у складніших сценаріях.
Довідка: [PostgreSQL: connect_timeout](https://www.postgresql.org/docs/17/libpq-connect.html#LIBPQ-CONNECT-CONNECT-TIMEOUT).

`SHUTDOWN_GRACE_SECONDS` задає загальний бюджет зупинки контейнера: ціле число
від 6 до 120 секунд, типово `20`. Compose використовує його як
`stop_grace_period`, а Uvicorn отримує на 5 секунд менше для завершення запитів.
Резерв потрібен для закриття пулу БД та виходу процесу. Зміна цього параметра
потребує перестворення `app`: `docker compose up -d app`.

У `.env.example` наведені всі локальні параметри. `.env`, `.env.*` (крім
шаблону) та каталог `secrets/` виключені з Git; секрети також не потрапляють
до Docker-контексту чи архіву для здачі. Не додавайте їх до архівів вручну.

Compose читає файли за шляхами `DB_PASSWORD_SECRET_FILE` і
`POSTGRES_PASSWORD_SECRET_FILE` з локального `.env` (типово
`./secrets/db_password` та `./secrets/postgres_password`) і монтує їх
як **Compose secrets** у `/run/secrets/` лише для читання.
Контейнер `app` отримує лише пароль `hw02_app`, контейнер `db` — обидва.
Compose не записує значення паролів у конфігурацію environment контейнерів
або Docker build arguments.
Локальний `.env` має права `0600` і містить тільки конфігурацію та шляхи.
Каталог `secrets/` має права `0700`, файли — `0444`, щоб non-root процеси
могли читати окремі bind mounts, а інші користувачі хоста не могли пройти
через приватний каталог. Compose secrets не є зашифрованим сховищем.
`DB_PASSWORD_FILE` у `.env` використовується для запуску Python на хості;
Compose перевизначає його на `/run/secrets/db_password`.

Ім'я `db` у спільній мережі Compose вказує на контейнер PostgreSQL. Усередині
контейнера `localhost` вказував би на сам цей контейнер. URL складається через
`SQLAlchemy URL.create`, тому спеціальні символи в паролі не потребують
ручного URL-кодування. Старий параметр `DATABASE_URL` більше не використовується.

На порожньому томі `docker/init-app-role.sh` створює роль `DB_USER`
(типово `hw02_app`). Вона має лише `LOGIN` і `CONNECT` до бази застосунку:
без superuser, створення БД/ролей, реплікації чи обходу RLS. Права `PUBLIC`
на базу та схему `public` відкликані; застосунок не може створювати звичайні
або тимчасові таблиці. Поточний `SELECT 1` не потребує прав на таблиці.
Коли з'являться CRUD-операції, права на конкретні таблиці й послідовності
слід додавати окремо; міграції не виконуються від імені runtime-користувача.

**Наявний том або зміна паролів:** ініціалізація виконується автоматично лише
один раз. Зміна secret-файлів сама по собі не змінює паролі в PostgreSQL.
Після резервного копіювання оновіть обидва файли та застосуйте налаштування явно:

```bash
docker compose up -d --force-recreate --wait db
docker compose exec -T db bash /docker-entrypoint-initdb.d/10-app-role.sh
docker compose up --build -d --force-recreate --wait app
```

Скрипт повторно застосовує права та обидва паролі в одній транзакції,
не видаляючи дані. Він призначений для окремої бази цього проєкту й окремої
ролі застосунку. Перед зміною паролів збережіть резервну копію бази. Не видаляйте том заради зміни пароля.

Примусове повторне створення контейнерів підключає нові файли навіть після їх
атомарної заміни, а застосунок перечитує пароль під час запуску.

Для всіх запусків використовується одна конфігурація файлових secrets
у `docker-compose.yaml`. Щоб зберігати паролі в іншому каталозі, змініть
`DB_PASSWORD_SECRET_FILE` та `POSTGRES_PASSWORD_SECRET_FILE` у `.env`.
Для запуску Python на хості узгодьте також `DB_PASSWORD_FILE` зі шляхом
до пароля застосунку.
Додатковий Compose-файл не потрібен; команда запуску залишається тією самою:

```bash
docker compose up --build -d --wait
```

Для зміни паролів на наявному томі застосовуйте попередню процедуру.
Сам застосунок і далі підтримує `DB_PASSWORD` для запуску поза
Compose; його не можна задавати одночасно з `DB_PASSWORD_FILE`.
Документація: [Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/).

PostgreSQL має перевірку готовності `pg_isready` через TCP; застосунок стартує після
того, як база стане доступною. Перевірка стану `app` звертається до
`/healthchecker`, де виконується SQL-запит `SELECT 1`. Дані PostgreSQL
зберігаються в іменованому томі `percona_postgres17_data`, змонтованому у
`/data/db` — каталозі `PGDATA` образу Percona.

Dockerfile використовує uv 0.13.0 та `uv sync --locked --no-dev` на окремому
етапі збірки на Debian 13 (Trixie). На цьому етапі Python встановлено в
`/usr/bin/python3`, як і у distroless, тому посилання у `.venv` залишаються
чинними після копіювання. Кінцевий образ `gcr.io/distroless/python3:nonroot`
зафіксовано за SHA-256 digest, щоб зміна тегу не змінила версію Python.
Окремий `frontend-builder` на Node.js 22 встановлює pnpm 12.11.2,
виконує `pnpm install --frozen-lockfile` та `pnpm run build`.
До фінального образу копіюється лише `frontend/out/` із HTML, JS та CSS.

Застосунок запускається від UID/GID `65532:65532`, без автоматичного
перезавантаження. Кінцевий образ не містить Node.js, pnpm, shell, pip, uv або інструментів
розробки. Сервер стартує через `/app/.venv/bin/python3 -m conf.server`, а healthcheck
викликає Python напряму у форматі `CMD`. Порт застосунку опублікований лише
на локальному комп'ютері.

Образи: [distroless Python](https://github.com/GoogleContainerTools/distroless/blob/main/python3/README.md),
[Percona PostgreSQL 17 у Docker](https://docs.percona.com/postgresql/17/docker.html).

## Фіксація та оновлення Docker-образів

Усі зовнішні образи задані у форматі `тег@sha256:digest`:

| Призначення | Тег | Де зафіксований повний digest |
| --- | --- | --- |
| Frontend builder | `node:22-slim` | `Dockerfile`, `FROM ... AS frontend-builder` |
| Python builder | `debian:trixie-slim` | `Dockerfile`, `FROM ... AS builder` |
| Bash runtime і тести | `rockylinux/rockylinux:10-minimal` | `docker/websites.Dockerfile`, `FROM ... AS base` |
| Інструмент uv | `ghcr.io/astral-sh/uv:0.13.0` | Обидва Dockerfile, `COPY --from` |
| Python runtime | `gcr.io/distroless/python3:nonroot` | `Dockerfile`, кінцевий `FROM` |
| PostgreSQL | `percona/percona-distribution-postgresql:17.11` | `docker-compose.yaml`, `services.db.image` |

Тег пояснює вибрану версію, а digest визначає точний вміст образу: перенесення
тегу видавцем не змінить наступне завантаження нашого проєкту.
Застосовані digest індексів образів, які містять `linux/amd64` та `linux/arm64`;
Docker вибирає відповідний manifest платформи. Фіксація не прив'язує проєкт
лише до архітектури комп'ютера розробника. `compose.test.yaml` успадковує
той самий образ Percona; його тег `TEST_APP_IMAGE` позначає локальну збірку
з цього Dockerfile, а не додатковий зовнішній образ.

**Процедура оновлення:**

1. Виберіть потрібні версії та перегляньте зміни видавців. Поточні digest
   тегів можна отримати без запуску контейнерів:

   ```bash
   docker buildx imagetools inspect debian:trixie-slim
   docker buildx imagetools inspect node:22-slim
   docker buildx imagetools inspect rockylinux/rockylinux:10-minimal
   docker buildx imagetools inspect ghcr.io/astral-sh/uv:0.13.0
   docker buildx imagetools inspect percona/percona-distribution-postgresql:17.11
   docker buildx imagetools inspect gcr.io/distroless/python3:nonroot
   ```

2. Перевірте наявність потрібних платформ. Скопіюйте **верхній `Digest:`**
   індексу після `@` у відповідному файлі, зберігши префікс `sha256:`.
   Не використовуйте локальний Image ID або digest одного вкладеного manifest.
   При переході на іншу версію змініть і тег, і digest. Для distroless
   перевірте сумісність Python з builder і вимогою проєкту `>=3.13,<3.14`.
   Новий major PostgreSQL потребує окремої міграції даних.
   Digest uv оновлюйте в обох Dockerfile разом. Debian належить builder
   застосунку, Rocky — Bash-образам. Версію тестового CPython змінюйте
   явно через `UV_PYTHON` у `docker/websites.Dockerfile`, у межах Python 3.13.

3. Перевірте конфігурацію, виконайте чисту збірку та весь набір тестів:

   ```bash
   docker compose config --quiet
   docker compose build --pull --no-cache app
   docker build --pull --no-cache -f docker/websites.Dockerfile --target runner -t goit-cs-hw-02-websites .
   docker build --pull --no-cache -f docker/websites.Dockerfile --target tests -t goit-cs-hw-02-bash-tests .
   make check
   ```

   Ці команди не перезапускають робочі контейнери: інтеграційні тести
   створюють власні проєкти й томи. `--pull` перевіряє вже заданий digest;
   він не оновлює значення в Dockerfile автоматично.

4. Запишіть нові версії та результати перевірки в `docs/verification.md`.
   Для здачі завантажте новий ZIP із GitHub після оновлення репозиторію.
   Оновлення digest виконується свідомо, зокрема для отримання
   виправлень безпеки: зафіксований образ не змінюється самостійно.

Фіксація образів і `uv.lock` ще не гарантує побайтово однакової збірки.
Builder виконує `apt-get update` і встановлює `python3`, `python3-venv` та
`ca-certificates` з актуальних Debian-репозиторіїв без фіксації їхніх версій.
Для фіксації цих apt-входів потрібні датований snapshot репозиторію та
узгоджені версії пакетів; у цьому проєкті вони поки не налаштовані.
У Bash-образах Bash, curl і CA-сертифікати вже входять у зафіксований Rocky
образ: `microdnf update/install` під час збірки не виконується. Керований
CPython має явну patch-версію; каталог дистрибутивів визначає зафіксований uv.
Довідка: [Docker: pin base image versions](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions),
[imagetools inspect](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/).

## Обмеження контейнера застосунку

Сервіс `app` у `docker-compose.yaml` працює з такими обмеженнями:

```yaml
read_only: true
cap_drop:
  - ALL
security_opt:
  - no-new-privileges:true
```

`read_only` монтує кореневу файлову систему контейнера лише для читання.
Застосунок читає код, шаблони та статичні файли, а журнали пише у stdout.
`PYTHONDONTWRITEBYTECODE=1` вимикає запис Python bytecode. Поточні функції
застосунку не потребують тимчасових файлів, тому `/tmp` також залишається
лише для читання; додатковий writable volume або tmpfs не потрібен.
Окремі системні монтування Docker, наприклад `/dev/shm`, не є частиною
кореневої файлової системи, на яку поширюється `read_only`.

`cap_drop: [ALL]` вилучає всі Linux capabilities, включно з bounding set.
`no-new-privileges` забороняє отримувати додаткові привілеї через `execve`,
зокрема через setuid/setgid та file capabilities. Разом із UID/GID 65532
ці налаштування обмежують повноваження процесу застосунку.
Дані PostgreSQL записуються окремим сервісом `db` у його іменований том.

Інтеграційні тести перевіряють фактичний стан ядра: `/proc/1/task/*/status`
для сервера й усіх наявних потоків, `/proc/1/mountinfo` для кореневого mount
та реальну відмову створення файлів у `/app/conf` і `/tmp` з кодом `EROFS`.
Очікуються UID/GID 65532, `NoNewPrivs: 1` та нульові `CapInh`, `CapPrm`,
`CapEff`, `CapBnd` і `CapAmb`. Після цього HTTP-перевірки підтверджують
роботу головної сторінки, Swagger, JavaScript і запиту до БД.
Перевірки запускаються в ізольованому Compose-проєкті з тимчасовими secrets:

```bash
uv run --locked pytest --integration tests/integration/test_container_security.py
```

Документація: [Docker Compose](https://docs.docker.com/reference/compose-file/services/),
[no_new_privs у Linux](https://docs.kernel.org/userspace-api/no_new_privs.html).

## Коректне завершення через SIGTERM

Distroless запускає Python безпосередньо через exec-form `ENTRYPOINT`; Uvicorn
працює як PID 1 і сам отримує сигнали Docker. Compose явно задає
`stop_signal: SIGTERM` і типово чекає 20 секунд перед примусовим `SIGKILL`.
У `conf/server.py` увімкнено lifespan та `timeout_graceful_shutdown=15`
для цього бюджету: сервер припиняє приймати нові з'єднання й чекає завершення
активних запитів. Після цього FastAPI lifespan у `conf/lifecycle.py` викликає
`engine.dispose()` та записує `Database connection pool closed` у JSON-журнал.
Закриття пулу виконується в робочому потоці, щоб не блокувати event loop.

Сценарій перевіряється в окремому тимчасовому Compose-проєкті:

```bash
uv run --locked pytest --integration tests/integration/test_graceful_shutdown.py -v
```

Оскільки звичайний `SELECT 1` завершується надто швидко, fixture підключає
`shutdown_probe.py` лише до тестового контейнера як read-only bind mount.
Цей bootstrap запускає той самий `conf.server.main()` у PID 1 та обгортає
наявну залежність `get_db`: лише запит із тестовим заголовком чекає PostgreSQL
advisory lock. Обробник `/healthchecker`, сесія та middleware залишаються
справжніми; Docker healthcheck продовжує працювати. У звичайному образі немає
цього bootstrap або спеціального endpoint для затримки.

Тест підтверджує через `pg_stat_activity` та `pg_blocking_pids`, що HTTP-запит
вже працює й утримує з'єднання БД. Потім виконує `docker compose stop app`
без перевизначення timeout. Блокування знімається лише після повідомлення
Uvicorn про очікування активних з'єднань; до цього запит і зупинка ще тривають.
Перевіряються:

- відповідь `200` з очікуваним JSON та тим самим `X-Request-ID` після SIGTERM;
- закриття всіх спостережуваних psycopg2-з'єднань після lifespan, ще до виходу
  PID 1, а також відсутність сесій ролі застосунку в PostgreSQL після виходу;
- послідовність журналу: початок зупинки → завершення запиту → закриття пулу
  → завершення lifespan → вихід сервера, без записів `ERROR` чи `CRITICAL`;
- фактичні `StopSignal=SIGTERM` і `StopTimeout=20`, вихід раніше цього ліміту,
  стан `exited`, відсутність OOM та лише SIGTERM у Docker events, без SIGKILL.

Uvicorn повторно надсилає отриманий сигнал після cleanup, тому тест допускає
код виходу `0` або `143` (128 + SIGTERM); код `137` (SIGKILL) не допускається.
Сам код виходу не є доказом: окремо перевіряються події Docker, завершений
запит і стан реальних з'єднань до виходу процесу.

Це підтверджує штатне завершення запиту, який встигає закінчитися в межах
бюджету. Після timeout Uvicorn скасовує незавершені задачі; завислий синхронний
SQL-запит може вимагати `statement_timeout`. `connect_timeout` обмежує лише
встановлення з'єднання. Якщо процес не вийде за весь бюджет Compose, Docker
застосує SIGKILL; резерв у 5 секунд не є гарантією завершення довільного cleanup.
Довідка: [Compose stop_grace_period](https://docs.docker.com/reference/compose-file/services/#stop_grace_period),
[Uvicorn timeouts](https://uvicorn.dev/settings/#timeouts),
[FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/).

## Журнали та зупинка

Застосунок, Uvicorn та SQLAlchemy використовують одну конфігурацію Python
`logging` у `conf/logging.py`: один JSON-об'єкт на рядок у stdout. Файли
журналів усередині контейнера не створюються. Grafana та збирачі логів не потрібні.
Це формат логів сервісу `app`; журнали самої Percona залишаються у форматі сервера БД.

`conf.server` налаштовує журналювання до запуску Uvicorn. Для запуску Python
поза Docker використовуйте `uv run --locked python -m conf.server` із доступним
PostgreSQL та відповідними `DB_HOST` / `DB_PORT`.

Кожен HTTP-запит отримує `X-Request-ID` у відповіді, включно з помилками `500`.
Вхідний `X-Request-ID` приймається лише як UUID; інакше генерується новий UUID.
Один підсумковий запис містить UTC-час, рівень, джерело, ID, HTTP-метод,
шаблон маршруту, статус і тривалість обробки в мілісекундах. Приклад:

```json
{"timestamp":"2026-10-11T12:00:00.000+00:00","level":"INFO","logger":"app.access","message":"request_completed","request_id":"5325f398-dc1f-45af-b1f9-70753ebf4a71","method":"GET","path":"/healthchecker","status":200,"duration_ms":2.154}
```

Успішні запити мають рівень `INFO`, `4xx` — `WARNING`, `5xx` або незавершена
відповідь — `ERROR`. `duration_ms` вимірює обробку на сервері до завершення
ASGI-виклику; це не час мережевого завантаження на клієнті. Шлях записується
як шаблон без значень параметрів; якщо шаблон недоступний, значення — `<unmatched>`.
Query-параметри, тіла та інші HTTP-заголовки не записуються.

Помилка БД додає один запис із типом винятку та stack trace: файл, рядок,
функція. Текст винятку, рядки вихідного коду та локальні змінні не серіалізуються,
бо вони можуть містити SQL або секрети. Необроблені винятки журналює Uvicorn
зі збереженим ID запиту. Стандартний access log Uvicorn вимкнений, щоб не
дублювати підсумки. SQLAlchemy має рівень щонайменше `WARNING`, SQL echo
залишається вимкненим навіть при `LOG_LEVEL=DEBUG`. Відомий пароль БД також
маскується у тексті повідомлень, включно з URL-кодуванням. У нових повідомленнях
використовуйте сталі описи подій і не передавайте секрети в текст логів.

Перегляд JSON без префіксів Compose:

```bash
docker compose logs --follow --no-log-prefix app
```

Змініть `LOG_LEVEL` у `.env` і виконайте `docker compose up -d app`, щоб
застосувати рівень. Наприклад, `WARNING` прибирає успішні HTTP-запити,
включно з регулярними healthcheck. Усі журнали та зупинка:

```bash
docker compose logs app db
docker compose down
```

Команда `down` зупиняє і видаляє контейнери; дані в іменованому томі залишаються.

## Перехід із PostgreSQL 16

Для PostgreSQL 17 використовується новий том `percona_postgres17_data`.
Старий том `goit-cs-hw-02_postgres_data` не видаляється і не підключається
до сервера іншої основної версії. Дані між версіями переносяться через
`pg_dump` / `pg_restore`, а не копіюванням каталогу даних.

Перед локальним переходом створено резервну копію бази `hw02` у
`artifacts/hw02-postgresql16-before-percona.dump` та успішно відновлено її
через `pg_restore` у Percona PostgreSQL 17. Каталог `artifacts/`
не входить до Git, Docker-контексту чи ZIP для здачі.
