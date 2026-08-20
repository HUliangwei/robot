export type MetricComparisonRow = {
  metric_key: string
  namespace: string
  name: string
  scope: string
  unit: string
  direction: string
  aggregation: string
  definition_version: string
  values: Record<string, number | null>
  best_run_ids: string[]
}

export type MetricComparison = {
  schema_version: 'rlw.metric_comparison/v1'
  run_ids: string[]
  rows: MetricComparisonRow[]
}

export function buildMetricComparisonPath(runIds: string[]): string {
  const distinct = [...new Set(runIds.map(runId => runId.trim()).filter(Boolean))]
  if (distinct.length < 2) {
    throw new Error('Metric comparison requires at least two distinct Runs')
  }
  const query = new URLSearchParams()
  distinct.forEach(runId => query.append('run_id', runId))
  return `/evaluation/compare?${query.toString()}`
}
