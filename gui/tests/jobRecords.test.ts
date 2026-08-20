import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const moduleUrl = new URL('../src/jobRecords.ts', import.meta.url)

test('buildJobRows groups durable attempts by job and sorts newest first', async () => {
  assert.ok(existsSync(fileURLToPath(moduleUrl)), 'Job/Attempt view model is missing')
  const { buildJobRows } = await import(moduleUrl.href)
  const rows = buildJobRows(
    [
      { job_id: 'job_a', run_id: 'run_1', kind: 'train', state: 'SUCCEEDED' },
      { job_id: 'job_b', run_id: 'run_2', kind: 'evaluate', state: 'READY' },
    ],
    [
      { attempt_id: 'attempt_old', job_id: 'job_a', state: 'FAILED', started_at: '2026-08-20T01:00:00Z' },
      { attempt_id: 'attempt_orphan', job_id: 'job_missing', state: 'RUNNING', started_at: '2026-08-20T03:00:00Z' },
      { attempt_id: 'attempt_new', job_id: 'job_a', state: 'SUCCEEDED', started_at: '2026-08-20T02:00:00Z' },
    ],
  )

  assert.deepEqual(rows.map(row => row.job.job_id), ['job_a', 'job_b'])
  assert.deepEqual(rows[0].attempts.map(attempt => attempt.attempt_id), ['attempt_new', 'attempt_old'])
  assert.deepEqual(rows[1].attempts, [])
})
