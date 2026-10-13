/**
 * Unit tests for the log timestamp guards (fix for Sentry 7670257837 /
 * HERMES-DISPATCHER-Q: RangeError "Invalid time value" in the Logs panel).
 *
 * Run with the Node built-in test runner (no extra deps, Node >= 22.18
 * strips TS types natively):
 *
 *   node --test app/tests/time.test.ts
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { isValidTimestamp, toValidTimestamp, safeIso } from '../src/utils/time.ts'

// The exact upstream garbage values the parseLogEntries regex captures.
const INVALID_INPUTS = [
  't_00fa8812.log', //      kanban source: [<file>.log] prefix captured as group 1
  '2026-10-13 11:21:29,572', // Python logging comma-millisecond timestamp
  'SILENT', //              arbitrary bracketed token from message body
  'hermes-dashboard.service', // journalctl bracketed token
  '',
]

const VALID_INPUTS = [
  '2026-10-13T11:21:29.572Z',
  '2026-10-13 11:21:29',
  'Mon, 13 Oct 2026 11:21:29 GMT',
]

test('isValidTimestamp rejects unparseable captures', () => {
  for (const raw of INVALID_INPUTS) {
    assert.equal(isValidTimestamp(raw), false, `expected invalid: ${JSON.stringify(raw)}`)
  }
  assert.equal(isValidTimestamp(undefined), false)
  assert.equal(isValidTimestamp(null), false)
})

test('isValidTimestamp accepts parseable dates', () => {
  for (const raw of VALID_INPUTS) {
    assert.equal(isValidTimestamp(raw), true, `expected valid: ${JSON.stringify(raw)}`)
  }
})

test('toValidTimestamp passes valid timestamps through unchanged', () => {
  for (const raw of VALID_INPUTS) {
    assert.equal(toValidTimestamp(raw), raw)
  }
})

test('toValidTimestamp falls back to a parseable ISO string for garbage', () => {
  for (const raw of INVALID_INPUTS) {
    const out = toValidTimestamp(raw)
    assert.notEqual(out, raw)
    assert.ok(!isNaN(new Date(out).getTime()), `fallback must be parseable: ${out}`)
    // The fallback itself must survive the display path.
    assert.doesNotThrow(() => new Date(out).toISOString())
  }
})

test('safeIso never throws RangeError on invalid input (the Sentry crash)', () => {
  for (const raw of INVALID_INPUTS) {
    assert.doesNotThrow(() => safeIso(raw))
    assert.equal(safeIso(raw), raw, 'invalid input renders as the raw string')
  }
})

test('safeIso formats valid timestamps as ISO', () => {
  assert.equal(safeIso('2026-10-13T11:21:29.572Z'), '2026-10-13T11:21:29.572Z')
  assert.equal(safeIso('Mon, 13 Oct 2026 11:21:29 GMT'), '2026-10-13T11:21:29.000Z')
})

test('regression: the exact crash line from the Logs panel no longer throws', () => {
  // Real line shape from routes/logs.py kanban source: the [<file>.log]
  // prefix lands in capture group 1 where the code expects a timestamp.
  const line = '[t_00fa8812.log] [SILENT] cron.scheduler: Job skipped'
  const match = line.match(/\[(.*?)\]\s+\[(.*?)\]\s+(.*?)\s*:\s*(.*)/)
  assert.ok(match, 'regex should match the kanban-prefixed line')
  const captured = match![1] // "t_00fa8812.log"
  // Old code: new Date(captured).toISOString() -> RangeError. New path:
  const stored = toValidTimestamp(captured)
  assert.doesNotThrow(() => safeIso(stored))
  assert.doesNotThrow(() => safeIso(captured))
})
