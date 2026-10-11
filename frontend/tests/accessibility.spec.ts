import { expect, type Page, test } from '@playwright/test'

import { expectAccessible } from './accessibility'

const buttonName = 'Перевірити БД'
const success = 'Welcome to FastAPI!'
const failure = 'Помилка запиту: Error connecting to the database'
const loading = 'Перевіряємо з’єднання з БД…'

const stateMessages = { idle: '', hover: '', loading, success, error: failure }
const settledMessages = { ...stateMessages, loading: success }

async function prepareState(page: Page, state: keyof typeof stateMessages) {
  await page.goto('/')
  const button = page.getByRole('button', { name: buttonName })
  if (state === 'hover') await button.hover()
  if (state !== 'idle' && state !== 'hover') await button.click()
}

test('exported 404 page is accessible', async ({ page }, info) => {
  await page.goto('/404.html')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Сторінку не знайдено')
  await expectAccessible(page, info)
  await page.getByRole('link', { name: 'На головну' }).click()
  await expect(page.getByRole('button', { name: buttonName })).toBeVisible()
})

for (const width of [1440, 320]) {
  for (const state of ['idle', 'hover', 'loading', 'success', 'error'] as const) {
    test(`axe: ${width}px, ${state}`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 900 })
      let release = () => {}
      const pending = new Promise<void>((resolve) => {
        release = resolve
      })
      await page.route('**/healthchecker', async (route) => {
        if (state === 'loading') await pending
        await route.fulfill(
          state === 'error'
            ? {
                status: 500,
                json: { detail: 'Error connecting to the database' },
              }
            : { status: 200, json: { message: success } },
        )
      })
      try {
        await prepareState(page, state)
        await expect(page.getByRole('status')).toHaveText(stateMessages[state])
        await expectAccessible(page, info)
      } finally {
        release()
      }
      await expect(page.getByRole('status')).toHaveText(settledMessages[state])
    })
  }
}

for (const key of ['Enter', 'Space']) {
  test(`keyboard ${key}: keeps focus, blocks duplicate requests and recovers`, async ({ page }) => {
    let requests = 0
    let release = () => {}
    const pending = new Promise<void>((resolve) => {
      release = resolve
    })
    await page.route('**/healthchecker', async (route) => {
      requests++
      if (requests === 1) {
        await pending
        await route.fulfill({
          status: 500,
          json: { detail: 'Error connecting to the database' },
        })
      } else {
        await route.fulfill({ status: 200, json: { message: success } })
      }
    })
    try {
      await page.goto('/')
      const button = page.getByRole('button', { name: buttonName })
      await page.keyboard.press('Tab')
      await expect(button).toBeFocused()
      await expect(button).toHaveCSS('outline-style', 'solid')
      await expect(button).toHaveCSS('outline-width', '3px')
      await page.keyboard.press(key)
      await expect(page.getByRole('status')).toHaveText(loading)
      await expect(button).toBeDisabled()
      await expect(button).toHaveAttribute('aria-busy', 'true')
      await expect(button).toBeFocused()
      await page.keyboard.press(key)
      expect(requests).toBe(1)
      release()
      await expect(page.getByRole('status')).toHaveText(failure)
      await expect(button).toBeEnabled()
      await expect(button).toBeFocused()
      await page.keyboard.press(key)
      await expect(page.getByRole('status')).toHaveText(success)
      await expect(button).toBeEnabled()
      await expect(button).toHaveAttribute('aria-busy', 'false')
      await expect(button).toBeFocused()
      expect(requests).toBe(2)
    } finally {
      release()
    }
  })
}

test('document has semantic structure, language and zoom-friendly metadata', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('html')).toHaveAttribute('lang', 'uk')
  await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
  await expect(page.locator('meta[name="viewport"]')).toHaveAttribute(
    'content',
    'width=device-width, initial-scale=1, viewport-fit=cover',
  )
  await expect(page.locator('meta[name="format-detection"]')).toHaveAttribute(
    'content',
    'telephone=no,email=no,address=no,date=no',
  )
  await expect(page.getByRole('main')).toHaveCount(1)
  await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)
  await expect(page.getByRole('main').getByRole('heading', { level: 1 })).toHaveText(
    'Домашня робота: Введення в Docker та контейнеризацію',
  )
  await expect(page.getByRole('status')).toHaveAttribute('aria-live', 'polite')
  await expect(page.getByRole('status')).toHaveAttribute('aria-atomic', 'true')
})

test('320px layout accommodates 200% text size without clipping', async ({ page }, info) => {
  await page.setViewportSize({ width: 320, height: 900 })
  await page.route('**/healthchecker', (route) =>
    route.fulfill({
      status: 500,
      json: { detail: 'Error connecting to the database' },
    }),
  )
  await page.goto('/')
  // Simulate a larger browser default font, independently of CSS pixel zoom.
  await page.addStyleTag({ content: 'html { font-size: 200%; }' })
  await expect(page.getByRole('heading', { level: 1 })).toHaveCSS('font-size', '48px')
  await page.getByRole('button', { name: buttonName }).click()
  await expect(page.getByRole('status')).toHaveText(failure)
  expect(
    await page.evaluate(() => ({
      width: document.documentElement.clientWidth,
      contentWidth: document.documentElement.scrollWidth,
    })),
  ).toEqual({ width: 320, contentWidth: 320 })
  expect(
    await page.getByRole('status').evaluate((element) => {
      const range = document.createRange()
      range.selectNodeContents(element)
      const text = range.getBoundingClientRect()
      const box = element.getBoundingClientRect()
      return text.top >= box.top && text.bottom <= box.bottom && text.left >= box.left && text.right <= box.right
    }),
  ).toBe(true)
  await expectAccessible(page, info)
})
