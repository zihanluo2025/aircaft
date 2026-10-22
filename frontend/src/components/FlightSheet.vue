<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  Button as VanButton,
  Cell as VanCell,
  CellGroup as VanCellGroup,
  Checkbox as VanCheckbox,
  CheckboxGroup as VanCheckboxGroup,
  Icon as VanIcon,
  Popup as VanPopup,
  Search as VanSearch,
  Tag as VanTag,
  showImagePreview,
} from 'vant'
import { api } from '../api.js'
import { FIXED_ROLES, PRESET_ROLES, SHIFT_LABEL, STATUS_LABEL } from '../constants.js'
import { compressImage } from '../lib/image.js'
import { shortName } from '../lib/names.js'
import { fmtElapsed, hhmm, isoFromLocal } from '../lib/time.js'
import { actions, onDuty, state, toast } from '../store.js'
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
function personOptions() {
  return onDuty.value.map((e) => {
    const other = busy.value.get(e.staff_id)
    const info = [SHIFT_LABEL[e.shift_type] || 'off', e.called_in_at ? 'call in' : null, e.role].filter(Boolean).join(', ')
    const tag = other ? (other.status === 'cleaning' ? ` - cleaning ${other.no}` : ` - also on ${other.no}`) : ''
    return {
      id: e.staff_id,
      label: `${shortName(e.name)} (${info})${tag}`,
      disabled: assignedIds.value.has(e.staff_id),
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
        disabled: assignedIds.value.has(x.staff_id),
      }
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

async function addPerson(role, staffId) {
  if (!staffId) return

  const other = busy.value.get(staffId)
  if (other && other.status === 'cleaning') {
    const name = shortName((onDuty.value.find((e) => e.staff_id === staffId) || {}).name || 'This person')
    if (!confirm(`${name} is currently cleaning ${other.no}. Move them to ${role} here instead?`)) return
    const freed = await freeFromOtherFlight(other.id, staffId)
    if (freed === undefined) return
  }

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

// ---- "+ Add" picker: a searchable, multi-select list (Vant popup + search + checkboxes), replacing
// the old native <select> -- a role/section can hold more than one person, so picking should too.
// A whole role/section is rarely removed, unlike adding/removing people in it -- keep that × out of
// the way behind an explicit Edit toggle so it can't be tapped by accident.
const editingRoles = ref(false)
const pickerOpen = ref(false)
const pickerRole = ref('')
const pickerQuery = ref('')
const pickerSelected = ref([])
function openPicker(role) {
  if (role === 'Toilet' && !toiletOptions.value.length) {
    return toast('Nobody is Toilet today. Set it on the Staff tab.')
  }
  pickerRole.value = role
  pickerQuery.value = ''
  pickerSelected.value = []
  pickerOpen.value = true
}
const pickerOptions = computed(() =>
  pickerRole.value === 'Toilet' ? toiletOptions.value : [...cleanerOptions.value, ...fixedPersonOptions.value],
)
const filteredPickerOptions = computed(() => {
  const q = pickerQuery.value.trim().toLowerCase()
  if (!q) return pickerOptions.value
  return pickerOptions.value.filter((o) => o.label.toLowerCase().includes(q))
})
async function confirmPicker() {
  const role = pickerRole.value
  const ids = pickerSelected.value
  pickerOpen.value = false
  for (const id of ids) {
    await addPerson(role, id)
  }
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
            <span class="who" :class="{ none: !holders(role).length }">
              {{ holders(role).length ? holders(role).join(', ') : 'Not set. Set it on the Staff tab.' }}
            </span>
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
          <van-cell-group v-if="roleGroups.length" inset class="rolecells">
            <van-cell v-for="g in roleGroups" :key="g.role" :title="g.role" center>
              <template v-if="!peopleIn(g).length" #value>
                <van-tag plain type="primary" round size="large" class="addtag" @click="openPicker(g.role)">+ Add</van-tag>
              </template>
              <template v-if="editingRoles" #right-icon>
                <van-icon name="cross" size="18" :aria-label="'Remove ' + g.role" @click="removeRoleGroup(g.role)" />
              </template>
              <template v-if="peopleIn(g).length || (g.role === 'Toilet' && !toiletOptions.length)" #label>
                <div v-if="peopleIn(g).length" class="ppl">
                  <van-tag
                    v-for="row in peopleIn(g)"
                    :key="row.index"
                    type="primary"
                    round
                    closeable
                    size="large"
                    @close="removePerson(g.role, row.index)"
                  >
                    {{ shortName(row.staff_name) }}
                  </van-tag>
                  <van-tag plain type="primary" round size="large" class="addtag" @click="openPicker(g.role)">+ Add</van-tag>
                </div>
                <p v-else class="muted" style="margin: 2px 0 0; font-size: 13px">Nobody is Toilet today. Set it on the Crew tab.</p>
              </template>
            </van-cell>
          </van-cell-group>
          <div class="addrow">
            <input v-model="newRole" type="text" list="role-list" placeholder="Role or section" aria-label="Role to add" autocomplete="off" />
            <datalist id="role-list"><option v-for="p in PRESET_ROLES" :key="p" :value="p"></option></datalist>
            <button class="btn2" @click="addRow">Add role</button>
          </div>
          <van-popup v-model:show="pickerOpen" position="bottom" round closeable class="pickersheet">
            <div class="pickerhead">
              <h3>Add to {{ pickerRole }}</h3>
              <van-search v-model="pickerQuery" placeholder="Search by name" />
            </div>
            <div class="pickerlist">
              <p v-if="!filteredPickerOptions.length" class="muted" style="margin: 16px">Nobody matches.</p>
              <van-checkbox-group v-else v-model="pickerSelected">
                <van-checkbox
                  v-for="o in filteredPickerOptions"
                  :key="o.id"
                  :name="o.id"
                  :disabled="o.disabled"
                  shape="square"
                  class="pickerrow"
                >
                  {{ o.label }}
                </van-checkbox>
              </van-checkbox-group>
            </div>
            <div class="pickerfoot">
              <van-button block type="primary" :disabled="!pickerSelected.length" @click="confirmPicker">
                {{ pickerSelected.length ? `Add ${pickerSelected.length}` : 'Add' }}
              </van-button>
            </div>
          </van-popup>
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
