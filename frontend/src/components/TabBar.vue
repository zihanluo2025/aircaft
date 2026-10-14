<script setup>
import { actions, state } from '../store.js'

const tabs = [
  { key: 'flights', label: 'Flights' },
  { key: 'crew', label: 'Staff' },
  { key: 'report', label: 'Report' },
]
</script>

<template>
  <nav class="tabs" aria-label="Sections">
    <button
      v-for="t in tabs"
      :key="t.key"
      :aria-current="state.tab === t.key ? 'page' : undefined"
      @click="actions.setTab(t.key)"
    >
      <svg v-if="t.key === 'flights'" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M2.5 14.5l8.5-3V5.5a1.5 1.5 0 013 0v6l8.5 3v2l-8.5-1.8V19l2.2 1.6V22L12.5 21 9.3 22v-1.4l2.2-1.6v-4.3l-9 1.8z" />
      </svg>
      <svg v-else-if="t.key === 'crew'" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="9" cy="8" r="3.2" />
        <path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5" />
        <path d="M16 5.2a3 3 0 010 5.6M18.5 14.8c1.6.8 2.5 2.4 2.5 5.2" />
      </svg>
      <svg v-else viewBox="0 0 24 24" aria-hidden="true">
        <rect x="5" y="3" width="14" height="18" rx="2" />
        <path d="M8.5 8h7M8.5 12h7M8.5 16h4" />
      </svg>
      <span>{{ t.label }}</span>
    </button>
  </nav>
</template>
