<script setup>
import { computed, ref } from 'vue'
import { Popup as VanPopup, TimePicker as VanTimePicker } from 'vant'
import { airportNow, pad } from '../lib/time.js'

const props = defineProps({ label: { type: String, default: '' }, modelValue: { type: String, default: '' } })
const emit = defineEmits(['update:modelValue'])

// The usual mobile pattern: an input-looking button, and a bottom sheet with Cancel / title / Done,
// a big read-out of the time being picked, quick nudges, and an hour : minute wheel.
const open = ref(false)
const draft = ref(['00', '00'])
const preview = computed(() => draft.value.join(':'))

function setMinutes(total) {
  const m = ((total % 1440) + 1440) % 1440
  draft.value = [pad(Math.floor(m / 60)), pad(m % 60)]
}
function openPicker() {
  if (props.modelValue) draft.value = props.modelValue.split(':')
  else setMinutes(airportNow().minutes)
  open.value = true
}
function nudge(delta) {
  setMinutes(Number(draft.value[0]) * 60 + Number(draft.value[1]) + delta)
}
function confirm() {
  if (preview.value !== props.modelValue) emit('update:modelValue', preview.value)
  open.value = false
}
</script>

<template>
  <div class="tf">
    <span class="tf-label">{{ label }}</span>
    <button type="button" class="tf-input" :class="{ empty: !modelValue }" :aria-label="`${label}: ${modelValue || 'not set'}`" @click="openPicker">
      <svg class="tf-icon" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </svg>
      <span class="tf-value">{{ modelValue || '--:--' }}</span>
      <svg class="tf-chev" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
    </button>
  </div>

  <van-popup v-model:show="open" position="bottom" round teleport="body" class="tf-sheet" safe-area-inset-bottom>
    <div class="tf-head">
      <button type="button" class="tf-btn" @click="open = false">Cancel</button>
      <h3>{{ label }}</h3>
      <button type="button" class="tf-btn tf-done" @click="confirm">Done</button>
    </div>
    <div class="tf-preview">{{ preview }}</div>
    <div class="tf-quick">
      <button type="button" @click="nudge(-5)">&minus;5 min</button>
      <button type="button" @click="setMinutes(airportNow().minutes)">Now</button>
      <button type="button" @click="nudge(5)">+5 min</button>
    </div>
    <div class="tf-wheel">
      <van-time-picker v-model="draft" :show-toolbar="false" :option-height="44" :visible-option-num="5" />
      <span class="tf-colon" aria-hidden="true">:</span>
    </div>
  </van-popup>
</template>

<style scoped>
.tf {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.tf-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--muted);
}
.tf-input {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  height: 48px;
  padding: 0 12px;
  background: var(--bg);
  color: var(--ink);
  border: 1px solid var(--line);
  border-radius: 10px;
  font: inherit;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.tf-input:hover {
  border-color: var(--muted);
}
.tf-input:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 25%, transparent);
}
.tf-icon,
.tf-chev {
  width: 18px;
  height: 18px;
  flex: none;
  fill: none;
  stroke: var(--muted);
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.tf-value {
  flex: 1;
  text-align: left;
  font-size: 18px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
}
.tf-input.empty .tf-value {
  color: var(--muted);
  font-weight: 500;
}
</style>

<!-- The sheet is teleported to <body>, outside this component's scope, so its styles are global. -->
<style>
.tf-sheet {
  background: var(--surface);
  color: var(--ink);
  padding-bottom: 12px;
}
.tf-head {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 8px 8px 0;
}
.tf-head h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.tf-btn {
  justify-self: start;
  background: none;
  border: 0;
  padding: 10px 12px;
  font: inherit;
  font-size: 15px;
  color: var(--muted);
  cursor: pointer;
}
.tf-done {
  justify-self: end;
  color: var(--accent);
  font-weight: 700;
}
.tf-preview {
  text-align: center;
  font-family: var(--f-disp);
  font-size: 44px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1;
  margin: 10px 0 12px;
}
.tf-quick {
  display: flex;
  justify-content: center;
  gap: 8px;
  padding: 0 16px 8px;
}
.tf-quick button {
  min-width: 76px;
  height: 34px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--bg);
  color: var(--ink);
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}
.tf-wheel {
  position: relative;
  max-width: 320px;
  margin: 0 auto;
  --van-picker-background: var(--surface);
  --van-picker-option-text-color: var(--ink);
  --van-picker-option-font-size: 22px;
  --van-picker-mask-color: linear-gradient(180deg, color-mix(in srgb, var(--surface) 90%, transparent), color-mix(in srgb, var(--surface) 40%, transparent)),
    linear-gradient(0deg, color-mix(in srgb, var(--surface) 90%, transparent), color-mix(in srgb, var(--surface) 40%, transparent));
}
.tf-wheel .van-picker-column__item {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.tf-wheel .van-picker__frame {
  left: 12px;
  right: 12px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}
.tf-wheel .van-picker__frame::after {
  display: none;
}
.tf-colon {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -54%);
  font-size: 22px;
  font-weight: 700;
  pointer-events: none;
}
</style>
