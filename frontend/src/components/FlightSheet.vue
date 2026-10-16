<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '../api.js'
import { FIXED_ROLES, PRESET_ROLES, SHIFT_LABEL, STATUS_LABEL } from '../constants.js'
import { shortName } from '../lib/names.js'
import { fmtElapsed, hhmm, isoFromLocal } from '../lib/time.js'
import { actions, onDuty, state, toast } from '../store.js'
import SignaturePad from './SignaturePad.vue'

const f = computed(() => state.flights.find((x) => x.id === state.openFlightId) || null)

// ---- details ----
function patch(field, value) {
  actions.patchFlight(f.value.id, { [field]: value })
}

// ---- fixed roles and crew rows ----
const holders = (role) => f.value.fixed.filter((x) => x.role === role).map((x) => x.staff_name)

/** People already working on another aircraft, so the same person is not booked twice. */
const busy = computed(() => {
  const map = new Map()
  for (const other of state.flights) {
    if (other.id === f.value.id || other.status === 'done' || other.status === 'cancelled') continue
    for (const a of other.assignments) {
      if (!a.staff_id) continue
      const prev = map.get(a.staff_id)
      if (!prev || other.status === 'cleaning') map.set(a.staff_id, { no: other.flight_no, status: other.status })
    }
  }
  return map
})

// Each role/section can now hold more than one person, so options are no longer scoped to a single
// row -- a person already on this flight anywhere just can't be picked again.
const assignedIds = computed(() => new Set(f.value.assignments.filter((a) => a.staff_id).map((a) => a.staff_id)))
function personOptions() {
  return onDuty.value.map((e) => {
    const other = busy.value.get(e.staff_id)
    const info = [SHIFT_LABEL[e.shift_type] || 'off', e.called_in_at ? 'call in' : null, e.role].filter(Boolean).join(', ')
    const tag = other ? (other.status === 'cleaning' ? ` - cleaning ${other.no}` : ` - also on ${other.no}`) : ''
    return {
      id: e.staff_id,
      label: `${shortName(e.name)} (${info})${tag}`,
      disabled: assignedIds.value.has(e.staff_id) || (!!other && other.status === 'cleaning'),
      fixed: !!e.role,
    }
  })
}
const cleanerOptions = computed(() => personOptions().filter((o) => !o.fixed))
const fixedPersonOptions = computed(() => personOptions().filter((o) => o.fixed))

// The Toilet section on an aircraft can only be done by whoever holds the Toilet fixed role today,
// unlike the other sections, which are open to anyone on duty.
const toiletOptions = computed(() =>
  f.value.fixed
    .filter((x) => x.role === 'Toilet')
    .map((x) => {
      const other = busy.value.get(x.staff_id)
      const tag = other ? (other.status === 'cleaning' ? ` - cleaning ${other.no}` : ` - also on ${other.no}`) : ''
      return {
        id: x.staff_id,
        label: `${shortName(x.staff_name)}${tag}`,
        disabled: assignedIds.value.has(x.staff_id) || (!!other && other.status === 'cleaning'),
      }
    }),
)

// Group the flat assignment rows by role so each section can show multiple people as chips.
const roleGroups = computed(() => {
  const order = []
  const byRole = new Map()
  f.value.assignments.forEach((a, index) => {
    let g = byRole.get(a.role)
    if (!g) {
      g = { role: a.role, rows: [] }
      byRole.set(a.role, g)
      order.push(g)
    }
    g.rows.push({ ...a, index })
  })
  return order
})
const peopleIn = (g) => g.rows.filter((r) => r.staff_id)

const rowsPayload = () => f.value.assignments.map((a) => ({ role: a.role, staff_id: a.staff_id }))

function addPerson(role, event) {
  const staffId = event.target.value ? Number(event.target.value) : null
  event.target.value = ''
  if (!staffId) return
  const rows = rowsPayload()
  const emptyIndex = rows.findIndex((r) => r.role === role && !r.staff_id)
  if (emptyIndex >= 0) rows[emptyIndex].staff_id = staffId
  else rows.push({ role, staff_id: staffId })
  actions.saveAssignments(f.value.id, rows)
}
function removePerson(role, index) {
  const rows = rowsPayload()
  const roleRows = rows.filter((r) => r.role === role)
  if (roleRows.length <= 1) rows[index].staff_id = null // keep the section, just clear it
  else rows.splice(index, 1)
  actions.saveAssignments(f.value.id, rows)
}
function removeRoleGroup(role) {
  const rows = rowsPayload().filter((r) => r.role !== role)
  actions.saveAssignments(f.value.id, rows)
}
const newRole = ref('')
function addRow() {
  const role = newRole.value.trim()
  if (!role) return toast('Pick or type a role')
  actions.saveAssignments(f.value.id, [...rowsPayload(), { role, staff_id: null }])
  newRole.value = ''
}

// ---- timing ----
const now = ref(Date.now())
let ticker = null
onMounted(() => {
  document.body.classList.add('lock')
  ticker = setInterval(() => {
    now.value = Date.now()
  }, 1000)
})
onUnmounted(() => {
  document.body.classList.remove('lock')
  clearInterval(ticker)
})
const elapsed = computed(() =>
  f.value && f.value.started_at && !f.value.finished_at ? fmtElapsed(now.value - new Date(f.value.started_at).getTime()) : '',
)
async function changeTime(field, event) {
  const value = event.target.value
  if (!value) return
  const before = hhmm(f.value[field])
  const result = await actions.setTimes(f.value.id, { [field]: isoFromLocal(f.value.work_date, value) })
  if (result === undefined) event.target.value = before
}

// ---- signature ----
const pad = ref(null)
const detail = ref(null) // the signature image is only included when a single flight is loaded
watch(
  () => [f.value && f.value.id, f.value && f.value.has_signature, f.value && f.value.signed_at],
  async () => {
    if (!f.value || !f.value.has_signature) {
      detail.value = null
      return
    }
    try {
      detail.value = await api.flights.get(f.value.id)
    } catch {
      detail.value = null
    }
  },
  { immediate: true },
)
async function saveSignature() {
  if (pad.value.isEmpty()) return toast('Ask the cabin crew to sign in the box')
  // No name field to ask the cabin crew for -- the flight number is enough to identify which
  // sign-off this is.
  await actions.signFlight(f.value.id, f.value.flight_no, pad.value.toDataURL())
}
</script>

<template>
  <div v-if="f" class="sheet" role="dialog" aria-modal="true" aria-label="Flight">
    <div class="sbar">
      <button class="ghost" @click="actions.closeSheet()">Close</button>
      <h2>{{ f.flight_no }}</h2>
      <em class="pill">{{ STATUS_LABEL[f.status] }}</em>
    </div>

    <div class="sbody">
      <details class="blk">
          <summary>Flight details</summary>
          <div class="fields">
            <label class="f">Flight number
              <input type="text" :value="f.flight_no" autocomplete="off" @change="patch('flight_no', $event.target.value)" />
            </label>
            <label class="f">Airline
              <input type="text" :value="f.airline" autocomplete="off" @change="patch('airline', $event.target.value)" />
            </label>
            <div class="grid2">
              <label class="f">Rego
                <input type="text" :value="f.rego" autocomplete="off" @change="patch('rego', $event.target.value)" />
              </label>
              <label class="f">Gate / bay
                <input type="text" :value="f.gate" autocomplete="off" @change="patch('gate', $event.target.value)" />
              </label>
            </div>
            <div class="grid2">
              <label class="f">Scheduled time
                <input type="time" :value="f.sched" @change="$event.target.value && patch('sched', $event.target.value)" />
              </label>
              <label class="f">Expected time (ETA)
                <input type="time" :value="f.eta" @change="$event.target.value && patch('eta', $event.target.value)" />
              </label>
            </div>
            <div class="two">
              <button class="btn2" :aria-pressed="f.landed" @click="patch('landed', !f.landed)">
                {{ f.landed ? 'Landed (tap to undo)' : 'Mark landed' }}
              </button>
              <button class="btn2" @click="patch('cancelled', !f.cancelled)">
                {{ f.cancelled ? 'Restore flight' : 'Mark cancelled' }}
              </button>
            </div>
          </div>
        </details>

        <section class="blk">
          <h3>Time on aircraft</h3>
          <button v-if="!f.started_at" class="big go" @click="actions.startFlight(f.id)">Start cleaning</button>
          <template v-else-if="!f.finished_at">
            <div class="clock">{{ elapsed }}</div>
            <button class="big stop" @click="actions.finishFlight(f.id)">Finish cleaning</button>
          </template>
          <template v-else>
            <div class="clock done">{{ f.minutes }} min</div>
            <button class="btn2" style="width: 100%" @click="actions.reopenFlight(f.id)">Reopen</button>
          </template>
          <div v-if="f.started_at" class="times">
            <label class="f">Started
              <input type="time" :value="hhmm(f.started_at)" @change="changeTime('started_at', $event)" />
            </label>
            <label v-if="f.finished_at" class="f">Finished
              <input type="time" :value="hhmm(f.finished_at)" @change="changeTime('finished_at', $event)" />
            </label>
            <span v-else></span>
          </div>
        </section>

        <section class="blk">
          <h3>Fixed all day</h3>
          <p v-if="f.started_at" class="muted" style="margin: 0 0 10px; font-size: 13px">
            As at {{ hhmm(f.started_at) }}, when cleaning started -- later changes on the Crew tab do not rewrite this record.
          </p>
          <div v-for="role in FIXED_ROLES" :key="role" class="frow">
            <span class="lbl">{{ role }}</span>
            <span class="who" :class="{ none: !holders(role).length }">
              {{ holders(role).length ? holders(role).join(', ') : 'Not set. Set it on the Crew tab.' }}
            </span>
          </div>
        </section>

        <section class="blk">
          <h3>On this aircraft</h3>
          <p v-if="!onDuty.length" class="muted" style="margin-top: 0">
            Nobody is on today's roster. Add people on the Crew tab first.
          </p>
          <div v-for="g in roleGroups" :key="g.role" class="rolegrp">
            <div class="rghead">
              <span class="rglbl">{{ g.role }}</span>
              <button class="x sm" :aria-label="'Remove ' + g.role" @click="removeRoleGroup(g.role)">&times;</button>
            </div>
            <div class="ppl">
              <span v-for="row in peopleIn(g)" :key="row.index" class="pchip">
                {{ shortName(row.staff_name) }}
                <button :aria-label="'Remove ' + row.staff_name + ' from ' + g.role" @click="removePerson(g.role, row.index)">&times;</button>
              </span>
              <span v-if="g.role === 'Toilet' && !toiletOptions.length" class="muted" style="font-size: 14px">
                Nobody is Toilet today. Set it on the Crew tab.
              </span>
              <select v-else class="addperson" :aria-label="'Add person to ' + g.role" @change="addPerson(g.role, $event)">
                <option value="">+ Add person</option>
                <template v-if="g.role === 'Toilet'">
                  <option v-for="o in toiletOptions" :key="o.id" :value="o.id" :disabled="o.disabled">{{ o.label }}</option>
                </template>
                <template v-else>
                  <optgroup v-if="cleanerOptions.length" label="Cleaners">
                    <option v-for="o in cleanerOptions" :key="o.id" :value="o.id" :disabled="o.disabled">{{ o.label }}</option>
                  </optgroup>
                  <optgroup v-if="fixedPersonOptions.length" label="Driver, toilet, truck">
                    <option v-for="o in fixedPersonOptions" :key="o.id" :value="o.id" :disabled="o.disabled">{{ o.label }}</option>
                  </optgroup>
                </template>
              </select>
            </div>
          </div>
          <div class="addrow">
            <input v-model="newRole" type="text" list="role-list" placeholder="Role or section" aria-label="Role to add" autocomplete="off" />
            <datalist id="role-list"><option v-for="p in PRESET_ROLES" :key="p" :value="p"></option></datalist>
            <button class="btn2" @click="addRow">Add role</button>
          </div>
        </section>

        <section class="blk">
          <h3>Notes</h3>
          <textarea
            :value="f.notes"
            aria-label="Notes"
            placeholder="Stains, lost property, damage, anything to hand over"
            @change="patch('notes', $event.target.value)"
          ></textarea>
        </section>

        <section class="blk">
          <h3>Cabin crew sign-off</h3>
          <template v-if="f.has_signature">
            <div class="sigbox">
              <img v-if="detail && detail.sig_image" :src="detail.sig_image" alt="Cabin crew signature" />
            </div>
            <p>Signed at {{ hhmm(f.signed_at) }}</p>
            <button class="btn2" @click="actions.unsignFlight(f.id)">Sign again</button>
          </template>
          <p v-else-if="!f.finished_at" class="muted" style="margin: 0">
            Finish cleaning first, then hand the phone to the cabin crew to sign.
          </p>
          <template v-else>
            <SignaturePad ref="pad" />
            <div class="two">
              <button class="btn2" @click="pad.clear()">Clear</button>
              <button class="btn" @click="saveSignature">Save signature</button>
            </div>
          </template>
        </section>
    </div>
  </div>
</template>
