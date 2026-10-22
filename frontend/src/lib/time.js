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

// 班次判断一律用阿德莱德时间（见 CLAUDE.md），不用浏览器所在时区。
export const AIRPORT_TZ = 'Australia/Adelaide'
const SHIFT_START = { morning: 6 * 60, night: 13 * 60 }

const toMinutes = (hm) => {
  const [h, m] = hm.split(':').map(Number)
  return h * 60 + m
}

/** Airport-local calendar date (YYYY-MM-DD) and minutes since midnight for a moment in time. */
export function airportNow(ms = Date.now()) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: AIRPORT_TZ,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    })
      .formatToParts(new Date(ms))
      .map((p) => [p.type, p.value]),
  )
  return { date: `${parts.year}-${parts.month}-${parts.day}`, minutes: Number(parts.hour) * 60 + Number(parts.minute) }
}

/** The shift running at a moment: Morning 06:00-13:00, otherwise Night; 00:00-06:00 belongs to the previous day's Night. */
export function currentShift(ms = Date.now()) {
  const { date, minutes } = airportNow(ms)
  if (minutes >= SHIFT_START.morning && minutes < SHIFT_START.night) return { date, shift: 'morning', minutes }
  if (minutes >= SHIFT_START.night) return { date, shift: 'night', minutes }
  const [y, m, d] = date.split('-').map(Number)
  const prev = new Date(Date.UTC(y, m - 1, d - 1))
  return { date: prev.toISOString().slice(0, 10), shift: 'night', minutes }
}

/** Whether a rostered start (HH:MM) has been reached, counted from the shift's own start so a
 * night shift that runs past midnight still compares correctly. */
export function hasStarted(rstart, shift, nowMinutes) {
  const begin = SHIFT_START[shift]
  return (toMinutes(rstart) - begin + 1440) % 1440 <= (nowMinutes - begin + 1440) % 1440
}
