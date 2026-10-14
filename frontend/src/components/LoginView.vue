<script setup>
import { ref } from 'vue'
import { actions } from '../store.js'

const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  if (!username.value.trim() || !password.value) return
  error.value = ''
  busy.value = true
  try {
    await actions.login(username.value.trim(), password.value)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login">
    <h1>Turnaround</h1>
    <p class="muted">Sign in to see today's flights and crew.</p>
    <label class="f">Username
      <input v-model="username" type="text" autocomplete="username" autocapitalize="none" @keyup.enter="submit" />
    </label>
    <label class="f">Password
      <input v-model="password" type="password" autocomplete="current-password" @keyup.enter="submit" />
    </label>
    <p v-if="error" class="impres bad">{{ error }}</p>
    <button class="btn" :disabled="busy || !username.trim() || !password" @click="submit">Sign in</button>
  </div>
</template>
