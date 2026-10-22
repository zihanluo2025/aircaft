<script setup>
import { ref } from 'vue'
import { actions } from '../store.js'

const username = ref('')
const password = ref('')
const showPassword = ref(false)
const error = ref('')
const busy = ref(false)

async function submit() {
  if (busy.value || !username.value.trim() || !password.value) return
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
  <div class="lg">
    <form class="lg-card" novalidate @submit.prevent="submit">
      <div class="lg-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24"><path d="M2.5 13.5l8-2.2V5a1.5 1.5 0 013 0v6.3l8 2.2v2l-8-1.6v4.3l2.5 1.8v1.5L12 20.5l-4 1V20l2.5-1.8v-4.3l-8 1.6z" /></svg>
      </div>
      <h1>Turnaround</h1>
      <p class="lg-sub">Sign in to see today's flights and crew.</p>

      <label class="lg-field">
        <span class="lg-label">Username</span>
        <span class="lg-box">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5" /></svg>
          <input v-model="username" type="text" autocomplete="username" autocapitalize="none" spellcheck="false" placeholder="Your username" />
        </span>
      </label>

      <label class="lg-field">
        <span class="lg-label">Password</span>
        <span class="lg-box">
          <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10.5" width="14" height="10" rx="2" /><path d="M8 10.5V7.5a4 4 0 018 0v3" /></svg>
          <input
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="current-password"
            placeholder="Your password"
          />
          <button
            type="button"
            class="lg-eye"
            :aria-label="showPassword ? 'Hide password' : 'Show password'"
            :aria-pressed="showPassword"
            @click="showPassword = !showPassword"
          >
            <svg v-if="showPassword" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M3 3l18 18M10.6 6.1A9.8 9.8 0 0112 6c5 0 8.5 4 9.5 6a12 12 0 01-2.6 3.4M6.6 7.6C4.6 8.9 3.2 10.7 2.5 12c1 2 4.5 6 9.5 6 1.5 0 2.9-.4 4.1-1M9.9 9.9a3 3 0 004.2 4.2" />
            </svg>
            <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12C3.5 10 7 6 12 6s8.5 4 9.5 6c-1 2-4.5 6-9.5 6s-8.5-4-9.5-6z" /><circle cx="12" cy="12" r="3" /></svg>
          </button>
        </span>
      </label>

      <p v-if="error" class="lg-error" role="alert">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5M12 16h.01" /></svg>
        {{ error }}
      </p>

      <button type="submit" class="lg-submit" :disabled="busy || !username.trim() || !password">
        <span v-if="busy" class="lg-spin" aria-hidden="true"></span>
        {{ busy ? 'Signing in...' : 'Sign in' }}
      </button>

      <p class="lg-foot">Accounts are set up by your manager.</p>
    </form>
  </div>
</template>

<style scoped>
.lg {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px calc(24px + env(safe-area-inset-bottom, 0px));
  background:
    radial-gradient(600px 320px at 50% 0%, color-mix(in srgb, var(--accent) 14%, transparent), transparent 70%),
    var(--bg);
}
.lg-card {
  width: 100%;
  max-width: 400px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 28px 24px 22px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 16px;
  box-shadow: 0 20px 50px -24px rgba(0, 0, 0, 0.5);
}
.lg-mark {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  color: var(--accent);
}
.lg-mark svg {
  width: 26px;
  height: 26px;
  fill: currentColor;
}
h1 {
  font-family: var(--f-disp);
  font-size: 40px;
  font-weight: 700;
  line-height: 1;
  margin: -2px 0 0;
}
.lg-sub {
  margin: -8px 0 4px;
  color: var(--muted);
  font-size: 15px;
}
.lg-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.lg-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--muted);
}
.lg-box {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 48px;
  padding: 0 6px 0 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--bg);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.lg-box:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 25%, transparent);
}
.lg-box > svg,
.lg-eye svg,
.lg-error svg {
  flex: none;
  width: 18px;
  height: 18px;
  fill: none;
  stroke: var(--muted);
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
/* beats the global input[type=text]/[type=password] box style: one box, not a box in a box */
.lg-box input[type='text'],
.lg-box input[type='password'] {
  flex: 1;
  min-width: 0;
  min-height: 0;
  height: 100%;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: none;
  color: var(--ink);
  font-size: 16px; /* 16px stops iOS zooming in on focus */
  outline: none;
}
.lg-box input::placeholder {
  color: var(--muted);
  opacity: 0.7;
}
/* the browser's saved-password autofill paints its own pale-blue fill; keep the theme instead */
.lg-box input:-webkit-autofill,
.lg-box input:-webkit-autofill:hover,
.lg-box input:-webkit-autofill:focus {
  -webkit-text-fill-color: var(--ink);
  -webkit-box-shadow: 0 0 0 100px var(--bg) inset;
  caret-color: var(--ink);
  transition: background-color 9999s;
}
.lg-eye {
  flex: none;
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 8px;
  background: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.lg-eye:hover {
  background: var(--line);
}
.lg-error {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 14px;
  color: var(--warn);
  background: color-mix(in srgb, var(--warn) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--warn) 35%, transparent);
}
.lg-error svg {
  stroke: currentColor;
}
.lg-submit {
  height: 50px;
  margin-top: 4px;
  border: 0;
  border-radius: 10px;
  background: var(--accent);
  color: var(--on-accent);
  font: inherit;
  font-size: 16px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  cursor: pointer;
}
.lg-submit:disabled {
  opacity: 0.5;
  cursor: default;
}
.lg-spin {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid currentColor;
  border-right-color: transparent;
  animation: lg-spin 0.7s linear infinite;
}
@keyframes lg-spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .lg-spin {
    animation: none;
  }
}
.lg-foot {
  margin: 2px 0 0;
  text-align: center;
  font-size: 13px;
  color: var(--muted);
}
</style>
