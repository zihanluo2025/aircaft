<script setup>
import { computed, onMounted, ref } from 'vue'
import { SHIFT_NAME, STATUS_LABEL } from '../constants.js'
import { actions, state, toast } from '../store.js'

const report = computed(() => state.report)
const summary = ref(null)

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
      <div class="scroll">
        <table>
          <thead>
            <tr><th>Flight</th><th>ETA</th><th>Status</th><th>Min</th><th>Crew</th><th>Signed</th></tr>
          </thead>
          <tbody>
            <tr v-for="f in report.flights" :key="f.id">
              <td>{{ f.flight_no }}</td>
              <td class="n">{{ f.eta }}</td>
              <td>{{ STATUS_LABEL[f.status] }}</td>
              <td class="n">{{ f.minutes ?? '-' }}</td>
              <td class="n">{{ f.crew_count }}</td>
              <td>{{ f.signed ? 'Yes' : 'No' }}</td>
            </tr>
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
