import { expect, test } from '@playwright/test'

import { expectAccessible } from './accessibility'

test('built React page reaches the real API and Percona', async ({ page }, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  const responsePromise = page.waitForResponse((response) => response.url().endsWith('/healthchecker'))
  await page.getByRole('button', { name: 'Перевірити БД' }).click()
  const response = await responsePromise
  expect(response.status()).toBe(200)
  expect(await response.json()).toEqual({ message: 'Welcome to FastAPI!' })
  await expect(page.getByRole('status')).toHaveText('Welcome to FastAPI!')
  await expect(page.getByRole('status')).toHaveClass('response success')
  expect(errors).toEqual([])
  await expectAccessible(page, info)
})
