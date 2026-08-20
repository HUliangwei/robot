import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const moduleUrl = new URL('../src/metricComparison.ts', import.meta.url)

test('buildMetricComparisonPath sends distinct selected Runs to the shared API', async () => {
  assert.ok(existsSync(fileURLToPath(moduleUrl)), 'Metric comparison API model is missing')
  const { buildMetricComparisonPath } = await import(moduleUrl.href)

  assert.equal(
    buildMetricComparisonPath(['run A', 'run/b', 'run A']),
    '/evaluation/compare?run_id=run+A&run_id=run%2Fb',
  )
  assert.throws(
    () => buildMetricComparisonPath(['run_a', 'run_a']),
    /at least two distinct Runs/,
  )
})
