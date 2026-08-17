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

// ---------------- console dock ----------------
const dock = () => $("#console-dock");
function setPulse(running) {
  const p = $("#console-pulse");
  if (p) { p.className = "pulse " + (running ? "" : "idle"); }
}
$("#console-toggle").onclick = () => {
  const d = dock();
  const open = d.classList.toggle("open");
  d.classList.remove("closed");
  $("#console-toggle").textContent = open ? "收起 ▾" : "展开 ▴";
};
$("#console-kill").onclick = async () => {
  if (currentRunId) await fetch("/api/run/" + currentRunId + "/kill", { method: "POST" });
};
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
    a.onclick = () => openProject(p.name);
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
  mainEl.innerHTML = `<h2>📁 ${name}</h2>
    <div class="card" id="readme-view"></div>
    <div class="card" id="progress-view">${md(data.progress || "（无 PROGRESS.md）")}</div>
    <div class="card"><h3>⚡ 常用命令</h3><div id="commands"></div></div>
    <div class="card"><h3>🎬 产出（视频 / 图表）</h3><div class="gallery" id="gallery"></div></div>
    <div class="card"><h3>📂 全部文件</h3><div id="files"></div></div>`;
  const rm = await fetch("/proj/" + encodeURIComponent(name) + "/file/README.md");
  if (rm.ok) {
    const rmd = await rm.text();
    $("#readme-view").innerHTML = `<div class="readme-tag">📖 项目介绍（README.md）</div>` + md(rmd);
  } else {
    $("#readme-view").innerHTML = "";
  }
  const cmds = $("#commands");
  if (!data.commands.length) cmds.innerHTML = '<p class="hint">（无 commands.json）</p>';
  for (const c of data.commands) {
    const div = document.createElement("div");
    div.className = "command";
    div.innerHTML = `<div class="head"><span class="name">${esc(c.name)}</span></div>
      <div class="desc">${esc(c.desc || "")}</div><div class="cmdline">${esc(c.cmd)}</div>
      <div class="runbar"><button class="run-btn">▶ 运行</button></div>`;
    div.querySelector(".run-btn").onclick = () => runCmd(c.name, name, c.cmd, c.cwd || "");
    cmds.appendChild(div);
  }
  const gal = $("#gallery");
  if (!data.artifacts.length) gal.innerHTML = '<p class="hint">（无产出文件）</p>';
  for (const a of data.artifacts) {
    const fig = document.createElement("figure");
    const cap = document.createElement("figcaption");
    cap.textContent = a.name;
    if (a.name.endsWith(".mp4")) {
      const v = document.createElement("video");
      v.controls = true; v.src = a.url;
      fig.appendChild(v);
    } else {
      const im = document.createElement("img");
      im.loading = "lazy"; im.src = a.url;
      fig.appendChild(im);
    }
    fig.appendChild(cap);
    gal.appendChild(fig);
  }
  const filesEl = $("#files");
  filesEl.innerHTML = '<p class="hint">加载中…</p>';
  const fr = await fetch("/api/project_files/" + encodeURIComponent(name));
  const files = await fr.json();
  if (!files.length) filesEl.innerHTML = '<p class="hint">（无文件）</p>';
  else {
    filesEl.innerHTML = fileGroupUI(files);
    filesEl.querySelectorAll(".file-link").forEach((el) => {
      el.onclick = (e) => { e.preventDefault(); viewFile(el.dataset.url, el.dataset.name); };
    });
  }
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
    <p class="hint">审查要点：① episodes/帧数是否充足；② 特征是否含 image/state/action/language_instruction；③ 动作范围与状态维度是否与策略配置一致；④ 用「查看数据集信息」命令（lerobot-info）看逐 episode 明细。</p>
  </div></details>`;
}

// ---------------- 模型和权重视图 ----------------
function archBox(label, sub, color) {
  return `<div class="arch-box" style="border-color:${color}"><div class="arch-label">${esc(label)}</div>${sub ? `<div class="arch-sub">${esc(sub)}</div>` : ""}</div>`;
}
function archArrow() { return `<div class="arch-arrow">→</div>`; }
function architectureHTML(m) {
  const t = m.type;
  if (t === "act") {
    return `<div class="arch">
      <div class="arch-row">${archBox("图像 image+image2", "2×256×256×3\n观测：双相机", "#1f77b4")}${archArrow()}${archBox("ResNet18 编码", "flatten→512 维视觉特征", "#2ca02c")}${archArrow()}${archBox("Transformer Encoder", "4 层 · 8 头 · dim 512\n处理当前观测", "#ff7f0e")}</div>
      <div class="arch-row">${archBox("状态 state", "8 维\n(关节+夹爪)", "#9467bd")}${archArrow()}${archBox("拼接 + VAE 潜变量", "latent_dim=32\n条件变分自编码", "#d62728")}</div>
      <div class="arch-row">${archBox("Transformer Decoder", "1 层\n自回归生成动作序列", "#ff7f0e")}${archArrow()}${archBox("动作块 chunk", "100 步 × 7 维关节增量\n每 100 步重规划", "#1f77b4")}</div>
      <div class="arch-note">ACT = 视觉直接映射动作的模仿学习网络（无语言理解）；训练用行为克隆 + VAE 正则。</div>
    </div>`;
  }
  if (t === "smolvla") {
    return `<div class="arch">
      <div class="arch-row">${archBox("图像 image+image2", "2×256×256×3", "#1f77b4")}${archArrow()}${archBox("SmolVLM2-500M 骨干", "视觉 token + 文本 token\n统一序列建模", "#2ca02c")}</div>
      <div class="arch-row">${archBox("语言指令", "如 pick up the black bowl…\nlanguage_instruction", "#9467bd")}${archArrow()}${archBox("同上骨干", "视觉+语言联合理解\n(理解看到什么+要做什么)", "#2ca02c")}</div>
      <div class="arch-row">${archBox("状态 state", "8 维（可选输入）", "#d62728")}${archArrow()}${archBox("动作头 Action Head", "LLM 输出 token → 动作解码", "#ff7f0e")}${archArrow()}${archBox("动作块", "100 步 × 7 维", "#1f77b4")}</div>
      <div class="arch-note">SmolVLA = VLA：先「视觉+语言理解」再生成动作 → 一个模型可按指令执行不同任务（语言条件策略）。</div>
    </div>`;
  }
  return `<p class="hint">模型类型 ${esc(t)} 暂无预设架构图，查看配置详情。</p>`;
}
async function modelsView() {
  mainEl.innerHTML = `<h2>🧠 模型和权重</h2>
    <div class="card"><p class="hint">按模型大类分组，每类下列出已有权重；点「架构」看带注释的结构图与超参数，「推理」填入推理表单，「删除」移除权重。</p>
      <div class="toolbar"><button id="md-refresh">🔄 刷新</button><button id="md-import">⬇ 导入模型/权重</button></div>
      <div id="md-list"></div></div>`;
  const refresh = async () => {
    const models = await (await fetch("/api/models")).json();
    const el = $("#md-list");
    if (!models.length) { el.innerHTML = '<p class="hint">（无本地模型，点「导入模型/权重」）</p>'; return; }
    // 按类型分组（大类），组内按名称排序（权重小类）
    const groups = {};
    for (const m of models) {
      const g = m.type === "vlm" ? "VLM 基础模型" : (m.type === "act" ? "ACT（模仿学习）" : (m.type === "smolvla" ? "SmolVLA（VLA）" : "其他"));
      (groups[g] = groups[g] || []).push(m);
    }
    let html = "";
    for (const [g, ms] of Object.entries(groups)) {
      html += `<details open class="grp"><summary>📦 ${esc(g)}（${ms.length}）</summary><div class="grp-inner">`;
      for (const m of ms) {
        const badge = m.type === "smolvla" ? "badge-vla" : (m.type === "act" ? "badge-act" : (m.type === "vlm" ? "badge-vlm" : "badge-other"));
        html += `<div class="model-card">
          <div class="model-head"><span class="model-name">${esc(m.name)}</span><span class="badge ${badge}">${esc(m.type)}</span><span class="model-src">${m.source}</span></div>
          <div class="model-meta">chunk=${m.chunk_size ?? "-"} · obs=${m.n_obs_steps ?? "-"} · 骨干=${esc(m.vision_backbone || m.model_id || "-")}</div>
          <div class="model-path">${esc(m.path)}</div>
          <div class="model-actions">
            <button class="arch-btn">🏗 架构与超参数</button>
            <button class="use-btn">🚀 用于推理</button>
            <button class="del-btn danger">🗑 删除</button>
          </div></div>`;
      }
      html += "</div></details>";
    }
    el.innerHTML = html;
    el.querySelectorAll(".arch-btn").forEach((b, i) => {
      const flat = Object.values(groups).flat();
      b.onclick = () => modelArchView(flat[i]);
    });
    el.querySelectorAll(".use-btn").forEach((b, i) => {
      const flat = Object.values(groups).flat();
      b.onclick = () => inferView(flat[i].path);
    });
    el.querySelectorAll(".del-btn").forEach((b, i) => {
      const flat = Object.values(groups).flat();
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
    <button id="arch-back">← 返回模型和权重</button>`;
  $("#arch-back").onclick = modelsView;
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

// ---------------- 推理 · 仿真视图 ----------------
async function inferView(prefillPath) {
  const models = await (await fetch("/api/models")).json();
  const mOpts = models.filter((m) => m.type !== "vlm").map((m) => `<option value="${esc(m.path)}">${esc(m.name)}（${esc(m.type)}）</option>`).join("");
  const envOpts = ['<option value="libero">LIBERO（Franka · MuJoCo）</option>',
    '<option value="mujoco">PushT-MuJoCo（自建）</option>',
    '<option value="official">PushT-官方（pymunk 2D）</option>'].join("");
  mainEl.innerHTML = `<h2>🚀 推理 · 仿真</h2>
    <div class="card"><form id="infer-form">
      <div class="form-row"><label>仿真环境</label><select id="inf-env">${envOpts}</select></div>
      <div class="form-row"><label>模型权重</label><select id="inf-model">${mOpts || '<option value="">（先导入模型）</option>'}</select></div>
      <div class="form-row"><label>或手填路径</label><input id="inf-path" value="${esc(prefillPath || "")}" placeholder="权重目录或 hub id" style="font-family:Consolas"></div>
      <div class="form-row"><label>局数</label><input id="inf-ep" type="number" value="3" min="1" class="mini"></div>
      <div class="form-row"><label>LIBERO 任务</label><input id="inf-task" value="libero_spatial" style="font-family:Consolas" class="mini"><input id="inf-taskids" value="[0]" class="mini" style="width:80px"></div>
      <div class="form-row"><label>输出目录</label><input id="inf-outdir" value="outputs/rollout_gui" placeholder="PushT 用；LIBERO 自动存 outputs/eval"></div>
      <div class="form-row"><button type="submit">🚀 开始推理</button><span class="hint">控制台显示命令与实时输出；完成后自动展示视频</span></div>
    </form></div>
    <div class="card"><h3>🎬 推理结果</h3><div class="gallery" id="inf-gallery"><p class="hint">（推理完成后显示视频）</p></div></div>`;
  $("#inf-model").onchange = () => { $("#inf-path").value = $("#inf-model").value; };
  $("#infer-form").onsubmit = async (e) => {
    e.preventDefault();
    const body = {
      env: $("#inf-env").value, policy_path: $("#inf-path").value || $("#inf-model").value,
      episodes: $("#inf-ep").value, task: $("#inf-task").value,
      task_ids: $("#inf-taskids").value, outdir: $("#inf-outdir").value,
    };
    if (!body.policy_path) { alert("请选择或填写模型权重路径"); return; }
    const j = await (await fetch("/api/infer", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    })).json();
    if (j.error) { alert("失败: " + j.error); return; }
    runCmd("推理 " + body.env + " @" + body.policy_path, j.project, j.cmd, j.cwd,
      () => showVideos(j.project, j.out_root || "outputs"));
  };
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
    for (const v of cands) {
      const fig = document.createElement("figure");
      const cap = document.createElement("figcaption");
      cap.textContent = v.path.split("/").pop();
      if (v.path.endsWith(".mp4")) {
        const vid = document.createElement("video");
        vid.controls = true; vid.src = "/proj/" + encodeURIComponent(project) + "/file/" + encodeURIComponent(v.path);
        fig.appendChild(vid);
      } else {
        const im = document.createElement("img");
        im.src = "/proj/" + encodeURIComponent(project) + "/file/" + encodeURIComponent(v.path);
        fig.appendChild(im);
      }
      fig.appendChild(cap);
      gal.appendChild(fig);
    }
  });
}

// ---------------- 分析视图（模型→权重→项目 分级） ----------------
async function analysisView() {
  mainEl.innerHTML = `<h2>📈 分析（分级：模型 → 权重 → 项目）</h2>
    <div class="card"><p class="hint">点击模型大类展开权重，再点权重展开各项目的推理/评估结果；点「原始」看 metrics.json。metrics 是每次评估的记录（成功率/覆盖率等），不是权重文件。</p>
      <div class="toolbar"><button id="an-refresh">🔄 刷新</button></div>
      <div id="an-list"></div></div>`;
  const refresh = async () => {
    const items = await (await fetch("/api/analysis")).json();
    const models = await (await fetch("/api/models")).json();
    const el = $("#an-list");
    if (!items.length) { el.innerHTML = '<p class="hint">（暂无 metrics 结果）</p>'; return; }
    const nameOf = (p) => {
      const mm = models.find((m) => p.includes(m.path.split(/[\\/]/).slice(-1)[0]));
      return mm ? mm.name : "";
    };
    // 树：type -> model_name -> project/rel
    const tree = {};
    for (const it of items) {
      const rel = it.rel;
      const mName = nameOf(rel) || it.project + "/" + rel;
      const type = (models.find((m) => m.name === mName) || {}).type || "?";
      (tree[type] = tree[type] || {});
      (tree[type][mName] = tree[type][mName] || []).push(it);
    }
    let html = "";
    for (const [type, modelsG] of Object.entries(tree)) {
      html += `<details open class="grp"><summary>🧩 ${esc(type)}</summary><div class="grp-inner">`;
      for (const [mName, its] of Object.entries(modelsG)) {
        html += `<details class="grp"><summary>📦 ${esc(mName)}（${its.length} 项）</summary><div class="grp-inner">`;
        for (const it of its) {
          const s = it.summary || {};
          const vals = Object.entries(s).filter(([k]) => k !== "raw").map(([k, v]) =>
            `<span class="metric">${esc(k)}=${esc(typeof v === "object" ? JSON.stringify(v) : v)}</span>`).join("");
          html += `<div class="model-card"><div class="model-head"><span class="model-name">📁 ${esc(it.project)} / ${esc(it.rel)}</span></div>
            <div class="model-meta">${vals || "（无结构化摘要）"}</div>
            ${s.raw ? `<pre class="code">${esc(s.raw)}</pre>` : ""}
            <div class="model-actions"><button class="raw-btn">🔎 查看原始</button></div></div>`;
        }
        html += "</div></details>";
      }
      html += "</div></details>";
    }
    el.innerHTML = html;
    el.querySelectorAll(".raw-btn").forEach((b) => {
      b.onclick = () => {
        const card = b.closest(".model-card");
        const title = card.querySelector(".model-name").textContent.trim();
        const rel = title.split("/").slice(1).join("/");
        const proj = title.split("/")[0];
        viewFile(`/proj/${encodeURIComponent(proj)}/file/${encodeURIComponent(rel)}`, rel);
      };
    });
  };
  $("#an-refresh").onclick = refresh;
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
