export type FailureDetail = {
  category: string
  reason: string
  retriable: boolean
  recommended_action: string
}

export type LogSummary = {
  path: string
  exists: boolean
  size_bytes: number
  tail: string[]
  truncated: boolean
  error?: string
}

export type AttemptDetail = {
  attempt: Record<string, any>
  logs: { stdout: LogSummary; stderr: LogSummary }
  failure: FailureDetail | null
}

export type JobDetail = {
  job: Record<string, any>
  attempts: AttemptDetail[]
}

export type LifecycleEvent = {
  event_id: string
  event_type: string
  occurred_at: string
  run_id: string
  job_id?: string
  attempt_id?: string
  category?: string
  payload: Record<string, any>
}

export type RunObservability = {
  schema_version: 'rlw.run_observability/v1'
  run: Record<string, any>
  jobs: JobDetail[]
  events: LifecycleEvent[]
  artifacts: Array<Record<string, any>>
  metrics: Array<Record<string, any>>
  summary: {
    jobs: number
    attempts: number
    artifacts: number
    metrics: number
    events: number
    failures: number
    latest_event_type: string | null
  }
}

export function buildRunObservabilityPath(runId: string): string {
  const normalized = runId.trim()
  if (!normalized) throw new Error('Run ID is required')
  return `/runs/${encodeURIComponent(normalized)}/observability`
}

export function formatFailure(failure: FailureDetail): string {
  return `${failure.category} · ${failure.reason} · ${failure.recommended_action}`
}

export function formatLogTail(log: LogSummary): string {
  if (!log.exists) return log.error ?? 'Log unavailable'
  return log.tail.join('\n')
}
