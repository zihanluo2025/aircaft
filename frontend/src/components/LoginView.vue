<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { AIRPORT_TZ, currentShift, pad } from '../lib/time.js'
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

// Live airport clock and the shift that is running now -- always Adelaide time, never the device's.
const now = ref(Date.now())
let ticker = null
onMounted(() => (ticker = setInterval(() => (now.value = Date.now()), 15000)))
onUnmounted(() => clearInterval(ticker))
const shiftNow = computed(() => currentShift(now.value))
const clock = computed(() => `${pad(Math.floor(shiftNow.value.minutes / 60))}:${pad(shiftNow.value.minutes % 60)}`)
const zone = computed(
  () =>
    new Intl.DateTimeFormat('en-AU', { timeZone: AIRPORT_TZ, timeZoneName: 'short' })
      .formatToParts(new Date(now.value))
      .find((p) => p.type === 'timeZoneName')?.value || 'Adelaide',
)
const shiftLabel = computed(() => (shiftNow.value.shift === 'morning' ? 'Morning shift' : 'Night shift'))
</script>

<template>
  <div class="lg">
    <aside class="lg-brand" aria-hidden="true">
      <div class="lg-brand-in">
        <div class="lg-word">Turnaround</div>
        <p class="lg-eyebrow">Aircraft cleaning operations</p>
        <h2>Every aircraft turned around on time.</h2>
        <ul>
          <li>Live arrivals for international, Jetstar and Virgin flights</li>
          <li>Crew allocation per aircraft, fixed roles for the day</li>
          <li>Cleaning times and cabin crew sign-off on one record</li>
        </ul>
      </div>
      <div class="lg-status">
        <span class="lg-dot"></span>
        {{ shiftLabel }} &middot; {{ clock }} {{ zone }}
      </div>
    </aside>

    <main class="lg-main">
      <form class="lg-form" novalidate @submit.prevent="submit">
        <div class="lg-mobilehead">
          <div class="lg-word">Turnaround</div>
          <span class="lg-pill"><span class="lg-dot"></span>{{ shiftLabel }} &middot; {{ clock }}</span>
        </div>

        <header class="lg-head">
          <h1>Sign in</h1>
          <p>Use the account your manager set up for you.</p>
        </header>

        <label class="lg-field">
          <span class="lg-label">Username</span>
          <span class="lg-box">
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5" /></svg>
            <input v-model="username" type="text" autocomplete="username" autocapitalize="none" spellcheck="false" placeholder="Enter your username" />
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
              placeholder="Enter your password"
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

        <p class="lg-foot">Forgot your password? Ask your manager to reset it.</p>
      </form>
    </main>
  </div>
</template>

<style scoped>
.lg {
  min-height: 100vh;
  min-height: 100dvh;
  display: grid;
  grid-template-columns: 1fr;
  background: var(--bg);
}

/* ---- brand panel (wide screens only) ---- */
.lg-brand {
  display: none;
  position: relative;
  overflow: hidden;
  flex-direction: column;
  justify-content: space-between;
  padding: 48px 56px;
  background: var(--hdr);
  color: var(--on-hdr);
}
/* faint runway-style grid, fading out towards the bottom */
.lg-brand::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(color-mix(in srgb, var(--on-hdr) 7%, transparent) 1px, transparent 1px),
    linear-gradient(90deg, color-mix(in srgb, var(--on-hdr) 7%, transparent) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: linear-gradient(180deg, #000 0%, transparent 85%);
  pointer-events: none;
}
.lg-brand-in,
.lg-status {
  position: relative;
}
.lg-word {
  font-family: var(--f-disp);
  font-size: 30px;
  font-weight: 700;
  letter-spacing: 0.01em;
  line-height: 1;
}
.lg-eyebrow {
  margin: 72px 0 12px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  opacity: 0.7;
}
.lg-brand h2 {
  margin: 0 0 28px;
  max-width: 14ch;
  font-family: var(--f-disp);
  font-size: 52px;
  font-weight: 700;
  line-height: 1.02;
}
.lg-brand ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 420px;
}
.lg-brand li {
  position: relative;
  padding-left: 22px;
  font-size: 16px;
  line-height: 1.4;
  opacity: 0.85;
}
.lg-brand li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0.5em;
  width: 8px;
  height: 8px;
  border-radius: 2px;
  background: var(--accent);
}
.lg-status {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  font-weight: 500;
  opacity: 0.8;
  font-variant-numeric: tabular-nums;
}
.lg-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ok);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ok) 25%, transparent);
  flex: none;
}

/* ---- form side ---- */
.lg-main {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 20px calc(24px + env(safe-area-inset-bottom, 0px));
}
.lg-form {
  width: 100%;
  max-width: 380px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.lg-mobilehead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 20px;
}
.lg-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  border-radius: 999px;
  border: 1px solid var(--line);
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.lg-pill .lg-dot {
  width: 6px;
  height: 6px;
  box-shadow: none;
}
.lg-head h1 {
  margin: 0 0 6px;
  font-family: var(--f-disp);
  font-size: 34px;
  font-weight: 700;
  line-height: 1.05;
}
.lg-head p {
  margin: 0;
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
  font-weight: 600;
  color: var(--ink);
}
.lg-box {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 50px;
  padding: 0 6px 0 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.lg-box:hover {
  border-color: color-mix(in srgb, var(--muted) 60%, var(--line));
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
  -webkit-box-shadow: 0 0 0 100px var(--surface) inset;
  caret-color: var(--ink);
  transition: background-color 9999s;
}
.lg-eye {
  flex: none;
  width: 38px;
  height: 38px;
  border: 0;
  border-radius: 8px;
  background: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.lg-eye:hover {
  background: var(--bg);
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
  margin-top: 6px;
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
  transition: filter 0.15s;
}
.lg-submit:hover:not(:disabled) {
  filter: brightness(1.06);
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
  margin: 4px 0 0;
  padding-top: 18px;
  border-top: 1px solid var(--line);
  font-size: 13px;
  color: var(--muted);
}

/* phones: form starts near the top rather than floating mid-screen */
@media (max-width: 859px) {
  .lg-main {
    align-items: flex-start;
    padding-top: calc(28px + env(safe-area-inset-top, 0px));
  }
}
/* wide screens: brand panel on the left, form on the right */
@media (min-width: 860px) {
  .lg {
    grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
  }
  .lg-brand {
    display: flex;
  }
  .lg-mobilehead {
    display: none;
  }
  .lg-form {
    gap: 20px;
  }
}
</style>
