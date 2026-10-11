import Link from 'next/link'

export default function NotFound() {
  return (
    <main>
      <h1 className="main-text">Сторінку не знайдено</h1>
      <p>Помилка 404. Перевірте адресу сторінки.</p>
      <Link href="/">На головну</Link>
    </main>
  )
}
