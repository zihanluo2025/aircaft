<script setup>
import { computed, onMounted, ref } from 'vue'
import { SHIFT_NAME } from '../constants.js'
import { hhmm } from '../lib/time.js'
import { actions, state, toast } from '../store.js'

const report = computed(() => state.report)
// The Flights table is a record of completed work -- flights still scheduled, landed or cleaning
// aren't done yet, so they don't belong in it.
const doneFlights = computed(() => report.value.flights.filter((f) => f.status === 'done'))
const summary = ref(null)

// Read-only detail, expanded inline -- not the editable flight sheet used elsewhere.
const expandedId = ref(null)
const toggleFlight = (id) => (expandedId.value = expandedId.value === id ? null : id)

onMounted(() => actions.loadReport())

async function copy() {
  const text = report.value.summary_text
  try {
    await navigator.clipboard.writeText(text)
    toast('Copied')
  } catch {
    summary.value.focus()
    summary.value.select()
    toast('Text selected. Use Copy from the menu.')
  }
}
</script>

<template>
  <div v-if="!report" class="empty"><p>Loading the report</p></div>
  <template v-else>
    <h2 style="margin-top: 6px">{{ report.date }}, {{ SHIFT_NAME[report.shift] }} shift</h2>
    <div class="sum">
      <div><b>{{ report.done }}/{{ report.total }}</b><span>flights done</span></div>
      <div><b>{{ report.average_minutes }}</b><span>avg minutes</span></div>
      <div><b>{{ report.signed }}</b><span>signed</span></div>
    </div>

    <div v-if="!report.flights.length" class="empty"><p>No flights to report on this day.</p></div>
    <template v-else>
      <h3>Flights</h3>
      <p class="muted" style="margin: 0 0 8px; font-size: 14px">Tap a flight to see who worked it and how long.</p>
      <div v-if="!doneFlights.length" class="empty"><p>No flights finished cleaning yet.</p></div>
      <div v-else class="scroll">
        <table>
          <thead>
            <tr><th>Flight</th><th>ETA</th><th>Min</th><th>Staff</th><th>Signed</th></tr>
          </thead>
          <tbody>
            <template v-for="f in doneFlights" :key="f.id">
              <tr
                class="rowbtn"
                tabindex="0"
                role="button"
                :aria-expanded="expandedId === f.id"
                :aria-label="'Details for ' + f.flight_no"
                @click="toggleFlight(f.id)"
                @keydown.enter="toggleFlight(f.id)"
                @keydown.space.prevent="toggleFlight(f.id)"
              >
                <td>{{ f.flight_no }}</td>
                <td class="n">{{ f.eta }}</td>
                <td class="n">{{ f.minutes ?? '-' }}</td>
                <td class="n">{{ f.crew_count || '-' }}</td>
                <td>{{ f.signed ? 'Yes' : 'No' }}</td>
              </tr>
              <tr v-if="expandedId === f.id" class="detailrow">
                <td colspan="5">
                  <p v-if="!f.crew.length" class="muted" style="margin: 0">Nobody was assigned to this flight.</p>
                  <div v-else class="fcrew">
                    <div v-for="(c, i) in f.crew" :key="i" class="fcrewrow">
                      <span class="lbl">{{ c.role }}</span><span>{{ c.staff_name || 'Unassigned' }}</span>
                    </div>
                  </div>
                  <p v-if="f.started_at" class="muted" style="margin: 8px 0 0; font-size: 13px">
                    {{ hhmm(f.started_at) }}&ndash;{{ f.finished_at ? hhmm(f.finished_at) : 'still cleaning' }}
                    <template v-if="f.minutes !== null"> &middot; {{ f.minutes }} min</template>
                  </p>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <template v-if="report.people.length">
        <h3 style="margin-top: 18px">Per person</h3>
        <div class="scroll">
          <table>
            <thead><tr><th>Name</th><th>Aircraft</th><th>Minutes</th></tr></thead>
            <tbody>
              <tr v-for="p in report.people" :key="p.staff_id">
                <td>{{ p.name }}</td><td class="n">{{ p.aircraft }}</td><td class="n">{{ p.minutes }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <h3 style="margin-top: 18px">Copy summary</h3>
      <textarea id="sumTxt" ref="summary" readonly :value="report.summary_text"></textarea>
      <div class="two"><button class="btn" @click="copy">Copy text</button><span></span></div>
    </template>

    <p class="foot">Signed in as {{ state.user.display_name || state.user.username }}</p>
    <div class="two"><button class="btn2" @click="actions.logout()">Sign out</button><span></span></div>
  </template>
</template>
