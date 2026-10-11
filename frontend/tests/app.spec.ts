import { expect, type Page, test } from '@playwright/test'
import { readFileSync } from 'node:fs'

const title = 'Домашня робота: Введення в Docker та контейнеризацію'
const buttonName = 'Перевірити БД'
const success = 'Welcome to FastAPI!'
const failure = 'Error connecting to the database'
const originalHTML = readFileSync(new URL('./fixtures/original.html', import.meta.url), 'utf8')
const originalCSS = readFileSync(new URL('./fixtures/original.css', import.meta.url), 'utf8')
const accessibilityCSS = readFileSync(new URL('./fixtures/accessibility-adjustments.css', import.meta.url), 'utf8')
const normalizationCSS = readFileSync(new URL('./fixtures/preflight-adjustments.css', import.meta.url), 'utf8')
const originalJS = readFileSync(new URL('./fixtures/original.js', import.meta.url), 'utf8')

async function mockAPI(page: Page, status: number, body: object) {
  await page.route('**/healthchecker', (route) => route.fulfill({ status, json: body }))
}

const stateMessages = { idle: '', hover: '', success, error: `Помилка запиту: ${failure}` }

async function capture(page: Page, path: string, state: keyof typeof stateMessages) {
  await page.goto(path)
  await expect(page.locator('.main-text')).toHaveText(title)
  const button = page.getByRole('button', { name: buttonName })
  if (state === 'success' || state === 'error') await button.click()
  await expect(page.locator('#response')).toHaveText(stateMessages[state])
  await page.mouse.move(0, 0)
  if (state === 'hover') await button.hover()
  return page.screenshot({ fullPage: true, animations: 'disabled' })
}

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  for (const state of ['idle', 'hover', 'success', 'error'] as const) {
    test(`original layout with accessibility and font normalization: ${viewport.width}px, ${state}`, async ({
      page,
    }, info) => {
      await page.setViewportSize(viewport)
      await mockAPI(page, state === 'error' ? 500 : 200, state === 'error' ? { detail: failure } : { message: success })
      // Keep the original fixture unchanged; explicitly apply only the documented
      // contrast, responsive status and inherited button font to the reference.
      // Do not apply Preflight here: the reference retains the original box model.
      // Both versions render in this browser, so fonts/OS cannot skew the comparison.
      await page.route('**/__reference__', (route) =>
        route.fulfill({
          contentType: 'text/html; charset=utf-8',
          // The original fixture has no charset; WebKit needs it in this mock.
          body: originalHTML.replace('<head>', '<head><meta charset="utf-8">'),
        }),
      )
      await page.route('**/static/style.css', (route) =>
        route.fulfill({
          contentType: 'text/css',
          body: `${originalCSS}\n${accessibilityCSS}\n${normalizationCSS}`,
        }),
      )
      await page.route('**/static/main.js', (route) =>
        route.fulfill({
          contentType: 'text/javascript',
          body: originalJS,
        }),
      )

      const before = await capture(page, '/__reference__', state)
      const after = await capture(page, '/', state)
      await info.attach('reference-with-a11y-and-font-adjustments', {
        body: before,
        contentType: 'image/png',
      })
      await info.attach('react', { body: after, contentType: 'image/png' })
      expect(
        after.equals(before),
        'Layout must match the reference with the documented accessibility and font changes',
      ).toBe(true)
    })
  }
}

test('requests the API only on click and recovers after a database error', async ({ page }) => {
  const methods: string[] = []
  await page.route('**/healthchecker', (route) => {
    methods.push(route.request().method())
    return route.fulfill(
      methods.length === 1 ? { status: 500, json: { detail: failure } } : { status: 200, json: { message: success } },
    )
  })
  await page.goto('/')
  const button = page.getByRole('button', { name: buttonName })
  await expect(button).toBeVisible()
  expect(methods).toEqual([])
  await expect(page.getByRole('status')).toBeEmpty()
  await button.click()
  await expect(page.getByRole('status')).toHaveText(`Помилка запиту: ${failure}`)
  await expect(page.getByRole('status')).toHaveClass('response error')
  await button.click()
  await expect(page.getByRole('status')).toHaveText(success)
  await expect(page.getByRole('status')).toHaveClass('response success')
  expect(methods).toEqual(['GET', 'GET'])
})

test('reports a network failure and allows retry', async ({ page }) => {
  await page.route('**/healthchecker', (route) => route.abort('failed'))
  await page.goto('/')
  await page.getByRole('button', { name: buttonName }).click()
  await expect(page.getByRole('status')).toContainText('Помилка запиту:')
  await expect(page.getByRole('status')).toHaveClass('response error')
  await page.unroute('**/healthchecker')
  await mockAPI(page, 200, { message: success })
  await page.getByRole('button', { name: buttonName }).click()
  await expect(page.getByRole('status')).toHaveText(success)
})

test('rejects HTML that violates the OpenAPI response literal', async ({ page }) => {
  const message = '<img src="missing" onerror="window.injected=true">'
  await mockAPI(page, 200, { message })
  await page.goto('/')
  await page.getByRole('button', { name: buttonName }).click()
  await expect(page.getByRole('status')).toHaveText('Помилка запиту: Невідома помилка')
  await expect(page.locator('#response img')).toHaveCount(0)
})

for (const [name, status, body] of [
  ['missing field', 200, { unexpected: true }],
  ['wrong field type', 200, { message: 42 }],
  ['wrong literal', 200, { message: 'Success' }],
  ['error payload with successful status', 200, { detail: failure }],
  ['invalid error detail', 500, { detail: 'private connection details' }],
  ['success payload with error status', 500, { message: success }],
  ['undocumented HTTP status', 201, { message: success }],
] as const) {
  test(`rejects contract violation: ${name}`, async ({ page }) => {
    await mockAPI(page, status, body)
    await page.goto('/')
    const button = page.getByRole('button', { name: buttonName })
    await button.click()
    await expect(page.getByRole('status')).toHaveText('Помилка запиту: Невідома помилка')
    await expect(page.getByRole('status')).toHaveClass('response error')
    await page.unroute('**/healthchecker')
    await mockAPI(page, 200, { message: success })
    await button.click()
    await expect(page.getByRole('status')).toHaveText(success)
  })
}

for (const [name, status, contentType, body] of [
  ['empty success', 200, 'application/json', ''],
  ['no content', 204, 'application/json', ''],
  ['invalid JSON', 200, 'application/json', '{'],
  ['HTML proxy error', 502, 'text/html', '<h1>Proxy error</h1>'],
] as const) {
  test(`handles ${name}`, async ({ page }) => {
    await page.route('**/healthchecker', (route) => route.fulfill({ status, contentType, body }))
    await page.goto('/')
    await page.getByRole('button', { name: buttonName }).click()
    await expect(page.getByRole('status')).toHaveText('Помилка запиту: Невідома помилка')
  })
}

test('renders the page before JavaScript without requesting the database', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false })
  try {
    const page = await context.newPage()
    const apiRequests: string[] = []
    page.on('request', (request) => {
      if (request.url().endsWith('/healthchecker')) apiRequests.push(request.url())
    })
    await page.goto('http://127.0.0.1:4173/')
    await expect(page.locator('.main-text')).toHaveText(title)
    await expect(page.getByRole('button', { name: buttonName })).toBeVisible()
    await expect(page.getByRole('status')).toBeEmpty()
    expect(apiRequests).toEqual([])
  } finally {
    await context.close()
  }
})

test('shows the second documented database error', async ({ page }) => {
  await mockAPI(page, 500, { detail: 'Database is not configured correctly' })
  await page.goto('/')
  await page.getByRole('button', { name: buttonName }).click()
  await expect(page.getByRole('status')).toHaveText('Помилка запиту: Database is not configured correctly')
})
