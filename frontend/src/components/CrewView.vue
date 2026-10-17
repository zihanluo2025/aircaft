<script setup>
import { computed, ref } from 'vue'
import { FIXED_ROLES, LICENCE_REQUIRED_ROLES, SHIFT_LABEL, SHIFT_NAME } from '../constants.js'
import { shortName } from '../lib/names.js'
import { actions, onDuty, state, toast } from '../store.js'
import StaffCard from './StaffCard.vue'

const filter = ref('every')
const pickRole = ref(null)
const importOpen = ref(false)
const impText = ref('')
const impRes = ref(null)

const hasPlan = computed(() => state.roster.has_plan)
const isChanged = (e) => hasPlan.value && !!e.shift_type && e.planned_type !== e.shift_type

// Everyone on the team, whether or not they have a roster row for today -- someone with no row yet
// (never imported, or a brand-new hire) gets a placeholder so the same card/edit panel covers them.
const everyone = computed(() => {
  const byStaff = new Map(state.roster.entries.map((e) => [e.staff_id, e]))
  return state.staff.map(
    (s) =>
      byStaff.get(s.id) || {
        staff_id: s.id,
        name: s.name,
        quals: s.quals,
        shift_type: null,
        planned_type: null,
        role: null,
        called_in_at: null,
        sick_at: null,
        rstart: '',
        rend: '',
      },
  )
})
const onDutyList = computed(() => everyone.value.filter((e) => e.shift_type))
const offDutyList = computed(() => everyone.value.filter((e) => !e.shift_type))

const groups = computed(() => {
  const all = onDutyList.value
  return {
    every: all,
    early: all.filter((e) => e.shift_type === 'early'),
    late: all.filter((e) => e.shift_type === 'late'),
    all: all.filter((e) => e.shift_type === 'all'),
    call: all.filter((e) => e.called_in_at),
    sick: all.filter((e) => e.sick_at),
    changed: all.filter(isChanged),
  }
})
const chips = computed(() => {
  const list = [
    ['every', 'Everyone'],
    ['early', 'Early'],
    ['late', 'Late'],
    ['all', 'All day'],
    ['call', 'Call in'],
    ['sick', 'Sick'],
  ]
  if (hasPlan.value) list.push(['changed', 'Changed'])
  return list
})
const visible = computed(() => groups.value[chips.value.some((c) => c[0] === filter.value) ? filter.value : 'every'])

// ---- fixed roles for the day: actually on duty, not just "has a card" ----
const holders = (role) => onDuty.value.filter((e) => e.role === role).map((e) => shortName(e.name))
const eligible = (role) =>
  LICENCE_REQUIRED_ROLES.includes(role) ? onDuty.value.filter((e) => e.quals.includes(role)) : onDuty.value
const toggleRole = (e, role) => actions.rosterPatch(e.staff_id, { role: e.role === role ? null : role })

// ---- roster import ----
const impFile = ref(null) // an .xlsx File goes to the server as-is; anything else is read as text
async function preview() {
  impRes.value = (await (impFile.value ? actions.importPreviewFile(impFile.value) : actions.importPreview(impText.value))) || null
}
async function applyImport() {
  const result = await (impFile.value ? actions.importApplyFile(impFile.value) : actions.importApply(impText.value))
  if (result) {
    impText.value = ''
    impFile.value = null
    impRes.value = null
    importOpen.value = false
  }
}
function onFile(event) {
  const file = event.target.files && event.target.files[0]
  if (!file) return
  if (file.name.toLowerCase().endsWith('.xlsx')) {
    impFile.value = file
    impText.value = ''
    preview()
    return
  }
  impFile.value = null
  const reader = new FileReader()
  reader.onload = () => {
    impText.value = String(reader.result || '')
    preview()
  }
  reader.onerror = () => toast('Could not read that file')
  reader.readAsText(file)
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
      <span v-if="holders(role).length" class="fxcount">{{ holders(role).length }}</span>
      <span>{{ role }}</span>
      <b :class="{ none: !holders(role).length }">{{ holders(role).length ? holders(role).join(', ') : 'Not set' }}</b>
      <small>{{ eligible(role).length }} {{ LICENCE_REQUIRED_ROLES.includes(role) ? 'qualified in' : 'on duty' }}</small>
    </button>
  </div>
  <div v-if="pickRole" class="card" style="margin-top: 8px">
    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; margin-bottom: 8px">
      <div class="meta" style="font-size: 14px">
        Who is {{ pickRole }} today? {{ LICENCE_REQUIRED_ROLES.includes(pickRole) ? 'Qualified people on duty:' : 'Anyone on duty:' }}
      </div>
      <button class="btn2" style="min-height: 36px; padding: 0 14px; flex: none" @click="pickRole = null">Done</button>
    </div>
    <p v-if="!eligible(pickRole).length" class="muted" style="margin: 0 0 10px">
      {{ LICENCE_REQUIRED_ROLES.includes(pickRole) ? `Nobody on duty is qualified for ${pickRole}. Set qualifications below.` : 'Nobody is on duty yet.' }}
    </p>
    <div v-else class="skills pickgrid">
      <button
        v-for="e in eligible(pickRole)"
        :key="e.staff_id"
        class="sk big"
        :aria-pressed="e.role === pickRole"
        :disabled="!!e.role && e.role !== pickRole"
        @click="toggleRole(e, pickRole)"
      >
        {{ shortName(e.name) }} ({{ SHIFT_LABEL[e.shift_type] }}{{ e.role && e.role !== pickRole ? ', ' + e.role + ' today' : '' }})
      </button>
    </div>
  </div>

  <h2>On duty today ({{ onDutyList.length }})</h2>
  <div class="chips" role="group" aria-label="Filter">
    <button v-for="c in chips" :key="c[0]" class="chip" :aria-pressed="filter === c[0]" @click="filter = c[0]">
      {{ c[1] }} ({{ groups[c[0]].length }})
    </button>
  </div>
  <div style="height: 8px"></div>

  <div v-if="!onDutyList.length" class="empty">
    <p>Nobody is on duty yet today. Import a roster, or call someone in under Off today below.</p>
  </div>
  <div v-else-if="!visible.length" class="empty"><p>Nobody in this group.</p></div>
  <StaffCard v-for="e in visible" :key="e.staff_id" :person="e" />

  <details class="blk offpanel" style="margin-top: 18px">
    <summary>Off today ({{ offDutyList.length }})</summary>
    <p v-if="!offDutyList.length" class="muted" style="margin: 0">Everyone on the team is on duty today.</p>
    <StaffCard v-for="e in offDutyList" :key="e.staff_id" :person="e" />
  </details>

  <details class="blk" style="margin-top: 10px" :open="importOpen" @toggle="importOpen = $event.target.open">
    <summary>Import roster</summary>
    <p class="muted" style="margin-top: 0; font-size: 14px">
      Upload the roster's own .xlsx file, paste from Excel, or choose a CSV file, in any of these
      layouts. Dates are read as day first, like 13/10/2026. The roster goes into the
      <b>{{ SHIFT_NAME[state.shift] }} shift</b> selected at the top.
    </p>
    <ul class="muted" style="margin: 0 0 10px; padding-left: 18px; font-size: 14px">
      <li>
        One row per person, with a paired <b>Start</b> / <b>Indicative End</b> column for each date, like the
        weekly export from the roster system. A trailing <b>note</b> column containing "driver" and/or
        "truck" marks who holds each licence (or use dedicated Driver Licence / Truck Licence columns
        instead). Early/Late/All day is worked out from the actual times. A leading title row above the
        header, like "ADL - PM SHIFT - Week ending...", is skipped automatically.
      </li>
      <li>One row per person with a single Early/Late/All day column per date.</li>
      <li>One row per shift, with the columns Date, Name, Shift and an optional Role (Driver or Truck).</li>
    </ul>
    <textarea
      id="impTxt"
      v-model="impText"
      aria-label="Roster text"
      placeholder="Name,13/10/2026,14/10/2026&#10;Alex K,Early,All day&#10;Priya S,Late,Off"
      @input="impRes = null; impFile = null"
    ></textarea>
    <label class="f" style="margin-top: 10px">Excel (.xlsx) or CSV file
      <input type="file" accept=".xlsx,.csv,.tsv,.txt" @change="onFile" />
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
</template>
