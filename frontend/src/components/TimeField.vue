<script setup>
import { ref } from 'vue'
import { Field as VanField, Popup as VanPopup, TimePicker as VanTimePicker } from 'vant'

const props = defineProps({ label: { type: String, default: '' }, modelValue: { type: String, default: '' } })
const emit = defineEmits(['update:modelValue'])

const open = ref(false)
const draft = ref(['00', '00'])
function openPicker() {
  const [h, m] = (props.modelValue || '00:00').split(':')
  draft.value = [h, m]
  open.value = true
}
function confirm() {
  emit('update:modelValue', draft.value.join(':'))
  open.value = false
}
</script>

<template>
  <label class="f">
    {{ label }}
    <van-field readonly is-link :model-value="modelValue || '--:--'" placeholder="--:--" @click="openPicker" />
  </label>
  <van-popup v-model:show="open" position="bottom" round teleport="body">
    <van-time-picker v-model="draft" :title="label" @confirm="confirm" @cancel="open = false" />
  </van-popup>
</template>
