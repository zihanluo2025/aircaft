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
  <div class="card person" :class="e.shift_type ? 'sh-' + e.shift_type : 'off'">
    <div class="namerow">
      <strong>{{ e.name }}</strong>
      <span v-if="e.role" class="tag role">{{ e.role }} today</span>
      <span v-if="e.called_in_at" class="tag call">Call in</span>
      <span v-if="e.sick_at" class="tag sick">Sick</span>
      <span v-if="isChanged && e.planned_type" class="tag chg">Changed</span>
    </div>
    <div class="cardrow">
      <span v-if="e.rstart || e.rend" class="meta">{{ e.rstart || '--:--' }}&ndash;{{ e.rend || '--:--' }}</span>
      <span v-else></span>
      <div class="nmactions">
        <button class="btn2" style="min-height: 36px; padding: 0 14px" :aria-expanded="open" @click="open = !open">
          {{ open ? 'Done' : e.shift_type ? 'Edit' : 'Call in' }}
        </button>
        <button
          v-if="e.shift_type"
          class="btn2 danger icn"
          :class="{ armed: confirmSick }"
          :aria-label="confirmSick ? 'Tap again to confirm call sick' : 'Call sick'"
          :title="confirmSick ? 'Tap again to confirm' : 'Call sick'"
          @click="callSick"
        >
          <svg
            width="19"
            height="19"
            viewBox="0 0 24 24"
            aria-hidden="true"
            fill="none"
            stroke="currentColor"
            stroke-width="2.2"
            stroke-linecap="round"
          >
            <line x1="12" y1="4.5" x2="12" y2="14.5" />
            <line x1="12" y1="19" x2="12" y2="19.01" />
          </svg>
        </button>
      </div>
    </div>
    <div v-if="e.quals.length" class="meta">Qualified: {{ e.quals.map((q) => QUAL_LABEL[q] || q).join(', ') }}</div>
    <div v-if="e.called_in_at" class="meta">Called in at {{ hhmm(e.called_in_at) }}</div>
    <div v-if="note" class="meta">{{ note }}</div>

    <template v-if="open">
      <div class="meta">{{ e.shift_type ? 'Change their shift today' : 'Call them in to cover' }}</div>
      <div class="seg" role="group" :aria-label="'Shift for ' + e.name">
        <button
          v-for="(label, key) in SHIFT_LABEL"
          :key="key"
          :class="'sh-' + key"
          :aria-pressed="e.shift_type === key"
          @click="changeShift(key)"
        >
          {{ label }}
        </button>
      </div>
      <button v-if="isChanged && e.planned_type" class="btn2" @click="backToPlan">
        Back to plan: {{ SHIFT_LABEL[e.planned_type] }}
      </button>

      <div v-if="e.shift_type" class="two">
        <TimeField label="Start" :model-value="e.rstart" @update:model-value="(v) => changeRosterTime('rstart', v)" />
        <TimeField label="Indicative end" :model-value="e.rend" @update:model-value="(v) => changeRosterTime('rend', v)" />
      </div>
      <button v-else-if="e.sick_at" class="btn2" style="width: 100%" @click="undoSick">Undo sick</button>

      <div class="meta" style="margin-top: 4px">Qualified for</div>
      <div class="skills" role="group" :aria-label="'Qualifications for ' + e.name">
        <button v-for="q in QUAL_ROLES" :key="q" class="sk" :aria-pressed="e.quals.includes(q)" @click="toggleQual(q)">
          {{ QUAL_LABEL[q] }}
        </button>
      </div>
    </template>
  </div>
</template>
