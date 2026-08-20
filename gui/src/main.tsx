import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { buildJobRows, type AttemptRecord, type JobRecord } from './jobRecords'
import {
  buildMetricComparisonPath,
  type MetricComparison,
} from './metricComparison'
import {
  buildRunActionPath,
  buildRunObservabilityPath,
  formatDocumentContent,
  formatFailure,
  formatLogTail,
  getArtifactReplicas,
  shouldPollRunObservability,
  type RunObservability,
} from './runObservability'
import './styles.css'

type Overview = {
  node: { id: string; capabilities: Record<string, boolean> }
  catalog: { runs: number; datasets: number; jobs: number; attempts: number; total_records: number }
  legacy: { projects: number; project_names: string[] }
}
type Doctor = { platform: string; checks: Record<string, { ok: boolean; value?: string | null }> }
type ListResponse = { items: any[] }
type Preflight = { run_id: string; ok: boolean; checks: Array<{ name: string; ok: boolean; required: boolean; detail?: any }> }

const API = (import.meta as any).env?.VITE_RLW_API ?? 'http://127.0.0.1:8000/api/v1'

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`)
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

async function postJson<T>(path: string, body: any = {}): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const text = await r.text()
    throw new Error(text)
  }
  return r.json()
}

const doctorLabels: Record<string, string> = {
  python: 'Python 运行时 Python Runtime',
  git: 'Git 版本控制 Git',
  project_root: '项目根目录 Project Root',
  workspace: '工作区 Workspace',
  node: 'Node.js 运行时 Node.js Runtime',
  npm: '前端包管理器 npm',
  nvidia_smi: 'NVIDIA 驱动 NVIDIA SMI',
  torch: 'PyTorch Provider 依赖',
  lerobot: 'LeRobot Provider 依赖',
}

const preflightLabels: Record<string, string> = {
  git_commit_match: 'Git 提交匹配 Git Commit Match',
  prepared_from_clean_source: '准备时源码干净 Clean Source at Prepare',
  source_tree_clean: '当前源码干净 Source Tree Clean',
  dataset_manifest_valid: '数据集清单有效 Dataset Manifest',
  dataset_revision_available: '数据集版本缓存 Dataset Revision Cache',
  command_spec_valid: '命令规范 CommandSpec',
  output_directory_writable: '输出目录可写 Output Directory',
  provider_runtime_resolved: 'Provider 环境 Provider Runtime',
  lerobot_import: 'LeRobot 导入 LeRobot Import',
  torch_import: 'PyTorch 导入 PyTorch Import',
  cuda_available: 'CUDA 可用 CUDA Available',
  provider_probe: 'Provider 探测 Provider Probe',
}

function App() {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [doctor, setDoctor] = useState<Doctor | null>(null)
  const [runs, setRuns] = useState<any[]>([])
  const [datasets, setDatasets] = useState<any[]>([])
  const [artifacts, setArtifacts] = useState<any[]>([])
  const [jobs, setJobs] = useState<JobRecord[]>([])
  const [attempts, setAttempts] = useState<AttemptRecord[]>([])
  const [error, setError] = useState('')
  const [tab, setTab] = useState('overview')
  const [revision, setRevision] = useState('')
  const [message, setMessage] = useState('')
  const [preflight, setPreflight] = useState<Record<string, Preflight>>({})
  const [busyRun, setBusyRun] = useState('')
  const [compareRunIds, setCompareRunIds] = useState<string[]>([])
  const [comparison, setComparison] = useState<MetricComparison | null>(null)
  const [observability, setObservability] = useState<RunObservability | null>(null)
  const [inspectingRun, setInspectingRun] = useState('')
  const [actionRun, setActionRun] = useState('')
  const [acceptedExecution, setAcceptedExecution] = useState<{ runId: string; until: number } | null>(null)

  const refresh = () => Promise.all([
    getJson<Overview>('/overview'),
    getJson<Doctor>('/doctor'),
    getJson<ListResponse>('/runs'),
    getJson<ListResponse>('/datasets'),
    getJson<ListResponse>('/artifacts'),
    getJson<ListResponse>('/jobs'),
    getJson<ListResponse>('/attempts'),
  ]).then(([o, d, r, ds, a, j, at]) => {
    setOverview(o)
    setDoctor(d)
    setRuns(r.items)
    setDatasets(ds.items)
    setArtifacts(a.items)
    setJobs(j.items)
    setAttempts(at.items)
    setError('')
  }).catch(e => setError(String(e)))

  useEffect(() => { refresh() }, [])
  const ok = useMemo(() => doctor ? Object.values(doctor.checks).filter(x => x.ok).length : 0, [doctor])

  const prepare = async () => {
    setMessage('')
    try {
      const x: any = await postJson('/golden/prepare', { dataset_revision: revision, provider_env: 'lerobot-win' })
      setMessage(`已准备 Prepared: ${x.run_id}`)
      await refresh()
      setTab('runs')
    } catch (e) {
      setMessage(`准备失败 Prepare failed: ${String(e)}`)
    }
  }

  const runPreflight = async (runId: string) => {
    setBusyRun(runId)
    try {
      const report = await postJson<Preflight>(`/runs/${runId}/preflight`)
      setPreflight(prev => ({ ...prev, [runId]: report }))
    } catch (e) {
      setError(`预检失败 Preflight failed: ${String(e)}`)
    } finally {
      setBusyRun('')
    }
  }

  const toggleCompareRun = (runId: string) => {
    setCompareRunIds(current => current.includes(runId)
      ? current.filter(item => item !== runId)
      : [...current, runId])
    setComparison(null)
  }

  const compareRuns = async () => {
    try {
      const result = await getJson<MetricComparison>(
        buildMetricComparisonPath(compareRunIds),
      )
      setComparison(result)
      setError('')
    } catch (e) {
      setError(`评测比较失败 Evaluation compare failed: ${String(e)}`)
    }
  }

  const inspectRun = async (runId: string, showBusy = true) => {
    if (showBusy) setInspectingRun(runId)
    try {
      setObservability(await getJson<RunObservability>(buildRunObservabilityPath(runId)))
      setError('')
    } catch (e) {
      setError(`运行详情加载失败 Run inspect failed: ${String(e)}`)
    } finally {
      if (showBusy) setInspectingRun('')
    }
  }

  useEffect(() => {
    const runId = String(observability?.run.run_id ?? '')
    const awaitingStart = acceptedExecution?.runId === runId && Date.now() < acceptedExecution.until
    if (!runId || (!awaitingStart && !shouldPollRunObservability(observability, runId))) return
    const timer = window.setTimeout(() => { void inspectRun(runId, false) }, 3000)
    return () => window.clearTimeout(timer)
  }, [observability, acceptedExecution])

  const executeRun = async (runId: string) => {
    if (!preflight[runId]?.ok) return
    if (!window.confirm(`确认执行本地 Run？\nConfirm local execution:\n${runId}`)) return
    setActionRun(runId)
    try {
      await postJson(buildRunActionPath(runId, 'execute'), { confirmation: runId })
      setAcceptedExecution({ runId, until: Date.now() + 90_000 })
      setMessage(`执行请求已接收 Execution accepted: ${runId}`)
      await inspectRun(runId, false)
    } catch (e) {
      setError(`执行请求失败 Execute request failed: ${String(e)}`)
    } finally {
      setActionRun('')
    }
  }

  const reconcileRun = async (runId: string) => {
    setActionRun(runId)
    try {
      await postJson(buildRunActionPath(runId, 'reconcile'))
      setMessage(`重对账完成 Reconciled: ${runId}`)
      await Promise.all([inspectRun(runId, false), refresh()])
    } catch (e) {
      setError(`重对账失败 Reconcile failed: ${String(e)}`)
    } finally {
      setActionRun('')
    }
  }

  const tabs = [
    ['overview', '总览 Overview'],
    ['runs', '运行 Runs'],
    ['jobs', '任务与尝试 Jobs / Attempts'],
    ['evaluation', '评测比较 Evaluation Compare'],
    ['datasets', '数据集 Datasets'],
    ['artifacts', '产物 Artifacts'],
    ['legacy', '遗留资产 Legacy Assets'],
    ['doctor', '节点检查 Node Doctor'],
  ]

  return <div className="shell">
    <aside>
      <div className="brand"><span className="dot" />RLW</div>
      <p className="subtitle">机器人学习工作台 Robot Learning Workbench</p>
      {tabs.map(([k, l]) => <button key={k} className={tab === k ? 'nav active' : 'nav'} onClick={() => setTab(k)}>{l}</button>)}
      <div className="footer">接口 API <code>127.0.0.1:8000</code></div>
    </aside>
    <main>
      <header>
        <div><div className="eyebrow">本地控制平面 Local Control Plane</div><h1>{overview?.node.id ?? '连接中 Connecting…'}</h1></div>
        <div className="pill">V3 · 本地优先 local-first</div>
      </header>
      {error && <div className="error">接口不可用 API unavailable: {error}</div>}

      {tab === 'overview' && <>
        <section className="grid">
          <Card label="运行记录 Catalog Runs" value={overview?.catalog.runs ?? '—'} />
          <Card label="数据集版本 Dataset Revisions" value={overview?.catalog.datasets ?? '—'} />
          <Card label="任务 Jobs" value={overview?.catalog.jobs ?? '—'} />
          <Card label="执行尝试 ExecutionAttempts" value={overview?.catalog.attempts ?? '—'} />
          <Card label="遗留项目 Legacy Projects" value={overview?.legacy.projects ?? '—'} />
          <Card label="检测项 Doctor Checks" value={doctor ? `${ok}/${Object.keys(doctor.checks).length}` : '—'} />
        </section>
        <section className="panel">
          <div className="panelTitle">PushT + ACT 标准路径 Golden Path</div>
          <p>准备 Prepare 会创建不可变数据集版本 DatasetRevision、实验 Experiment → 试验 Trial → 运行 Run → 任务 Job 元数据，并生成解析配置 Resolved Config 与命令规范 CommandSpec。</p>
          <p className="muted">真正执行会产生执行尝试 ExecutionAttempt；训练逻辑仍由 LeRobot Provider 负责。</p>
          <div className="formrow">
            <input value={revision} onChange={e => setRevision(e.target.value)} placeholder="不可变数据集版本 / Immutable Dataset Revision / Commit SHA" />
            <button className="primary" onClick={prepare} disabled={!revision.trim()}>准备 PushT ACT 运行 Prepare Run</button>
          </div>
          {message && <p className="muted">{message}</p>}
          <p className="muted">执行前先做预检 Preflight；可在 Runs 页面确认执行，也可从项目根目录使用 <code>rlw run execute &lt;RUN_ID&gt;</code>。</p>
        </section>
      </>}

      {tab === 'runs' && <>
        <RunRecords
          items={runs}
          preflight={preflight}
          busyRun={busyRun}
          actionRun={actionRun}
          inspectingRun={inspectingRun}
          onPreflight={runPreflight}
          onInspect={inspectRun}
          onExecute={executeRun}
          onReconcile={reconcileRun}
        />
        {message && <p className="actionMessage">{message}</p>}
        {observability && <RunObservabilityPanel detail={observability} />}
      </>}
      {tab === 'jobs' && <JobRecords jobs={jobs} attempts={attempts} />}
      {tab === 'evaluation' && <EvaluationCompare
        runs={runs}
        selectedRunIds={compareRunIds}
        comparison={comparison}
        onToggle={toggleCompareRun}
        onCompare={compareRuns}
      />}
      {tab === 'datasets' && <Records title="数据集版本 Dataset Revisions" empty="暂无数据集版本 No dataset revisions yet." items={datasets} keys={['dataset_id', 'revision', 'immutable']} />}
      {tab === 'artifacts' && <Records title="产物 Artifacts" empty="暂无产物 No artifacts yet." items={artifacts} keys={['artifact_id', 'kind', 'display_name', 'producer_run']} />}
      {tab === 'legacy' && <section className="panel"><div className="panelTitle">检测到的遗留项目 Detected Legacy Projects</div><div className="chips">{overview?.legacy.project_names.map(x => <span className="chip" key={x}>{x}</span>)}</div></section>}
      {tab === 'doctor' && <section className="panel"><div className="panelTitle">节点能力 Node Capabilities</div><div className="checks">{doctor && Object.entries(doctor.checks).map(([n, x]) => <div className="check" key={n}><span className={x.ok ? 'ok' : 'bad'}>{x.ok ? '●' : '○'}</span><b>{doctorLabels[n] ?? n}</b><span className="muted">{x.value ?? ''}</span></div>)}</div></section>}
    </main>
  </div>
}

function Card({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="card"><div className="label">{label}</div><div className="value">{value}</div></div>
}

function RunRecords({ items, preflight, busyRun, actionRun, inspectingRun, onPreflight, onInspect, onExecute, onReconcile }: { items: any[]; preflight: Record<string, Preflight>; busyRun: string; actionRun: string; inspectingRun: string; onPreflight: (runId: string) => void; onInspect: (runId: string) => void; onExecute: (runId: string) => void; onReconcile: (runId: string) => void }) {
  return <section className="panel">
    <div className="panelTitle">标准运行 Canonical Runs</div>
    {items.length === 0 ? <p className="muted">暂无运行 No runs yet.</p> : <div className="records">
      {items.map(run => {
        const report = preflight[run.run_id]
        return <div className="record runRecord" key={run.run_id}>
          <div><span className="recordKey">运行 ID Run ID</span><span>{run.run_id}</span></div>
          <div><span className="recordKey">状态 Status</span><span>{run.status}</span></div>
          <div><span className="recordKey">Git 提交 Git Commit</span><span className="mono">{run.git_commit ?? ''}</span></div>
          <div className="runActions">
            <button className="secondary" onClick={() => onPreflight(run.run_id)} disabled={busyRun === run.run_id}>{busyRun === run.run_id ? '预检中 Checking…' : '预检 Preflight'}</button>
            <button className="secondary" onClick={() => onInspect(run.run_id)} disabled={inspectingRun === run.run_id}>{inspectingRun === run.run_id ? '加载中 Loading…' : '查看详情 Inspect'}</button>
            <button className="primary" onClick={() => onExecute(run.run_id)} disabled={!report?.ok || actionRun === run.run_id}>{actionRun === run.run_id ? '处理中 Working…' : '确认执行 Execute'}</button>
            <button className="secondary" onClick={() => onReconcile(run.run_id)} disabled={actionRun === run.run_id}>重对账 Reconcile</button>
          </div>
          {report && <PreflightPanel report={report} />}
        </div>
      })}
    </div>}
  </section>
}

function RunObservabilityPanel({ detail }: { detail: RunObservability }) {
  return <section className="panel observabilityPanel">
    <div className="panelTitle">运行详情 Run Observability · <span className="mono">{detail.run.run_id}</span></div>
    <div className="summaryChips">
      <span className="chip">事件 Events {detail.summary.events}</span>
      <span className="chip">尝试 Attempts {detail.summary.attempts}</span>
      <span className="chip">产物 Artifacts {detail.summary.artifacts}</span>
      <span className="chip">指标 Metrics {detail.summary.metrics}</span>
      <span className={detail.summary.failures ? 'chip failureChip' : 'chip'}>失败 Failures {detail.summary.failures}</span>
    </div>

    <div className="detailSection">
      <h3>可移植运行记录 Portable Run Documents</h3>
      <div className="documentGrid">{Object.values(detail.documents).map(document => <div className="documentCard" key={document.kind}>
        <div><b>{document.kind}</b><span className={document.available ? 'ok' : 'bad'}>{document.source}</span></div>
        <div className="muted mono">{document.path}</div>
        <pre>{formatDocumentContent(document)}</pre>
      </div>)}</div>
    </div>

    <div className="detailSection">
      <h3>生命周期 Lifecycle Events</h3>
      {detail.events.length === 0 ? <p className="muted">此运行创建于事件记录启用前 No structured events for this Run.</p> : <div className="eventTimeline">
        {detail.events.map(event => <div className="eventRow" key={event.event_id}>
          <span className="eventType">{event.event_type}</span>
          <span className="mono">{event.occurred_at}</span>
          <span className="muted">{event.category ?? 'lifecycle'}</span>
          <code>{JSON.stringify(event.payload)}</code>
        </div>)}
      </div>}
    </div>

    <div className="detailSection">
      <h3>任务、尝试与日志 Jobs, Attempts & Logs</h3>
      {detail.jobs.length === 0 ? <p className="muted">暂无持久任务 No durable Jobs.</p> : detail.jobs.map(({ job, attempts }) => <div className="detailJob" key={job.job_id}>
        <div><b className="mono">{job.job_id}</b> · {job.kind} · {job.state}</div>
        {attempts.length === 0 ? <p className="muted">尚未执行 Not executed.</p> : attempts.map(({ attempt, logs, failure }) => <div className="detailAttempt" key={attempt.attempt_id}>
          <div className="attemptHeader"><span className="mono">{attempt.attempt_id}</span><b>{attempt.state}</b><span>exit {String(attempt.exit_code ?? '—')}</span></div>
          {failure && <div className="failureGuide"><b>失败类别 Failure Category</b><span>{formatFailure(failure)}</span><small>可重试 Retriable: {failure.retriable ? 'yes' : 'no'}</small></div>}
          <div className="logGrid">
            {(['stdout', 'stderr'] as const).map(stream => <div className="logCard" key={stream}>
              <div><b>{stream}</b> <span className="muted mono">{logs[stream].path}</span></div>
              <pre>{formatLogTail(logs[stream]) || '—'}</pre>
            </div>)}
          </div>
        </div>)}
      </div>)}
    </div>

    <div className="detailColumns">
      <div className="detailSection"><h3>产物与副本 Artifacts & Replicas</h3>{detail.artifacts.length === 0 ? <p className="muted">暂无产物 No artifacts.</p> : detail.artifacts.map(item => <div className="artifactDetail" key={item.artifact_id}><div className="compactRecord"><b>{item.kind}</b><span>{item.display_name ?? item.artifact_id}</span><span className="mono">{item.artifact_id}</span></div>{getArtifactReplicas(item).length === 0 ? <p className="muted replicaEmpty">无副本信息 No Replica facts.</p> : getArtifactReplicas(item).map((replica, index) => <div className="replicaRecord" key={`${replica.uri ?? 'replica'}-${index}`}>
        <b>{replica.node_id ?? replica.node ?? 'unknown node'}</b><span>{replica.state ?? 'UNKNOWN'}</span><span className="mono">{replica.uri ?? '—'}</span>
        <small>digest {replica.digest ?? '—'} · bytes {String(replica.size_bytes ?? '—')} · persistent {String(replica.persistent ?? '—')} · cache {String(replica.cache ?? '—')} · pinned {String(replica.pinned ?? '—')}</small>
      </div>)}</div>)}</div>
      <div className="detailSection"><h3>指标 Metrics</h3>{detail.metrics.length === 0 ? <p className="muted">暂无指标 No metrics.</p> : detail.metrics.map(item => <div className="compactRecord" key={item.metric_id}><b>{item.name}</b><span>{String(item.value)}</span><span>{item.unit ?? item.scope ?? ''}</span></div>)}</div>
    </div>
  </section>
}

function PreflightPanel({ report }: { report: Preflight }) {
  return <div className={report.ok ? 'preflightBox passBox' : 'preflightBox failBox'}>
    <div className="preflightTitle">{report.ok ? '预检通过 Preflight PASS' : '预检未通过 Preflight FAIL'}</div>
    <div className="preflightChecks">{report.checks.map(item => <div className="preflightCheck" key={item.name}>
      <span className={item.ok ? 'ok' : item.required ? 'bad' : 'warn'}>{item.ok ? '●' : item.required ? '●' : '○'}</span>
      <span>{preflightLabels[item.name] ?? item.name}</span>
      <small>{item.required ? '必需 Required' : '建议 Advisory'}</small>
    </div>)}</div>
  </div>
}

function JobRecords({ jobs, attempts }: { jobs: JobRecord[]; attempts: AttemptRecord[] }) {
  const rows = useMemo(() => buildJobRows(jobs, attempts), [jobs, attempts])
  return <section className="panel">
    <div className="panelTitle">任务与执行尝试 Jobs / ExecutionAttempts</div>
    {rows.length === 0 ? <p className="muted">暂无持久任务记录 No durable Job records yet.</p> : <div className="records">
      {rows.map(({ job, attempts: jobAttempts }) => <div className="record jobRecord" key={job.job_id}>
        <div><span className="recordKey">任务 ID Job ID</span><span className="mono">{job.job_id}</span></div>
        <div><span className="recordKey">运行 Run</span><span className="mono">{job.run_id}</span></div>
        <div><span className="recordKey">类型 Kind</span><span>{job.kind}</span></div>
        <div><span className="recordKey">状态 State</span><span>{job.state}</span></div>
        <div className="attemptList"><span className="recordKey">执行尝试 Attempts</span><div>
          {jobAttempts.length === 0 ? <span className="muted">尚未执行 Not executed</span> : jobAttempts.map(attempt => <div className="attemptRow" key={attempt.attempt_id}>
            <span className="mono">{attempt.attempt_id}</span>
            <span>{attempt.state}</span>
            <span>exit {String(attempt.exit_code ?? '—')}</span>
          </div>)}
        </div></div>
      </div>)}
    </div>}
  </section>
}

function EvaluationCompare({
  runs,
  selectedRunIds,
  comparison,
  onToggle,
  onCompare,
}: {
  runs: any[]
  selectedRunIds: string[]
  comparison: MetricComparison | null
  onToggle: (runId: string) => void
  onCompare: () => void
}) {
  return <section className="panel">
    <div className="panelTitle">评测指标比较 Evaluation Metric Compare</div>
    <p className="muted">选择至少两个运行；CLI 使用同一比较服务：<code>rlw evaluation compare RUN_A RUN_B</code></p>
    <div className="compareRuns">
      {runs.map(run => <label className="compareChoice" key={run.run_id}>
        <input
          type="checkbox"
          checked={selectedRunIds.includes(run.run_id)}
          onChange={() => onToggle(run.run_id)}
        />
        <span className="mono">{run.run_id}</span>
      </label>)}
    </div>
    {runs.length === 0 && <p className="muted">暂无运行可比较 No Runs available.</p>}
    <button className="primary" onClick={onCompare} disabled={selectedRunIds.length < 2}>
      比较指标 Compare Metrics
    </button>
    {comparison && <div className="metricTableWrap"><table className="metricTable">
      <thead><tr>
        <th>指标 Metric</th>
        <th>范围 Scope</th>
        <th>方向 Direction</th>
        {comparison.run_ids.map(runId => <th className="mono" key={runId}>{runId}</th>)}
      </tr></thead>
      <tbody>{comparison.rows.map(row => <tr key={row.metric_key}>
        <td><b>{row.namespace}:{row.name}</b><small>{row.unit || '—'}</small></td>
        <td>{row.scope || 'global'}</td>
        <td>{row.direction || 'unspecified'}</td>
        {comparison.run_ids.map(runId => <td
          className={row.best_run_ids.includes(runId) ? 'bestMetric' : ''}
          key={runId}
        >{row.values[runId] ?? '—'}</td>)}
      </tr>)}</tbody>
    </table>
    {comparison.rows.length === 0 && <p className="muted">所选运行没有可比较的同源指标 No comparable MetricRecords.</p>}
    </div>}
  </section>
}

function Records({ title, empty, items, keys }: { title: string; empty: string; items: any[]; keys: string[] }) {
  return <section className="panel"><div className="panelTitle">{title}</div>{items.length === 0 ? <p className="muted">{empty}</p> : <div className="records">{items.map((x, i) => <div className="record" key={x.run_id ?? x.dataset_id ?? x.artifact_id ?? i}>{keys.map(k => <div key={k}><span className="recordKey">{k}</span><span>{String(x[k] ?? '')}</span></div>)}</div>)}</div>}</section>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
