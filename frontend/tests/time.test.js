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
