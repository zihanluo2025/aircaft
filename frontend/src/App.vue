<script setup>
import { onMounted } from 'vue'
import { init, sheetOpen, state } from './store.js'
import AppHeader from './components/AppHeader.vue'
import CrewView from './components/CrewView.vue'
import FlightSheet from './components/FlightSheet.vue'
import FlightsView from './components/FlightsView.vue'
import LoginView from './components/LoginView.vue'
import ReportView from './components/ReportView.vue'
import TabBar from './components/TabBar.vue'

onMounted(init)
</script>

<template>
  <div v-if="!state.ready" class="loading">Loading</div>
  <LoginView v-else-if="!state.user" />
  <template v-else>
    <AppHeader />
    <main>
      <FlightsView v-if="state.tab === 'flights'" />
      <CrewView v-else-if="state.tab === 'crew'" />
      <ReportView v-else />
    </main>
    <TabBar />
    <FlightSheet v-if="sheetOpen" />
  </template>
  <div v-if="state.toastMsg" class="toast" role="status">{{ state.toastMsg }}</div>
</template>
