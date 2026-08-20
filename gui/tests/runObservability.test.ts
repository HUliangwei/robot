import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  buildRunActionPath,
  buildRunObservabilityPath,
  formatDocumentContent,
  formatFailure,
  formatLogTail,
  getArtifactReplicas,
  shouldPollRunObservability,
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


test('Run action paths share the encoded root-scoped API identity', () => {
  assert.equal(buildRunActionPath(' run A/测试 ', 'execute'), '/runs/run%20A%2F%E6%B5%8B%E8%AF%95/execute')
  assert.equal(buildRunActionPath('run_a', 'reconcile'), '/runs/run_a/reconcile')
  assert.throws(() => buildRunActionPath('', 'execute'), /Run ID is required/)
})


test('polling continues only for the selected active Run', () => {
  const running: any = {run: {run_id: 'run_a', status: 'RUNNING'}, jobs: []}
  const attemptRunning: any = {run: {run_id: 'run_a', status: 'READY'}, jobs: [{job: {}, attempts: [{attempt: {state: 'RUNNING'}}]}]}
  const done: any = {run: {run_id: 'run_a', status: 'SUCCEEDED'}, jobs: []}

  assert.equal(shouldPollRunObservability(running, 'run_a'), true)
  assert.equal(shouldPollRunObservability(attemptRunning, 'run_a'), true)
  assert.equal(shouldPollRunObservability(running, 'run_b'), false)
  assert.equal(shouldPollRunObservability(done, 'run_a'), false)
})


test('portable document and Artifact Replica helpers preserve canonical facts', () => {
  const document: any = {available: true, content: {seed: 7, provider: 'lerobot'}}
  const unavailable: any = {available: false, content: null, error: 'document is not recorded'}
  const replicas = [{node_id: 'local', uri: 'file:///model', state: 'AVAILABLE', digest: 'sha256:abc', size_bytes: 123, persistent: true, cache: false, pinned: true}]

  assert.equal(formatDocumentContent(document), '{\n  "seed": 7,\n  "provider": "lerobot"\n}')
  assert.equal(formatDocumentContent(unavailable), 'document is not recorded')
  assert.deepEqual(getArtifactReplicas({artifact_id: 'artifact_model', replicas}), replicas)
  assert.deepEqual(getArtifactReplicas({artifact_id: 'artifact_old'}), [])
})


test('GUI helpers consume the canonical CLI and API fixture unchanged', () => {
  const detail = JSON.parse(readFileSync(new URL('../../tests/fixtures/run_observability_v1.json', import.meta.url), 'utf-8'))

  assert.equal(detail.schema_version, 'rlw.run_observability/v1')
  assert.equal(formatDocumentContent(detail.documents.resolved_config), '{\n  "seed": 7\n}')
  assert.equal(shouldPollRunObservability(detail, 'run_contract'), true)
  assert.equal(buildRunObservabilityPath(detail.run.run_id), '/runs/run_contract/observability')
})
