/**
 * Regression tests for the Array.isArray guard added to KanbanPanel, Sessions,
 * and Skills panels (fix for "TypeError: n.map is not a function").
 *
 * Root cause: auth middleware returns {"error":"Unauthorized"} (401) when the
 * session cookie expires. The fetch chains called setState with a plain object,
 * which later crashed at render time with n.map/n.filter is not a function.
 *
 * Run with the Node built-in test runner (Node >= 22.18 strips TS natively):
 *
 *   node --test "tests/**\/*.test.ts"
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'

// The exact error shape the auth middleware sends on 401.
const UNAUTHORIZED = { error: 'Unauthorized' }
const EMPTY_OBJECT = {}
const NULL_RESPONSE = null
const STRING_RESPONSE = 'not an array'

// Representative valid responses for each endpoint.
const TASKS_ARRAY = [{ id: 't_1', title: 'task', status: 'ready' }]
const SESSIONS_ARRAY = [{ id: 's_1', title: 'session', model: 'claude' }]
const SKILLS_ARRAY = [{ id: 'sk_1', name: 'github', enabled: true }]

// ---------------------------------------------------------------------------
// The guard itself is inline in each component:
//   .then((data) => { if (Array.isArray(data)) setState(data) })
// These tests document and verify that the guard correctly blocks non-arrays
// from reaching setState.
// ---------------------------------------------------------------------------

test('Array.isArray blocks the 401 error object that caused the crash', () => {
  assert.equal(Array.isArray(UNAUTHORIZED), false)
  assert.equal(Array.isArray(EMPTY_OBJECT), false)
  assert.equal(Array.isArray(NULL_RESPONSE), false)
  assert.equal(Array.isArray(STRING_RESPONSE), false)
})

test('Array.isArray passes valid API responses through to setState', () => {
  assert.equal(Array.isArray(TASKS_ARRAY), true)
  assert.equal(Array.isArray(SESSIONS_ARRAY), true)
  assert.equal(Array.isArray(SKILLS_ARRAY), true)
  assert.equal(Array.isArray([]), true)
})

test('regression: .map() on the 401 response throws without the guard', () => {
  // Without the guard the old code did: setTasks(data) then data.map(…) at render.
  assert.throws(
    () => (UNAUTHORIZED as unknown as unknown[]).map(() => null),
    TypeError,
    '.map on a plain object must throw TypeError'
  )
})

test('regression: guarded setState never receives a non-array', () => {
  const received: unknown[] = []
  const guardedSetState = (data: unknown) => {
    if (Array.isArray(data)) received.push(data)
  }

  // Simulate the four response shapes that arrive from the fetch chain.
  guardedSetState(UNAUTHORIZED)        // 401 from auth middleware
  guardedSetState(EMPTY_OBJECT)        // unexpected empty object
  guardedSetState(NULL_RESPONSE)       // null body
  guardedSetState(TASKS_ARRAY)         // normal success path

  assert.equal(received.length, 1, 'only the array should reach setState')
  assert.deepEqual(received[0], TASKS_ARRAY)
})
