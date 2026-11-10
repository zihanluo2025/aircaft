// 人员按实际的 Start / End 时间分组，不再用 Early / Late / All day 这种固定分类。

/** "15:45–22:15", or '' when the roster has no times for them. */
export const timeSlot = (e) => (e && e.rstart && e.rend ? `${e.rstart}–${e.rend}` : '')

/** The planned times, for "Planned ..." notes and "Back to plan". */
export const plannedSlot = (e) => (e && e.planned_rstart && e.planned_rend ? `${e.planned_rstart}–${e.planned_rend}` : '')

/** Distinct Start–End pairs among people on duty, in the order given (the API sorts by start time). */
export function todaySlots(entries) {
  const seen = new Map()
  for (const e of entries) {
    const slot = timeSlot(e)
    if (e.shift_type && slot && !seen.has(slot)) seen.set(slot, [e.rstart, e.rend])
  }
  return [...seen.entries()].map(([label, times]) => ({ label, times }))
}

// Used to call someone in when nobody on the day has times yet -- the shift's full window.
export const DEFAULT_TIMES = { morning: ['06:00', '13:00'], night: ['13:00', '06:00'] }
