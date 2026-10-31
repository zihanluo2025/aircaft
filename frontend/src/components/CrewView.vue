<script setup>
import { computed, ref } from 'vue'
import { FIXED_ROLES, LICENCE_REQUIRED_ROLES, QUAL_LABEL, SHIFT_LABEL, SHIFT_NAME, SHIFT_ORDER } from '../constants.js'
import { shortName } from '../lib/names.js'
import { api } from '../api.js'
import { actions, onDuty, state, toast } from '../store.js'
import PeoplePicker from './PeoplePicker.vue'
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
// Grouped by shift type (Early, then Late, then All day) so people on the same shift sit together,
// rather than in whatever order the roster happened to list them.
const onDutyList = computed(() =>
  everyone.value.filter((e) => e.shift_type).sort((a, b) => SHIFT_ORDER[a.shift_type] - SHIFT_ORDER[b.shift_type]),
)
const offDutyList = computed(() => everyone.value.filter((e) => !e.shift_type))

const groups = computed(() => {
  const all = onDutyList.value
  return {
    every: all,
    early: all.filter((e) => e.shift_type === 'early'),
    late: all.filter((e) => e.shift_type === 'late'),
    all: all.filter((e) => e.shift_type === 'all'),
    call: all.filter((e) => e.called_in_at),
    // calling someone sick takes them off duty, so look across the whole team, not just on duty
    sick: everyone.value.filter((e) => e.sick_at),
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

// Choosing who holds a fixed role uses the same people sheet as the Flights page: today's holders
// start ticked, and Save applies the difference (adds and removals) in one go.
const pickOpen = ref(false)
const pickSelected = ref([])
const pickSaving = ref(false)
function openRole(role) {
  pickRole.value = role
  pickSelected.value = onDuty.value.filter((e) => e.role === role).map((e) => e.staff_id)
  pickOpen.value = true
}
const pickOptions = computed(() => {
  const role = pickRole.value
  if (!role) return []
  const needsLicence = LICENCE_REQUIRED_ROLES.includes(role)
  return onDuty.value.map((e) => {
    const reason =
      e.role && e.role !== role ? `${e.role} today` : needsLicence && !e.quals.includes(role) ? `No ${QUAL_LABEL[role] || role}` : ''
    return {
      id: e.staff_id,
      name: shortName(e.name),
      shiftType: e.shift_type,
      meta: [SHIFT_LABEL[e.shift_type], e.rstart && e.rend ? `${e.rstart}–${e.rend}` : ''].filter(Boolean).join(' · '),
      disabled: !!reason,
      reason,
      section: reason ? 'Not available' : needsLicence ? 'Qualified' : 'On duty',
    }
  })
})
async function saveRole() {
  if (pickSaving.value) return
  pickSaving.value = true
  const role = pickRole.value
  const want = new Set(pickSelected.value)
  const have = new Set(onDuty.value.filter((e) => e.role === role).map((e) => e.staff_id))
  pickOpen.value = false
  try {
    for (const id of want) if (!have.has(id)) await actions.rosterPatch(id, { role })
    for (const id of have) if (!want.has(id)) await actions.rosterPatch(id, { role: null })
  } finally {
    pickSaving.value = false
  }
}

// ---- roster import ----
const impFile = ref(null) // an .xlsx File goes to the server as-is; anything else is read as text
async function preview() {
  impRes.value = (await (impFile.value ? actions.importPreviewFile(impFile.value) : actions.importPreview(impText.value))) || null
}
async function applyImport() {
  const result = await (impFile.value ? actions.importApplyFile(impFile.value) : actions.importApply(impText.value))
  if (result) {
    resetImport()
    importOpen.value = false
  }
}
function takeFile(file) {
  if (!file) return
  impRes.value = null
  if (file.name.toLowerCase().endsWith('.xlsx')) {
    impFile.value = file
    impText.value = ''
    preview()
    return
  }
  impFile.value = null
  impFileName.value = file.name
  const reader = new FileReader()
  reader.onload = () => {
    impText.value = String(reader.result || '')
    preview()
  }
  reader.onerror = () => toast('Could not read that file')
  reader.readAsText(file)
}
const impFileName = ref('')
const fileLabel = computed(() => impFile.value?.name || impFileName.value)
function onFile(event) {
  takeFile(event.target.files && event.target.files[0])
  event.target.value = '' // picking the same file again should still trigger a change
}
const dragging = ref(false)
function onDrop(event) {
  dragging.value = false
  takeFile(event.dataTransfer.files && event.dataTransfer.files[0])
}
function resetImport() {
  impFile.value = null
  impFileName.value = ''
  impText.value = ''
  impRes.value = null
}
const pasteOpen = ref(false)

// ---- roster template: the week (Monday to Sunday) that contains the date picked at the top ----
const weekStart = computed(() => {
  const [y, m, d] = state.date.split('-').map(Number)
  const day = new Date(Date.UTC(y, m - 1, d))
  day.setUTCDate(day.getUTCDate() - ((day.getUTCDay() + 6) % 7))
  return day
})
const weekLabel = computed(() => {
  const end = new Date(weekStart.value)
  end.setUTCDate(end.getUTCDate() + 6)
  const fmt = (x, opts) => x.toLocaleDateString('en-AU', { timeZone: 'UTC', ...opts })
  return `${fmt(weekStart.value, { day: 'numeric', month: 'short' })} – ${fmt(end, { day: 'numeric', month: 'short' })}`
})
const downloading = ref(false)
async function downloadTemplate() {
  downloading.value = true
  try {
    const start = weekStart.value.toISOString().slice(0, 10)
    const { blob, filename } = await api.roster.template(state.shift, start)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename || `roster-${state.shift}-${start}.xlsx`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (error) {
    toast(error.message || 'Could not download the template')
  } finally {
    downloading.value = false
  }
}
</script>

<template>
  <h2 style="margin-top: 6px">Fixed all day</h2>
  <p class="muted" style="margin: 0 0 8px; font-size: 14px">Tap a role to choose who does it today.</p>
  <div class="fx">
    <button
      v-for="role in FIXED_ROLES"
      :key="role"
      :class="{ on: pickOpen && pickRole === role }"
      @click="openRole(role)"
    >
      <span v-if="holders(role).length" class="fxcount">{{ holders(role).length }}</span>
      <span>{{ role }}</span>
      <b :class="{ none: !holders(role).length }">{{ holders(role).length ? holders(role).join(', ') : 'Not set' }}</b>
      <small>{{ eligible(role).length }} {{ LICENCE_REQUIRED_ROLES.includes(role) ? 'qualified in' : 'on duty' }}</small>
    </button>
  </div>
  <PeoplePicker
    v-model:show="pickOpen"
    v-model="pickSelected"
    :title="`Who is ${pickRole} today?`"
    :options="pickOptions"
    :section-order="['Qualified', 'On duty', 'Not available']"
    confirm-text="Save"
    allow-empty
    :saving="pickSaving"
    @confirm="saveRole"
  >
    <template #empty><p class="pp-none">Nobody is on duty yet. Import a roster or call someone in first.</p></template>
  </PeoplePicker>

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
  <div v-else class="sc-group">
    <StaffCard v-for="e in visible" :key="e.staff_id" :person="e" />
  </div>

  <details class="blk offpanel" style="margin-top: 18px">
    <summary>Off today ({{ offDutyList.length }})</summary>
    <p v-if="!offDutyList.length" class="muted" style="margin: 0">Everyone on the team is on duty today.</p>
    <div v-else class="sc-group">
      <StaffCard v-for="e in offDutyList" :key="e.staff_id" :person="e" />
    </div>
  </details>

  <details class="blk rt" style="margin-top: 10px" :open="importOpen" @toggle="importOpen = $event.target.open">
    <summary>Import roster</summary>
    <p class="rt-lead">Download the template, fill in the times, then upload it. It goes into the <b>{{ SHIFT_NAME[state.shift] }}</b> shift.</p>

    <ol class="rt-steps">
      <li>
        <span class="rt-num">1</span>
        <div class="rt-body">
          <b>Download the template</b>
          <small>Week of {{ weekLabel }}, with everyone on the {{ SHIFT_NAME[state.shift] }} team</small>
        </div>
        <button type="button" class="rt-dl" :disabled="downloading" @click="downloadTemplate">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14" /></svg>
          {{ downloading ? 'Preparing...' : 'Template' }}
        </button>
      </li>
      <li>
        <span class="rt-num">2</span>
        <div class="rt-body">
          <b>Fill in Start and End</b>
          <small>Leave both blank for a day off. Write driver or truck in Note for licences.</small>
        </div>
      </li>
      <li>
        <span class="rt-num">3</span>
        <div class="rt-body"><b>Upload it</b></div>
      </li>
    </ol>

    <label
      class="rt-drop"
      :class="{ over: dragging, has: fileLabel }"
      @dragover.prevent="dragging = true"
      @dragleave="dragging = false"
      @drop.prevent="onDrop"
    >
      <input type="file" accept=".xlsx,.csv,.tsv,.txt" @change="onFile" />
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V5M7 10l5-5 5 5M5 20h14" /></svg>
      <span v-if="fileLabel" class="rt-file">{{ fileLabel }}</span>
      <span v-else>Choose the filled-in .xlsx, or drop it here</span>
      <small v-if="fileLabel">Tap to choose another file</small>
    </label>

    <div v-if="impRes" class="rt-after">
    <div class="rt-result" :class="{ bad: !impRes.days }">
      <template v-if="impRes.days">
        <b>Ready to import</b>
        <span>
          {{ impRes.days }} day{{ impRes.days > 1 ? 's' : '' }} &middot; {{ impRes.people }} people<template v-if="impRes.new_people"> ({{ impRes.new_people }} new)</template>
          &middot; {{ impRes.shifts }} shifts
        </span>
        <small>This replaces the current roster from the first day in the file onward.</small>
      </template>
      <template v-else>
        <b>No shifts found</b>
        <small>Use the template above, and make sure each worked day has a Start and an End time.</small>
      </template>
      <small v-if="impRes.bad.length" class="rt-warn">
        Skipped {{ impRes.bad.length }} unreadable cell{{ impRes.bad.length > 1 ? 's' : '' }}, e.g. {{ impRes.bad.slice(0, 2).join('; ') }}
      </small>
    </div>

    <button v-if="impRes.days" type="button" class="btn rt-go" @click="applyImport">
      Import {{ impRes.shifts }} shifts
    </button>
    </div>

    <button type="button" class="rt-link" :aria-expanded="pasteOpen" @click="pasteOpen = !pasteOpen">
      {{ pasteOpen ? 'Hide paste box' : 'Or paste from Excel instead' }}
    </button>
    <div v-if="pasteOpen" class="rt-paste">
      <textarea
        id="impTxt"
        v-model="impText"
        aria-label="Roster text"
        placeholder="Copy the rows from Excel, including the header, and paste here"
        @input="impRes = null; impFile = null; impFileName = ''"
      ></textarea>
      <button type="button" class="btn2" :disabled="!impText.trim()" @click="preview">Check pasted roster</button>
    </div>
  </details>
</template>

<style scoped>
.rt-lead {
  margin: 0 0 14px;
  font-size: 14px;
  color: var(--muted);
}
.rt-steps {
  list-style: none;
  margin: 0 0 12px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.rt-steps li {
  display: flex;
  align-items: center;
  gap: 12px;
}
.rt-num {
  flex: none;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  color: var(--accent);
}
.rt-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.rt-body b {
  font-size: 15px;
  font-weight: 600;
}
.rt-body small {
  font-size: 13px;
  color: var(--muted);
}
svg {
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.rt-dl {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 38px;
  padding: 0 14px 0 12px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--accent) 55%, transparent);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--accent);
  font: inherit;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
}
.rt-dl svg {
  width: 17px;
  height: 17px;
}
.rt-dl:disabled {
  opacity: 0.6;
  cursor: default;
}
.rt-drop {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 96px;
  margin-left: 38px;
  padding: 14px;
  border: 1.5px dashed var(--line);
  border-radius: 12px;
  background: var(--bg);
  color: var(--muted);
  font-size: 14px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.rt-drop:hover,
.rt-drop.over {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 6%, var(--bg));
}
.rt-drop.has {
  border-style: solid;
}
.rt-drop input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  overflow: hidden;
}
.rt-drop svg {
  width: 22px;
  height: 22px;
}
.rt-file {
  color: var(--ink);
  font-weight: 600;
  overflow-wrap: anywhere;
}
.rt-drop small {
  font-size: 12px;
}
/* result + Import button share one indented column, so the button can't run past the card */
.rt-after {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 10px 0 0 38px;
}
.rt-result {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--ok) 40%, transparent);
  background: color-mix(in srgb, var(--ok) 10%, transparent);
  font-size: 14px;
}
.rt-result b {
  color: var(--ok);
}
.rt-result.bad {
  border-color: color-mix(in srgb, var(--warn) 40%, transparent);
  background: color-mix(in srgb, var(--warn) 10%, transparent);
}
.rt-result.bad b {
  color: var(--warn);
}
.rt-result small {
  font-size: 13px;
  color: var(--muted);
}
.rt-result .rt-warn {
  color: var(--warn);
}
.rt-go {
  width: 100%;
}
.rt-link {
  display: block;
  margin: 12px 0 0 38px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--muted);
  font: inherit;
  font-size: 13px;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}
.rt-paste {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 8px 0 0 38px;
}
@media (max-width: 400px) {
  .rt-drop,
  .rt-after,
  .rt-link,
  .rt-paste {
    margin-left: 0;
  }
}
</style>
