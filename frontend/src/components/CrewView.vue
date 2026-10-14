<script setup>
import { computed, ref } from 'vue'
import { FIXED_ROLES, QUAL_LABEL, QUAL_ROLES, SHIFT_LABEL, SHIFT_NAME } from '../constants.js'
import { hhmm } from '../lib/time.js'
import { actions, onDuty, state, toast } from '../store.js'

const filter = ref('every')
const editId = ref(null)
const pickRole = ref(null)
const callMode = ref(false)
const teamOpen = ref(false)
const importOpen = ref(false)
const impText = ref('')
const impRes = ref(null)
const confirmRemove = ref(null)
const newName = ref('')
const newQuals = ref([])

const entries = computed(() => state.roster.entries)
const hasPlan = computed(() => state.roster.has_plan)
const isChanged = (e) => hasPlan.value && !!e.shift_type && e.planned_type !== e.shift_type

const groups = computed(() => {
  const on = onDuty.value
  return {
    every: on,
    early: on.filter((e) => e.shift_type === 'early'),
    late: on.filter((e) => e.shift_type === 'late'),
    all: on.filter((e) => e.shift_type === 'all'),
    call: on.filter((e) => e.called_in_at),
    changed: on.filter(isChanged),
  }
})
const chips = computed(() => {
  const list = [
    ['every', 'Everyone'],
    ['early', 'Early'],
    ['late', 'Late'],
    ['all', 'All day'],
    ['call', 'Call in'],
  ]
  if (hasPlan.value) list.push(['changed', 'Changed'])
  return list
})
const visible = computed(() => groups.value[chips.value.some((c) => c[0] === filter.value) ? filter.value : 'every'])

const entryByStaff = computed(() => new Map(entries.value.map((e) => [e.staff_id, e])))
const offDuty = computed(() => {
  const on = new Set(onDuty.value.map((e) => e.staff_id))
  return state.staff.filter((s) => !on.has(s.id))
})

function note(e) {
  if (!isChanged(e)) return ''
  if (e.planned_type) return `Planned ${SHIFT_LABEL[e.planned_type]}, changed today`
  return e.called_in_at ? '' : 'Added today, not on the planned roster'
}
function plannedNote(staff) {
  const entry = entryByStaff.value.get(staff.id)
  return entry && entry.planned_type ? `Planned ${SHIFT_LABEL[entry.planned_type]}, taken off today` : ''
}

// ---- fixed roles for the day ----
const holders = (role) => onDuty.value.filter((e) => e.role === role).map((e) => e.name)
const eligible = (role) => (QUAL_ROLES.includes(role) ? onDuty.value.filter((e) => e.quals.includes(role)) : onDuty.value)
const rolesFor = (e) => FIXED_ROLES.filter((r) => r === 'Toilet' || e.quals.includes(r))

// ---- roster changes ----
const changeShift = (e, type) => actions.rosterPatch(e.staff_id, { shift_type: type })
const toggleRole = (e, role) => actions.rosterPatch(e.staff_id, { role: e.role === role ? null : role })
const toggleCall = (e) => actions.rosterPatch(e.staff_id, { called_in: !e.called_in_at })
const backToPlan = (e) => actions.rosterPatch(e.staff_id, { shift_type: e.planned_type })
async function changeRosterTime(e, field, event) {
  const value = event.target.value
  if (!value) return
  const before = e[field]
  const result = await actions.rosterPatch(e.staff_id, { [field]: value })
  if (result === undefined) event.target.value = before // the server said no, show the old time again
}
async function takeOff(e) {
  const result = await actions.rosterPatch(e.staff_id, { shift_type: null })
  if (editId.value === e.staff_id) editId.value = null
  if (result && result.unassigned) {
    toast(`${e.name} taken off, cleared from ${result.unassigned} job${result.unassigned > 1 ? 's' : ''}`)
  }
}
function addToRoster(staff, type) {
  actions.rosterPatch(staff.id, { shift_type: type, ...(callMode.value ? { called_in: true } : {}) })
}

// ---- roster import ----
async function preview() {
  impRes.value = (await actions.importPreview(impText.value)) || null
}
async function applyImport() {
  const result = await actions.importApply(impText.value)
  if (result) {
    impText.value = ''
    impRes.value = null
    importOpen.value = false
  }
}
function onFile(event) {
  const file = event.target.files && event.target.files[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    impText.value = String(reader.result || '')
    preview()
  }
  reader.onerror = () => toast('Could not read that file')
  reader.readAsText(file)
}

// ---- team ----
function toggleQual(staff, role) {
  const quals = staff.quals.includes(role) ? staff.quals.filter((q) => q !== role) : [...staff.quals, role]
  actions.patchStaff(staff.id, { quals })
}
function toggleNewQual(role) {
  newQuals.value = newQuals.value.includes(role) ? newQuals.value.filter((q) => q !== role) : [...newQuals.value, role]
}
async function addStaff() {
  const name = newName.value.trim()
  if (!name) return toast('Enter a name')
  const result = await actions.addStaff({ name, team: state.shift, quals: newQuals.value })
  if (result) {
    newName.value = ''
    newQuals.value = []
  }
}
async function removeStaff(staff) {
  if (confirmRemove.value !== staff.id) {
    confirmRemove.value = staff.id
    return
  }
  confirmRemove.value = null
  await actions.removeStaff(staff.id)
}
</script>

<template>
  <h2 style="margin-top: 6px">Fixed all day</h2>
  <p class="muted" style="margin: 0 0 8px; font-size: 14px">Tap a role to choose who does it today.</p>
  <div class="fx">
    <button
      v-for="role in FIXED_ROLES"
      :key="role"
      :class="{ on: pickRole === role }"
      :aria-expanded="pickRole === role"
      @click="pickRole = pickRole === role ? null : role"
    >
      <span>{{ role }}</span>
      <b :class="{ none: !holders(role).length }">{{ holders(role).length ? holders(role).join(', ') : 'Not set' }}</b>
      <small>{{ eligible(role).length }} {{ QUAL_ROLES.includes(role) ? 'qualified in' : 'on duty' }}</small>
    </button>
  </div>
  <div v-if="pickRole" class="card" style="margin-top: 8px">
    <div class="meta" style="margin-bottom: 8px; font-size: 14px">
      Who is {{ pickRole }} today? {{ QUAL_ROLES.includes(pickRole) ? 'Qualified people on duty:' : 'Anyone on duty:' }}
    </div>
    <p v-if="!eligible(pickRole).length" class="muted" style="margin: 0 0 10px">
      {{ QUAL_ROLES.includes(pickRole) ? `Nobody on duty is qualified for ${pickRole}. Set qualifications under Manage staff.` : 'Nobody is on duty yet.' }}
    </p>
    <div v-else class="skills">
      <button
        v-for="e in eligible(pickRole)"
        :key="e.staff_id"
        class="sk big"
        :aria-pressed="e.role === pickRole"
        @click="toggleRole(e, pickRole)"
      >
        {{ e.name }} ({{ SHIFT_LABEL[e.shift_type] }}{{ e.role && e.role !== pickRole ? ', ' + e.role + ' today' : '' }})
      </button>
    </div>
    <button class="btn2" style="margin-top: 10px; width: 100%" @click="pickRole = null">Done</button>
  </div>

  <h2>On duty today ({{ onDuty.length }})</h2>
  <div class="chips" role="group" aria-label="Filter by shift">
    <button v-for="c in chips" :key="c[0]" class="chip" :aria-pressed="filter === c[0]" @click="filter = c[0]">
      {{ c[1] }} ({{ groups[c[0]].length }})
    </button>
  </div>
  <div style="height: 8px"></div>

  <div v-if="!onDuty.length" class="empty">
    <p>No roster for this day yet. Import the roster from your manager, or add people below.</p>
    <button class="btn" @click="importOpen = true">Import roster</button>
  </div>
  <div v-else-if="!visible.length" class="empty"><p>Nobody in this group.</p></div>

  <div v-for="e in visible" :key="e.staff_id" class="card person" :class="'sh-' + e.shift_type">
    <div class="nm">
      <div class="namerow">
        <strong>{{ e.name }}</strong>
        <span class="tag" :class="'sh-' + e.shift_type">{{ SHIFT_LABEL[e.shift_type] }}</span>
        <span v-if="e.role" class="tag role">{{ e.role }} today</span>
        <span v-if="e.called_in_at" class="tag call">Call in</span>
        <span v-if="isChanged(e) && e.planned_type" class="tag chg">Changed</span>
      </div>
      <button
        class="btn2"
        style="min-height: 36px; padding: 0 14px"
        :aria-expanded="editId === e.staff_id"
        @click="editId = editId === e.staff_id ? null : e.staff_id"
      >
        {{ editId === e.staff_id ? 'Done' : 'Edit' }}
      </button>
    </div>
    <div v-if="e.rstart || e.rend" class="meta">{{ e.rstart || '--:--' }}&ndash;{{ e.rend || '--:--' }}</div>
    <div v-if="e.quals.length" class="meta">Qualified: {{ e.quals.map((q) => QUAL_LABEL[q] || q).join(', ') }}</div>
    <div v-if="e.called_in_at" class="meta">Called in at {{ hhmm(e.called_in_at) }}</div>
    <div v-if="note(e)" class="meta">{{ note(e) }}</div>

    <template v-if="editId === e.staff_id">
      <div class="seg" role="group" :aria-label="'Shift for ' + e.name">
        <button
          v-for="(label, key) in SHIFT_LABEL"
          :key="key"
          :class="'sh-' + key"
          :aria-pressed="e.shift_type === key"
          @click="changeShift(e, key)"
        >
          {{ label }}
        </button>
      </div>
      <button v-if="isChanged(e) && e.planned_type" class="btn2" @click="backToPlan(e)">
        Back to plan: {{ SHIFT_LABEL[e.planned_type] }}
      </button>
      <div class="two">
        <label class="f">Start
          <input type="time" :value="e.rstart" @change="changeRosterTime(e, 'rstart', $event)" />
        </label>
        <label class="f">Indicative end
          <input type="time" :value="e.rend" @change="changeRosterTime(e, 'rend', $event)" />
        </label>
      </div>
      <div class="meta">Fixed role today (Driver and Truck need a qualification, leave empty for cleaner)</div>
      <div class="seg role" role="group" :aria-label="'Fixed role for ' + e.name">
        <button v-for="role in rolesFor(e)" :key="role" :aria-pressed="e.role === role" @click="toggleRole(e, role)">
          {{ role }}
        </button>
      </div>
      <div class="acts">
        <button class="btn2 callbtn" :aria-pressed="!!e.called_in_at" @click="toggleCall(e)">Call in</button>
        <button class="btn2" @click="takeOff(e)">Take off roster</button>
      </div>
    </template>
  </div>

  <h2>Add to today's roster</h2>
  <div class="seg two" role="group" aria-label="How are they joining">
    <button class="mode-plan" :aria-pressed="!callMode" @click="callMode = false">Planned</button>
    <button class="mode-call" :aria-pressed="callMode" @click="callMode = true">Call in</button>
  </div>
  <p class="muted" style="margin: 6px 0 10px; font-size: 14px">
    {{ callMode ? 'People you add now are tagged Call in, with the time you called them.' : "Choose a shift to put someone on today's roster." }}
  </p>
  <div v-if="!state.staff.length" class="empty"><p>No staff yet. Import a roster or add them under Manage staff below.</p></div>
  <div v-else-if="!offDuty.length" class="empty"><p>Everyone is already on today's roster.</p></div>
  <div v-for="s in offDuty" :key="s.id" class="card person off">
    <div class="nm"><strong>{{ s.name }}</strong></div>
    <div v-if="plannedNote(s)" class="meta">{{ plannedNote(s) }}</div>
    <div class="seg" role="group" :aria-label="'Add ' + s.name + ' to roster'">
      <button v-for="(label, key) in SHIFT_LABEL" :key="key" :class="'sh-' + key" @click="addToRoster(s, key)">{{ label }}</button>
    </div>
  </div>

  <details class="blk" style="margin-top: 18px" :open="importOpen" @toggle="importOpen = $event.target.open">
    <summary>Import roster</summary>
    <p class="muted" style="margin-top: 0; font-size: 14px">
      Paste from Excel or choose a CSV file, in any of these layouts. Dates are read as day first, like
      13/10/2026. The roster goes into the <b>{{ SHIFT_NAME[state.shift] }} shift</b> selected at the top.
    </p>
    <ul class="muted" style="margin: 0 0 10px; padding-left: 18px; font-size: 14px">
      <li>
        One row per person, with a paired <b>Start</b> / <b>Indicative End</b> column for each date, like the
        weekly export from the roster system. Add trailing <b>Driver Licence</b> / <b>Truck Licence</b>
        columns to mark who holds each. Early/Late/All day is worked out from the actual times.
      </li>
      <li>One row per person with a single Early/Late/All day column per date.</li>
      <li>One row per shift, with the columns Date, Name, Shift and an optional Role (Driver or Truck).</li>
    </ul>
    <textarea
      id="impTxt"
      v-model="impText"
      aria-label="Roster text"
      placeholder="Name,13/10/2026,14/10/2026&#10;Alex K,Early,All day&#10;Priya S,Late,Off"
      @input="impRes = null"
    ></textarea>
    <label class="f" style="margin-top: 10px">CSV file
      <input type="file" accept=".csv,.tsv,.txt" @change="onFile" />
    </label>
    <div class="two">
      <button class="btn2" @click="preview">Preview</button>
      <button class="btn" :disabled="!impRes || !impRes.days" @click="applyImport">Import</button>
    </div>
    <template v-if="impRes">
      <p v-if="!impRes.days" class="impres bad">No shifts found. Check the layout described above and try again.</p>
      <p v-else class="impres">
        Found {{ impRes.days }} day{{ impRes.days > 1 ? 's' : '' }}, {{ impRes.people }} people ({{ impRes.new_people }} new),
        {{ impRes.shifts }} shifts. Days that already have a roster will be replaced.
      </p>
      <p v-if="impRes.bad.length" class="impres bad">
        Could not read {{ impRes.bad.length }} row{{ impRes.bad.length > 1 ? 's' : '' }}, for example: {{ impRes.bad.slice(0, 3).join('; ') }}
      </p>
    </template>
  </details>

  <details class="blk" :open="teamOpen" @toggle="teamOpen = $event.target.open">
    <summary>Manage {{ SHIFT_NAME[state.shift].toLowerCase() }} staff ({{ state.staff.length }})</summary>
    <div v-for="s in state.staff" :key="s.id" class="card person off">
      <div class="nm">
        <strong>{{ s.name }}</strong>
        <button
          class="btn2"
          :class="{ danger: confirmRemove === s.id }"
          style="min-height: 36px; padding: 0 10px"
          @click="removeStaff(s)"
        >
          {{ confirmRemove === s.id ? 'Tap again to remove' : 'Remove' }}
        </button>
      </div>
      <div class="meta">Qualified for</div>
      <div class="skills" role="group" :aria-label="'Qualifications for ' + s.name">
        <button v-for="q in QUAL_ROLES" :key="q" class="sk" :aria-pressed="s.quals.includes(q)" @click="toggleQual(s, q)">{{ QUAL_LABEL[q] }}</button>
      </div>
    </div>
    <h3 style="margin-top: 14px">Add staff member</h3>
    <div class="addp">
      <label class="f">Name <input v-model="newName" type="text" autocomplete="off" placeholder="e.g. Alex K" /></label>
      <div class="meta">Qualified for</div>
      <div class="skills" role="group" aria-label="Qualifications">
        <button v-for="q in QUAL_ROLES" :key="q" class="sk" :aria-pressed="newQuals.includes(q)" @click="toggleNewQual(q)">{{ QUAL_LABEL[q] }}</button>
      </div>
      <button class="btn" @click="addStaff">Add to staff</button>
    </div>
  </details>
</template>
