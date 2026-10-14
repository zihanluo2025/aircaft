export const pad = (n) => String(n).padStart(2, '0')

/** Local calendar date as YYYY-MM-DD. */
export function todayStr(d = new Date()) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** Local HH:MM for an ISO timestamp from the API. */
export function hhmm(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** ISO (UTC) timestamp for a local date and HH:MM, used when the leading hand corrects a time. */
export function isoFromLocal(dateStr, time) {
  const [y, m, d] = dateStr.split('-').map(Number)
  const [h, min] = time.split(':').map(Number)
  return new Date(y, m - 1, d, h, min).toISOString()
}

/** Minutes and seconds, like 07:05. */
export function fmtElapsed(ms) {
  const s = Math.max(0, Math.floor(ms / 1000))
  return `${pad(Math.floor(s / 60))}:${pad(s % 60)}`
}
