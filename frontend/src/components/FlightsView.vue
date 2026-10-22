<script setup>
import { computed, ref } from 'vue'
import { STATUS_LABEL } from '../constants.js'
import { actions, state } from '../store.js'
import jetstarLogo from '../assets/airlines/jetstar.svg'
import virginLogo from '../assets/airlines/virgin-australia.svg'
import qatarLogo from '../assets/airlines/qatar.svg'
import emiratesLogo from '../assets/airlines/emirates.svg'
import singaporeLogo from '../assets/airlines/singapore.svg'
import malaysiaLogo from '../assets/airlines/malaysia.svg'
import chinaSouthernLogo from '../assets/airlines/china-southern.svg'
import fijiLogo from '../assets/airlines/fiji.svg'

const filter = ref('all')
const chips = [
  ['all', 'All'],
  ['upcoming', 'Upcoming'],
  ['cleaning', 'Cleaning'],
  ['done', 'Done'],
]

// Airline logo badge, read off the flight number prefix (works even for flights added by
// hand, which may not have the airline name field filled in).
const AIRLINE_LOGO = {
  JQ: jetstarLogo,
  VA: virginLogo,
  QR: qatarLogo,
  EK: emiratesLogo,
  SQ: singaporeLogo,
  MH: malaysiaLogo,
  CZ: chinaSouthernLogo,
  FJ: fijiLogo,
}
function airlineCode(flightNo) {
  return (flightNo || '').match(/^[A-Za-z]{2,3}/)?.[0]?.toUpperCase()
}
function airlineLogo(flightNo) {
  const code = airlineCode(flightNo)
  return code ? AIRLINE_LOGO[code] : undefined
}

// The Flight mix cards (international / Jetstar / Virgin) double as a second filter, on top of
// the status chips. Clicking an active one again clears it. Mutually exclusive with the hour
// filter below -- picking one clears the other.
const mixFilter = ref(null)
// International takes priority: an international Jetstar/Virgin flight counts under
// "international", not under its airline, so each flight lands in exactly one bucket.
const MIX_PREDICATES = {
  international: (f) => f.international,
  jetstar: (f) => !f.international && airlineCode(f.flight_no) === 'JQ',
  virgin: (f) => !f.international && airlineCode(f.flight_no) === 'VA',
}
function toggleMix(key) {
  mixFilter.value = mixFilter.value === key ? null : key
  hourFilter.value = null // mix and hour filters are mutually exclusive
}

// The Arrivals per hour bars are a third filter: click an hour to see just what lands then.
const hourFilter = ref(null)
function toggleHour(hour) {
  hourFilter.value = hourFilter.value === hour ? null : hour
  mixFilter.value = null // mix and hour filters are mutually exclusive
}

// The status chips (All / Upcoming / Cleaning / Done) always count the whole shift, whatever
// Intl/JQ/VA or hour filter is on. Tapping one clears those other filters, so the list it shows
// still matches its count.
const STATUS_PREDICATES = {
  all: () => true,
  upcoming: (f) => ['sched', 'landed'].includes(f.status),
  cleaning: (f) => f.status === 'cleaning',
  done: (f) => f.status === 'done',
}
const list = computed(() => {
  let items = state.flights.filter(STATUS_PREDICATES[filter.value] || STATUS_PREDICATES.all)
  if (mixFilter.value) items = items.filter(MIX_PREDICATES[mixFilter.value])
  if (hourFilter.value !== null) items = items.filter((f) => f.eta && Number(f.eta.slice(0, 2)) === hourFilter.value)
  return items
})
function chipCount(key) {
  return state.flights.filter(STATUS_PREDICATES[key]).length
}
// A chip only looks selected while it alone decides the list.
function chipPressed(key) {
  return filter.value === key && !mixFilter.value && hourFilter.value === null
}
function selectChip(key) {
  filter.value = key
  mixFilter.value = null
  hourFilter.value = null
}

/** Arrivals per hour, so the leading hand can see when aircraft bunch up. The Night chart starts
 * at 15:00 (nobody is cleaning before the first crew starts) and runs past midnight to the end of
 * the shift, so hours are ordered from the chart's start rather than 0-23. */
const CHART_FROM = { morning: 6, night: 15 }
const chart = computed(() => {
  const from = CHART_FROM[state.shift] ?? 0
  const offset = (hour) => (hour - from + 24) % 24
  const shiftLen = state.shift === 'night' ? 15 : 24 // night chart: 15:00 to 05:59
  const flights = state.flights.filter((f) => f.eta && !f.cancelled && offset(Number(f.eta.slice(0, 2))) < shiftLen)
  if (!flights.length) return []
  const byHour = {}
  for (const f of flights) {
    const hour = Number(f.eta.slice(0, 2))
    byHour[hour] = (byHour[hour] || 0) + 1
  }
  const offsets = Object.keys(byHour).map((h) => offset(Number(h)))
  const lo = Math.min(...offsets)
  const hi = Math.max(...offsets)
  const max = Math.max(...Object.values(byHour))
  const cols = []
  let peakFound = false
  for (let o = lo; o <= hi; o++) {
    const hour = (from + o) % 24
    const n = byHour[hour] || 0
    const peak = !peakFound && n > 0 && n === max
    if (peak) peakFound = true // only the first hour to hit the max is "the" peak, even on a tie
    cols.push({
      hour,
      n,
      peak,
      height: n ? 8 + Math.round((n / max) * 34) : 2,
      label: `${String(hour).padStart(2, '0')}:00`,
    })
  }
  return cols
})

// Everything except the gate, which the template renders separately so the gate number can be bold.
function subLead(f) {
  return [f.airline, f.origin && `from ${f.origin}`, f.rego && `Rego ${f.rego}`].filter(Boolean).join(', ')
}

/** How the shift's arrivals break down by airline / international, cancelled flights excluded. */
const mix = computed(() => {
  const flights = state.flights.filter((f) => !f.cancelled)
  return {
    international: flights.filter(MIX_PREDICATES.international).length,
    jetstar: flights.filter(MIX_PREDICATES.jetstar).length,
    virgin: flights.filter(MIX_PREDICATES.virgin).length,
  }
})

/** One line under the toolbar: what the filter shows, and when flights were last updated. */
const dataNote = computed(() => {
  const d = state.flightData
  if (!d) return ''
  if (!d.configured) return 'Flight data is not set up. Add FLIGHT_API_KEY to backend/.env.'
  const parts = [d.filter_text]
  if (d.last_sync_at) {
    const when = new Date(d.last_sync_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    parts.push(d.last_ok ? `updated ${when}` : `last update failed at ${when}`)
  }
  parts.push(`${d.calls_this_month} of ${d.monthly_limit} result sets used this month`)
  return parts.join('. ')
})
</script>

<template>
  <div class="toolbar">
    <div class="chips" style="flex: 1; margin: 0; padding: 0">
      <button v-for="c in chips" :key="c[0]" class="chip" :aria-pressed="chipPressed(c[0])" @click="selectChip(c[0])">
        {{ c[1] }} ({{ chipCount(c[0]) }})
      </button>
    </div>
    <button
      class="btn2"
      :disabled="state.syncing || (state.flightData && !state.flightData.configured)"
      @click="actions.syncFlights()"
    >
      {{ state.syncing ? 'Updating...' : 'Update' }}
    </button>
  </div>
  <p v-if="dataNote" class="note-line syncrow">{{ dataNote }}</p>

  <section v-if="chart.length" class="load" aria-label="Arrivals per hour">
    <div class="loadhead">
      <h2>Arrivals per hour</h2>
      <div class="mixpills">
        <button :aria-pressed="mixFilter === 'international'" @click="toggleMix('international')">{{ mix.international }} Intl</button>
        <button :aria-pressed="mixFilter === 'jetstar'" @click="toggleMix('jetstar')">{{ mix.jetstar }} JQ</button>
        <button :aria-pressed="mixFilter === 'virgin'" @click="toggleMix('virgin')">{{ mix.virgin }} VA</button>
      </div>
    </div>
    <div class="hcs">
      <button
        v-for="c in chart"
        :key="c.hour"
        class="hc"
        :class="{ peak: c.peak }"
        :aria-pressed="hourFilter === c.hour"
        @click="toggleHour(c.hour)"
      >
        <b>{{ c.n || '' }}</b>
        <i :style="{ height: c.height + 'px' }"></i>
        <span>{{ c.label }}</span>
      </button>
    </div>
  </section>

  <div v-if="!state.flights.length" class="empty">
    <p>No flights for this shift yet. Tap Update to pull the arrivals you cover.</p>
  </div>
  <div v-else-if="!list.length" class="empty"><p>Nothing in this list.</p></div>
  <div v-else class="strips">
    <button v-for="f in list" :key="f.id" class="strip" :class="'s-' + f.status" @click="actions.openFlight(f.id)">
      <div class="t">
        <b>{{ f.eta || '--:--' }}</b>
        <small v-if="f.delay_minutes" :class="f.delay_minutes > 0 ? 'late' : 'early'">
          {{ f.delay_minutes > 0 ? '+' : '' }}{{ f.delay_minutes }} min
        </small>
      </div>
      <div class="m">
        <strong>
          <span v-if="airlineLogo(f.flight_no)" class="allogo"
            ><img :src="airlineLogo(f.flight_no)" :alt="f.airline || airlineCode(f.flight_no)"
          /></span>
          {{ f.flight_no }}<i v-if="f.international" class="intl">Intl</i>
        </strong>
        <span v-if="subLead(f)">{{ subLead(f) }}</span>
        <span v-else>No details</span>
      </div>
      <div class="r">
        <em>{{ STATUS_LABEL[f.status] }}</em>
        <small>
          <span v-if="f.gate" class="gatechip">Gate {{ f.gate }}</span>
          <template v-if="f.gate && f.minutes !== null">, </template>
          <template v-if="f.minutes !== null">{{ f.minutes }} min</template>
        </small>
      </div>
    </button>
  </div>
</template>
