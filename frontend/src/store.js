// Small shared store built on Vue's reactive(). The server is the source of truth: every change is sent to the
// API and the screen then reloads the current day, so several phones always agree.
import { computed, reactive } from 'vue'
import { api, getToken, setToken, setUnauthorizedHandler } from './api.js'
import { THEME_COLOR } from './constants.js'
import { todayStr } from './lib/time.js'

const SHIFT_KEY = 'turnaround.shift'

export const state = reactive({
  ready: false,
  user: null,
  shift: localStorage.getItem(SHIFT_KEY) === 'night' ? 'night' : 'morning',
  date: todayStr(),
  tab: 'flights',
  staff: [],
  roster: { entries: [], has_plan: false },
  flights: [],
  flightData: null,
  syncing: false,
  report: null,
  openFlightId: null,
  toastMsg: '',
})

/** People on the roster who are working today. */
export const onDuty = computed(() => state.roster.entries.filter((e) => e.shift_type))

export const sheetOpen = computed(
  () => state.openFlightId !== null && state.flights.some((f) => f.id === state.openFlightId),
)

let toastTimer = null
export function toast(message) {
  state.toastMsg = message
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    state.toastMsg = ''
  }, 2800)
}

function applyTheme() {
  document.documentElement.dataset.shift = state.shift
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', THEME_COLOR[state.shift])
}

/** The flight data note (filter, last update, usage). Failures are ignored: it is only a hint. */
async function loadFlightData() {
  try {
    state.flightData = await api.flightData.status()
  } catch {
    /* keep the previous value */
  }
}

let refreshSeq = 0
/** Reload staff, roster and flights (and the report when it is open) for the chosen date and shift. */
export async function refreshAll({ silent = false } = {}) {
  if (!state.user) return
  const seq = ++refreshSeq
  const { date, shift } = state
  try {
    const jobs = [api.staff.list(shift), api.roster.get(date, shift), api.flights.list(date, shift)]
    if (state.tab === 'report') jobs.push(api.report(date, shift))
    const [staff, roster, flights, report] = await Promise.all(jobs)
    if (seq !== refreshSeq) return // the shift or date changed while this was loading
    state.staff = staff
    state.roster = roster
    state.flights = flights
    if (report) state.report = report
    if (state.tab === 'flights') loadFlightData()
  } catch (error) {
    if (!silent && error.status !== 401 && seq === refreshSeq) toast(error.message)
  }
}

/** Run an API call, then resync the screen. Returns undefined if the call failed. */
async function run(fn, okMessage) {
  try {
    const result = await fn()
    await refreshAll()
    if (okMessage) toast(okMessage)
    return result ?? true
  } catch (error) {
    if (error.status !== 401) toast(error.message)
    await refreshAll({ silent: true })
    return undefined
  }
}

let pollTimer = null
function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => {
    if (!document.hidden && state.user) refreshAll({ silent: true })
  }, 15000)
}
function stopPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
}

function resetScreen() {
  state.openFlightId = null
  state.staff = []
  state.roster = { entries: [], has_plan: false }
  state.flights = []
  state.report = null
  state.flightData = null
}

export const actions = {
  async login(username, password) {
    const result = await api.login(username, password)
    setToken(result.access_token)
    state.user = result.user
    applyTheme()
    await refreshAll()
    startPolling()
  },

  logout() {
    setToken(null)
    state.user = null
    stopPolling()
    resetScreen()
  },

  setShift(shift) {
    if (state.shift === shift) return
    state.shift = shift
    localStorage.setItem(SHIFT_KEY, shift)
    resetScreen()
    applyTheme()
    refreshAll()
  },

  setDate(date) {
    if (!date || date === state.date) return
    state.date = date
    resetScreen()
    refreshAll()
  },

  setTab(tab) {
    state.tab = tab
    if (tab === 'report') refreshAll()
  },

  // ---- flights ----
  openFlight(id) {
    state.openFlightId = id
  },
  closeSheet() {
    state.openFlightId = null
  },
  patchFlight: (id, body) => run(() => api.flights.patch(id, body)),
  async deleteFlight(id) {
    const ok = await run(() => api.flights.remove(id), 'Flight deleted')
    if (ok) state.openFlightId = null
  },
  saveAssignments: (id, rows) => run(() => api.flights.setAssignments(id, rows)),
  startFlight: (id) => run(() => api.flights.start(id)),
  async finishFlight(id) {
    const flight = await run(() => api.flights.finish(id))
    if (flight && flight.minutes !== undefined) toast(`Finished in ${flight.minutes} min`)
  },
  reopenFlight: (id) => run(() => api.flights.reopen(id)),
  setTimes: (id, body) => run(() => api.flights.setTimes(id, body)),
  signFlight: (id, name, image) => run(() => api.flights.sign(id, name, image), 'Signature saved'),
  unsignFlight: (id) => run(() => api.flights.unsign(id)),

  async syncFlights() {
    if (state.syncing) return
    state.syncing = true
    try {
      const r = await api.flightData.sync(state.date, state.shift)
      const parts = []
      if (r.created) parts.push(`${r.created} new`)
      if (r.updated) parts.push(`${r.updated} changed`)
      toast(parts.length ? `Flights updated: ${parts.join(', ')}` : 'Flights are up to date')
    } catch (error) {
      if (error.status !== 401) toast(error.message)
    } finally {
      state.syncing = false
      await refreshAll({ silent: true })
      loadFlightData()
    }
  },

  // ---- roster and team ----
  rosterPatch: (staffId, body, okMessage) =>
    run(() => api.roster.patch(staffId, state.date, state.shift, body), okMessage).then((r) => (r === true ? undefined : r)),
  async importPreview(text) {
    try {
      return await api.roster.importPreview(state.shift, text)
    } catch (error) {
      toast(error.message)
      return undefined
    }
  },
  async importApply(text) {
    const result = await run(() => api.roster.importApply(state.shift, text))
    if (result && result.days) {
      toast(`Imported ${result.days} day${result.days > 1 ? 's' : ''}` + (result.created_staff ? `, ${result.created_staff} new people` : ''))
    }
    return result
  },
  async importPreviewFile(file) {
    try {
      return await api.roster.importPreviewFile(state.shift, file)
    } catch (error) {
      toast(error.message)
      return undefined
    }
  },
  async importApplyFile(file) {
    const result = await run(() => api.roster.importApplyFile(state.shift, file))
    if (result && result.days) {
      toast(`Imported ${result.days} day${result.days > 1 ? 's' : ''}` + (result.created_staff ? `, ${result.created_staff} new people` : ''))
    }
    return result
  },
  patchStaff: (id, body) => run(() => api.staff.patch(id, body)),
  removeStaff: (id) => run(() => api.staff.remove(id), 'Removed from team'),

  async loadReport() {
    try {
      state.report = await api.report(state.date, state.shift)
    } catch (error) {
      if (error.status !== 401) toast(error.message)
    }
  },
}

export async function init() {
  setUnauthorizedHandler(() => {
    if (state.user) {
      actions.logout()
      toast('Please sign in again')
    }
  })
  applyTheme()
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && state.user) refreshAll({ silent: true })
  })
  if (getToken()) {
    try {
      state.user = await api.me()
      await refreshAll()
      startPolling()
    } catch (error) {
      if (error.status === 401) setToken(null)
      else toast(error.message)
    }
  }
  state.ready = true
}
