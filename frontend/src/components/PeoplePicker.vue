<script setup>
import { computed, ref, watch } from 'vue'
import { Popup as VanPopup } from 'vant'

// The bottom-sheet "pick people" list shared by the Flights page (who works a section of the
// aircraft) and the Staff page (who holds a fixed role today). The parent builds the options and
// decides what Confirm does; this only handles search, sections and selection.
//
// option: { id, name, shiftType, meta, section, disabled, reason, note, noteHot }
const props = defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, default: '' },
  options: { type: Array, default: () => [] },
  modelValue: { type: Array, default: () => [] }, // selected ids
  sectionOrder: { type: Array, default: () => [] },
  confirmText: { type: String, default: 'Add' },
  allowEmpty: { type: Boolean, default: false }, // Confirm with nothing selected (e.g. clear a role)
  saving: { type: Boolean, default: false },
})
const emit = defineEmits(['update:show', 'update:modelValue', 'confirm'])

const query = ref('')
watch(
  () => props.show,
  (open) => {
    if (open) query.value = ''
  },
)

const sections = computed(() => {
  const q = query.value.trim().toLowerCase()
  const items = q ? props.options.filter((o) => o.name.toLowerCase().includes(q)) : props.options
  const titles = [...props.sectionOrder]
  for (const o of items) if (!titles.includes(o.section)) titles.push(o.section)
  return titles.map((title) => ({ title, items: items.filter((o) => o.section === title) })).filter((s) => s.items.length)
})

const selected = computed(() => new Set(props.modelValue))
function toggle(o) {
  if (o.disabled) return
  emit('update:modelValue', selected.value.has(o.id) ? props.modelValue.filter((id) => id !== o.id) : [...props.modelValue, o.id])
}

const initials = (name) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .filter((_, i, all) => i === 0 || i === all.length - 1)
    .map((w) => w[0].toUpperCase())
    .join('')
const SHIFT_TONE = { early: 'var(--early)', late: 'var(--lateS)', all: 'var(--long)' }
</script>

<template>
  <van-popup :show="show" position="bottom" round teleport="body" class="pp-sheet" safe-area-inset-bottom @update:show="emit('update:show', $event)">
    <div class="pp-sheet-in">
      <div class="pp-sheet-head">
        <button type="button" class="pp-hbtn" @click="emit('update:show', false)">Cancel</button>
        <h3>{{ title }}</h3>
        <button type="button" class="pp-hbtn pp-hdone" :disabled="(!modelValue.length && !allowEmpty) || saving" @click="emit('confirm')">
          {{ confirmText }}
        </button>
      </div>
      <label class="pp-search">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></svg>
        <input v-model="query" type="search" placeholder="Search by name" aria-label="Search by name" />
      </label>
      <div class="pp-list">
        <slot name="empty" v-if="!options.length" />
        <p v-if="!sections.length && options.length" class="pp-none">Nobody matches.</p>
        <template v-for="sec in sections" :key="sec.title">
          <div class="pp-sec">{{ sec.title }}</div>
          <button
            v-for="o in sec.items"
            :key="o.id"
            type="button"
            class="pp-row"
            :class="{ on: selected.has(o.id) }"
            :disabled="o.disabled"
            :aria-pressed="selected.has(o.id)"
            @click="toggle(o)"
          >
            <i class="pp-av" :style="{ '--tone': SHIFT_TONE[o.shiftType] || 'var(--muted)' }">{{ initials(o.name) }}</i>
            <span class="pp-who">
              <b>{{ o.name }}</b>
              <small>{{ o.meta }}</small>
            </span>
            <span v-if="o.reason" class="pp-badge">{{ o.reason }}</span>
            <span v-else-if="o.note" class="pp-badge" :class="{ hot: o.noteHot }">{{ o.note }}</span>
            <span v-if="!o.disabled" class="pp-check" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d="M6 12.5l4 4 8-9" /></svg>
            </span>
          </button>
        </template>
      </div>
    </div>
  </van-popup>
</template>

<!-- Global (not scoped): the sheet is teleported to <body>. -->
<style>
.pp-sheet svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.pp-av {
  --tone: var(--accent);
  flex: none;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-style: normal;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.02em;
  background: color-mix(in srgb, var(--tone) 22%, transparent);
  color: var(--tone);
}
/* picker sheet */
.pp-sheet {
  background: var(--surface);
  color: var(--ink);
  max-height: 85vh;
  display: flex;
  flex-direction: column;
}
.pp-sheet-in {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
  width: 100%;
  max-width: 640px;
  margin: 0 auto;
}
.pp-sheet-head {
  flex: none;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 8px 8px 0;
}
.pp-sheet-head h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
}
.pp-hbtn {
  justify-self: start;
  background: none;
  border: 0;
  padding: 10px 12px;
  font: inherit;
  font-size: 15px;
  color: var(--muted);
  cursor: pointer;
}
.pp-hdone {
  justify-self: end;
  color: var(--accent);
  font-weight: 700;
}
.pp-hdone:disabled {
  color: var(--muted);
  opacity: 0.6;
  cursor: default;
}
.pp-search {
  display: flex;
  align-items: center;
  flex: none; /* the sheet is a flex column: a long list must not squash the search box */
  gap: 10px;
  height: 48px;
  margin: 10px 16px 6px;
  padding: 0 14px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: var(--bg);
  color: var(--muted);
}
.pp-search:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 25%, transparent);
}
.pp-search svg {
  width: 18px;
  height: 18px;
}
.pp-search input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: none;
  color: var(--ink);
  font: inherit;
  font-size: 16px; /* 16px stops iOS zooming in on focus */
  outline: none;
  padding: 0;
  min-height: 0;
  height: 100%;
}
.pp-list {
  overflow-y: auto;
  flex: 1;
  min-height: 0;
  padding: 0 8px 12px;
}
.pp-sec {
  padding: 14px 8px 6px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}
.pp-none {
  margin: 24px 8px;
  text-align: center;
  color: var(--muted);
}
.pp-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 8px;
  border: 0;
  border-radius: 10px;
  background: none;
  color: var(--ink);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.pp-row:hover:not(:disabled) {
  background: var(--bg);
}
.pp-row.on {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}
.pp-row:disabled {
  cursor: default;
  opacity: 0.55;
}
.pp-who {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.pp-who b {
  font-weight: 600;
  font-size: 15px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pp-who small {
  font-size: 13px;
  color: var(--muted);
}
.pp-badge {
  flex: none;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--bg);
  border: 1px solid var(--line);
  color: var(--muted);
}
.pp-badge.hot {
  color: var(--warn);
  border-color: color-mix(in srgb, var(--warn) 50%, transparent);
}
.pp-check {
  flex: none;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid var(--line);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: transparent;
}
.pp-row.on .pp-check {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
}
.pp-check svg {
  width: 14px;
  height: 14px;
  stroke-width: 3;
}
</style>
