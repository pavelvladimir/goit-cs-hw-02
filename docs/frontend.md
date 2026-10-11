# Frontend і контракт API

[До README](../README.md)

Збірка статичної сторінки, генерація клієнта, доступність і перевірка вигляду.
Для команд потрібне середовище з [інструкції розробника](development.md); робочий каталог — корінь репозиторію.

Frontend у `frontend/` використовує Next.js 16.4.0, React 19.3.0,
Hey API 0.99.0, Zod 4.6.5 та Base UI 1.9.0. Збережено градієнт, шрифт,
основні відступи й кольори результату. Для доступності зменшено яскравість
зеленої кнопки, додано видимий фокус та адаптивну область повідомлення.
Viewport задано
як `width=device-width, initial-scale=1, viewport-fit=cover`; на мобільних
пристроях сторінка використовує ширину екрана. `format-detection` вимикає
автоматичне розпізнавання телефонів, email, адрес і дат. Мова й напрямок
задані разом у layout: для української — `<html lang="uk" dir="ltr">`.
Той самий `locale.direction` передається `DirectionProvider` для поведінки
компонентів Base UI; HTML-атрибут `dir` задає напрямок для браузера.
Next.js з `output: 'export'` створює готове HTML
під час збірки: заголовок і кнопка видимі ще до виконання JavaScript.
Для перевірки БД потрібен JavaScript; запит виконується лише після натискання
«Перевірити БД», через `/healthchecker` на тому самому origin.

`docker compose up --build -d --wait` сам збирає frontend. Python builder
перевіряє актуальність OpenAPI, Node.js builder генерує клієнта й статичний
експорт. До distroless копіюється тільки `frontend/out/`; Node.js, pnpm,
Next.js server, генератор та вихідний код frontend у runtime не потрібні.
FastAPI віддає `out/index.html` через `/`, JS/CSS — через `/_next/static/`.
Для HTML задано `Cache-Control: no-cache`. Swagger та API мають власні
маршрути; невідома адреса повертає 404.

**Єдине джерело API-контракту — FastAPI.** `scripts/export_openapi.py`
експортує `app.openapi()` у `frontend/openapi.json`. Він вимикає dotenv
і використовує ізольовані фіктивні налаштування: не читає secret-файли,
не виконує запити та не підключається до БД. JSON зберігається разом із
кодом. `make check-api` і Docker build відхиляють застарілий експорт.
Після зміни endpoint або Pydantic-моделі виконайте:

```bash
make generate-api        # FastAPI → openapi.json → клієнт і Zod-схеми
make check-api           # перевірка відповідності поточному FastAPI
```

Hey API читає локальний JSON за конфігурацією `frontend/openapi-ts.config.ts`
та створює `src/api/generated/`. Цей каталог не редагується вручну, не
додається до Git/ZIP і відновлюється командою `pnpm --dir frontend generate`
або кожним build. Працюючий API для генерації не потрібен.

SDK вмикає Zod-валідатор успішних відповідей. `src/api/health.ts` також
перевіряє документований HTTP-статус, порожні відповіді та payload помилки
500 через згенеровані схеми. Валідація зберігає обмеження Pydantic `Literal`:
успіх має містити саме `Welcome to FastAPI!`, помилка — одну з двох
документованих причин. Неправильний тип, невідомий текст, HTML замість JSON
або порушений контракт дають загальне повідомлення «Невідома помилка»;
внутрішні Zod issues та неочікувані дані не показуються. Автоматичних retry
або кешування healthcheck немає. TanStack Query не використовується.

## Розробка frontend

Коли API працює на `127.0.0.1:8000`:

```bash
make dev-frontend         # Next.js dev server на http://127.0.0.1:3000
make build-frontend       # OpenAPI, генерація, static export, TypeScript, HTML-validate
make lint-frontend        # ESLint + SonarJS, перевірка форматування Prettier
make test-frontend        # build, 117 перевірок у Chromium/Firefox/WebKit, включно з axe
make audit-frontend       # pnpm audit для всіх frontend залежностей
```

`frontend/eslint.config.mjs` використовує ESLint 10, Next.js Core Web Vitals,
TypeScript, рекомендований набір SonarJS, правила доступності JSX та імпортів.
SonarJS перевіряє, зокрема, когнітивну складність (поріг 20), ігноровані
винятки та вкладені функції; вкладені тернарні вирази заборонено.
Невикористані змінні перевіряє TypeScript-правило без дублювання SonarJS.
Type-aware правило `@typescript-eslint/no-deprecated` виявляє застарілі API.
Для тестів увімкнено правила Playwright; Jest і Testing Library
у цьому проєкті не використовуються. Попередження також зупиняють lint
завдяки `--max-warnings 0`.

Prettier налаштовано в `.prettierrc.json`: 120 символів, одинарні лапки,
без крапок з комою, відступ у два пробіли. `pnpm --dir frontend format`
форматує код та застосовує автоматичні виправлення ESLint;
`make format` додатково форматує Python через Ruff. Generated API,
результати збірки й незалежні візуальні fixtures виключені з перевірок.
CSS та JSON перевіряє окремий `prettier --check` у команді lint.

Next.js 16.4 підтримує ESLint 10 і адаптує API правил React та import.
Три plugin-пакети ще декларують старі peer-версії, тому
`pnpm-workspace.yaml` містить вузькі `allowedVersions` для перевіреної
комбінації; їх слід прибрати після оновлення upstream.
Postinstall `unrs-resolver` вимкнено: платформні бінарні модулі встановлюються
як optional dependencies з lockfile, без додаткового завантаження його скриптом.
Довідка: [Next.js ESLint](https://nextjs.org/docs/app/api-reference/config/eslint),
[SonarJS](https://github.com/SonarSource/SonarJS/blob/master/packages/analysis/src/jsts/rules/README.md),
[pnpm peer dependencies](https://pnpm.io/settings/peer-dependencies).

Dev server пересилає `/healthchecker` до FastAPI через rewrite, який
увімкнено тільки у development. Якщо порт API змінено, оновіть destination
у `frontend/next.config.ts`. Production export не використовує rewrites,
Server Actions чи сервер Next.js. Make-команди та Docker build вимикають
телеметрію Next.js.

Playwright відкриває `out/` через локальний Python HTTP server, а не Next.js
server. 39 сценаріїв запускаються у Chromium, Firefox і WebKit — 117 перевірок.
Вісім візуальних сценаріїв у кожному браузері порівнюють PNG із незалежним
початковим еталоном у тому самому engine: ширини 1440 і 390 px, початковий стан, hover,
успіх і помилка. Оригінальні fixtures не змінено; до еталона явно додається
`tests/fixtures/accessibility-adjustments.css` з новими кольорами кнопки
та адаптивними розмірами повідомлення, а `preflight-adjustments.css`
задає успадкування шрифту кнопкою. Останнє навмисно вирівнює системні
шрифти кнопки у Firefox/WebKit з Arial сторінки та попереднього Chromium.
Сам Preflight до еталона не застосовується: старий box model залишається
незалежною перевіркою розмірів. PNG різних engines між собою не порівнюються.
Окремо перевірено HTML без JavaScript, відсутність запиту
до кліку, відновлення після помилки, обидві документовані помилки БД,
мережевий збій, невалідні типи/literal/status, порожнє тіло, пошкоджений JSON
та HTML-відповідь proxy. API цих тестів локально підмінено.

`tests/integration/test_frontend.py` відкриває справжній distroless
контейнер із Percona, натискає кнопку у кожному з трьох браузерів та перевіряє відповідь API
і зелений результат без JavaScript-помилок, а також запускає axe на цій
сторінці. Браузер працює на хості,
Bash-тести — лише в Rocky. Перша установка браузерів потребує інтернету.
На Linux потрібні системні бібліотеки браузера:
`pnpm --dir frontend exec playwright install --with-deps chromium firefox webkit`.
Окремий engine: `pnpm --dir frontend test --project=firefox` після збірки.
`node_modules`, `.next`, `out`, generated client, результати тестів
і браузери не додаються до Git/ZIP. Для прямого запуску Python або pytest
спочатку виконайте `make build-frontend`; Make-цілі `test`, `test-integration`
та `check` роблять це автоматично.

## CSS reset: Tailwind Preflight

Tailwind CSS 4.3.3 використовується для
[Preflight](https://tailwindcss.com/docs/preflight): `src/style.css` імпортує
`tailwindcss/preflight.css` у CSS layer `reset`, за яким ідуть `base` та
`components`. Власні стилі мають явний пріоритет. Theme та utility-класи
не імпортуються; існуючі CSS-класи компонентів збережено.
`postcss.config.mjs` підключає `@tailwindcss/postcss` 4.3.3 для обробки
функцій `--theme()` у Preflight цієї версії. Конфігурація використовується
і в Next.js dev/build, і в Docker frontend-builder. У distroless потрапляє
готовий CSS, без Tailwind/PostCSS або Node.js.

Власні стилі явно зберігають відступ body 8 px, Arial, попереднє рядкування,
відступи абзаців, підкреслені кольорові посилання на сторінці 404 та focus
кнопки. Preflight задає `border-box`, тому ширина й мінімальна висота
повідомлення включають початкові 20 px padding. Це зберігає зовнішні
розміри без повернення до `content-box`. Zoom і розмір шрифту користувача
не обмежуються. Reset нормалізує базові стилі, але не гарантує однакової
растеризації шрифтів у різних браузерах або операційних системах.

## Семантика HTML і доступність

Основний вміст розміщено в `<main>`, назва сторінки — єдиний `<h1>`.
`Button` із `@base-ui/react/button` створює нативний `<button type="button">`.
Поки виконується запит, кнопка недоступна для повторної активації,
але зберігає фокус завдяки `focusableWhenDisabled`; `aria-busy` позначає
очікування. Постійна область `role="status"`, `aria-live="polite"`,
`aria-atomic="true"` повідомляє про перевірку, успіх або помилку без
переміщення фокусу. Керування працює клавішами Tab, Enter і Space.

Контраст білого тексту кнопки змінено з приблизно 2,78:1 на 5,13:1
у звичайному стані та 6,97:1 при hover. Для клавіатури додано виразну рамку
фокусу. Розміри тексту задані в `rem`, надпис і повідомлення переносять
довгі слова, область відповіді має мінімальну висоту замість фіксованої.
На вузьких екранах вона використовує доступну ширину. Масштабування
браузера не обмежується.

`@axe-core/playwright` 4.13.0 перевіряє весь документ без виключення
елементів або вимкнення правил: idle, hover, очікування, успіх і помилку
при ширинах 1440 та 320 px, а також 200% розмір тексту та експортовану 404.
Звіти axe додаються до результатів Playwright. Окремі тести перевіряють
фокус, блокування повторного запиту, відновлення після помилки, метадані,
семантику та відсутність горизонтального прокручування й обрізаного
повідомлення при 320 px / 200% тексту. Збільшення тексту моделює зміну
базового шрифту браузера; це не автоматизація всіх режимів browser zoom.

Кожний build, включно з Docker, запускає `html-validate` 11.16.2 з
`html-validate:standard` для **всіх** файлів `out/**/*.html`. Перевіряється
сирий експорт до виправлень DOM браузером, без вимкнених правил валідності.
Для усунення дубльованого `<title>` та `<style>` усередині `<div>` у
стандартній 404 Next.js додано власний `src/app/not-found.tsx`.
Маршрути невідомих URL у FastAPI, як і раніше, повертають JSON 404.
Повторна перевірка вже зібраного HTML: `pnpm --dir frontend validate:html`.
Axe не доводить повну відповідність WCAG: перевірка зі справжнім скринридером
і оцінка зрозумілості текстів залишаються ручними.

Довідка: [Base UI Button](https://base-ui.com/react/components/button),
[DirectionProvider](https://base-ui.com/react/utils/direction-provider),
[Playwright accessibility testing](https://playwright.dev/docs/accessibility-testing),
[HTML-validate](https://html-validate.org/usage/index.html).

Довідка: [Next.js static export](https://nextjs.org/docs/app/guides/static-exports),
[Hey API SDK validation](https://heyapi.dev/docs/openapi/typescript/plugins/sdk#validators),
[Zod plugin](https://heyapi.dev/docs/openapi/typescript/plugins/zod),
[pnpm у Docker](https://pnpm.io/docker), [Playwright](https://playwright.dev/docs/intro).

## Документація API

[Swagger UI](http://localhost:8000/docs) показує назву
**goit-cs-hw-02 | FastAPI & PostgreSQL**, версію **0.1.0**, призначення
застосунку та інструкцію перевірки. Доступні також
[ReDoc](http://localhost:8000/redoc) і [OpenAPI JSON](http://localhost:8000/openapi.json).
Версія API перевіряється тестом на відповідність `pyproject.toml`.

| Ендпоінт | Група | Відповідь |
| --- | --- | --- |
| `GET /` | Web | `200 text/html`: HTML, який завантажує React і кнопку «Перевірити БД» |
| `GET /healthchecker` | Database | `200 application/json`: модель `HealthCheckResponse` |
| `GET /healthchecker` | Database | `500 application/json`: модель `HealthCheckError` |

Успішний JSON має вигляд `{"message":"Welcome to FastAPI!"}`. Він підтверджує,
що SQL-запит `SELECT 1` виконався та повернув рядок на момент перевірки.
Запит не змінює дані й не потребує параметрів або авторизації.

Для відповіді `500` наведено два іменовані приклади:

- `database_unavailable`: `{"detail":"Error connecting to the database"}` —
  помилка з'єднання або виконання SQL-запиту.
- `empty_result`: `{"detail":"Database is not configured correctly"}` —
  контрольний запит не повернув рядка.

Розгорніть `GET /healthchecker`, натисніть **Try it out → Execute**.
У розділі **Responses** можна порівняти фактичну відповідь із прикладами,
а через **Schema** — переглянути обов'язкові поля та допустимі значення.
Тести перевіряють відповідність прикладів реальним успішним і помилковим
відповідям. Для HTML-сторінки приклад позначений як скорочений фрагмент.
