import test from 'node:test'
import assert from 'node:assert/strict'
import { fmtElapsed, hhmm, isoFromLocal, pad, todayStr } from '../src/lib/time.js'

test('pad', () => {
  assert.equal(pad(5), '05')
  assert.equal(pad(12), '12')
})

test('todayStr uses the local calendar date', () => {
  assert.equal(todayStr(new Date(2026, 9, 3, 23, 59)), '2026-10-03')
})

test('fmtElapsed', () => {
  assert.equal(fmtElapsed(0), '00:00')
  assert.equal(fmtElapsed(65_000), '01:05')
  assert.equal(fmtElapsed(-5), '00:00')
  assert.equal(fmtElapsed(125 * 60_000), '125:00')
})

test('isoFromLocal and hhmm round trip in any time zone', () => {
  assert.equal(hhmm(isoFromLocal('2026-10-13', '05:50')), '05:50')
  assert.equal(hhmm(isoFromLocal('2026-10-13', '23:05')), '23:05')
})

test('hhmm of nothing is empty', () => {
  assert.equal(hhmm(null), '')
})

test('currentShift uses Adelaide time, early hours belong to the previous night', async () => {
  const { currentShift } = await import('../src/lib/time.js')
  // 2026-10-22 08:50 UTC = 19:20 ACDT
  assert.deepEqual(currentShift(Date.UTC(2026, 9, 22, 8, 50)), { date: '2026-10-22', shift: 'night', minutes: 19 * 60 + 20 })
  // 2026-10-22 22:00 UTC = 08:30 ACDT on the 23rd
  assert.equal(currentShift(Date.UTC(2026, 9, 22, 22, 0)).shift, 'morning')
  // 2026-10-22 15:00 UTC = 01:30 ACDT on the 23rd -> night of the 22nd
  assert.deepEqual(currentShift(Date.UTC(2026, 9, 22, 15, 0)), { date: '2026-10-22', shift: 'night', minutes: 90 })
})

test('hasStarted counts from the shift start, across midnight', async () => {
  const { hasStarted } = await import('../src/lib/time.js')
  assert.equal(hasStarted('19:50', 'night', 18 * 60 + 20), false)
  assert.equal(hasStarted('15:50', 'night', 18 * 60 + 20), true)
  assert.equal(hasStarted('19:50', 'night', 19 * 60 + 50), true)
  assert.equal(hasStarted('23:30', 'night', 60), true) // 01:00 is after a 23:30 start
  assert.equal(hasStarted('00:30', 'night', 23 * 60), false)
})
