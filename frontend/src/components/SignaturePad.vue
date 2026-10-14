<script setup>
import { onMounted, ref } from 'vue'

const canvas = ref(null)
let ctx = null
let drawing = false
let last = null
let dirty = false

onMounted(() => {
  const el = canvas.value
  const rect = el.getBoundingClientRect()
  const dpr = window.devicePixelRatio || 1
  el.width = Math.round(rect.width * dpr)
  el.height = Math.round(rect.height * dpr)
  ctx = el.getContext('2d')
  ctx.scale(dpr, dpr)
  ctx.lineWidth = 2.4
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.strokeStyle = '#13202B'
})

function pos(e) {
  const b = canvas.value.getBoundingClientRect()
  return { x: e.clientX - b.left, y: e.clientY - b.top }
}
function down(e) {
  drawing = true
  try {
    canvas.value.setPointerCapture(e.pointerId)
  } catch {
    /* some browsers refuse capture */
  }
  last = pos(e)
  ctx.beginPath()
  ctx.moveTo(last.x, last.y)
  ctx.lineTo(last.x + 0.01, last.y + 0.01)
  ctx.stroke()
  dirty = true
}
function move(e) {
  if (!drawing) return
  const p = pos(e)
  ctx.beginPath()
  ctx.moveTo(last.x, last.y)
  ctx.lineTo(p.x, p.y)
  ctx.stroke()
  last = p
}
function up() {
  drawing = false
}

function clear() {
  const b = canvas.value.getBoundingClientRect()
  ctx.clearRect(0, 0, b.width, b.height)
  dirty = false
}
function isEmpty() {
  return !dirty
}
/** PNG on a white background, scaled down so the upload stays small. */
function toDataURL() {
  const src = canvas.value
  const out = document.createElement('canvas')
  out.width = 420
  out.height = Math.round((420 * src.height) / src.width)
  const g = out.getContext('2d')
  g.fillStyle = '#fff'
  g.fillRect(0, 0, out.width, out.height)
  g.drawImage(src, 0, 0, out.width, out.height)
  return out.toDataURL('image/png')
}

defineExpose({ clear, isEmpty, toDataURL })
</script>

<template>
  <canvas
    ref="canvas"
    class="pad"
    aria-label="Signature box"
    @pointerdown.prevent="down"
    @pointermove.prevent="move"
    @pointerup="up"
    @pointercancel="up"
  ></canvas>
</template>
