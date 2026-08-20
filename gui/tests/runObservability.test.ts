import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildRunObservabilityPath,
  formatFailure,
  formatLogTail,
} from '../src/runObservability.ts'


test('buildRunObservabilityPath trims and encodes the selected Run ID', () => {
  assert.equal(
    buildRunObservabilityPath('  run A/测试  '),
    '/runs/run%20A%2F%E6%B5%8B%E8%AF%95/observability',
  )
  assert.throws(() => buildRunObservabilityPath('   '), /Run ID is required/)
})


test('observability presentation helpers preserve API failure and log facts', () => {
  assert.equal(
    formatFailure({
      category: 'ExecutionError',
      reason: 'Command exited with code 7.',
      retriable: false,
      recommended_action: 'Inspect stderr.',
    }),
    'ExecutionError · Command exited with code 7. · Inspect stderr.',
  )
  assert.equal(
    formatLogTail({
      path: '.rlw/state/jobs/job/attempt/stdout.log',
      exists: true,
      size_bytes: 12,
      tail: ['line one', 'line two'],
      truncated: true,
    }),
    'line one\nline two',
  )
  assert.equal(
    formatLogTail({
      path: 'missing.log',
      exists: false,
      size_bytes: 0,
      tail: [],
      truncated: false,
      error: 'log file does not exist',
    }),
    'log file does not exist',
  )
})
