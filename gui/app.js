"use strict";

const $ = (s) => document.querySelector(s);
const listEl = $("#project-list");
const mainEl = $("#main");
let current = null;
let pollTimer = null;
let currentRunId = null;
let onRunDone = () => {};

// ---------------- tiny markdown renderer ----------------
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function md(text) {
  let lines = String(text).split(/\r?\n/);
  let html = "";
  let inTable = false;
  const flushTable = () => { if (inTable) { html += "</table>"; inTable = false; } };
  for (let raw of lines) {
    const line = raw.trimEnd();
    if (/^```/.test(line)) { html += "<pre>"; continue; }
    if (html.endsWith("<pre>")) {
      if (/^```/.test(line)) { html += "</pre>"; } else { html += esc(line) + "\n"; }
      continue;
    }
    let t = esc(line)
      .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\[(.+?)\]\((.+?)\)/g, (m, a, h) => h.startsWith("http") ? `<a href="${h}" target="_blank">${a}</a>` : `<a href="${h}">${a}</a>`);
    const h1 = line.match(/^# (.*)$/), h2 = line.match(/^## (.*)$/), h3 = line.match(/^### (.*)$/);
    if (h1) { flushTable(); html += `<h1>${esc(h1[1])}</h1>`; continue; }
    if (h2) { flushTable(); html += `<h2>${esc(h2[1])}</h2>`; continue; }
    if (h3) { flushTable(); html += `<h3>${esc(h3[1])}</h3>`; continue; }
    if (line.startsWith("|") && line.includes("|")) {
      if (!inTable) { html += "<table>"; inTable = true; }
      const cells = line.split("|").slice(1, -1).map((c) => c.trim());
      if (cells.every((c) => /^:?-+:?$/.test(c))) continue;
      html += "<tr>" + cells.map((c) => `<td>${c}</td>`).join("") + "</tr>";
      continue;
    }
    if (line.startsWith("- ")) { flushTable(); html += `<p>• ${t.slice(2)}</p>`; continue; }
    if (line.startsWith("> ")) { flushTable(); html += `<blockquote>${t.slice(2)}</blockquote>`; continue; }
    if (/^-{3,}$/.test(line.trim())) { flushTable(); html += "<hr>"; continue; }
    if (line.trim() === "") { flushTable(); continue; }
    html += `<p>${t}</p>`;
  }
  flushTable();
  return html;
}
function fmtSize(n) {
  if (n == null) return "-";
  if (n < 1024) return n + " B";
  if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
  return (n / 1048576).toFixed(1) + " MB";
}
const MEDIA_EXT = ["mp4", "gif", "png", "jpg", "jpeg", "svg", "webp"];

// 浏览器优先显示 GIF（mp4v 编码浏览器不支持）；mp4 作为下载链接
function mediaFigure(project, candidates) {
  const gif = candidates.find((c) => c.path.endsWith(".gif"));
  const mp4 = candidates.find((c) => c.path.endsWith(".mp4"));
  const src = gif || mp4 || candidates[0];
  if (!src) return "";
  const fig = document.createElement("figure");
  const cap = document.createElement("figcaption");
  cap.textContent = src.path.split("/").pop();
  if (gif || !mp4) {
    const im = document.createElement("img");
    im.loading = "lazy";
    im.src = "/proj/" + encodeURIComponent(project) + "/file/" + encodeURIComponent(src.path);
    fig.appendChild(im);
  } else {
    const v = document.createElement("video");
    v.controls = true;
    v.src = "/proj/" + encodeURIComponent(project) + "/file/" + encodeURIComponent(mp4.path);
    fig.appendChild(v);
  }
  if (mp4 && gif) {
    const dl = document.createElement("a");
    dl.href = "/proj/" + encodeURIComponent(project) + "/file/" + encodeURIComponent(mp4.path);
    dl.textContent = " ⬇ mp4";
    dl.style.fontSize = ".72rem";
    cap.appendChild(dl);
  }
  fig.appendChild(cap);
  return fig;
}

// ---------------- console dock ----------------
const dock = () => $("#console-dock");
let _drag = null;
function setPulse(running) {
  const p = $("#console-pulse");
  if (p) { p.className = "pulse " + (running ? "" : "idle"); }
}
$("#console-resize").addEventListener("mousedown", (e) => {
  _drag = { startY: e.clientY, startH: $("#console-body").offsetHeight };
  e.preventDefault();
});
document.addEventListener("mousemove", (e) => {
  if (!_drag) return;
  const d = dock();
  d.classList.add("open"); d.classList.remove("closed");
  const h = Math.max(80, Math.min(window.innerHeight - 120, _drag.startH - (e.clientY - _drag.startY)));
  $("#console-body").style.maxHeight = h + "px";
  $("#console-body").style.height = h + "px";
});
document.addEventListener("mouseup", () => { _drag = null; });
$("#console-toggle").onclick = () => {
  const d = dock();
  const open = d.classList.toggle("open");
  d.classList.remove("closed");
  $("#console-toggle").textContent = open ? "收起 ▾" : "展开 ▴";
  if (open) {
    const body = $("#console-body");
    if (!body.style.height) body.style.maxHeight = "30vh";
  }
};
$("#console-kill").onclick = async () => {
  if (currentRunId) await fetch("/api/run/" + currentRunId + "/kill", { method: "POST" });
};
// GPU 监控（每 2s）
async function pollGpu() {
  try {
    const r = await fetch("/api/gpu");
    const j = await r.json();
    const el = $("#gpu-bar");
    if (!el) return;
    if (!j.ok) { el.textContent = "GPU 不可用"; return; }
    const hot = j.util > 60 ? "gpu-hot" : "";
    el.textContent = `GPU ${j.util}% · ${j.mem_used_gb}/${j.mem_total_gb}G`;
    el.className = "gpu " + hot;
  } catch (e) { /* ignore */ }
}
setInterval(pollGpu, 2000);
pollGpu();
function consoleEcho(cmd, cwd) {
  const d = dock();
  d.classList.add("open"); d.classList.remove("closed");
  $("#console-toggle").textContent = "收起 ▾";
  $("#console-head-cmd").textContent = cmd ? "$ " + cmd : "";
  $("#console-body").textContent = cmd ? "$ " + cmd + "\n\n" + (cwd ? `# cwd: ${cwd}\n\n` : "") : "";
}
async function runCmd(title, project, cmd, cwd, onDone) {
  setPulse(true);
  consoleEcho(cmd, cwd);
  onRunDone = onDone || (() => {});
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  const r = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project, cmd, cwd: cwd || "" }),
  });
  const j = await r.json();
  if (!j.run_id) { $("#console-body").textContent += "\n启动失败: " + JSON.stringify(j); setPulse(false); return; }
  currentRunId = j.run_id;
  $("#console-kill").disabled = false;
  pollTimer = setInterval(pollRun, 800);
}
async function pollRun() {
  if (!currentRunId) return;
  const r = await fetch("/api/run/" + currentRunId);
  if (!r.ok) {
    clearInterval(pollTimer); pollTimer = null;
    $("#console-body").textContent += "\n\n[运行记录已失效（服务器可能已重启）]";
    $("#console-kill").disabled = true; setPulse(false);
    return;
  }
  const j = await r.json();
  $("#console-body").textContent = j.output || "";
  $("#console-body").scrollTop = $("#console-body").scrollHeight;
  if (!j.running) {
    clearInterval(pollTimer); pollTimer = null;
    $("#console-body").textContent += `\n\n[进程结束 exit=${j.exit_code}]`;
    $("#console-kill").disabled = true; setPulse(false);
    onRunDone();
  }
}

// ---------------- file viewer ----------------
async function viewFile(url, label) {
  const r = await fetch(url);
  if (!r.ok) { mainEl.innerHTML = `<h2>${esc(label)}</h2><p class="hint">无法读取（404）</p>`; return; }
  const ext = (url.split(".").pop() || "").toLowerCase();
  if (MEDIA_EXT.includes(ext)) {
    const media = ext === "mp4"
      ? `<video controls src="${url}" style="max-width:100%;max-height:70vh"></video>`
      : `<img src="${url}" style="max-width:100%;max-height:70vh">`;
    mainEl.innerHTML = `<h2>${esc(label)}</h2><div class="card">${media}</div>`;
    return;
  }
  const text = await r.text();
  let body;
  if (ext === "ipynb") {
    try {
      const nb = JSON.parse(text);
      let h = "";
      for (const cell of nb.cells || []) {
        const src = (cell.source || []).join("");
        if (cell.cell_type === "markdown") h += md(src);
        else if (cell.cell_type === "code") h += `<pre class="code">${esc(src)}</pre>`;
      }
      body = h || `<pre class="code">${esc(text)}</pre>`;
    } catch (e) { body = `<pre class="code">${esc(text)}</pre>`; }
  } else if (ext === "md") body = md(text);
  else body = `<pre class="code">${esc(text)}</pre>`;
  mainEl.innerHTML = `<h2>${esc(label)}</h2><div class="card">${body}</div>`;
}

// ---------------- project list ----------------
async function loadProjects() {
  const r = await fetch("/api/projects");
  const projects = await r.json();
  listEl.innerHTML = "";
  for (const p of projects) {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.textContent = p.name;
    a.href = "#project=" + encodeURIComponent(p.name);
    a.onclick = (e) => { e.preventDefault(); openProject(p.name); };
    li.appendChild(a);
    if (p.snippet) {
      const s = document.createElement("div");
      s.className = "snippet";
      s.textContent = p.snippet;
      li.appendChild(s);
    }
    listEl.appendChild(li);
  }
}

// ---------------- project detail ----------------
function fileGroupUI(files) {
  const groups = new Map();
  for (const f of files) {
    const parts = f.path.split("/");
    const g = parts.length > 1 ? parts[0] : "(根)";
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(f);
  }
  let html = "";
  for (const [g, fs] of groups) {
    html += `<details class="file-group" ${g === "(根)" ? "open" : ""}><summary>📂 ${esc(g)} (${fs.length})</summary><ul class="file-list">`;
    for (const f of fs) {
      html += `<li><a class="file-link" data-url="/proj/${encodeURIComponent(current)}/file/${encodeURIComponent(f.path)}" data-name="${esc(f.path)}">${esc(f.path)} <span class="fsize">${fmtSize(f.size)}</span></a></li>`;
    }
    html += "</ul></details>";
  }
  return html;
}
async function openProject(name) {
  current = name;
  document.querySelectorAll("#project-list li").forEach((li) => li.classList.remove("active"));
  const r = await fetch("/api/project/" + encodeURIComponent(name));
  const data = await r.json();
  const wfs = data.workflows || [];
  // 首页只展示工作流；项目介绍 / PROGRESS / 全部文件 / 产出都收进「📊 项目报告」
  mainEl.innerHTML = `<h2>📁 ${esc(name)} <button class="secondary" id="rep-btn" style="margin-left:.6rem;vertical-align:middle">📊 项目报告（介绍 / 进度 / 文件 / 指标）</button></h2>
    <div id="workflow-root"></div>
    <div class="card" id="no-wf" style="display:none"><p class="hint">本项目暂无 workflows.json 工作流配置。点右上「📊 项目报告」查看项目介绍、PROGRESS、全部文件与评估指标。</p></div>`;
  $("#rep-btn").onclick = () => projectReport(name);

  // ---- 工作流 ----
  const wroot = $("#workflow-root");
  if (!wfs.length) {
    $("#no-wf").style.display = "";
  } else {
    wroot.innerHTML = `<h3 style="margin:.4rem 0 .6rem">🔄 已跑通的训练-推理工作流（${wfs.length}）</h3>` +
      wfs.map((wf) => workflowCardHTML(name, wf)).join("");
    bindWorkflowCards(name, wfs, data.artifacts || []);
  }
}

// ---- 工作流卡片 ----
function workflowCardHTML(project, wf) {
  const kindBadge = wf.kind === "rl" ? '<span class="badge badge-sac">强化学习</span>'
    : wf.kind === "vla" ? '<span class="badge badge-vla">VLA</span>'
    : '<span class="badge badge-act">模仿学习</span>';
  const steps = (wf.steps || []).map((s, i) => `
    <div class="wf-step">
      <div class="wf-step-title">${esc(s.title || ("步骤 " + (i + 1)))}</div>
      <div class="wf-meaning">💡 含义：${esc(s.meaning || "")}</div>
      ${s.desc ? `<div class="wf-desc">${esc(s.desc)}</div>` : ""}
      ${s.cmd ? `<div class="wf-cmd"><code>${esc(s.cmd)}</code><button class="run-btn wf-run" data-cmd="${esc(s.cmd)}" data-cwd="workspace/${esc(project)}">▶ 运行</button></div>` : ""}
    </div>`).join("");
  const weights = (wf.weights || []).map((w, i) =>
    `<option value="${i}">${esc(w.label || w.path)}</option>`).join("");
  return `<div class="card wf-card" data-wf="${esc(wf.id || "")}">
    <div class="wf-head"><span class="wf-icon">${esc(wf.icon || "🔄")}</span>
      <div style="flex:1"><div class="wf-name">${esc(wf.name || wf.id)} ${kindBadge}</div>
      <div class="wf-summary">${esc(wf.summary || "")}</div></div></div>
    <div class="wf-steps">${steps}</div>
    <div class="wf-weights">
      <div class="form-row"><label>权重切换</label>
        <select class="wf-wsel">${weights || '<option value="">（无权重）</option>'}</select>
        <button class="secondary wf-use">🚀 用于推理</button></div>
      <div class="wf-weight-meta hint"></div>
    </div>
    <div class="wf-videos gallery"></div>
  </div>`;
}
function bindWorkflowCards(project, wfs, artifacts) {
  const cards = [...document.querySelectorAll(".wf-card")];
  wfs.forEach((wf) => {
    const card = cards.find((c) => c.dataset.wf === (wf.id || ""));
    if (!card) return;
    const ws = wf.weights || [];
    const sel = card.querySelector(".wf-wsel");
    const meta = card.querySelector(".wf-weight-meta");
    const useBtn = card.querySelector(".wf-use");
    // 步骤里的「运行」按钮
    card.querySelectorAll(".wf-run").forEach((b) => {
      b.onclick = () => runCmd(b.dataset.cmd, project, b.dataset.cmd, b.dataset.cwd || "workspace/" + project);
    });
    const update = () => {
      const w = ws[parseInt(sel.value)];
      if (!w) { meta.textContent = ""; return; }
      meta.textContent = `${w.note || ""}${w.desc ? " · " + w.desc : ""} — ${w.path}`;
    };
    sel.onchange = update;
    useBtn.onclick = () => {
      const w = ws[parseInt(sel.value)];
      if (!w) { alert("无权重"); return; }
      if (wf.kind === "rl") {
        const ck = w.path.includes("/checkpoints/") ? w.path.split("/pretrained_model")[0] : w.path;
        rlEvalDirect(project, ck);
      } else {
        inferView(w.path);
      }
    };
    update();
    const vdirs = wf.video_dirs || [];
    const vg = card.querySelector(".wf-videos");
    const cands = artifacts.filter((a) => vdirs.some((d) => a.name.startsWith(d + "/")));
    if (!cands.length) { vg.innerHTML = '<p class="hint">（该工作流暂无产出视频）</p>'; return; }
    const byStem = {};
    for (const a of cands) {
      const stem = a.name.split("/").pop().replace(/\.(mp4|gif)$/i, "");
      (byStem[stem] = byStem[stem] || []).push({ path: a.name });
    }
    for (const group of Object.values(byStem)) {
      const fig = mediaFigure(project, group);
      if (fig) vg.appendChild(fig);
    }
  });
}
// 从工作流跳转到 RL 评估（直接填入 checkpoint 并展开评估表单）
function rlEvalDirect(project, checkpointDir) {
  rlView().then(() => {
    // rlView 渲染后，直接展示评估表单并预填
    const card = $("#rl-eval-card");
    if (card) {
      card.style.display = "";
      $("#rl-eval-form").innerHTML = `<form id="rl-eval-form-inner">
        <div class="form-row"><label>checkpoint</label><input id="rev-ck" value="${esc(checkpointDir)}" style="font-family:Consolas" class="mini"></div>
        <div class="form-row"><label>局数</label><input id="rev-ep" type="number" value="3" min="1" class="mini"></div>
        <div class="form-row"><label>输出目录</label><input id="rev-outdir" value="outputs/eval/sac_pusht_gui" class="mini"></div>
        <div class="form-row"><label>🔴 实时画面</label><label class="hint" style="flex:1"><input type="checkbox" id="rev-live" style="width:auto;min-width:0"> 评估过程实时推流</label></div>
        <div class="form-row"><button type="submit">🎯 开始评估</button></div></form>`;
      $("#rl-eval-form-inner").onsubmit = async (e) => {
        e.preventDefault();
        const body = { checkpoint: $("#rev-ck").value, episodes: $("#rev-ep").value,
                       outdir: $("#rev-outdir").value, stream: $("#rev-live").checked };
        const j = await (await fetch("/api/rl_eval", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        })).json();
        if (j.error) { alert("失败: " + j.error); return; }
        const onDone = () => { stopLive(); showVideos(j.project, j.out_root || "outputs"); };
        if (j.stream_dir) startLive(j.project, j.stream_dir);
        runCmd("RL 评估 " + checkpointDir, j.project, j.cmd, j.cwd, onDone);
      };
      card.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
}

// ---------------- 项目报告 ----------------
async function projectReport(name) {
  const rm = await (await fetch("/proj/" + encodeURIComponent(name) + "/file/README.md"));
  const readme = rm.ok ? await rm.text() : "（无 README）";
  const [an, files, pj] = await Promise.all([
    (await fetch("/api/analysis")).json(),
    (await fetch("/api/project_files/" + encodeURIComponent(name))).json(),
    (await fetch("/api/project/" + encodeURIComponent(name))).json(),
  ]);
  const progress = pj.progress || "";
  const workflows = pj.workflows || [];
  const mine = an.filter((it) => it.project === name);

  // 指标分派到工作流（按 match 子串匹配；未匹配的归入「其他」）
  const buckets = workflows.map((w) => ({ wf: w, items: [] }));
  const other = { wf: { id: "other", name: "其他 / 未归类", icon: "📁", summary: "" }, items: [] };
  for (const it of mine) {
    let placed = false;
    for (const b of buckets) {
      if ((b.wf.match || []).some((pat) => it.rel.includes(pat))) { b.items.push(it); placed = true; break; }
    }
    if (!placed) other.items.push(it);
  }
  const allBuckets = [...buckets.filter((b) => b.items.length), ...(other.items.length ? [other] : [])];

  const metricTable = (items) => {
    const rows = items.map((it) => {
      const s = it.summary || {};
      const key = ["success_rate", "pc_success", "mean_max_coverage", "mean_sum_reward", "n_episodes", "ep0_max_coverage", "avg_reward", "avg_max_coverage"]
        .filter((k) => k in s).map((k) => `${esc(k)}=${esc(s[k])}`).join(" · ");
      return `<tr><td class="small">${esc(it.rel)}</td><td>${key || "（无结构化摘要）"}</td>
        <td><a class="file-link" href="#" data-url="/proj/${encodeURIComponent(name)}/file/${encodeURIComponent(it.rel)}" data-name="${esc(it.rel)}">打开</a></td></tr>`;
    }).join("");
    return `<table><thead><tr><th>结果文件</th><th>摘要</th><th></th></tr></thead><tbody>${rows || '<tr><td colspan="3">（无）</td></tr>'}</tbody></table>`;
  };
  const videoGallery = (vdirs) => {
    const cands = files.filter((f) => /\.(mp4|gif)$/.test(f.path) && vdirs.some((d) => f.path.startsWith(d + "/")));
    if (!cands.length) return '<p class="hint">（无视频）</p>';
    const byStem = {};
    for (const v of cands) { const stem = v.path.split("/").pop().replace(/\.(mp4|gif)$/i, ""); (byStem[stem] = byStem[stem] || []).push(v); }
    return Object.values(byStem).map((g) => {
      const gif = g.find((c) => c.path.endsWith(".gif"));
      const mp4 = g.find((c) => c.path.endsWith(".mp4"));
      const s = gif || mp4;
      if (!s) return "";
      const src = `/proj/${encodeURIComponent(name)}/file/${encodeURIComponent(s.path)}`;
      const dl = mp4 && gif ? ` <a class="file-link" href="${`/proj/${encodeURIComponent(name)}/file/${encodeURIComponent(mp4.path)}`}">⬇mp4</a>` : "";
      return `<figure>${gif ? `<img src="${src}">` : `<video controls src="${src}"></video>`}<figcaption class="hint">${esc(s.path.split("/").pop())}${dl}</figcaption></figure>`;
    }).join("");
  };

  const wfSections = allBuckets.map((b) => `
    <div class="card rep-wf">
      <h3>${esc(b.wf.icon || "🔄")} ${esc(b.wf.name || b.wf.id)}</h3>
      ${b.wf.summary ? `<p class="hint">${esc(b.wf.summary)}</p>` : ""}
      ${(b.wf.steps || []).length ? `<details><summary>流程步骤</summary><ol class="wf-steps">${(b.wf.steps || []).map((s) => `<li><b>${esc(s.title)}</b><br><span class="hint">${esc(s.meaning || "")}</span>${s.cmd ? `<br><code>${esc(s.cmd)}</code>` : ""}</li>`).join("")}</ol></details>` : ""}
      ${(b.wf.weights || []).length ? `<details><summary>权重（${b.wf.weights.length}）</summary><ul>${(b.wf.weights || []).map((w) => `<li><code>${esc(w.path)}</code> <span class="hint">${esc(w.label || "")} · ${esc(w.note || "")}</span></li>`).join("")}</ul></details>` : ""}
      <h4>📈 评估/推理指标（${b.items.length} 项）</h4>${metricTable(b.items)}
      <h4>🎬 推理视频</h4><div class="gallery">${videoGallery(b.wf.video_dirs || [])}</div>
    </div>`).join("");

  mainEl.innerHTML = `<h2>📊 项目报告 · ${esc(name)} <button class="secondary" onclick="window.print()">🖨 打印/导出 PDF</button> <button class="secondary" id="rep-export">⬇ 导出静态 HTML</button> <button class="secondary" id="rep-back">← 返回项目</button></h2>
    <div id="rep-body">
    <div class="card"><h3>📖 项目介绍</h3><div id="rep-readme">${md(readme)}</div></div>
    ${wfSections || '<div class="card"><p class="hint">（暂无工作流）</p></div>'}
    <div class="card"><h3>📈 进度（PROGRESS.md）</h3><div>${md(progress)}</div></div>
    <div class="card"><h3>📂 全部文件</h3><div id="rep-files">${fileGroupUI(files)}</div></div>
    </div>`;
  $("#rep-back").onclick = () => openProject(name);
  $("#rep-export").onclick = async () => {
    const css = `body{font-family:Inter,'Microsoft YaHei',sans-serif;background:#f5f7fa;color:#1f2733;margin:0;padding:2rem}
      h1{font-size:1.6rem}.card{background:#fff;border:1px solid #e4e8ef;border-radius:16px;padding:1.2rem 1.4rem;margin-bottom:1rem;box-shadow:0 1px 3px rgba(16,24,40,.06)}
      table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #e4e8ef;padding:.4rem .6rem;text-align:left;font-size:.85rem}
      .metric{display:inline-block;background:#f0f4f9;border-radius:8px;padding:.15rem .55rem;margin:.15rem .3rem;font-size:.76rem;font-family:Consolas,monospace}
      .gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:.9rem}
      .gallery img,.gallery video{width:100%;max-height:220px;object-fit:contain;border:1px solid #e4e8ef;border-radius:10px;background:#0f1520}
      figure{margin:0}.hint{color:#6b7686;font-size:.82rem}code{background:#f0f3f8;padding:.1rem .35rem;border-radius:5px}
      ol.wf-steps li{margin:.4rem 0}
      #rep-body{max-width:1000px;margin:0 auto}`;
    const html = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
      <title>项目报告 · ${esc(name)}</title><style>${css}</style></head>
      <body><h1>📊 项目报告 · ${esc(name)}</h1><div id="rep-body">${$("#rep-body").innerHTML}</div>
      <p class="hint" style="text-align:center;color:#9aa3ad;margin-top:2rem">由 robot GUI 生成 · ${new Date().toLocaleString()}</p>
      </body></html>`;
    const res = await fetch("/api/save_report", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: name, html }),
    });
    const j = await res.json();
    if (j.url) { window.open(j.url, "_blank"); alert("已导出: docs/reports/" + name + "_report.html"); }
    else alert("导出失败: " + (j.error || ""));
  };
  mainEl.querySelectorAll(".file-link").forEach((el) => {
    el.onclick = (e) => { e.preventDefault(); viewFile(el.dataset.url, el.dataset.name); };
  });
}

// ---------------- 数据集视图 ----------------
async function datasetsView() {
  mainEl.innerHTML = `<h2>📊 数据集</h2>
    <div class="card"><p class="hint">点击行查看详情（meta + 统计 + 审查指引）。「导入」从 HF 下载数据集。</p>
      <div class="toolbar"><button id="ds-refresh">🔄 刷新</button><button id="ds-import">⬇ 导入数据集</button></div>
      <table id="ds-table"><thead><tr><th>repo_id</th><th>来源</th><th>大小</th><th>episodes</th><th>帧数</th><th>fps</th><th>特征</th></tr></thead><tbody></tbody></table>
      <div id="ds-detail"></div>
    </div>`;
  const refresh = async () => {
    const ds = await (await fetch("/api/datasets")).json();
    const tb = $("#ds-table tbody");
    tb.innerHTML = ds.length ? "" : '<tr><td colspan="7">（无本地数据集，点「导入」下载）</td></tr>';
    for (const d of ds) {
      const tr = document.createElement("tr");
      tr.style.cursor = "pointer";
      tr.innerHTML = `<td>${esc(d.repo_id)}</td><td>${d.source}</td><td>${d.size_mb} MB</td>
        <td>${d.episodes ?? "-"}</td><td>${d.frames ?? "-"}</td><td>${d.fps ?? "-"}</td>
        <td class="small">${esc((d.features || []).slice(0, 4).join(", "))}</td>`;
      tr.onclick = () => datasetDetail(d.repo_id);
      tb.appendChild(tr);
    }
  };
  $("#ds-refresh").onclick = refresh;
  $("#ds-import").onclick = async () => {
    const repo = prompt("HF 数据集 repo_id（如 lerobot/libero、lerobot/pusht）：", "lerobot/libero");
    if (!repo) return;
    const j = await (await fetch("/api/datasets/import", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ repo_id: repo }),
    })).json();
    if (j.error) { alert("失败: " + j.error); return; }
    runCmd("导入数据集 " + repo, "libero", j.cmd, "workspace/libero", refresh);
  };
  refresh();
}
async function datasetDetail(repo) {
  const el = $("#ds-detail");
  if (!el) return;
  el.innerHTML = '<p class="hint">加载中…</p>';
  const r = await fetch("/api/dataset_detail?repo_id=" + encodeURIComponent(repo));
  const j = await r.json();
  if (j.error) { el.innerHTML = `<p class="hint">${esc(j.error)}</p>`; return; }
  const info = j.info || {}, stats = j.stats || {};
  const infoRows = Object.entries(info).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(typeof v === "object" ? JSON.stringify(v) : v)}</td></tr>`).join("");
  el.innerHTML = `<details open class="grp"><summary>🔎 ${esc(repo)} 详情</summary><div class="grp-inner">
    <h3>meta/info.json</h3><table>${infoRows || '<tr><td colspan="2">（无）</td></tr>'}</table>
    ${Object.keys(stats).length ? `<h3>meta/stats.json（特征统计）</h3><pre class="code">${esc(JSON.stringify(stats, null, 2))}</pre>` : ""}
    <div class="toolbar"><button id="pv-btn">🔍 数据预览（加载样本帧 + 动作分布）</button></div>
    <div id="pv-out"><p class="hint">点击按钮加载：取 3 个 episode 的首帧 + 动作分布（首次加载数据集约需 10-30 秒）</p></div>
    <p class="hint">审查要点：① episodes/帧数是否充足；② 特征是否含 image/state/action/language_instruction；③ 动作范围与状态维度是否与策略配置一致；④ 预览帧确认画面内容正确。</p>
  </div></details>`;
  $("#pv-btn").onclick = async () => {
    const out = $("#pv-out");
    out.innerHTML = '<p class="hint">加载数据集并采样…（约 10-40 秒）</p>';
    const r = await fetch("/api/dataset_preview?repo_id=" + encodeURIComponent(repo));
    const j = await r.json();
    if (j.error) { out.innerHTML = `<p class="hint">失败: ${esc(j.error)}</p>`; return; }
    const st = j.action_stats;
    let html = `<div class="toolbar" style="margin-top:.6rem"><button class="secondary" id="pv-playall">▶ 全部播放</button><button class="secondary" id="pv-stop">⏹ 停止</button></div><div style="display:flex;gap:1rem;flex-wrap:wrap">`;
    for (const e of j.episodes) {
      html += `<div style="border:1px solid var(--line);border-radius:14px;padding:.6rem">
        <h4 style="margin:.2rem 0">episode ${e.idx}（${e.length} 帧）</h4>
        <div class="pv-strip" data-frames='${JSON.stringify(e.frames)}' style="display:flex;gap:3px;flex-wrap:wrap">
          ${e.frames.map((b, i) => `<img src="data:image/jpeg;base64,${b}" style="width:96px;border-radius:8px;border:1px solid var(--line)">`).join("")}
        </div>
        <canvas class="pv-ts" width="420" height="120" data-series='${esc(JSON.stringify(e.action_series))}' style="width:100%;border:1px solid var(--line);border-radius:10px;background:#fafbfc;margin-top:.4rem"></canvas>
      </div>`;
    }
    html += `</div>
      <h4 style="margin:.6rem 0 .2rem">动作分布统计（${st.dims} 维）</h4>
      <p class="hint">mean=[${st.mean.join(",")}] · std=[${st.std.join(",")}] · range=[${st.min.join(",")}]~[${st.max.join(",")}]</p>`;
    out.innerHTML = html;
    out.querySelectorAll(".pv-ts").forEach((cv) => drawActionSeries(cv, JSON.parse(cv.dataset.series)));
    // 播放：轮播各 strip 的帧
    const strips = [...out.querySelectorAll(".pv-strip")];
    let timer = null;
    $("#pv-stop").onclick = () => { clearInterval(timer); timer = null; };
    $("#pv-playall").onclick = () => {
      if (timer) { clearInterval(timer); timer = null; }
      timer = setInterval(() => {
        strips.forEach((st2) => {
          const frames = JSON.parse(st2.dataset.frames);
          const imgs = [...st2.querySelectorAll("img")];
          const cur = imgs.findIndex((im) => im.style.borderColor === "rgb(232, 134, 60)");
          const next = (cur + 1) % imgs.length;
          imgs.forEach((im, i) => { im.style.borderColor = i === next ? "#e8863c" : "var(--line)"; });
        });
      }, 500);
    };
  };
}
function drawActionSeries(canvas, series) {
  if (!canvas || !series) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height, pad = 6;
  ctx.clearRect(0, 0, W, H);
  const keys = Object.keys(series);
  if (!keys.length) return;
  const all = keys.flatMap((k) => series[k]);
  const min = Math.min(...all), max = Math.max(...all), span = (max - min) || 1;
  const colors = ["#e8863c", "#1f77b4", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#6b3fa0"];
  keys.forEach((k, di) => {
    const data = series[k];
    ctx.strokeStyle = colors[di % colors.length];
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    data.forEach((v, i) => {
      const x = pad + ((W - pad * 2) * i) / Math.max(1, data.length - 1);
      const y = H - pad - ((H - pad * 2) * (v - min)) / span;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
  });
  // 图例
  ctx.font = "10px sans-serif";
  keys.forEach((k, di) => {
    ctx.fillStyle = colors[di % colors.length];
    ctx.fillText(k, pad + 4 + (di % 4) * 105, 12 + Math.floor(di / 4) * 12);
  });
}

// ---------------- 模型和权重视图 ----------------
function archBox(label, sub, color, kw) {
  return `<div class="arch-box" data-kw="${esc(kw || "")}" style="border-color:${color};cursor:pointer" title="点击查看参数"><div class="arch-label">${esc(label)}</div>${sub ? `<div class="arch-sub">${esc(sub)}</div>` : ""}<div class="arch-detail" style="display:none"></div></div>`;
}
function archArrow() { return `<div class="arch-arrow">→</div>`; }
function architectureHTML(m) {
  const t = m.type;
  if (t === "act") {
    return `<div class="arch">
      <div class="arch-row">${archBox("图像 image+image2", "2×256×256×3\n观测：双相机", "#1f77b4", "image vision input_features")}${archArrow()}${archBox("ResNet18 编码", "flatten→512 维视觉特征", "#2ca02c", "vision_backbone backbone")}${archArrow()}${archBox("Transformer Encoder", "处理当前观测", "#ff7f0e", "n_encoder_layers n_heads dim_model")}</div>
      <div class="arch-row">${archBox("状态 state", "8 维\n(关节+夹爪)", "#9467bd", "state input_features")}${archArrow()}${archBox("拼接 + VAE 潜变量", "latent_dim=32\n条件变分自编码", "#d62728", "use_vae latent_dim kl_weight")}</div>
      <div class="arch-row">${archBox("Transformer Decoder", "自回归生成动作序列", "#ff7f0e", "n_decoder_layers dim_feedforward")}${archArrow()}${archBox("动作块 chunk", "100 步 × 7 维关节增量\n每 100 步重规划", "#1f77b4", "chunk_size n_action_steps")}</div>
      <div class="arch-note">点击模块查看对应超参数。ACT = 视觉直接映射动作的模仿学习网络（无语言理解）。</div>
    </div>`;
  }
  if (t === "smolvla") {
    return `<div class="arch">
      <div class="arch-row">${archBox("图像 image+image2", "2×256×256×3", "#1f77b4", "image input_features")}${archArrow()}${archBox("SmolVLM2-500M 骨干", "视觉 token + 文本 token\n统一序列建模", "#2ca02c", "model_id vlm")}</div>
      <div class="arch-row">${archBox("语言指令", "如 pick up the black bowl…\nlanguage_instruction", "#9467bd", "task language")}${archArrow()}${archBox("同一骨干", "视觉+语言联合理解", "#2ca02c", "model_id")}</div>
      <div class="arch-row">${archBox("状态 state", "8 维（eef+轴角+夹爪）", "#d62728", "state input_features")}${archArrow()}${archBox("动作头 Action Head", "LLM token → 动作解码", "#ff7f0e", "action")}${archArrow()}${archBox("动作块", "100 步 × 7 维", "#1f77b4", "chunk_size n_action_steps")}</div>
      <div class="arch-note">点击模块查看对应超参数。SmolVLA = VLA：先理解再动作，一个模型按指令执行不同任务。</div>
    </div>`;
  }
  return `<p class="hint">模型类型 ${esc(t)} 暂无预设架构图，查看配置详情。</p>`;
}
const TYPE_GROUPS = {
  act: { label: "ACT（模仿学习）", badge: "badge-act", desc: "Transformer+ResNet 行为克隆" },
  smolvla: { label: "SmolVLA（视觉-语言-动作）", badge: "badge-vla", desc: "VLM 骨干 + 动作头" },
  gaussian_actor: { label: "SAC（强化学习）", badge: "badge-sac", desc: "CNN 编码器 + 高斯策略 + Critic" },
  vlm: { label: "VLM 基础模型", badge: "badge-vlm", desc: "视觉-语言骨干" },
};
function typeLabel(t) { return TYPE_GROUPS[t] ? TYPE_GROUPS[t].label : "其他模型"; }
function typeBadge(t) { return TYPE_GROUPS[t] ? TYPE_GROUPS[t].badge : "badge-other"; }
async function modelsView() {
  mainEl.innerHTML = `<h2>🧠 模型</h2>
    <div class="card"><p class="hint">两级分类：<b>模型架构</b>（ACT / SAC / SmolVLA / VLM）→ <b>权重实例</b>（同一训练的各 checkpoint 按步数承接）。每个权重带<b>功能注释</b>与<b>时间戳</b>。「架构」看结构图，「推理」填入推理表单，「删除」移除权重。</p>
      <div class="toolbar"><button id="md-refresh">🔄 刷新</button><button id="md-import">⬇ 导入模型/权重</button></div>
      <div id="md-list"></div></div>`;
  const refresh = async () => {
    const models = await (await fetch("/api/models")).json();
    const el = $("#md-list");
    if (!models.length) { el.innerHTML = '<p class="hint">（无本地模型，点「导入模型/权重」）</p>'; return; }
    // 第一级：按模型架构分组
    const byType = {};
    for (const m of models) (byType[m.type] = byType[m.type] || []).push(m);
    // 第二级：同一架构下按「模型实例（group）」分组
    let html = "";
    for (const t of Object.keys(byType).sort()) {
      const ms = byType[t];
      const byGroup = {};
      for (const m of ms) (byGroup[m.group] = byGroup[m.group] || []).push(m);
      const tg = TYPE_GROUPS[t];
      html += `<details class="grp" ${Object.keys(byType).length === 1 ? "open" : ""}><summary>📦 ${esc(typeLabel(t))}（${Object.keys(byGroup).length} 个模型实例）${tg ? `<span class="grp-sub">${esc(tg.desc)}</span>` : ""}</summary><div class="grp-inner">`;
      for (const [grp, gms] of Object.entries(byGroup)) {
        // 权重按承接顺序（checkpoint 步数 / last 靠后）
        const sorted = gms.slice().sort((a, b) => {
          const na = a.label === "last" ? 1e12 : (parseInt(a.label) || 0);
          const nb = b.label === "last" ? 1e12 : (parseInt(b.label) || 0);
          return na - nb;
        });
        const head = sorted[0];
        html += `<div class="model-card">
          <div class="model-head">
            <span class="model-name">${esc(grp)}</span>
            <span class="badge ${typeBadge(t)}">${esc(t)}</span>
            ${head.source === "hf-cache" ? '<span class="model-src">HF 缓存</span>' : '<span class="model-src">本地自训</span>'}
          </div>
          <div class="model-meta">${esc(head.note || "")}${head.desc ? " · " + esc(head.desc) : ""}</div>
          <table class="weights-table"><thead><tr><th>权重（step）</th><th>功能注释</th><th>时间戳</th><th></th></tr></thead><tbody>`;
        for (const m of sorted) {
          html += `<tr>
            <td class="wlabel">${esc(m.label)}</td>
            <td class="small">${esc(m.note || "-")}</td>
            <td class="small">${esc(m.ts_str || "-")}</td>
            <td class="wactions">
              <button class="arch-btn mini">🏗 架构</button>
              <button class="use-btn mini">🚀 推理</button>
              <button class="del-btn mini danger">🗑</button>
            </td></tr>`;
        }
        html += `</tbody></table></div>`;
      }
      html += "</div></details>";
    }
    el.innerHTML = html;
    // 计算按钮对应的权重顺序（架构→组→步数承接）
    const flat = [];
    for (const t of Object.keys(byType).sort()) {
      const gmap = {};
      for (const m of byType[t]) (gmap[m.group] = gmap[m.group] || []).push(m);
      for (const grp of Object.keys(gmap)) {
        flat.push(...gmap[grp].sort((a, b) => (a.label === "last" ? 1e12 : parseInt(a.label) || 0) - (b.label === "last" ? 1e12 : parseInt(b.label) || 0)));
      }
    }
    el.querySelectorAll(".arch-btn").forEach((b, i) => { b.onclick = () => modelArchView(flat[i]); });
    el.querySelectorAll(".use-btn").forEach((b, i) => { b.onclick = () => inferView(flat[i].path); });
    el.querySelectorAll(".del-btn").forEach((b, i) => {
      b.onclick = async () => {
        const m = flat[i];
        if (!confirm("确认删除权重：\n" + m.name + "\n" + m.path + " ?")) return;
        const j = await (await fetch("/api/models/delete", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: m.path }),
        })).json();
        alert(j.ok ? "已删除" : ("失败: " + j.error));
        refresh();
      };
    });
  };
  $("#md-refresh").onclick = refresh;
  $("#md-import").onclick = async () => {
    const repo = prompt("HF 模型 repo_id（如 HuggingFaceVLA/smolvla_libero）：", "HuggingFaceVLA/smolvla_libero");
    if (!repo) return;
    const j = await (await fetch("/api/models/import", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ repo_id: repo }),
    })).json();
    if (j.error) { alert("失败: " + j.error); return; }
    runCmd("导入模型 " + repo, "libero", j.cmd, "workspace/libero", refresh);
  };
  refresh();
}
async function modelArchView(m) {
  let cfg = {};
  try {
    const r = await fetch("/api/models_config?path=" + encodeURIComponent(m.path));
    if (r.ok) cfg = await r.json();
  } catch (e) { /* ignore */ }
  const kv = Object.entries(cfg).filter(([k]) => !["input_features", "output_features"].includes(k))
    .map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(JSON.stringify(v))}</td></tr>`).join("");
  mainEl.innerHTML = `<h2>🏗 ${esc(m.name)}（${esc(m.type)}）</h2>
    <div class="card">${architectureHTML(m)}</div>
    <div class="card"><h3>超参数（config.json）</h3>
      <table><thead><tr><th>键</th><th>值</th></tr></thead><tbody>${kv || '<tr><td colspan="2">（无）</td></tr>'}</tbody></table>
    </div>
    <div class="card"><h3>输入 / 输出特征</h3>
      <pre class="code">${esc(JSON.stringify({ input_features: cfg.input_features, output_features: cfg.output_features }, null, 2))}</pre>
    </div>
    <button id="arch-back">← 返回模型</button>`;
  $("#arch-back").onclick = modelsView;
  // 点击架构模块展开对应超参数
  mainEl.querySelectorAll(".arch-box").forEach((box) => {
    box.onclick = () => {
      const detail = box.querySelector(".arch-detail");
      const kw = (box.dataset.kw || "").toLowerCase().split(" ");
      const rows = Object.entries(cfg).filter(([k]) => kw.some((w) => k.toLowerCase().includes(w)))
        .map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(JSON.stringify(v))}</td></tr>`).join("");
      const show = detail.style.display === "none";
      detail.style.display = show ? "block" : "none";
      if (show) {
        detail.innerHTML = rows ? `<table class="arch-params"><tbody>${rows}</tbody></table>` : '<p class="hint">（该模块无匹配超参数）</p>';
      }
    };
  });
}

// ---------------- 训练视图 ----------------
async function trainView() {
  const ds = await (await fetch("/api/datasets")).json();
  const dsOpts = ds.map((d) => `<option value="${esc(d.repo_id)}">${esc(d.repo_id)}（${d.episodes ?? "?"} ep）</option>`).join("");
  mainEl.innerHTML = `<h2>🎓 训练</h2>
    <div class="card"><form id="train-form">
      <div class="form-row"><label>数据集</label><select id="tr-dataset">${dsOpts || '<option value="lerobot/pusht">lerobot/pusht</option>'}</select></div>
      <div class="form-row"><label>模型类型</label><select id="tr-policy"><option value="act">ACT</option><option value="smolvla">SmolVLA</option></select></div>
      <div class="form-row"><label>LIBERO 套件</label><input id="tr-task" value="libero_spatial" placeholder="libero_spatial/object/goal/10"></div>
      <div class="form-row"><label>训练步数</label><input id="tr-steps" type="number" value="5000" min="1"></div>
      <div class="form-row"><label>batch_size</label><input id="tr-batch" type="number" value="8" min="1" class="mini"></div>
      <div class="form-row"><label>chunk_size</label><input id="tr-chunk" type="number" value="100" min="1" class="mini"></div>
      <div class="form-row"><label>save_freq</label><input id="tr-save" type="number" value="5000" min="100" class="mini"></div>
      <div class="form-row"><label>🔁 训练中评估</label><label class="hint" style="flex:1"><input type="checkbox" id="tr-eval" style="width:auto;min-width:0"> 每 <input id="tr-evalfreq" type="number" value="5000" min="100" style="width:90px;display:inline-block"> 步在仿真环境里评估一次（边训边看成功率，会占用训练时间）</label></div>
      <div class="form-row"><label>输出目录</label><input id="tr-outdir" value="outputs/train/act_gui" placeholder="默认临时目录，不保存下次覆盖"></div>
      <div class="form-row"><label>（冒烟=50 步验证管线）</label><span style="flex:1;display:flex;gap:.6rem">
        <button type="submit" class="secondary">⚡ 正式训练</button>
        <button type="button" id="tr-smoke">🔥 冒烟测试（50 步）</button></span>
      </div>
    </form></div>
    <div class="card"><h3>说明</h3><ul class="hint">
      <li>输出目录留空/写 <code>outputs/train/tmp</code> 表示临时：不另存的话下次训练直接覆盖</li>
      <li>冒烟 = 50 步小跑，验证数据→预处理→模型→反向全链路（本机已多次验证）</li>
      <li>PushT 官方配方 batch8 + 60-80k 步；LIBERO-Spatial ACT 预算 10k≈1-2h</li></ul></div>`;
  const run = async (steps) => {
    const body = {
      dataset: $("#tr-dataset").value, policy: $("#tr-policy").value,
      env_task: $("#tr-task").value, steps: steps,
      batch_size: $("#tr-batch").value, output_dir: $("#tr-outdir").value,
      chunk_size: $("#tr-chunk").value, save_freq: $("#tr-save").value,
      eval_freq: $("#tr-eval").checked ? $("#tr-evalfreq").value : 0,
    };
    const j = await (await fetch("/api/train", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    })).json();
    if (j.error) { alert("失败: " + j.error); return; }
    runCmd((steps < 100 ? "冒烟训练" : "训练") + " " + body.policy + " @" + body.dataset, j.project, j.cmd, j.cwd);
  };
  $("#train-form").onsubmit = (e) => { e.preventDefault(); run(parseInt($("#tr-steps").value) || 5000); };
  $("#tr-smoke").onclick = () => run(50);
}

// ---------------- 推理 · 仿真视图（统一参数表单） ----------------
const INFER_PRESETS = {
  libero_spatial: { env: "libero", task: "libero_spatial", taskids: "[0]", outdir: "outputs/rollout_libero_spatial", label: "LIBERO · 空间" },
  libero_object: { env: "libero", task: "libero_object", taskids: "[0]", outdir: "outputs/rollout_libero_object", label: "LIBERO · 物体" },
  libero_goal: { env: "libero", task: "libero_goal", taskids: "[0]", outdir: "outputs/rollout_libero_goal", label: "LIBERO · 目标" },
  libero_long: { env: "libero", task: "libero_long", taskids: "[0]", outdir: "outputs/rollout_libero_long", label: "LIBERO · 长程" },
  pusht_official: { env: "official", task: "", taskids: "", outdir: "outputs/rollout_pusht_official", label: "PushT · 官方" },
  pusht_mujoco: { env: "mujoco", task: "", taskids: "", outdir: "outputs/rollout_pusht_mujoco", label: "PushT · MuJoCo" },
};
async function inferView(prefillPath) {
  const models = await (await fetch("/api/models")).json();
  const mOpts = models.filter((m) => m.type !== "vlm").map((m) => `<option value="${esc(m.path)}">${esc(m.name)}（${esc(m.type)}）</option>`).join("");
  const envOpts = ['<option value="libero">LIBERO（Franka · MuJoCo）</option>',
    '<option value="mujoco">PushT-MuJoCo（自建）</option>',
    '<option value="official">PushT-官方（pymunk 2D）</option>'].join("");
  const chips = Object.entries(INFER_PRESETS).map(([k, v]) =>
    `<button type="button" class="chip" data-preset="${k}" title="${esc(v.outdir)}">${esc(v.label)}</button>`).join("");
  mainEl.innerHTML = `<h2>🚀 推理</h2>
    <div class="card"><form id="infer-form">
      <div class="form-row"><label>任务预设</label><div class="chips" id="inf-chips">${chips}</div></div>
      <div class="form-row"><label>仿真环境</label><select id="inf-env">${envOpts}</select>
        <span class="hint" id="inf-preset-hint"></span></div>
      <div class="form-row"><label>模型权重</label><select id="inf-model">${mOpts || '<option value="">（先导入模型）</option>'}</select></div>
      <div class="form-row"><label>或手填路径</label><input id="inf-path" value="${esc(prefillPath || "")}" placeholder="权重目录或 hub id" style="font-family:Consolas"></div>
      <div class="form-row"><label>推理局数</label><input id="inf-ep" type="number" value="3" min="1" class="mini"></div>
      <div class="form-row"><label>输出目录</label><input id="inf-outdir" value="outputs/rollout_libero_spatial" placeholder="LIBERO 实时/ PushT 用；LIBERO 非实时自动存 outputs/eval"></div>
      <div class="form-row"><label>🔴 实时画面</label><label class="hint" style="flex:1"><input type="checkbox" id="inf-live" style="width:auto;min-width:0"> 推理过程中实时推流画面（结束仍生成视频）</label></div>
      <details id="inf-task-details"><summary>LIBERO 任务参数（套件 / task_ids）</summary>
        <div class="form-row"><label>任务套件</label><input id="inf-task" value="libero_spatial" style="font-family:Consolas" class="mini"></div>
        <div class="form-row"><label>task_ids</label><input id="inf-taskids" value="[0]" class="mini" style="width:90px"><span class="hint">范围 [0,9]；多任务如 [0,1]</span></div>
      </details>
      <div class="form-row"><button type="submit">🚀 开始推理</button><span class="hint">控制台显示命令与实时输出</span></div>
    </form></div>
    <div class="card" id="live-card" style="display:none"><h3>🖥 实时仿真画面</h3>
      <div class="live-panel"><div class="live-frame"><img id="live-img" alt="waiting..."><p class="hint" id="live-status">等待画面…</p></div>
      <div class="live-meta" id="live-meta"></div></div></div>
    <div class="card"><h3>🎬 推理结果</h3><div class="gallery" id="inf-gallery"><p class="hint">（推理完成后显示视频）</p></div></div>`;
  const applyEnvPreset = (env, task, taskids, outdir) => {
    const hint = $("#inf-preset-hint");
    const details = $("#inf-task-details");
    if (env === "libero") {
      details.style.display = "";
      hint.textContent = "LIBERO 实时用 inference_libero（带流），非实时用 lerobot-eval";
    } else {
      details.style.display = "none";
      hint.textContent = "PushT 用 run_pusht_rollout（官方 pymunk / 自建 MuJoCo）";
    }
    if (task) $("#inf-task").value = task;
    if (taskids) $("#inf-taskids").value = taskids;
    if (outdir) $("#inf-outdir").value = outdir;
  };
  $("#inf-chips").querySelectorAll(".chip").forEach((c) => {
    c.onclick = () => {
      const p = INFER_PRESETS[c.dataset.preset];
      $("#inf-env").value = p.env;
      applyEnvPreset(p.env, p.task, p.taskids, p.outdir);
      $("#inf-chips").querySelectorAll(".chip").forEach((x) => x.classList.toggle("active", x === c));
    };
  });
  $("#inf-env").onchange = () => applyEnvPreset($("#inf-env").value);
  $("#inf-model").onchange = () => { $("#inf-path").value = $("#inf-model").value; };
  $("#infer-form").onsubmit = async (e) => {
    e.preventDefault();
    const body = {
      env: $("#inf-env").value, policy_path: $("#inf-path").value || $("#inf-model").value,
      episodes: $("#inf-ep").value, task: $("#inf-task").value,
      task_ids: $("#inf-taskids").value, outdir: $("#inf-outdir").value,
      stream: $("#inf-live").checked,
    };
    if (!body.policy_path) { alert("请选择或填写模型权重路径"); return; }
    const j = await (await fetch("/api/infer", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    })).json();
    if (j.error) { alert("失败: " + j.error); return; }
    const onDone = () => {
      stopLive();
      showVideos(j.project, j.out_root || "outputs");
    };
    if (j.stream_dir) startLive(j.project, j.stream_dir);
    runCmd("推理 " + body.env + " @" + body.policy_path, j.project, j.cmd, j.cwd, onDone);
  };
  applyEnvPreset("libero");
}

// ---------------- RL 工作台（SAC on PushT） ----------------
async function rlView() {
  mainEl.innerHTML = `<h2>🎮 强化学习（SAC on PushT）</h2>
    <div class="card"><h3>SAC 训练流程</h3>
      <div class="arch">
        <div class="arch-row">
          ${archBox("① 采样（Actor 交互）", "策略看图像+位置\n输出动作 → 环境执行\n奖励=覆盖率", "#2ca02c", "")}${archArrow()}${archBox("② 训练（Learner 更新）", "Critic 学打分\nActor 学改进\n经验存 replay buffer", "#ff7f0e", "")}${archArrow()}${archBox("③ 评估（Checkpoint）", "加载权重去探索噪声\n跑 N 局算覆盖率/成功率", "#1f77b4", "")}
        </div>
        <div class="arch-note">SAC = 试错学习：没有标准答案，只有奖励数字。Actor 在仿真里不断交互攒经验，Critic 从中学习「什么动作未来奖励高」，Actor 跟着改进。训练与评估在同一页：先训练出 checkpoint，再评估该 checkpoint。</div>
      </div>
    </div>
    <div class="card"><h3>⚙️ 训练（阶段 ①+②，learner + actor 双进程）</h3><form id="rl-form">
      <div class="form-row"><label>运行名</label><input id="rl-job" value="sac_pusht" style="font-family:Consolas" class="mini"></div>
      <div class="form-row"><label>训练预设</label><select id="rl-preset">
        <option value="smoke">🔥 冒烟（600 交互步 · 约 1-2 分钟）</option>
        <option value="short">⚡ 短训（3000 步 · 约 5-10 分钟）</option>
        <option value="full">🚀 正式（10 万步 · 数小时）</option></select></div>
      <details><summary>高级参数（留空则用预设值）</summary>
        <div class="form-row"><label>episode_length</label><input id="rl-elen" type="number" class="mini" placeholder="200/300"></div>
        <div class="form-row"><label>online_steps（交互步数）</label><input id="rl-steps" type="number" class="mini" placeholder="600/3000/100000"></div>
        <div class="form-row"><label>batch_size</label><input id="rl-batch" type="number" value="64" class="mini"></div>
        <div class="form-row"><label>save_freq</label><input id="rl-save" type="number" class="mini" placeholder="200/1000/10000"></div>
        <div class="form-row"><label>开始学习前步数</label><input id="rl-before" type="number" value="40" class="mini"></div>
        <div class="form-row"><label>obs_type</label><select id="rl-obs"><option value="pixels_agent_pos">pixels_agent_pos（96×96 视觉 + 状态）</option><option value="environment_state_agent_pos">environment_state_agent_pos（16 关键点 + 状态）</option></select></div>
        <div class="form-row"><label>设备</label><select id="rl-device"><option value="cuda">cuda</option><option value="cpu">cpu</option></select></div>
        <div class="form-row"><label>fps</label><input id="rl-fps" type="number" value="10" class="mini"></div>
      </details>
      <div class="form-row"><button type="submit">🎮 开始训练（learner + actor）</button>
        <span class="hint">监督脚本自动：启 learner → 等端口 → 启 actor → 等完成 → 冲刷落盘 → 清理</span></div>
    </form></div>
    <div class="card"><h3>📦 训练运行（checkpoint 承接） <button id="rl-refresh" class="secondary">🔄 刷新</button></h3><div id="rl-runs"></div></div>
    <div class="card" id="rl-eval-card" style="display:none"><h3>🎯 评估（阶段 ③：加载 checkpoint 推理）</h3><div id="rl-eval-form"></div></div>
    <div class="card" id="live-card" style="display:none"><h3>🖥 实时仿真画面</h3>
      <div class="live-panel"><div class="live-frame"><img id="live-img" alt="waiting..."><p class="hint" id="live-status">等待画面…</p></div>
      <div class="live-meta" id="live-meta"></div></div></div>
    <div class="card"><h3>🎬 评估结果</h3><div class="gallery" id="inf-gallery"><p class="hint">（评估完成后显示视频）</p></div></div>`;

  const run = async () => {
    const body = {
      job_name: $("#rl-job").value, preset: $("#rl-preset").value,
      episode_length: $("#rl-elen").value, online_steps: $("#rl-steps").value,
      batch_size: $("#rl-batch").value, save_freq: $("#rl-save").value,
      online_before: $("#rl-before").value, obs_type: $("#rl-obs").value,
      device: $("#rl-device").value, fps: $("#rl-fps").value,
    };
    const j = await (await fetch("/api/rl", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    })).json();
    if (j.error) { alert("失败: " + j.error); return; }
    runCmd("RL 训练 " + body.job_name, j.project, j.cmd, j.cwd, refreshRuns);
  };

  const refreshRuns = async () => {
    const runs = await (await fetch("/api/rl_runs")).json();
    const el = $("#rl-runs");
    if (!el) return;
    if (!runs.length) { el.innerHTML = '<p class="hint">（暂无 RL 训练运行。点上方「开始训练」跑一次冒烟）</p>'; return; }
    el.innerHTML = runs.map((r) => `
      <div class="model-card">
        <div class="model-head"><span class="model-name">📦 ${esc(r.job)}</span><span class="model-src">${esc(r.dir)}</span></div>
        <div class="model-meta">
          <span class="metric">优化步数=${r.opt_step ?? "—"}</span>
          <span class="metric">交互局=${r.n_episodes}</span>
          <span class="metric">最新局奖励=${r.latest_ep_reward ?? "—"}</span>
          <span class="metric">checkpoints=[${r.checkpoints.join(", ")}]${r.has_last ? " + last" : ""}</span>
        </div>
        <div class="model-actions">
          <select class="rl-ck" data-dir="${esc(r.dir)}">
            ${r.checkpoints.map((s) => `<option value="${s}">${s}</option>`).join("")}
            ${r.has_last ? '<option value="last">last</option>' : ""}
          </select>
          <button class="secondary rl-eval" data-dir="${esc(r.dir)}" data-job="${esc(r.job)}">🎯 评估该 checkpoint</button>
          <a class="btn-link" href="/proj/pusht/out/${esc(r.dir)}/checkpoints/last" target="_blank">📂 打开目录</a>
        </div>
      </div>`).join("");
    el.querySelectorAll(".rl-eval").forEach((b) => {
      b.onclick = () => showRlEval(b.dataset.dir, b.dataset.job, b.closest(".model-card").querySelector(".rl-ck").value);
    });
  };

  const showRlEval = (dir, job, ck) => {
    const card = $("#rl-eval-card");
    card.style.display = "";
    card.scrollIntoView({ behavior: "smooth", block: "start" });
    $("#rl-eval-form").innerHTML = `<form id="rl-eval-form-inner">
      <div class="form-row"><label>checkpoint</label><input id="rev-ck" value="${esc(dir)}/checkpoints/${esc(ck || "last")}" style="font-family:Consolas" class="mini"></div>
      <div class="form-row"><label>局数</label><input id="rev-ep" type="number" value="3" min="1" class="mini"></div>
      <div class="form-row"><label>输出目录</label><input id="rev-outdir" value="outputs/eval/sac_pusht_gui" class="mini"></div>
      <div class="form-row"><label>🔴 实时画面</label><label class="hint" style="flex:1"><input type="checkbox" id="rev-live" style="width:auto;min-width:0"> 评估过程实时推流（结束仍生成视频）</label></div>
      <div class="form-row"><button type="submit">🎯 开始评估</button><span class="hint">评估 = SAC 的「推理」：确定性动作跑环境，输出覆盖率/成功率</span></div></form>`;
    $("#rl-eval-form-inner").onsubmit = async (e) => {
      e.preventDefault();
      const body = { checkpoint: $("#rev-ck").value, episodes: $("#rev-ep").value,
                     outdir: $("#rev-outdir").value, stream: $("#rev-live").checked };
      const j = await (await fetch("/api/rl_eval", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      })).json();
      if (j.error) { alert("失败: " + j.error); return; }
      const onDone = () => { stopLive(); showVideos(j.project, j.out_root || "outputs"); };
      if (j.stream_dir) startLive(j.project, j.stream_dir);
      runCmd("RL 评估 " + job + " @" + body.checkpoint, j.project, j.cmd, j.cwd, onDone);
    };
  };

  $("#rl-form").onsubmit = (e) => { e.preventDefault(); run(); };
  $("#rl-refresh").onclick = refreshRuns;
  refreshRuns();
}
let _liveEs = null;
let _liveStop = false;
function startLive(project, sdir) {
  const card = $("#live-card");
  if (!card) return;
  card.style.display = "";
  const img = $("#live-img"), meta = $("#live-meta"), status = $("#live-status");
  if (status) status.textContent = "连接中…";
  if (_liveEs) { try { _liveEs.close(); } catch (e) { /* */ } _liveEs = null; }
  _liveStop = false;
  const url = `/ws/stream?project=${encodeURIComponent(project)}&dir=${encodeURIComponent(sdir)}`;
  const wsProto = location.protocol === "https:" ? "wss:" : "ws:";
  const connect = () => {
    if (_liveStop) return;
    let ws;
    try { ws = new WebSocket(wsProto + "//" + location.host + url); } catch (e) { if (status) status.textContent = "WS 失败: " + e; return; }
    _liveEs = ws;
    ws.onmessage = (e) => {
      let d = {};
      try { d = JSON.parse(e.data); } catch (err) { return; }
      if (d.done) { if (status) status.textContent = "✅ 推理完成"; stopLive(false); return; }
      if (d.img && img) { img.src = d.img; img.style.display = "block"; if (status) status.textContent = ""; }
      if (d.info && meta) {
        let it = {};
        try { it = JSON.parse(d.info); } catch (err) { it = { raw: d.info }; }
        meta.innerHTML = Object.entries(it).map(([k, v]) =>
          `<span class="metric">${esc(k)} = ${esc(typeof v === "object" ? JSON.stringify(v) : v)}</span>`).join("");
      }
    };
    ws.onerror = () => { if (status) status.textContent = "流中断（运行结束或异常）"; };
    ws.onclose = () => {
      if (!_liveStop) setTimeout(connect, 800); // 自动重连
    };
  };
  connect();
}
function stopLive(close = true) {
  _liveStop = true;
  if (_liveEs) { try { _liveEs.close(); } catch (e) { /* */ } _liveEs = null; }
}
function showVideos(project, outRoot) {
  const gal = $("#inf-gallery");
  if (!gal) return;
  const base = String(outRoot || "outputs").replace(/^\.\.\/|^\.\//, "");
  fetch(`/api/project_files/${encodeURIComponent(project)}`).then((r) => r.json()).then((files) => {
    let cands = files.filter((f) => f.path.startsWith(base + "/") && /\.(mp4|gif)$/.test(f.path));
    if (base === "outputs/eval" && cands.length) {
      const groups = {};
      for (const c of cands) {
        const parts = c.path.split("/");
        const seg = parts.length > 3 ? parts[2] + "/" + parts[3] : parts[2] || "?";
        (groups[seg] = groups[seg] || []).push(c);
      }
      cands = groups[Object.keys(groups).sort().pop()] || [];
    }
    gal.innerHTML = cands.length ? "" : '<p class="hint">（输出目录暂无视频，检查控制台输出）</p>';
    const byStem = {};
    for (const v of cands) {
      const stem = v.path.split("/").pop().replace(/\.(mp4|gif)$/i, "");
      (byStem[stem] = byStem[stem] || []).push(v);
    }
    for (const group of Object.values(byStem)) {
      const fig = mediaFigure(project, group);
      if (fig) gal.appendChild(fig);
    }
  });
}

// ---------------- 分析视图（模型→权重→项目 分级） ----------------
async function analysisView() {
  mainEl.innerHTML = `<h2>📈 分析（分级：模型 → 权重 → 项目）</h2>
    <div class="card"><p class="hint">点击模型大类展开权重，再点权重展开各项目的推理/评估结果；勾选权重可对比覆盖率曲线；点「原始」看 metrics.json。metrics 是每次评估的记录（成功率/覆盖率等），不是权重文件。</p>
      <div class="toolbar"><button id="an-refresh">🔄 刷新</button><button id="an-chart-btn" class="secondary">📈 覆盖率曲线对比</button></div>
      <div id="an-list"></div>
      <div id="an-chart" style="display:none"><h3>📉 覆盖率 / 成功率曲线（勾选对比）</h3><canvas id="an-canvas" width="900" height="320" style="width:100%;border:1px solid var(--line);border-radius:12px;background:#fff"></canvas></div>
    </div>`;
  let checked = [];
  const refresh = async () => {
    const items = await (await fetch("/api/analysis")).json();
    const models = await (await fetch("/api/models")).json();
    const el = $("#an-list");
    if (!items.length) { el.innerHTML = '<p class="hint">（暂无 metrics 结果）</p>'; return; }
    // 权重级 = 模型名（若 metrics 路径能对上模型）否则项目名；项目级 = 具体结果路径
    const tree = {};
    for (const it of items) {
      const p = it.rel;
      let mName = null;
      for (const m of models) {
        if (p.includes(m.path.split(/[\\/]/).slice(-1)[0]) || p.includes(m.name.replace("/", "_"))) { mName = m.name; break; }
      }
      const type = mName ? ((models.find((m) => m.name === mName) || {}).type || "?") : "项目产出";
      const weight = mName || it.project;
      (tree[type] = tree[type] || {});
      (tree[type][weight] = tree[type][weight] || []).push(it);
    }
    let html = "";
    let flat = [];
    for (const [type, wg] of Object.entries(tree)) {
      html += `<details class="grp"><summary>🧩 ${esc(type)}</summary><div class="grp-inner">`;
      for (const [weight, its] of Object.entries(wg)) {
        html += `<details class="grp"><summary>📦 ${esc(weight)}（${its.length} 项）</summary><div class="grp-inner">`;
        for (const it of its) {
          const s = it.summary || {};
          const vals = Object.entries(s).filter(([k]) => k !== "raw").map(([k, v]) =>
            `<span class="metric">${esc(k)}=${esc(typeof v === "object" ? JSON.stringify(v) : v)}</span>`).join("");
          html += `<div class="model-card" data-proj="${esc(it.project)}" data-rel="${esc(it.rel)}">
            <div class="model-head"><label class="hint" style="margin-right:.3rem"><input type="checkbox" class="an-check"> 对比</label>
              <span class="model-name">${esc(it.project)} / ${esc(it.rel)}</span></div>
            <div class="model-meta">${vals || "（无结构化摘要）"}</div>
            ${s.raw ? `<pre class="code">${esc(s.raw)}</pre>` : ""}
            <div class="model-actions"><button class="raw-btn">🔎 查看原始</button></div></div>`;
          flat.push(it);
        }
        html += "</div></details>";
      }
      html += "</div></details>";
    }
    el.innerHTML = html;
    el.querySelectorAll(".raw-btn").forEach((b) => {
      b.onclick = () => {
        const card = b.closest(".model-card");
        viewFile(`/proj/${encodeURIComponent(card.dataset.proj)}/file/${encodeURIComponent(card.dataset.rel)}`, card.dataset.rel);
      };
    });
    el.querySelectorAll(".an-check").forEach((cb, i) => {
      cb.checked = checked.includes(flat[i].rel);
      cb.onchange = () => {
        const it = flat[i];
        checked = cb.checked ? [...checked, it.rel] : checked.filter((x) => x !== it.rel);
        drawCompare();
      };
    });
  };
  async function drawCompare() {
    const wrap = $("#an-chart");
    if (!checked.length) { wrap.style.display = "none"; return; }
    const items = await (await fetch("/api/analysis")).json();
    const sel = items.filter((it) => checked.includes(it.rel));
    const canvas = $("#an-canvas");
    if (!canvas) return;
    wrap.style.display = "";
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height, pad = 34;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#fafbfc"; ctx.fillRect(0, 0, W, H);
    const colors = ["#e8863c", "#1f77b4", "#2ca02c", "#d62728", "#9467bd", "#8c564b"];
    // 同权重多次运行（rel 去掉尾部的 seed/序号）聚合为均值±std
    const groups = {};
    for (const it of sel) {
      try {
        const r = await fetch(`/proj/${encodeURIComponent(it.project)}/file/${encodeURIComponent(it.rel)}`);
        const data = await r.json();
        const eps = data.episodes || [];
        const cov = eps.map((e, i) => (e.coverages ? Math.max(...e.coverages) : (e.max_coverage ?? e.max_rewards ?? 0)));
        if (!cov.length) continue;
        const base = it.rel.replace(/\.\.\/|metrics\.(json|txt)$/g, "").replace(/[\s_]*(seed|s|run)?[\s_]*\d+$/i, "");
        (groups[base] = groups[base] || { runs: [] }).runs.push(cov);
      } catch (e) { /* ignore */ }
    }
    let maxY = 1, n = 0;
    const series = Object.entries(groups).map(([name, { runs }]) => {
      const len = Math.max(...runs.map((r) => r.length));
      n = Math.max(n, len);
      const mean = [], std = [], cnt = [];
      for (let i = 0; i < len; i++) {
        const vals = runs.map((r) => r[i]).filter((v) => v != null);
        const m = vals.reduce((a, b) => a + b, 0) / (vals.length || 1);
        mean.push(m);
        std.push(vals.length > 1 ? Math.sqrt(vals.reduce((a, b) => a + (b - m) * (b - m), 0) / vals.length) : 0);
        cnt.push(vals.length);
      }
      maxY = Math.max(maxY, ...mean.map((m, i) => m + std[i]));
      return { name, mean, std, cnt };
    });
    const x = (i) => pad + ((W - pad * 2) * i) / Math.max(1, n - 1);
    const y = (v) => H - pad - ((H - pad * 2) * v) / maxY;
    ctx.strokeStyle = "#c3cad4"; ctx.fillStyle = "#6b7686";
    for (let g = 0; g <= 4; g++) {
      const yy = y(maxY * g / 4);
      ctx.beginPath(); ctx.moveTo(pad, yy); ctx.lineTo(W - pad, yy); ctx.stroke();
      ctx.fillText((maxY * g / 4).toFixed(2), 4, yy + 4);
    }
    ctx.fillText("episode →", W - pad - 52, H - 8);
    series.forEach((s, si) => {
      const col = colors[si % colors.length];
      // 阴影带（均值±std）
      ctx.fillStyle = col + "55";
      ctx.beginPath();
      s.mean.forEach((_, i) => { const xv = x(i); i === 0 ? ctx.moveTo(xv, y(s.mean[i] - s.std[i])) : ctx.lineTo(xv, y(s.mean[i] - s.std[i])); });
      for (let i = s.mean.length - 1; i >= 0; i--) ctx.lineTo(x(i), y(s.mean[i] + s.std[i]));
      ctx.closePath(); ctx.fill();
      // 均值线
      ctx.strokeStyle = col; ctx.lineWidth = 2;
      ctx.beginPath();
      s.mean.forEach((v, i) => { const xv = x(i); i === 0 ? ctx.moveTo(xv, y(v)) : ctx.lineTo(xv, y(v)); });
      ctx.stroke();
      ctx.fillStyle = col; ctx.font = "11px sans-serif";
      ctx.fillText(`${s.name} (n=${s.cnt[0]})`, pad + 4, 14 + si * 14);
    });
  }
  $("#an-refresh").onclick = refresh;
  $("#an-chart-btn").onclick = drawCompare;
  refresh();
}

// ---------------- 全局导航 ----------------
async function loadGlobalNav() {
  const g = await (await fetch("/api/global_files")).json();
  const wrap = $("#global-files");
  if (!wrap) return;
  let html = "";
  const mdOnly = (arr) => arr.filter((f) => f.ext === "md").map((f) => f.path);
  const baseUrl = (kind, path) => `/proj/_/${kind}/${encodeURIComponent(path)}`;
  for (const p of mdOnly(g.root)) html += `<li><a class="file-link" data-url="${baseUrl("root", p)}" data-name="${esc(p)}">📄 ${esc(p)}</a></li>`;
  if (mdOnly(g.note).length) {
    html += `<li class="nav-sep">📓 学习笔记</li>`;
    for (const p of mdOnly(g.note)) html += `<li><a class="file-link" data-url="${baseUrl("note", p)}" data-name="${esc(p)}">${esc(p)}</a></li>`;
  }
  if (mdOnly(g.docs).length) {
    html += `<li class="nav-sep">📚 文档</li>`;
    for (const p of mdOnly(g.docs)) html += `<li><a class="file-link" data-url="${baseUrl("doc", p)}" data-name="${esc(p)}">${esc(p)}</a></li>`;
  }
  wrap.innerHTML = html;
  wrap.querySelectorAll(".file-link").forEach((el) => {
    el.onclick = (e) => { e.preventDefault(); viewFile(el.dataset.url, el.dataset.name); };
  });
}
$("#nav-datasets").onclick = (e) => { e.preventDefault(); datasetsView(); };
$("#nav-models").onclick = (e) => { e.preventDefault(); modelsView(); };
$("#nav-train").onclick = (e) => { e.preventDefault(); trainView(); };
$("#nav-rl").onclick = (e) => { e.preventDefault(); rlView(); };
$("#nav-infer").onclick = (e) => { e.preventDefault(); inferView(); };
$("#nav-analysis").onclick = (e) => { e.preventDefault(); analysisView(); };
$("#nav-report").onclick = (e) => {
  e.preventDefault();
  mainEl.innerHTML = `<h2>🖼 推理报告</h2>
    <div class="card"><iframe src="/api/report" style="width:100%;height:78vh;border:0;border-radius:10px;"></iframe></div>`;
};
$("#nav-new-project").onclick = async (e) => {
  e.preventDefault();
  const name = prompt("新小项目名（字母数字下划线）：", "my_project");
  if (!name) return;
  const desc = prompt("一句话介绍：", "新小项目");
  const j = await (await fetch("/api/create_project", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, desc }),
  })).json();
  if (j.error) { alert("失败: " + j.error); return; }
  await loadProjects();
  openProject(j.name);
};
$("#nav-shutdown").onclick = async (e) => {
  e.preventDefault();
  if (!confirm("确定关闭本地 GUI 服务？关闭后需重新运行 python gui/server.py 启动。")) return;
  try { await fetch("/api/shutdown"); } catch (err) { /* gone */ }
  document.body.innerHTML = '<div style="padding:3rem;font-family:Microsoft YaHei;color:#f5f6f7"><h2>服务已关闭</h2><p>可关闭此标签页，或重新运行 <code>python gui/server.py</code> 再次启动。</p></div>';
};

loadProjects();
loadGlobalNav();

// URL hash 深链：#project=pusht 直达项目首页（刷新/分享/书签可用）
function initHashRoute() {
  const m = location.hash.match(/^#project=(.+)$/);
  if (m) {
    const name = decodeURIComponent(m[1]);
    if (name && !/^[A-Za-z0-9_\-]+$/.test(name)) return;
    if (name) openProject(name);
  }
}
window.addEventListener("hashchange", initHashRoute);
initHashRoute();
