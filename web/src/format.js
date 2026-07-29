// Formatting helpers.

// published comes as RFC 822 ("Wed, 29 Jul 2026 01:53:15 +0000" or "... GMT").
export function parseDate(value) {
  if (!value) return null
  const d = new Date(value)
  return isNaN(d.getTime()) ? null : d
}

export function formatDate(value) {
  const d = parseDate(value)
  if (!d) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// First <img src> inside a content HTML string (used by Awwwards thumbnails).
export function extractImage(content) {
  if (!content) return null
  const m = content.match(/<img[^>]+src="([^"]+)"/)
  return m ? m[1] : null
}

export function formatShort(value) {
  const d = parseDate(value)
  if (!d) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function isToday(value) {
  const d = parseDate(value)
  if (!d) return false
  const n = new Date()
  return d.getFullYear() === n.getFullYear() && d.getMonth() === n.getMonth() && d.getDate() === n.getDate()
}
