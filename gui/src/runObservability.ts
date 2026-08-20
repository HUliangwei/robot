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

export type RecordDocument = {
  schema_version: 'rlw.record_document/v1'
  kind: 'manifest' | 'run_spec' | 'resolved_config' | 'lineage'
  path: string
  format: 'json' | 'yaml'
  source: 'file' | 'manifest_embedded' | 'unavailable'
  available: boolean
  content: any
  error?: string
}

export type ArtifactReplica = {
  node_id?: string
  node?: string
  uri?: string
  state?: string
  digest?: string
  size_bytes?: number
  persistent?: boolean
  cache?: boolean
  pinned?: boolean
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
  documents: Record<'manifest' | 'run_spec' | 'resolved_config' | 'lineage', RecordDocument>
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

export function buildRunActionPath(
  runId: string,
  action: 'execute' | 'reconcile',
): string {
  const normalized = runId.trim()
  if (!normalized) throw new Error('Run ID is required')
  return `/runs/${encodeURIComponent(normalized)}/${action}`
}

export function shouldPollRunObservability(
  detail: RunObservability | null,
  activeRunId: string,
): boolean {
  if (!detail || detail.run.run_id !== activeRunId) return false
  if (detail.run.status === 'RUNNING') return true
  return detail.jobs.some(({ attempts }) =>
    attempts.some(({ attempt }) => attempt.state === 'RUNNING'),
  )
}

export function formatDocumentContent(document: RecordDocument): string {
  if (!document.available) return document.error ?? 'Document unavailable'
  return JSON.stringify(document.content, null, 2)
}

export function getArtifactReplicas(artifact: Record<string, any>): ArtifactReplica[] {
  return Array.isArray(artifact.replicas) ? artifact.replicas : []
}

export function formatFailure(failure: FailureDetail): string {
  return `${failure.category} · ${failure.reason} · ${failure.recommended_action}`
}

export function formatLogTail(log: LogSummary): string {
  if (!log.exists) return log.error ?? 'Log unavailable'
  return log.tail.join('\n')
}
