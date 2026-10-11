import { checkDatabase } from './generated/sdk.gen'
import type { HealthCheckResponse } from './generated/types.gen'
import { zHealthCheckError, zHealthCheckResponse } from './generated/zod.gen'

const HTTP_OK = 200
const HTTP_DATABASE_ERROR = 500

export async function checkHealth(): Promise<HealthCheckResponse> {
  const { data, error, response } = await checkDatabase({
    parseAs: 'json',
    cache: 'no-store',
  })

  if (response?.status === HTTP_OK && error === undefined) {
    // The SDK skips its validator for empty bodies. Check those here as well.
    const parsed = zHealthCheckResponse.safeParse(data)
    if (parsed.success) return parsed.data
  }
  if (response?.status === HTTP_DATABASE_ERROR) {
    // SDK response validators apply to success responses, not HTTP errors.
    const parsed = zHealthCheckError.safeParse(error)
    if (parsed.success) throw new Error(parsed.data.detail)
  }
  if (!response && error instanceof Error) throw error
  // Never display raw Zod issues, invalid payloads, or proxy error pages.
  throw new Error('Невідома помилка')
}
