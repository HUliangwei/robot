export type JobRecord = {
  job_id: string
  run_id: string
  kind: string
  state: string
  [key: string]: unknown
}

export type AttemptRecord = {
  attempt_id: string
  job_id: string
  state: string
  started_at?: string
  ended_at?: string
  exit_code?: number | null
  [key: string]: unknown
}

export type JobRow = { job: JobRecord; attempts: AttemptRecord[] }

export function buildJobRows(jobs: JobRecord[], attempts: AttemptRecord[]): JobRow[] {
  const knownJobs = new Set(jobs.map(job => job.job_id))
  const attemptsByJob = new Map<string, AttemptRecord[]>()
  for (const attempt of attempts) {
    if (!knownJobs.has(attempt.job_id)) continue
    const records = attemptsByJob.get(attempt.job_id) ?? []
    records.push(attempt)
    attemptsByJob.set(attempt.job_id, records)
  }
  for (const records of attemptsByJob.values()) {
    records.sort((left, right) => (right.started_at ?? '').localeCompare(left.started_at ?? ''))
  }
  return jobs.map(job => ({ job, attempts: attemptsByJob.get(job.job_id) ?? [] }))
}
