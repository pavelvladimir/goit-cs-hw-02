import type { ReactNode } from 'react'

import { DirectionProvider } from '@base-ui/react/direction-provider'
import type { Metadata, Viewport } from 'next'
import '../style.css'

const locale = { language: 'uk', direction: 'ltr' } as const

export const metadata: Metadata = {
  title: 'Домашня робота: Введення в Docker та контейнеризацію',
  other: {
    'format-detection': 'telephone=no,email=no,address=no,date=no',
  },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
}

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang={locale.language} dir={locale.direction}>
      <body>
        <DirectionProvider direction={locale.direction}>{children}</DirectionProvider>
      </body>
    </html>
  )
}
