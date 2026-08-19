import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

type Overview = {
  node: { id: string; capabilities: Record<string, boolean> }
  catalog: { runs: number; datasets: number; total_records: number }
  legacy: { projects: number; project_names: string[] }
}

type Doctor = {
  platform: string
  checks: Record<string, { ok: boolean; value?: string | null }>
}

const API = (import.meta as any).env?.VITE_RLW_API ?? 'http://127.0.0.1:8000/api/v1'

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`)
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response.json() as Promise<T>
}

function App() {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [doctor, setDoctor] = useState<Doctor | null>(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<'overview' | 'legacy' | 'doctor'>('overview')

  useEffect(() => {
    Promise.all([getJson<Overview>('/overview'), getJson<Doctor>('/doctor')])
      .then(([o, d]) => { setOverview(o); setDoctor(d) })
      .catch((e) => setError(String(e)))
  }, [])

  const requiredOk = useMemo(() => {
    if (!doctor) return 0
    return Object.values(doctor.checks).filter((x) => x.ok).length
  }, [doctor])

  return <div className="shell">
    <aside>
      <div className="brand"><span className="dot" />RLW</div>
      <p className="subtitle">Robot Learning Workbench</p>
      {(['overview','legacy','doctor'] as const).map((name) =>
        <button className={tab === name ? 'nav active' : 'nav'} onClick={() => setTab(name)} key={name}>
          {name === 'overview' ? 'Overview' : name === 'legacy' ? 'Legacy Assets' : 'Node Doctor'}
        </button>
      )}
      <div className="footer">API <code>127.0.0.1:8000</code></div>
    </aside>
    <main>
      <header>
        <div><div className="eyebrow">LOCAL CONTROL PLANE</div><h1>{overview?.node.id ?? 'Connecting…'}</h1></div>
        <div className="pill">V3 · local-first</div>
      </header>
      {error && <div className="error">API unavailable: {error}<br/>先运行 <code>rlw api</code></div>}
      {tab === 'overview' && <>
        <section className="grid">
          <Card label="Catalog Runs" value={overview?.catalog.runs ?? '—'} />
          <Card label="Dataset Revisions" value={overview?.catalog.datasets ?? '—'} />
          <Card label="Legacy Projects" value={overview?.legacy.projects ?? '—'} />
          <Card label="Doctor Checks" value={doctor ? `${requiredOk}/${Object.keys(doctor.checks).length}` : '—'} />
        </section>
        <section className="panel">
          <div className="panelTitle">Current migration boundary</div>
          <p>现有 <code>workspace/</code> 继续作为 legacy research assets；新实验逐步进入 Experiment → Trial → Run → Job → ExecutionAttempt。</p>
          <div className="flow"><b>Legacy Assets</b><span>→</span><b>Candidate Scan</b><span>→</span><b>Reviewed Import</b><span>→</span><b>RLW Catalog</b></div>
        </section>
      </>}
      {tab === 'legacy' && <section className="panel">
        <div className="panelTitle">Detected legacy projects</div>
        <div className="chips">{overview?.legacy.project_names.map((x) => <span className="chip" key={x}>{x}</span>)}</div>
        <p className="muted">运行 <code>rlw legacy scan --write</code> 生成只读候选清单。不会自动猜测历史 Git commit、Dataset revision 或 Run 边界。</p>
      </section>}
      {tab === 'doctor' && <section className="panel">
        <div className="panelTitle">Node capabilities</div>
        <div className="checks">{doctor && Object.entries(doctor.checks).map(([name, item]) =>
          <div className="check" key={name}><span className={item.ok ? 'ok' : 'bad'}>{item.ok ? '●' : '○'}</span><b>{name}</b><span className="muted">{item.value ?? ''}</span></div>
        )}</div>
      </section>}
    </main>
  </div>
}

function Card({label, value}: {label: string; value: React.ReactNode}) {
  return <div className="card"><div className="label">{label}</div><div className="value">{value}</div></div>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
