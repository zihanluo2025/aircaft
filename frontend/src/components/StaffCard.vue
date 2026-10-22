<script setup>
import { computed, onUnmounted, ref } from 'vue'
import { QUAL_LABEL, QUAL_ROLES, SHIFT_LABEL, SHIFT_TIMES } from '../constants.js'
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
const isChanged = computed(() => hasPlan.value && !!e.value.shift_type && e.value.planned_type !== e.value.shift_type)
const note = computed(() => {
  if (e.value.sick_at && e.value.planned_type) return `Planned ${SHIFT_LABEL[e.value.planned_type]}, called in sick`
  if (!isChanged.value) return ''
  if (e.value.planned_type) return `Planned ${SHIFT_LABEL[e.value.planned_type]}, changed today`
  return e.value.called_in_at ? '' : 'Added today, not on the planned roster'
})

// Picking a shift for someone off duty is how you call them in to cover -- tag it as a call-in too,
// since it was not part of the imported plan. The times jump to that type's standard Start/End (the
// whole point of e.g. All day -> Early is to actually change when they leave); still editable below
// for a genuinely one-off time.
const changeShift = (type) => {
  const [rstart, rend] = SHIFT_TIMES[type] || []
  return actions.rosterPatch(e.value.staff_id, {
    shift_type: type,
    ...(rstart ? { rstart, rend } : {}),
    ...(e.value.shift_type ? {} : { called_in: true }),
  })
}
const backToPlan = () => actions.rosterPatch(e.value.staff_id, { shift_type: e.value.planned_type })

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
  <div class="sc" :class="[e.shift_type ? 'sh-' + e.shift_type : 'off', { open }]">
    <div class="sc-top">
      <i class="sc-av" aria-hidden="true">{{ initials }}</i>
      <div class="sc-id">
        <div class="sc-name">
          <strong>{{ displayName }}</strong>
          <span v-if="empNo" class="sc-no">{{ empNo }}</span>
        </div>
        <div class="sc-sub">
          <span v-if="e.shift_type" class="sc-shift">{{ SHIFT_LABEL[e.shift_type] }}</span>
          <span v-else class="sc-shift off" :class="{ sick: e.sick_at }">{{ e.sick_at ? 'Sick today' : 'Off today' }}</span>
          <span v-if="e.rstart || e.rend" class="sc-time">
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
            {{ e.rstart || '--:--' }}&ndash;{{ e.rend || '--:--' }}
          </span>
        </div>
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

    <div v-if="e.role || e.called_in_at || (isChanged && e.planned_type) || e.quals.length" class="sc-badges">
      <span v-if="e.role" class="sc-badge role">{{ e.role }} today</span>
      <span v-if="e.called_in_at" class="sc-badge call">Call in {{ hhmm(e.called_in_at) }}</span>
      <span v-if="isChanged && e.planned_type" class="sc-badge chg">Changed</span>
      <span v-for="q in e.quals" :key="q" class="sc-badge lic">
        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="6" width="18" height="12" rx="2" /><path d="M7 10h4M7 14h6" /></svg>
        {{ QUAL_LABEL[q] || q }}
      </span>
    </div>
    <p v-if="note" class="sc-note">{{ note }}</p>

    <div v-if="open" class="sc-edit-panel">
      <div class="sc-sec">{{ e.shift_type ? 'Shift today' : 'Call them in to cover' }}</div>
      <div class="sc-seg" role="group" :aria-label="'Shift for ' + e.name">
        <button
          v-for="(label, key) in SHIFT_LABEL"
          :key="key"
          type="button"
          :class="'sh-' + key"
          :aria-pressed="e.shift_type === key"
          @click="changeShift(key)"
        >
          {{ label }}
        </button>
      </div>
      <button v-if="isChanged && e.planned_type" type="button" class="sc-plan" @click="backToPlan">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 14L4 9l5-5M4 9h10a6 6 0 010 12h-3" /></svg>
        Back to plan: {{ SHIFT_LABEL[e.planned_type] }}
      </button>

      <template v-if="e.shift_type">
        <div class="sc-sec">Times</div>
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
.sc {
  --tone: var(--muted);
  position: relative;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 12px 12px 16px;
  margin-bottom: 8px;
}
/* shift colour as a slim bar on the left */
.sc::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  border-radius: 12px 0 0 12px;
  background: var(--tone);
}
.sc.sh-early {
  --tone: var(--early);
}
.sc.sh-late {
  --tone: var(--lateS);
}
.sc.sh-all {
  --tone: var(--long);
}
.sc.off {
  --tone: var(--line);
}
.sc.open {
  border-color: color-mix(in srgb, var(--tone) 55%, var(--line));
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
  font-weight: 700;
  background: color-mix(in srgb, var(--tone) 20%, transparent);
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
  min-width: 0;
  line-height: 1.25;
}
.sc-name strong {
  font-size: 17px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.sc-no {
  margin-left: 8px;
  white-space: nowrap;
  font-size: 13px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.sc-sub {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 3px;
  font-size: 13px;
  color: var(--muted);
}
.sc-shift {
  font-weight: 700;
  color: var(--tone);
}
.sc-shift.off {
  color: var(--muted);
  font-weight: 600;
}
.sc-shift.sick {
  color: var(--warn);
}
.sc-time {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-variant-numeric: tabular-nums;
}
.sc-time svg {
  width: 14px;
  height: 14px;
}

.sc-actions {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
}
/* round icon-only buttons, same size and shape; what they do shows as a tooltip */
.sc-btn {
  position: relative;
  flex: none;
  width: 36px;
  height: 36px;
  padding: 0;
  border-radius: 50%;
  border: 1px solid var(--line);
  background: var(--bg);
  color: var(--ink);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.sc-btn svg {
  width: 17px;
  height: 17px;
}
.sc-btn:hover {
  border-color: var(--muted);
}
.sc-btn.on {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
}
.sc-btn.sick {
  color: var(--warn);
  border-color: color-mix(in srgb, var(--warn) 40%, transparent);
  background: color-mix(in srgb, var(--warn) 10%, transparent);
}
.sc-btn.sick svg {
  stroke-width: 2.6;
}
.sc-btn.sick:hover {
  border-color: var(--warn);
}
.sc-btn.sick.armed {
  background: var(--warn);
  border-color: var(--warn);
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
  z-index: 2;
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
}
.sc-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 10px 0 0 52px;
}
.sc-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 24px;
  padding: 0 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  border: 1px solid var(--line);
  color: var(--muted);
  background: var(--bg);
}
.sc-badge svg {
  width: 14px;
  height: 14px;
}
.sc-badge.role {
  color: var(--ink);
  border-color: color-mix(in srgb, var(--ink) 35%, transparent);
}
.sc-badge.call {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}
.sc-badge.chg {
  color: var(--info);
  border-color: color-mix(in srgb, var(--info) 45%, transparent);
}
.sc-note {
  margin: 8px 0 0 52px;
  font-size: 13px;
  color: var(--muted);
}

/* ---- editor ---- */
.sc-edit-panel {
  margin-top: 12px;
  padding-top: 4px;
  border-top: 1px solid var(--line);
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
/* segmented control, iOS style: one track, the chosen shift filled in its colour */
.sc-seg {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  padding: 4px;
  border-radius: 12px;
  background: var(--bg);
  border: 1px solid var(--line);
}
.sc-seg button {
  height: 40px;
  border: 0;
  border-radius: 9px;
  background: none;
  color: var(--ink);
  font: inherit;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
}
.sc-seg button:hover:not([aria-pressed='true']) {
  background: var(--surface);
}
.sc-seg button[aria-pressed='true'] {
  color: var(--on-shift);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
}
.sc-seg button[aria-pressed='true'].sh-early {
  background: var(--early);
}
.sc-seg button[aria-pressed='true'].sh-late {
  background: var(--lateS);
}
.sc-seg button[aria-pressed='true'].sh-all {
  background: var(--long);
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
  .sc-badges,
  .sc-note {
    margin-left: 0;
  }
  .sc-av {
    width: 34px;
    height: 34px;
    font-size: 12px;
  }
  .sc-times {
    gap: 8px;
  }
}
</style>
