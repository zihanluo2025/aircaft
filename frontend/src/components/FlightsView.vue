<script setup>
import { computed, ref } from 'vue'
import { STATUS_LABEL } from '../constants.js'
import { hhmm } from '../lib/time.js'
import { actions, state } from '../store.js'
import jetstarLogo from '../assets/airlines/jetstar.svg'
import virginLogo from '../assets/airlines/virgin-australia.svg'
import qatarLogo from '../assets/airlines/qatar.svg'
import emiratesLogo from '../assets/airlines/emirates.svg'
import singaporeLogo from '../assets/airlines/singapore.svg'
import malaysiaLogo from '../assets/airlines/malaysia.svg'
import chinaSouthernLogo from '../assets/airlines/china-southern.svg'
import fijiLogo from '../assets/airlines/fiji.svg'
import airNewZealandLogo from '../assets/airlines/air-new-zealand.png'

const scope = ref('following')
const DEFAULT_GROUP = 'international'
const groupFilter = ref(DEFAULT_GROUP)
const hourFilter = ref(null)
const groups = [
  ['international', 'Intl'],
  ['jetstar', 'JQ'],
  ['virgin', 'VA'],
]
const followSaving = ref(new Set())

async function toggleFollow(flight) {
  if (followSaving.value.has(flight.id)) return
  followSaving.value.add(flight.id)
  try {
    await actions.patchFlight(flight.id, { followed: !flight.followed })
  } finally {
    followSaving.value.delete(flight.id)
  }
}

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
  NZ: airNewZealandLogo,
}
function airlineCode(flightNo) {
  return (flightNo || '').match(/^[A-Za-z]{2,3}/)?.[0]?.toUpperCase()
}
function airlineLogo(flightNo) {
  const code = airlineCode(flightNo)
  return code ? AIRLINE_LOGO[code] : undefined
}

// International arrivals belong to Intl, including those operated by JQ or VA.
const GROUP_PREDICATES = {
  international: (f) => f.international,
  jetstar: (f) => !f.international && airlineCode(f.flight_no) === 'JQ',
  virgin: (f) => !f.international && airlineCode(f.flight_no) === 'VA',
}
const arrivalHour = (f) => (f.eta ? Number(f.eta.slice(0, 2)) : null)
const hourLabel = (hour, minutes = '00') => `${String(hour).padStart(2, '0')}:${minutes}`
const following = computed(() => state.flights.filter((f) => f.followed))
const scopedFlights = computed(() => scope.value === 'following' ? following.value : state.flights)
const groupedFlights = computed(() => scopedFlights.value.filter(GROUP_PREDICATES[groupFilter.value]))

function matchesHour(flight) {
  return hourFilter.value === null || arrivalHour(flight) === hourFilter.value
}

const statusFlights = computed(() => ({
  cleaning: state.flights.filter((f) => f.status === 'cleaning'),
  done: state.flights.filter((f) => f.status === 'done'),
}))
const activeStatusFlights = computed(() => statusFlights.value[scope.value])
const groupCounts = computed(() => {
  const flights = scopedFlights.value.filter(matchesHour)
  return Object.fromEntries(groups.map(([key]) => [key, flights.filter(GROUP_PREDICATES[key]).length]))
})
const list = computed(() => activeStatusFlights.value ?? groupedFlights.value.filter(matchesHour))
const hasFilters = computed(() => groupFilter.value !== DEFAULT_GROUP || hourFilter.value !== null)
const resultLabel = computed(() => {
  const count = list.value.length
  if (activeStatusFlights.value) return `${STATUS_LABEL[scope.value]} · ${count} ${count === 1 ? 'flight' : 'flights'}`
  const selectedHour = hourFilter.value
  const timeRange = selectedHour === null ? '' : ` · ${hourLabel(selectedHour)}–${hourLabel(selectedHour, '59')}`
  return `${count} ${count === 1 ? 'flight' : 'flights'}${timeRange}`
})

function toggleHour(hour) {
  hourFilter.value = hourFilter.value === hour ? null : hour
}

function clearFilters() {
  groupFilter.value = DEFAULT_GROUP
  hourFilter.value = null
}

// Order populated hours from the shift start so night hours run across midnight.
const CHART_FROM = { morning: 6, night: 13 }
const chart = computed(() => {
  const from = CHART_FROM[state.shift] ?? 0
  const offset = (hour) => (hour - from + 24) % 24
  const byHour = new Map()
  for (const flight of groupedFlights.value) {
    const hour = arrivalHour(flight)
    if (hour !== null) byHour.set(hour, (byHour.get(hour) || 0) + 1)
  }

  const max = Math.max(0, ...byHour.values())
  return [...byHour]
    .sort(([a], [b]) => offset(a) - offset(b))
    .map(([hour, n]) => ({
      hour,
      n,
      height: 8 + Math.round((n / max) * 34),
      label: hourLabel(hour),
    }))
})

// Everything except the gate, which the template renders separately so the gate number can be bold.
function subLead(f) {
  return [f.airline, f.origin && `from ${f.origin}`, f.rego && `Rego ${f.rego}`].filter(Boolean).join(', ')
}

/** One line under the toolbar: when flights were last updated, and how much of the quota is used. */
const dataNote = computed(() => {
  const d = state.flightData
  if (!d) return ''
  if (!d.configured) return 'Flight data is not set up. Add FLIGHT_API_KEY to backend/.env.'
  const parts = []
  if (d.last_sync_at) {
    const when = hhmm(d.last_sync_at)
    parts.push(d.last_ok ? `Updated ${when}` : `Last update failed at ${when}`)
  }
  parts.push(`${d.calls_this_month} of ${d.monthly_limit} result sets used this month`)
  return parts.join('. ')
})
</script>

<template>
  <div class="flight-toolbar">
    <div class="flight-views">
      <div class="flight-view-group" role="group" aria-label="Flight scope">
        <button type="button" class="chip" :aria-pressed="scope === 'following'" @click="scope = 'following'">
          Following ({{ following.length }})
        </button>
        <button type="button" class="chip" :aria-pressed="scope === 'all'" @click="scope = 'all'">
          All flights ({{ state.flights.length }})
        </button>
      </div>
      <div class="flight-view-group" role="group" aria-label="Cleaning status">
        <button
          v-for="(flights, status) in statusFlights"
          :key="status"
          type="button"
          class="chip"
          :aria-pressed="scope === status"
          @click="scope = status"
        >
          {{ STATUS_LABEL[status] }} ({{ flights.length }})
        </button>
      </div>
    </div>
    <button
      type="button"
      class="btn2 flight-update"
      :disabled="state.syncing || (state.flightData && !state.flightData.configured)"
      @click="actions.syncFlights()"
    >
      {{ state.syncing ? 'Updating...' : 'Update' }}
    </button>
  </div>
  <p v-if="dataNote" class="note-line flight-sync-note">{{ dataNote }}</p>

  <section v-if="state.flights.length && !activeStatusFlights" class="blk arrival-filter" aria-labelledby="flight-hour-label">
    <div class="arrival-heading">
      <h2 id="flight-hour-label">Arrivals per hour</h2>
      <div class="flight-view-group group-options" role="group" aria-label="Flight group">
        <button
          v-for="[key, label] in groups"
          :key="key"
          type="button"
          class="chip"
          :aria-pressed="groupFilter === key"
          @click="groupFilter = key"
        >
          {{ label }} ({{ groupCounts[key] }})
        </button>
      </div>
    </div>
    <div v-if="chart.length" class="arrival-hours">
      <button
        v-for="c in chart"
        :key="c.hour"
        class="arrival-hour"
        type="button"
        :aria-label="`${c.label}, ${c.n} ${c.n === 1 ? 'flight' : 'flights'}`"
        :aria-pressed="hourFilter === c.hour"
        @click="toggleHour(c.hour)"
      >
        <span class="bar-track" aria-hidden="true">
          <b>{{ c.n }}</b>
          <i :style="{ height: c.height + 'px' }"></i>
        </span>
        <span class="hour-label">{{ c.label }}</span>
      </button>
    </div>
  </section>

  <div v-if="state.flights.length" class="flight-results">
    <h2><span role="status">{{ resultLabel }}</span></h2>
    <button v-if="!activeStatusFlights && hasFilters" type="button" class="ghost" @click="clearFilters">Clear filters</button>
  </div>

  <div v-if="!state.flights.length" class="empty">
    <p>No flights for this shift yet. Tap Update to pull the arrivals you cover.</p>
  </div>
  <div v-else-if="!list.length" class="empty">
    <p v-if="scope === 'cleaning'">No flights are being cleaned this shift.</p>
    <p v-else-if="scope === 'done'">No flights have been completed this shift.</p>
    <p v-else-if="scope === 'following' && !following.length">No followed flights yet. Open All flights and tap the star on a flight to follow it.</p>
    <p v-else>No flights match these filters.</p>
  </div>
  <div v-else class="strips">
    <div v-for="f in list" :key="f.id" class="strip" :class="'s-' + f.status">
      <button type="button" class="strip-main" @click="actions.openFlight(f.id)">
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
      <button
        type="button"
        class="follow-button"
        :aria-label="`Follow flight ${f.flight_no}`"
        :aria-pressed="!!f.followed"
        :disabled="followSaving.has(f.id)"
        @click="toggleFollow(f)"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-2.9-5.6 2.9 1.1-6.2L3 9.6l6.2-.9L12 3Z" />
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.flight-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-top: 6px;
}
.flight-views {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.flight-view-group {
  display: inline-flex;
  max-width: 100%;
  border: 1px solid var(--line);
  border-radius: var(--r);
  background: var(--surface);
}
.flight-view-group .chip {
  flex: 1 1 auto;
  border: 0;
  border-radius: 0;
}
.flight-view-group .chip:first-child {
  border-radius: var(--r) 0 0 var(--r);
}
.flight-view-group .chip + .chip {
  border-inline-start: 1px solid var(--line);
}
.flight-view-group .chip:last-child {
  border-radius: 0 var(--r) var(--r) 0;
}
.flight-view-group .chip:focus-visible {
  z-index: 1;
}
.flight-views .chip,
.group-options .chip {
  min-height: 44px;
}
.flight-update {
  flex: none;
}
.flight-sync-note {
  margin-top: 8px;
}
.arrival-filter {
  min-width: 0;
  margin: 18px 0 0;
}
.arrival-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.arrival-heading h2 {
  margin: 0;
}
.group-options .chip {
  padding-inline: 10px;
  font-size: 14px;
}
.arrival-hours {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(46px, 1fr);
  gap: 8px;
  margin-top: 8px;
  padding: 4px;
  overflow-x: auto;
}
.arrival-hour {
  display: grid;
  grid-template-rows: 62px auto;
  align-items: end;
  justify-items: stretch;
  gap: 4px;
  min-width: 0;
  min-height: 44px;
  padding: 2px;
  border: 0;
  border-radius: var(--r);
  background: none;
}
.bar-track {
  display: grid;
  justify-items: center;
  align-content: end;
  gap: 2px;
  color: var(--muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.bar-track i {
  width: 72%;
  border-radius: 4px 4px 2px 2px;
  background: color-mix(in srgb, var(--info) 32%, var(--line));
}
.hour-label {
  padding: 3px 0;
  border-radius: 6px;
  color: var(--muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.arrival-hour[aria-pressed="true"] .bar-track i,
.arrival-hour[aria-pressed="true"] .hour-label {
  background: var(--info);
  color: var(--on-shift);
}
.flight-results {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 18px 0 8px;
}
.flight-results h2 {
  margin: 0;
}
.flight-results .ghost {
  padding-inline: 8px;
}
@media (max-width: 400px) {
  .flight-views {
    gap: 6px;
  }
  .flight-views .chip,
  .flight-update {
    padding-inline: 10px;
    font-size: 14px;
  }
}
.follow-button {
  display: grid;
  place-items: center;
  width: 44px;
  min-height: 44px;
  padding: 0;
  color: var(--muted);
  border: 0;
  border-radius: var(--r);
  background: transparent;
}
.follow-button:hover {
  background: var(--line);
}
.follow-button[aria-pressed="true"] {
  color: var(--warn);
}
.follow-button svg {
  width: 22px;
  height: 22px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linejoin: round;
}
.follow-button[aria-pressed="true"] svg {
  fill: currentColor;
}
</style>
