import type { NextConfig } from 'next'
import { PHASE_DEVELOPMENT_SERVER } from 'next/constants'

export default function config(phase: string): NextConfig {
  const shared: NextConfig = { turbopack: { root: process.cwd() } }
  if (phase === PHASE_DEVELOPMENT_SERVER) {
    return {
      ...shared,
      async rewrites() {
        return [
          {
            source: '/healthchecker',
            destination: 'http://127.0.0.1:8000/healthchecker',
          },
        ]
      },
    }
  }
  return { ...shared, output: 'export' }
}
