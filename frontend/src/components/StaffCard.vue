<script setup>
import { computed, ref } from 'vue'
import { QUAL_LABEL, SHIFT_LABEL, SHIFT_TIMES } from '../constants.js'
import { hhmm } from '../lib/time.js'
import { actions, state, toast } from '../store.js'

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
const callSick = () => actions.rosterPatch(e.value.staff_id, { sick: true })
const undoSick = () => actions.rosterPatch(e.value.staff_id, { sick: false })
async function changeRosterTime(field, event) {
  const value = event.target.value
  if (!value) return
  const before = e.value[field]
  const result = await actions.rosterPatch(e.value.staff_id, { [field]: value })
  if (result === undefined) event.target.value = before // the server said no, show the old time again
}
</script>

<template>
  <div class="card person" :class="e.shift_type ? 'sh-' + e.shift_type : 'off'">
    <div class="nm">
      <div class="namerow">
        <strong>{{ e.name }}</strong>
        <span v-if="e.shift_type" class="tag" :class="'sh-' + e.shift_type">{{ SHIFT_LABEL[e.shift_type] }}</span>
        <span v-if="e.role" class="tag role">{{ e.role }} today</span>
        <span v-if="e.called_in_at" class="tag call">Call in</span>
        <span v-if="e.sick_at" class="tag sick">Sick</span>
        <span v-if="isChanged && e.planned_type" class="tag chg">Changed</span>
      </div>
      <div style="display: flex; gap: 6px">
        <button v-if="e.shift_type" class="btn2 danger" style="min-height: 36px; padding: 0 14px" @click="callSick">
          Call sick
        </button>
        <button class="btn2" style="min-height: 36px; padding: 0 14px" :aria-expanded="open" @click="open = !open">
          {{ open ? 'Done' : e.shift_type ? 'Edit' : 'Call in' }}
        </button>
      </div>
    </div>
    <div v-if="e.rstart || e.rend" class="meta">{{ e.rstart || '--:--' }}&ndash;{{ e.rend || '--:--' }}</div>
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
        <label class="f">Start
          <input type="time" :value="e.rstart" @change="changeRosterTime('rstart', $event)" />
        </label>
        <label class="f">Indicative end
          <input type="time" :value="e.rend" @change="changeRosterTime('rend', $event)" />
        </label>
      </div>
      <button v-else-if="e.sick_at" class="btn2" style="width: 100%" @click="undoSick">Undo sick</button>
    </template>
  </div>
</template>
