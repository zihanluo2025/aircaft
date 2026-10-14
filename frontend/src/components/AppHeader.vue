<script setup>
import { computed } from 'vue'
import { actions, onDuty, state } from '../store.js'

const done = computed(() => state.flights.filter((f) => f.status === 'done').length)
const total = computed(() => state.flights.length)
const shifts = [
  ['morning', 'Morning'],
  ['night', 'Night'],
]
</script>

<template>
  <header class="top">
    <div class="r1">
      <h1>Turnaround</h1>
      <div class="stats">
        <div><b>{{ done }}/{{ total }}</b><span>flights done</span></div>
        <div><b>{{ onDuty.length }}</b><span>on duty</span></div>
      </div>
    </div>
    <div class="r2">
      <input class="date" type="date" :value="state.date" aria-label="Date" @change="actions.setDate($event.target.value)" />
      <div class="shiftsw" role="group" aria-label="Shift">
        <button v-for="s in shifts" :key="s[0]" :aria-pressed="state.shift === s[0]" @click="actions.setShift(s[0])">
          <svg v-if="s[0] === 'morning'" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8" />
          </svg>
          <svg v-else viewBox="0 0 24 24" aria-hidden="true">
            <path d="M20 14.5A8.5 8.5 0 119.5 4a7 7 0 0010.5 10.5z" />
          </svg>
          {{ s[1] }}
        </button>
      </div>
    </div>
  </header>
</template>
