<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Icon as VanIcon, showImagePreview } from 'vant'
import { api } from '../api.js'
import { FIXED_ROLES, PRESET_ROLES, SHIFT_LABEL, SHIFT_TIMES, STATUS_LABEL } from '../constants.js'
import { compressImage } from '../lib/image.js'
import { shortName } from '../lib/names.js'
import { vFitLine } from '../lib/fitLine.js'
import { currentShift, fmtElapsed, hasStarted, hhmm, isoFromLocal } from '../lib/time.js'
import { actions, onDuty, state, toast } from '../store.js'
import PeoplePicker from './PeoplePicker.vue'
import SignaturePad from './SignaturePad.vue'
import TimeField from './TimeField.vue'

const f = computed(() => state.flights.find((x) => x.id === state.openFlightId) || null)

// ---- details ----
function patch(field, value) {
  actions.patchFlight(f.value.id, { [field]: value })
}

// ---- fixed roles and crew rows ----
const holders = (role) => f.value.fixed.filter((x) => x.role === role).map((x) => x.staff_name)

/** People already working on another aircraft -- shown so the leading hand can see where someone
 * is, but picking them is still allowed: in practice people finish their part on one aircraft and
 * move to a second one that's already underway, well before the first one is actually done. */
const busy = computed(() => {
  const map = new Map()
  for (const other of state.flights) {
    if (other.id === f.value.id || other.status === 'done' || other.status === 'cancelled') continue
    for (const a of other.assignments) {
      if (!a.staff_id) continue
      const prev = map.get(a.staff_id)
      if (!prev || other.status === 'cleaning') map.set(a.staff_id, { id: other.id, no: other.flight_no, status: other.status })
    }
  }
  return map
})

// Each role/section can now hold more than one person, so options are no longer scoped to a single
// row -- a person already on this flight anywhere just can't be picked again.
const assignedIds = computed(() => new Set(f.value.assignments.filter((a) => a.staff_id).map((a) => a.staff_id)))

// On the shift that is running right now (Adelaide time), someone whose start time has not come yet
// cannot be picked. Their start is today's roster time, so moving it earlier on the Staff tab makes
// them pickable straight away. Past and future shifts are not limited.
const notStartedYet = computed(() => {
  const cur = currentShift(nowMinute.value * 60000)
  const late = new Map()
  if (cur.date !== f.value.work_date || cur.shift !== f.value.shift) return late
  for (const e of onDuty.value) {
    const start = e.rstart || (f.value.shift === 'night' ? SHIFT_TIMES[e.shift_type]?.[0] : '')
    if (start && !hasStarted(start, f.value.shift, cur.minutes)) late.set(e.staff_id, start)
  }
  return late
})
// One picker row: who, their shift today, and why they can't be picked (or are busy elsewhere).
function personOption(staffId, name, shiftType, meta, fixed) {
  const other = busy.value.get(staffId)
  const start = notStartedYet.value.get(staffId)
  const here = assignedIds.value.has(staffId)
  return {
    id: staffId,
    name: shortName(name),
    shiftType,
    meta,
    fixed,
    note: other ? (other.status === 'cleaning' ? `Cleaning ${other.no}` : `Also on ${other.no}`) : '',
    noteHot: other?.status === 'cleaning',
    disabled: here || !!start,
    reason: here ? 'On this aircraft' : start ? `Starts ${start}` : '',
  }
}
function personOptions() {
  return onDuty.value.map((e) =>
    personOption(
      e.staff_id,
      e.name,
      e.shift_type,
      [SHIFT_LABEL[e.shift_type] || 'Off', e.called_in_at ? 'Call in' : null, e.role].filter(Boolean).join(' · '),
      !!e.role,
    ),
  )
}

// The Toilet section on an aircraft can only be done by whoever holds the Toilet fixed role today,
// unlike the other sections, which are open to anyone on duty.
const toiletOptions = computed(() =>
  f.value.fixed
    .filter((x) => x.role === 'Toilet')
    .map((x) => {
      const e = onDuty.value.find((d) => d.staff_id === x.staff_id)
      return personOption(x.staff_id, x.staff_name, e?.shift_type, 'Toilet today', true)
    }),
)

/** Clears every row on another flight that still has this person, freeing them up to be assigned
 * here -- used when moving someone off an aircraft that is still mid-clean. */
function freeFromOtherFlight(otherFlightId, staffId) {
  const other = state.flights.find((x) => x.id === otherFlightId)
  if (!other) return Promise.resolve(true)
  const rows = other.assignments.map((a) => ({ role: a.role, staff_id: a.staff_id === staffId ? null : a.staff_id }))
  return actions.saveAssignments(otherFlightId, rows)
}

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

// Everyone picked in one go is saved in a single request, built after any moves off other
// aircraft have finished -- several overlapping saves of the whole list used to race on the server
// and leave the same person on the aircraft twice.
async function addPeople(role, staffIds) {
  const accepted = []
  for (const staffId of staffIds) {
    const other = busy.value.get(staffId)
    if (other && other.status === 'cleaning') {
      const name = shortName((onDuty.value.find((e) => e.staff_id === staffId) || {}).name || 'This person')
      if (!confirm(`${name} is currently cleaning ${other.no}. Move them to ${role} here instead?`)) continue
      const freed = await freeFromOtherFlight(other.id, staffId)
      if (freed === undefined) continue
    }
    accepted.push(staffId)
  }

  const rows = rowsPayload()
  let changed = false
  for (const staffId of accepted) {
    if (rows.some((r) => r.staff_id === staffId)) continue
    const emptyIndex = rows.findIndex((r) => r.role === role && !r.staff_id)
    if (emptyIndex >= 0) rows[emptyIndex].staff_id = staffId
    else rows.push({ role, staff_id: staffId })
    changed = true
  }
  if (changed) await actions.saveAssignments(f.value.id, rows)
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

// ---- "+ Add" picker: a searchable, multi-select list (Vant popup + search + checkboxes), replacing
// the old native <select> -- a role/section can hold more than one person, so picking should too.
// A whole role/section is rarely removed, unlike adding/removing people in it -- keep that × out of
// the way behind an explicit Edit toggle so it can't be tapped by accident.
const editingRoles = ref(false)
const pickerOpen = ref(false)
const pickerRole = ref('')
const pickerSelected = ref([])
function openPicker(role) {
  if (role === 'Toilet' && !toiletOptions.value.length) {
    return toast('Nobody is Toilet today. Set it on the Staff tab.')
  }
  pickerRole.value = role
  pickerSelected.value = []
  pickerOpen.value = true
}
// Sections in the sheet: who can be picked, fixed-role holders (usually busy with that role), and
// who can't be picked right now, each with the reason.
const pickerOptions = computed(() => {
  const toilet = pickerRole.value === 'Toilet'
  return (toilet ? toiletOptions.value : personOptions()).map((o) => ({
    ...o,
    section: o.disabled ? 'Not available' : toilet ? 'Toilet today' : o.fixed ? 'On a fixed role today' : 'Available',
  }))
})
const initials = (name) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .filter((_, i, all) => i === 0 || i === all.length - 1)
    .map((w) => w[0].toUpperCase())
    .join('')
const presetsToAdd = computed(() => PRESET_ROLES.filter((r) => !roleGroups.value.some((g) => g.role === r)))
const pickerSaving = ref(false)
async function confirmPicker() {
  if (pickerSaving.value) return // a double tap must not send the same add twice
  pickerSaving.value = true
  const role = pickerRole.value
  const ids = [...pickerSelected.value]
  pickerOpen.value = false
  try {
    await addPeople(role, ids)
  } finally {
    pickerSaving.value = false
  }
}
const newRole = ref('')
function addRow(preset) {
  const role = (typeof preset === 'string' ? preset : newRole.value).trim()
  if (!role) return toast('Pick or type a role')
  if (roleGroups.value.some((g) => g.role.toLowerCase() === role.toLowerCase())) return toast(`${role} is already on this aircraft`)
  actions.saveAssignments(f.value.id, [...rowsPayload(), { role, staff_id: null }])
  newRole.value = ''
}

// ---- timing ----
const now = ref(Date.now())
// Changes once a minute, so things that only care about the minute don't recompute every second.
const nowMinute = computed(() => Math.floor(now.value / 60000))
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
// TimeField is a controlled component driven by hhmm(f.started_at/finished_at) -- if the save
// fails, the prop simply doesn't change, no manual revert needed.
function changeTime(field, value) {
  if (!value) return
  actions.setTimes(f.value.id, { [field]: isoFromLocal(f.value.work_date, value) })
}

// ---- photos (attached to Notes: stains, damage, lost property) ----
const photos = ref([])
watch(
  () => f.value && f.value.id,
  async (id) => {
    if (!id) {
      photos.value = []
      return
    }
    try {
      photos.value = await api.flights.photos.list(id)
    } catch {
      photos.value = []
    }
  },
  { immediate: true },
)
async function refreshPhotos() {
  if (!f.value) return
  try {
    photos.value = await api.flights.photos.list(f.value.id)
  } catch {
    /* keep showing the previous list */
  }
}
async function addPhotos(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  for (const file of files) {
    try {
      const image = await compressImage(file)
      await actions.addPhoto(f.value.id, { name: `Photo ${photos.value.length + 1}`, image })
      await refreshPhotos()
    } catch (error) {
      toast(error.message || 'Could not add that photo')
    }
  }
}
function openPhoto(index) {
  showImagePreview({ images: photos.value.map((p) => p.image), startPosition: index })
}

const renamingPhotoId = ref(null)
const renameDraft = ref('')
const renameInputEl = ref(null)
function startRename(p) {
  renamingPhotoId.value = p.id
  renameDraft.value = p.name
  nextTick(() => renameInputEl.value?.focus())
}
async function commitRename(p) {
  if (renamingPhotoId.value !== p.id) return
  renamingPhotoId.value = null
  const name = renameDraft.value.trim()
  if (name === p.name) return
  await actions.renamePhoto(f.value.id, p.id, name)
  await refreshPhotos()
}

// Tap once to arm, tap again to actually delete -- same pattern as StaffCard's Call sick button, so
// an accidental tap on a small overlay icon can't silently remove someone's evidence photo.
const confirmDeletePhotoId = ref(null)
let confirmDeletePhotoTimer = null
function deletePhoto(p) {
  if (confirmDeletePhotoId.value !== p.id) {
    confirmDeletePhotoId.value = p.id
    toast('Tap again to confirm')
    clearTimeout(confirmDeletePhotoTimer)
    confirmDeletePhotoTimer = setTimeout(() => (confirmDeletePhotoId.value = null), 3000)
    return
  }
  clearTimeout(confirmDeletePhotoTimer)
  confirmDeletePhotoId.value = null
  actions.removePhoto(f.value.id, p.id).then(refreshPhotos)
}
onUnmounted(() => clearTimeout(confirmDeletePhotoTimer))

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
          <div class="detgrid">
            <div class="detfield"><span class="lbl">Flight</span><b>{{ f.flight_no || '—' }}</b></div>
            <div class="detfield"><span class="lbl">Airline</span><b>{{ f.airline || '—' }}</b></div>
            <div class="detfield"><span class="lbl">Rego</span><b>{{ f.rego || '—' }}</b></div>
            <div class="detfield"><span class="lbl">Gate / bay</span><b>{{ f.gate || '—' }}</b></div>
            <div class="detfield"><span class="lbl">Scheduled</span><b>{{ f.sched || '—' }}</b></div>
            <div class="detfield"><span class="lbl">ETA</span><b>{{ f.eta || '—' }}</b></div>
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
            <TimeField label="Started" :model-value="hhmm(f.started_at)" @update:model-value="(v) => changeTime('started_at', v)" />
            <TimeField
              v-if="f.finished_at"
              label="Finished"
              :model-value="hhmm(f.finished_at)"
              @update:model-value="(v) => changeTime('finished_at', v)"
            />
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
            <span v-if="holders(role).length" v-fit-line class="who fitline">
              <span v-for="(n, i) in holders(role)" :key="i">{{ n }}</span>
            </span>
            <span v-else class="who none">Not set. Set it on the Staff tab.</span>
          </div>
        </section>

        <section class="blk">
          <div class="sectionhead">
            <h3>On this aircraft</h3>
            <button class="ghost" @click="editingRoles = !editingRoles">{{ editingRoles ? 'Done' : 'Edit' }}</button>
          </div>
          <p v-if="!onDuty.length" class="muted" style="margin-top: 0">
            Nobody is on today's roster. Add people on the Crew tab first.
          </p>

          <div v-if="roleGroups.length" class="ac-roles">
            <div v-for="g in roleGroups" :key="g.role" class="ac-role">
              <button v-if="editingRoles" type="button" class="ac-del" :aria-label="'Remove ' + g.role" @click="removeRoleGroup(g.role)">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 12h10" /></svg>
              </button>
              <div class="ac-main">
                <div class="ac-head">
                  <span class="ac-name">{{ g.role }}</span>
                  <span v-if="peopleIn(g).length" class="ac-count">{{ peopleIn(g).length }}</span>
                </div>
                <div v-if="peopleIn(g).length" class="ac-people">
                  <span v-for="row in peopleIn(g)" :key="row.index" class="ac-chip">
                    <i class="ac-av">{{ initials(shortName(row.staff_name)) }}</i>
                    <span>{{ shortName(row.staff_name) }}</span>
                    <button type="button" :aria-label="'Remove ' + shortName(row.staff_name)" @click="removePerson(g.role, row.index)">
                      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7l10 10M17 7L7 17" /></svg>
                    </button>
                  </span>
                </div>
                <p v-else-if="g.role === 'Toilet' && !toiletOptions.length" class="ac-empty">Nobody is Toilet today. Set it on the Staff tab.</p>
                <p v-else class="ac-empty">No one yet</p>
              </div>
              <button v-if="!editingRoles" type="button" class="ac-add" :aria-label="'Add to ' + g.role" @click="openPicker(g.role)">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 6v12M6 12h12" /></svg>
                <span>Add</span>
              </button>
            </div>
          </div>

          <div class="ac-newrole">
            <div v-if="presetsToAdd.length" class="ac-presets">
              <button v-for="r in presetsToAdd" :key="r" type="button" @click="addRow(r)">+ {{ r }}</button>
            </div>
            <form class="ac-custom" @submit.prevent="addRow()">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 6v12M6 12h12" /></svg>
              <input v-model="newRole" type="text" placeholder="Add another role or section" aria-label="Role to add" autocomplete="off" enterkeyhint="done" />
              <button type="submit" :disabled="!newRole.trim()">Add</button>
            </form>
          </div>

          <PeoplePicker
            v-model:show="pickerOpen"
            v-model="pickerSelected"
            :title="`Add to ${pickerRole}`"
            :options="pickerOptions"
            :section-order="['Toilet today', 'Available', 'On a fixed role today', 'Not available']"
            :confirm-text="pickerSelected.length ? `Add ${pickerSelected.length}` : 'Add'"
            :saving="pickerSaving"
            @confirm="confirmPicker"
          />
        </section>

        <section class="blk">
          <h3>Notes</h3>
          <textarea
            :value="f.notes"
            aria-label="Notes"
            placeholder="Stains, lost property, damage, anything to hand over"
            @change="patch('notes', $event.target.value)"
          ></textarea>
          <div class="phototools">
            <label class="btn2 phototool">
              Take photo
              <input type="file" accept="image/*" capture="environment" @change="addPhotos" />
            </label>
            <label class="btn2 phototool">
              Choose photos
              <input type="file" accept="image/*" multiple @change="addPhotos" />
            </label>
          </div>
          <div v-if="photos.length" class="photogrid">
            <div v-for="(p, i) in photos" :key="p.id" class="photoitem">
              <img :src="p.image" :alt="p.name || 'Photo'" @click="openPhoto(i)" />
              <button
                class="btn2 icn photodelete"
                :class="{ armed: confirmDeletePhotoId === p.id }"
                :aria-label="confirmDeletePhotoId === p.id ? 'Tap again to confirm delete' : 'Delete photo'"
                @click="deletePhoto(p)"
              >
                <van-icon name="delete-o" size="16" />
              </button>
              <input
                v-if="renamingPhotoId === p.id"
                ref="renameInputEl"
                v-model="renameDraft"
                type="text"
                class="photoname"
                @blur="commitRename(p)"
                @keyup.enter="commitRename(p)"
              />
              <button v-else class="photoname photonamebtn" @click="startRename(p)">{{ p.name || 'Untitled' }}</button>
            </div>
          </div>
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

<!-- Same visual language as TimeField: 10px radius, --bg filled inputs, accent highlights. -->
<style>
.ac-roles {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--line);
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 12px;
}
.ac-role {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--surface);
}
.ac-role + .ac-role {
  border-top: 1px solid var(--line);
}
.ac-main {
  flex: 1;
  min-width: 0;
}
.ac-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ac-name {
  font-weight: 600;
  font-size: 15px;
}
.ac-count {
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent) 18%, transparent);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.ac-empty {
  margin: 2px 0 0;
  font-size: 13px;
  color: var(--muted);
}
.ac-people {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.ac-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 4px 0 4px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--bg);
  font-size: 14px;
  font-weight: 500;
  max-width: 100%;
}
.ac-chip > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ac-chip button {
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 50%;
  background: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex: none;
}
.ac-chip button:hover {
  background: var(--line);
}
.ac-av {
  --tone: var(--accent);
  flex: none;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-style: normal;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
  background: color-mix(in srgb, var(--tone) 22%, transparent);
  color: var(--tone);
}
.ac-roles svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.ac-add {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 34px;
  padding: 0 12px 0 10px;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--accent) 55%, transparent);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--accent);
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}
.ac-del {
  flex: none;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 0;
  background: var(--warn);
  color: var(--surface);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.ac-del svg {
  width: 20px;
  height: 20px;
  stroke-width: 3;
}
.ac-chip svg {
  width: 18px;
  height: 18px;
  color: var(--muted);
}
.ac-newrole {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ac-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.ac-presets button {
  height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px dashed var(--line);
  background: none;
  color: var(--muted);
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}
.ac-presets button:hover {
  color: var(--ink);
  border-color: var(--muted);
}
.ac-custom {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 48px;
  padding: 0 6px 0 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--bg);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.ac-custom:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 25%, transparent);
}
.ac-custom > svg {
  flex: none;
  width: 18px;
  height: 18px;
  fill: none;
  stroke: var(--muted);
  stroke-width: 2;
  stroke-linecap: round;
}
/* beats the global input[type=text] box style, so the field stays one box, not a box in a box */
.ac-custom input[type='text'] {
  flex: 1;
  min-width: 0;
  min-height: 0;
  height: 100%;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: none;
  color: var(--ink);
  font-size: 16px; /* under 16px, iOS zooms the whole page in on focus and leaves it zoomed */
  outline: none;
  box-shadow: none;
}
.ac-custom input[type='text']::placeholder {
  color: var(--muted);
}
.ac-custom button {
  flex: none;
  height: 36px;
  padding: 0 16px;
  border-radius: 8px;
  border: 0;
  background: var(--accent);
  color: var(--on-accent);
  font: inherit;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
}
.ac-custom button:disabled {
  background: none;
  color: var(--muted);
  opacity: 0.6;
  cursor: default;
}

</style>
