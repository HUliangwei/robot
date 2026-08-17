"use strict";

const $ = (s) => document.querySelector(s);
const listEl = $("#project-list");
const mainEl = $("#main");
let current = null;
let pollTimer = null;
let currentRunId = null;

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
const CODE_EXT = ["py", "xml", "json", "yml", "yaml", "txt", "csv", "sh", "toml", "cfg", "ini", "js", "css"];

// ---------------- console / command runner ----------------
function showConsole(title) {
  $("#console-title").textContent = "运行: " + title;
  const cmdEl = $("#console-head-cmd");
  if (cmdEl) cmdEl.textContent = "";
  $("#console-body").textContent = "";
  $("#console-overlay").classList.remove("hidden");
}
async function pollRun() {
  if (!currentRunId) return;
  const r = await fetch("/api/run/" + currentRunId);
  if (!r.ok) { // 运行记录已失效（如服务器重启）
    clearInterval(pollTimer);
    pollTimer = null;
    $("#console-body").textContent += "\n\n[运行记录已失效（服务器可能已重启）]";
    $("#console-kill").disabled = true;
    return;
  }
  const j = await r.json();
  $("#console-body").textContent = j.output || "";
  $("#console-body").scrollTop = $("#console-body").scrollHeight;
  if (!j.running) {
    clearInterval(pollTimer);
    pollTimer = null;
    $("#console-body").textContent += `\n\n[进程结束 exit=${j.exit_code}]`;
    $("#console-kill").disabled = true;
    onRunDone();
  }
}
async function runCmd(title, project, cmd, cwd, onDone) {
  showConsole(title);
  $("#console-body").textContent = "$ " + cmd + "\n\n" + (cwd ? `# cwd: ${cwd}\n\n` : "");
  const cmdEl = $("#console-head-cmd");
  if (cmdEl) cmdEl.textContent = "$ " + cmd;
  onRunDone = onDone || (() => {});
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  const r = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project, cmd, cwd: cwd || "" }),
  });
  const j = await r.json();
  if (!j.run_id) { $("#console-body").textContent += "\n启动失败: " + JSON.stringify(j); return; }
  currentRunId = j.run_id;
  $("#console-kill").disabled = false;
  pollTimer = setInterval(pollRun, 800);
}
let onRunDone = () => {};
$("#console-close").onclick = () => {
  clearInterval(pollTimer);
  pollTimer = null;
  $("#console-overlay").classList.add("hidden");
};
$("#console-kill").onclick = async () => {
  if (currentRunId) await fetch("/api/run/" + currentRunId + "/kill", { method: "POST" });
};

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
    div.innerHTML = `<div class="head"><span class="name">${esc(c.name)}</span><span class="status"></span></div>
      <div class="desc">${esc(c.desc || "")}</div><div class="cmdline">${esc(c.cmd)}</div>
      <div class="runbar"><button class="run-btn">▶ 运行</button></div>`;
    const btn = div.querySelector(".run-btn");
    btn.onclick = () => runCmd(c.name, name, c.cmd, c.cwd || "");
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
    <div class="card"><p class="hint">本地已缓存的数据集（HF 缓存 + lerobot 本地格式）。「导入」= 从 HF 下载并生成结构信息。</p>
      <div class="toolbar"><button id="ds-refresh">🔄 刷新</button><button id="ds-import">⬇ 导入数据集</button></div>
      <table id="ds-table"><thead><tr><th>repo_id</th><th>来源</th><th>大小</th><th>episodes</th><th>帧数</th><th>fps</th><th>特征</th><th>机器人</th></tr></thead><tbody></tbody></table>
    </div>`;
  const refresh = async () => {
    const r = await fetch("/api/datasets");
    const ds = await r.json();
    const tb = $("#ds-table tbody");
    tb.innerHTML = ds.length ? "" : '<tr><td colspan="8">（无本地数据集，点「导入」下载）</td></tr>';
    for (const d of ds) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${esc(d.repo_id)}</td><td>${d.source}</td><td>${d.size_mb} MB</td>
        <td>${d.episodes ?? "-"}</td><td>${d.frames ?? "-"}</td><td>${d.fps ?? "-"}</td>
        <td class="small">${esc((d.features || []).join(", ")) || "-"}</td><td>${esc(d.robot || "-")}</td>`;
      tb.appendChild(tr);
    }
  };
  $("#ds-refresh").onclick = refresh;
  $("#ds-import").onclick = async () => {
    const repo = prompt("HF 数据集 repo_id（如 lerobot/libero、lerobot/pusht）：", "lerobot/libero");
    if (!repo) return;
    const res = await fetch("/api/datasets/import", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ repo_id: repo }),
    });
    const j = await res.json();
    if (j.error) { alert("失败: " + j.error); return; }
    runCmd("导入数据集 " + repo, "libero", j.cmd, "workspace/libero", refresh);
  };
  refresh();
}

// ---------------- 模型与架构视图 ----------------
function archBox(label, sub, color) {
  return `<div class="arch-box" style="border-color:${color}"><div class="arch-label">${esc(label)}</div>${sub ? `<div class="arch-sub">${esc(sub)}</div>` : ""}</div>`;
}
function archArrow() { return `<div class="arch-arrow">→</div>`; }

function architectureHTML(m) {
  const t = m.type;
  if (t === "act") {
    return `<div class="arch">
      <div class="arch-row">${archBox("图像 image+image2", "2×256×256×3", "#1f77b4")}${archArrow()}${archBox("ResNet18 视觉编码", "flatten → 512", "#2ca02c")}${archArrow()}${archBox("Transformer Encoder", "4 层 · 8 头 · 512", "#ff7f0e")}</div>
      <div class="arch-row">${archBox("状态 state", "8 (关节+夹爪)", "#9467bd")}${archArrow()}${archBox("拼接 + VAE 潜变量", "latent_dim=32", "#d62728")}</div>
      <div class="arch-row">${archBox("Transformer Decoder", "1 层 · 生成动作序列", "#ff7f0e")}${archArrow()}${archBox("动作块 Action Chunk", "100 步 × 7 维关节增量", "#1f77b4")}</div>
      <div class="arch-note">ACT = 视觉直接编码成动作的专用模仿学习网络；每 100 步重规划一次。</div>
    </div>`;
  }
  if (t === "smolvla") {
    return `<div class="arch">
      <div class="arch-row">${archBox("图像 image+image2", "2×256×256×3", "#1f77b4")}${archArrow()}${archBox("SmolVLM2-500M 视觉-语言骨干", "理解「看到什么」", "#2ca02c")}</div>
      <div class="arch-row">${archBox("语言指令 language_instruction", "如: pick up the black bowl…", "#9467bd")}${archArrow()}${archBox("同上骨干", "理解「要做什么」", "#2ca02c")}</div>
      <div class="arch-row">${archBox("状态 state", "8 维", "#d62728")}${archArrow()}${archBox("动作头 Action Head", "生成动作 token → 动作", "#ff7f0e")}${archArrow()}${archBox("动作块", "100 步 × 7 维", "#1f77b4")}</div>
      <div class="arch-note">SmolVLA = 先「视觉+语言理解」再「生成动作」——语言条件让一个模型可按指令执行不同任务。</div>
    </div>`;
  }
  return `<p class="hint">该模型类型（${esc(t)}）暂无预设架构图，查看下方配置详情。</p>`;
}

async function modelsView() {
  mainEl.innerHTML = `<h2>🧠 模型与架构</h2>
    <div class="card"><p class="hint">本地可用的策略权重（HF 缓存 + 自训 checkpoint）。点「架构」看结构图与配置，「推理」填入推理表单。</p>
      <div class="toolbar"><button id="md-refresh">🔄 刷新</button></div>
      <div id="md-list"></div></div>`;
  const refresh = async () => {
    const r = await fetch("/api/models");
    const models = await r.json();
    const el = $("#md-list");
    el.innerHTML = models.length ? "" : '<p class="hint">（无本地模型）</p>';
    for (const m of models) {
      const badge = m.type === "smolvla" ? "badge-vla" : (m.type === "act" ? "badge-act" : "badge-other");
      const div = document.createElement("div");
      div.className = "model-card";
      div.innerHTML = `<div class="model-head"><span class="model-name">${esc(m.name)}</span><span class="badge ${badge}">${esc(m.type)}</span><span class="model-src">${m.source}</span></div>
        <div class="model-meta">chunk=${m.chunk_size ?? "-"} · obs=${m.n_obs_steps ?? "-"} · 骨干=${esc(m.vision_backbone || m.model_id || "-")}</div>
        <div class="model-path">${esc(m.path)}</div>
        <div class="model-actions"><button class="arch-btn">🏗 架构</button><button class="use-btn">🚀 用于推理</button></div>`;
      div.querySelector(".arch-btn").onclick = () => modelArchView(m);
      div.querySelector(".use-btn").onclick = () => { inferView(m.path); };
      el.appendChild(div);
    }
  };
  $("#md-refresh").onclick = refresh;
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
  mainEl.innerHTML = `<h2>🏗 ${esc(m.name)}</h2>
    <div class="card">${architectureHTML(m)}</div>
    <div class="card"><h3>配置（config.json）</h3>
      <table><thead><tr><th>键</th><th>值</th></tr></thead><tbody>${kv || '<tr><td colspan="2">（无）</td></tr>'}</tbody></table>
    </div>
    <div class="card"><h3>输入 / 输出特征</h3>
      <pre class="code">${esc(JSON.stringify({ input_features: cfg.input_features, output_features: cfg.output_features }, null, 2))}</pre>
    </div>
    <button id="arch-back">← 返回模型列表</button>`;
  $("#arch-back").onclick = modelsView;
}

// ---------------- 训练视图 ----------------
async function trainView() {
  const ds = await (await fetch("/api/datasets")).json();
  const dsOpts = ds.map((d) => `<option value="${esc(d.repo_id)}">${esc(d.repo_id)}（${d.episodes ?? "?"} ep）</option>`).join("");
  mainEl.innerHTML = `<h2>🎓 训练（生成并运行 lerobot-train）</h2>
    <div class="card"><form id="train-form">
      <div class="form-row"><label>数据集</label><select id="tr-dataset">${dsOpts || '<option value="lerobot/pusht">lerobot/pusht</option>'}</select></div>
      <div class="form-row"><label>模型类型</label><select id="tr-policy"><option value="act">ACT</option><option value="smolvla">SmolVLA</option></select></div>
      <div class="form-row"><label>LIBERO 套件（仅 libero 数据集）</label><input id="tr-task" value="libero_spatial" placeholder="libero_spatial / libero_object / …"></div>
      <div class="form-row"><label>训练步数</label><input id="tr-steps" type="number" value="5000" min="1"></div>
      <div class="form-row"><label>batch_size</label><input id="tr-batch" type="number" value="8" min="1"></div>
      <div class="form-row"><label>输出目录</label><input id="tr-outdir" value="outputs/train/act_gui" style="font-family:Consolas"></div>
      <div class="form-row"><button type="submit">⚡ 生成命令并训练</button><span class="hint" style="margin-left:.8rem">控制台会显示完整命令与实时输出</span></div>
    </form></div>
    <div class="card"><h3>训练要点</h3>
      <ul class="hint"><li>PushT：官方配方 batch8 + 60-80k 步才接近高成功率（8GB 显卡约 1-2 步/秒）</li>
      <li>LIBERO-Spatial：ACT 预算 10k≈1-2h / 25k≈3-6h；SmolVLA 训练更长（官方教程 smolvla.mdx）</li>
      <li>数据不足时先跑 50 步冒烟验证管线（本机已验证）</li></ul>
    </div>`;
  $("#train-form").onsubmit = async (e) => {
    e.preventDefault();
    const body = {
      dataset: $("#tr-dataset").value, policy: $("#tr-policy").value,
      env_task: $("#tr-task").value, steps: $("#tr-steps").value,
      batch_size: $("#tr-batch").value, output_dir: $("#tr-outdir").value,
    };
    const res = await fetch("/api/train", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const j = await res.json();
    if (j.error) { alert("失败: " + j.error); return; }
    runCmd("训练 " + body.policy + " @" + body.dataset, j.project, j.cmd, j.cwd);
  };
}

// ---------------- 推理 · 仿真视图 ----------------
async function inferView(prefillPath) {
  const models = await (await fetch("/api/models")).json();
  const mOpts = models.map((m) => `<option value="${esc(m.path)}">${esc(m.name)}（${esc(m.type)}）</option>`).join("");
  const envOpts = ['<option value="libero">LIBERO（Franka · MuJoCo）</option>',
    '<option value="mujoco">PushT-MuJoCo（自建）</option>',
    '<option value="official">PushT-官方（pymunk 2D）</option>'].join("");
  mainEl.innerHTML = `<h2>🚀 推理 · 仿真（命令行推理 + 可视化）</h2>
    <div class="card"><form id="infer-form">
      <div class="form-row"><label>仿真环境</label><select id="inf-env">${envOpts}</select></div>
      <div class="form-row"><label>模型权重</label><select id="inf-model">${mOpts || '<option value="">（先导入模型）</option>'}</select></div>
      <div class="form-row"><label>或手填权重路径</label><input id="inf-path" value="${esc(prefillPath || "")}" placeholder="datasets/hub/models--…/snapshots/… 或 outputs/train/…/pretrained_model" style="font-family:Consolas"></div>
      <div class="form-row"><label>局数</label><input id="inf-ep" type="number" value="3" min="1"></div>
      <div class="form-row"><label>LIBERO 任务（仅 libero）</label><input id="inf-task" value="libero_spatial" style="font-family:Consolas"><input id="inf-taskids" value="[0]" style="width:90px;font-family:Consolas"></div>
      <div class="form-row"><label>输出目录（PushT 用）</label><input id="inf-outdir" value="outputs/rollout_gui" style="font-family:Consolas"></div>
      <div class="form-row"><button type="submit">🚀 开始推理</button><span class="hint" style="margin-left:.8rem">控制台显示命令与实时输出；完成后自动列出产出的视频</span></div>
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
    const res = await fetch("/api/infer", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const j = await res.json();
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
    // lerobot_eval 会写 outputs/eval/<时间戳>_<模型>/，只展示最新的那次运行
    if (base === "outputs/eval" && cands.length) {
      const groups = {};
      for (const c of cands) {
        const seg = c.path.split("/")[2]; // outputs/eval/<seg>/...
        (groups[seg] = groups[seg] || []).push(c);
      }
      const newest = Object.keys(groups).sort().pop();
      cands = groups[newest] || [];
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

// ---------------- 分析视图 ----------------
async function analysisView() {
  mainEl.innerHTML = `<h2>📈 分析（指标总览）</h2>
    <div class="card"><div class="toolbar"><button id="an-refresh">🔄 刷新</button></div>
      <div id="an-list"></div></div>`;
  const refresh = async () => {
    const r = await fetch("/api/analysis");
    const items = await r.json();
    const el = $("#an-list");
    el.innerHTML = items.length ? "" : '<p class="hint">（暂无 metrics 结果）</p>';
    for (const it of items) {
      const s = it.summary || {};
      const div = document.createElement("div");
      div.className = "model-card";
      const vals = Object.entries(s).filter(([k]) => k !== "raw").map(([k, v]) =>
        `<span class="metric">${esc(k)}=${esc(typeof v === "object" ? JSON.stringify(v) : v)}</span>`).join("");
      div.innerHTML = `<div class="model-head"><span class="model-name">${esc(it.project)} / ${esc(it.rel)}</span></div>
        <div class="model-meta">${vals || "（无结构化摘要）"}</div>
        ${s.raw ? `<pre class="code">${esc(s.raw)}</pre>` : ""}
        <div class="model-actions"><button class="use-btn">🔎 查看原始文件</button></div>`;
      div.querySelector(".use-btn").onclick = () => {
        viewFile(`/proj/${encodeURIComponent(it.project)}/file/${encodeURIComponent(it.rel)}`, it.rel);
      };
      el.appendChild(div);
    }
  };
  $("#an-refresh").onclick = refresh;
  refresh();
}

// ---------------- 全局导航 ----------------
function mdNavClick(ev, url, label) {
  ev.preventDefault();
  viewFile(url, label);
}

async function loadGlobalNav() {
  const r = await fetch("/api/global_files");
  const g = await r.json();
  const wrap = $("#global-files");
  if (!wrap) return;
  let html = "";
  const mdOnly = (arr) => arr.filter((f) => f.ext === "md").map((f) => f.path);
  const baseUrl = (kind, path) => `/proj/_/${kind}/${encodeURIComponent(path)}`;
  for (const p of mdOnly(g.root)) {
    html += `<li><a class="file-link" data-url="${baseUrl("root", p)}" data-name="${esc(p)}">📄 ${esc(p)}</a></li>`;
  }
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
    <div class="card"><iframe src="/api/report" style="width:100%;height:78vh;border:0;"></iframe></div>`;
};
$("#nav-new-project").onclick = async (e) => {
  e.preventDefault();
  const name = prompt("新小项目名（字母数字下划线）：", "my_project");
  if (!name) return;
  const desc = prompt("一句话介绍：", "新小项目");
  const res = await fetch("/api/create_project", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, desc }),
  });
  const j = await res.json();
  if (j.error) { alert("失败: " + j.error); return; }
  await loadProjects();
  openProject(j.name);
};
$("#nav-shutdown").onclick = async (e) => {
  e.preventDefault();
  if (!confirm("确定关闭本地 GUI 服务？关闭后需重新运行 python gui/server.py 启动。")) return;
  try { await fetch("/api/shutdown"); } catch (err) { /* server already gone */ }
  document.body.innerHTML = '<div style="padding:3rem;font-family:Microsoft YaHei"><h2>服务已关闭</h2><p>可关闭此标签页，或重新运行 <code>python gui/server.py</code> 再次启动。</p></div>';
};

loadProjects();
loadGlobalNav();
