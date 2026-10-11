'use client'

import { useState } from 'react'

import { Button } from '@base-ui/react/button'

import { checkHealth } from './api/health'

type Result = {
  kind: 'idle' | 'loading' | 'success' | 'error'
  message: string
}

export function App() {
  const [result, setResult] = useState<Result>({ kind: 'idle', message: '' })

  async function handleCheck() {
    if (result.kind === 'loading') return
    setResult({ kind: 'loading', message: 'Перевіряємо з’єднання з БД…' })
    try {
      const { message } = await checkHealth()
      setResult({ kind: 'success', message })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Невідома помилка'
      setResult({
        kind: 'error',
        message: `Помилка запиту: ${message.replace(/^Error: /, '')}`,
      })
    }
  }

  return (
    <main>
      <h1 className="main-text">Домашня робота: Введення в Docker та контейнеризацію</h1>
      <Button
        type="button"
        className="check-button"
        disabled={result.kind === 'loading'}
        focusableWhenDisabled
        aria-busy={result.kind === 'loading'}
        onClick={() => void handleCheck()}
      >
        Перевірити БД
      </Button>
      <div
        id="response"
        className={result.kind === 'idle' ? 'response' : `response ${result.kind}`}
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        {result.message}
      </div>
    </main>
  )
}
