<script setup>
import { computed, onUnmounted, ref } from 'vue'
import { QUAL_LABEL, QUAL_ROLES } from '../constants.js'
import { DEFAULT_TIMES, plannedSlot, timeSlot, todaySlots } from '../lib/roster.js'
import { hhmm } from '../lib/time.js'
import { actions, state, toast } from '../store.js'
import TimeField from './TimeField.vue'

const props = defineProps({ person: { type: Object, required: true } })
// `props.person` is swapped for a brand-new object every time the roster refreshes (the API returns
// fresh JSON each time, not a mutated version of the old one). `const e = props.person` would just
// snapshot that first object forever; using a computed instead keeps `e` pointing at the current one.
const e = computed(() => props.person)

const open = ref(false)
const editTip = computed(() => (open.value ? 'Done' : e.value.shift_type ? 'Edit' : 'Call in'))

// "Amit Kumar - 09367" -> name "Amit Kumar", employee number "09367"
const displayName = computed(() => e.value.name.replace(/\s-\s*\d+$/, ''))
const empNo = computed(() => e.value.name.match(/-\s*(\d+)$/)?.[1] || '')
const initials = computed(() => {
  const words = displayName.value.split(/\s+/).filter(Boolean)
  return words.length ? (words[0][0] + (words.length > 1 ? words[words.length - 1][0] : '')).toUpperCase() : '?'
})

const hasPlan = computed(() => state.roster.has_plan)
// Changed = on/off duty or Start/End differs from the imported plan (worked out by the API).
const isChanged = computed(() => hasPlan.value && !!e.value.shift_type && !!e.value.changed)
const planLabel = computed(() => plannedSlot(e.value) || 'on duty')
const note = computed(() => {
  if (e.value.sick_at && e.value.planned_type) return `Planned ${planLabel.value}, called in sick`
  if (!isChanged.value) return ''
  if (e.value.planned_type) return `Planned ${planLabel.value}, changed today`
  return e.value.called_in_at ? '' : 'Added today, not on the planned roster'
})

// Calling someone in to cover: pick one of the Start–End pairs already on today's roster (or the
// shift's full window if nobody has times yet); still editable below for a one-off time. The API
// only needs a non-null shift_type to mark them on duty -- it works the rest out from the times.
const callInSlots = computed(() => {
  const slots = todaySlots(state.roster.entries)
  if (slots.length) return slots
  const times = DEFAULT_TIMES[state.shift]
  return [{ label: `${times[0]}–${times[1]}`, times }]
})
const callIn = ([rstart, rend]) =>
  actions.rosterPatch(e.value.staff_id, { shift_type: 'all', rstart, rend, called_in: true })
const backToPlan = () => {
  const { planned_type, planned_rstart, planned_rend } = e.value
  if (!planned_type) return actions.rosterPatch(e.value.staff_id, { shift_type: null })
  return actions.rosterPatch(e.value.staff_id, {
    shift_type: planned_type,
    ...(planned_rstart && planned_rend ? { rstart: planned_rstart, rend: planned_rend } : {}),
  })
}

// Tap once to arm, tap again to actually call it in -- a single accidental tap on this icon-only
// button must not take someone off the roster. Resets itself if left untouched.
const confirmSick = ref(false)
let confirmSickTimer = null
function callSick() {
  if (!confirmSick.value) {
    confirmSick.value = true
    toast('Tap again to confirm')
    clearTimeout(confirmSickTimer)
    confirmSickTimer = setTimeout(() => (confirmSick.value = false), 3000)
    return
  }
  clearTimeout(confirmSickTimer)
  confirmSick.value = false
  actions.rosterPatch(e.value.staff_id, { sick: true }, `${e.value.name} called in sick today`)
}
onUnmounted(() => clearTimeout(confirmSickTimer))

const undoSick = () => actions.rosterPatch(e.value.staff_id, { sick: false })
// TimeField is a controlled component driven by e.rstart/e.rend -- if the save fails, the prop
// simply doesn't change, so the field naturally keeps showing the last real value with no manual
// revert needed (unlike the native <input type=time> this replaced).
function changeRosterTime(field, value) {
  if (!value) return
  actions.rosterPatch(e.value.staff_id, { [field]: value })
}
// Qualifications usually come from the weekly roster import's note column -- this lets a wrong or
// outdated entry be fixed on the spot instead of needing someone to go edit the database.
function toggleQual(role) {
  const quals = e.value.quals.includes(role) ? e.value.quals.filter((q) => q !== role) : [...e.value.quals, role]
  actions.patchStaff(e.value.staff_id, { quals })
}
</script>

<template>
  <div class="sc" :class="[e.shift_type ? 'on' : 'off', { open }]">
    <div class="sc-top">
      <i class="sc-av" aria-hidden="true">{{ initials }}</i>
      <div class="sc-id">
        <div class="sc-name">
          <strong>{{ displayName }}</strong>
          <span v-if="empNo" class="sc-no">#{{ empNo }}</span>
        </div>
        <div class="sc-sub">
          <span class="sc-shift" :class="{ sick: e.sick_at }">
            <i class="sc-dot" aria-hidden="true"></i>{{ e.shift_type ? timeSlot(e) || 'On duty' : e.sick_at ? 'Sick today' : 'Off today' }}
          </span>
          <span v-if="e.role" class="sc-badge role">{{ e.role }}</span>
          <span v-if="e.called_in_at" class="sc-badge call">Call in {{ hhmm(e.called_in_at) }}</span>
          <span v-if="isChanged && e.planned_type" class="sc-badge chg">Changed</span>
          <span v-for="q in e.quals" :key="q" class="sc-badge lic">{{ QUAL_LABEL[q] || q }}</span>
        </div>
        <p v-if="note" class="sc-note">{{ note }}</p>
      </div>
      <div class="sc-actions">
        <button
          v-if="e.shift_type"
          type="button"
          class="sc-btn sick"
          :class="{ armed: confirmSick }"
          :aria-label="confirmSick ? 'Tap again to confirm call sick' : 'Call sick'"
          :data-tip="confirmSick ? 'Tap again to confirm' : 'Call sick'"
          @click="callSick"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v9M12 19h.01" /></svg>
        </button>
        <button
          type="button"
          class="sc-btn"
          :class="{ on: open }"
          :aria-expanded="open"
          :aria-label="editTip"
          :data-tip="editTip"
          @click="open = !open"
        >
          <svg v-if="open" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
          <svg v-else-if="e.shift_type" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16v4zM13.5 6.5l4 4" /></svg>
          <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M12 6v12M6 12h12" /></svg>
        </button>
      </div>
    </div>

    <div v-if="open" class="sc-edit-panel">
      <template v-if="!e.shift_type">
        <div class="sc-sec">Call them in to cover</div>
        <div class="sc-slots" role="group" :aria-label="'Call in ' + e.name">
          <button v-for="s in callInSlots" :key="s.label" type="button" @click="callIn(s.times)">{{ s.label }}</button>
        </div>
      </template>
      <button v-if="isChanged && e.planned_type" type="button" class="sc-plan" @click="backToPlan">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 14L4 9l5-5M4 9h10a6 6 0 010 12h-3" /></svg>
        Back to plan: {{ planLabel }}
      </button>

      <template v-if="e.shift_type">
        <div class="sc-sec">Times today</div>
        <div class="sc-times">
          <TimeField label="Start" :model-value="e.rstart" @update:model-value="(v) => changeRosterTime('rstart', v)" />
          <TimeField label="Indicative end" :model-value="e.rend" @update:model-value="(v) => changeRosterTime('rend', v)" />
        </div>
      </template>
      <button v-else-if="e.sick_at" type="button" class="sc-plan" @click="undoSick">Undo sick</button>

      <div class="sc-sec">Qualified for</div>
      <div class="sc-quals" role="group" :aria-label="'Qualifications for ' + e.name">
        <button
          v-for="q in QUAL_ROLES"
          :key="q"
          type="button"
          class="sc-qual"
          :aria-pressed="e.quals.includes(q)"
          @click="toggleQual(q)"
        >
          <span class="sc-check" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M6 12.5l4 4 8-9" /></svg></span>
          {{ QUAL_LABEL[q] }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* One row of the grouped staff list (.sc-group in styles.css). */
.sc {
  --tone: var(--muted);
  position: relative;
  padding: 12px 14px;
  transition: background 0.15s;
}
.sc + .sc {
  border-top: 1px solid var(--line);
}
.sc:first-child {
  border-radius: 13px 13px 0 0;
}
.sc:last-child {
  border-radius: 0 0 13px 13px;
}
.sc:only-child {
  border-radius: 13px;
}
.sc.on {
  --tone: var(--early);
}
.sc.open {
  background: color-mix(in srgb, var(--bg) 55%, var(--surface));
}
@media (hover: hover) {
  .sc:not(.open):hover {
    background: color-mix(in srgb, var(--bg) 35%, var(--surface));
  }
}
svg {
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.sc-top {
  display: flex;
  align-items: center;
  gap: 12px;
}
.sc-av {
  flex: none;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-style: normal;
  font-size: 14px;
  font-weight: 600;
  background: color-mix(in srgb, var(--tone) 18%, transparent);
  color: var(--tone);
}
.sc.off .sc-av {
  color: var(--muted);
  background: var(--bg);
}
.sc-id {
  flex: 1;
  min-width: 0;
}
.sc-name {
  line-height: 1.25;
}
.sc-name strong {
  font-size: 16px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.sc-no {
  margin-left: 6px;
  font-size: 13px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.sc-sub {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: 3px;
  font-size: 13px;
  color: var(--muted);
}
.sc-shift {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.sc.off .sc-shift {
  color: var(--muted);
}
.sc-shift.sick {
  color: var(--warn);
}
.sc-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--tone);
}
.sc.off .sc-dot {
  background: var(--line);
}
.sc-shift.sick .sc-dot {
  background: var(--warn);
}
/* small soft-filled labels, no outlines */
.sc-badge {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 7px;
  border-radius: 5px;
  font-size: 12px;
  font-weight: 600;
  background: var(--bg);
  color: var(--muted);
}
.sc-badge.role {
  background: color-mix(in srgb, var(--ink) 12%, transparent);
  color: var(--ink);
}
.sc-badge.call {
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  color: var(--accent);
}
.sc-badge.chg {
  background: color-mix(in srgb, var(--info) 16%, transparent);
  color: var(--info);
}
.sc-note {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--muted);
}

/* ghost icon buttons: quiet until hovered or active */
.sc-actions {
  flex: none;
  display: flex;
  align-items: center;
  gap: 2px;
}
.sc-btn {
  position: relative;
  flex: none;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 0;
  border-radius: 10px;
  background: none;
  color: var(--muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.sc-btn svg {
  width: 18px;
  height: 18px;
}
.sc-btn:hover {
  background: var(--bg);
  color: var(--ink);
}
.sc-btn.on {
  background: var(--accent);
  color: var(--on-accent);
}
.sc-btn.sick svg {
  stroke-width: 2.6;
}
.sc-btn.sick:hover {
  background: color-mix(in srgb, var(--warn) 14%, transparent);
  color: var(--warn);
}
.sc-btn.sick.armed {
  background: var(--warn);
  color: var(--surface);
}
/* tooltip above the button, right-aligned so it never runs off the screen's right edge */
.sc-btn[data-tip]::after {
  content: attr(data-tip);
  position: absolute;
  right: 0;
  bottom: calc(100% + 6px);
  transform: translateY(4px);
  padding: 5px 9px;
  border-radius: 6px;
  background: var(--ink);
  color: var(--bg);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.12s, transform 0.12s;
  z-index: 3;
}
.sc-btn:hover::after,
.sc-btn:focus-visible::after,
.sc-btn.sick.armed::after {
  opacity: 1;
  transform: none;
}
@media (hover: none) {
  /* on touch screens a tap leaves :hover stuck -- only the armed sick button keeps its tooltip */
  .sc-btn:hover:not(.armed)::after {
    opacity: 0;
  }
  .sc-btn:hover:not(.on):not(.armed) {
    background: none;
    color: var(--muted);
  }
}

/* ---- editor ---- */
.sc-edit-panel {
  margin: 12px 0 2px 52px;
  padding-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sc-sec {
  margin-top: 10px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}
/* call-in choices: one button per Start–End already on today's roster */
.sc-slots {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.sc-slots button {
  height: 40px;
  padding: 0 14px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: var(--bg);
  color: var(--ink);
  font: inherit;
  font-size: 15px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
}
.sc-slots button:hover {
  background: var(--surface);
}
.sc-plan {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px dashed var(--line);
  background: none;
  color: var(--ink);
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}
.sc-plan svg {
  width: 16px;
  height: 16px;
}
.sc-times {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.sc-quals {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.sc-qual {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 14px 0 10px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: var(--bg);
  color: var(--ink);
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}
.sc-check {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  border: 2px solid var(--line);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: transparent;
}
.sc-check svg {
  width: 14px;
  height: 14px;
  stroke-width: 3;
}
.sc-qual[aria-pressed='true'] {
  border-color: color-mix(in srgb, var(--accent) 55%, transparent);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}
.sc-qual[aria-pressed='true'] .sc-check {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
}

@media (max-width: 400px) {
  .sc {
    padding: 12px;
  }
  .sc-av {
    width: 36px;
    height: 36px;
    font-size: 13px;
  }
  .sc-edit-panel {
    margin-left: 0;
  }
  .sc-times {
    gap: 8px;
  }
}
</style>
