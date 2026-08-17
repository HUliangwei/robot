"use strict";

const $ = (s) => document.querySelector(s);
const listEl = $("#project-list");
const mainEl = $("#main");
let projects = [];
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
      .replace(/\[(.+?)\]\((.+?)\)/g, (m, a, h) => {
        if (h.startsWith("http")) return `<a href="${h}" target="_blank">${a}</a>`;
        return `<a href="${h}">${a}</a>`;
      });
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
  if (n < 1024) return n + " B";
  if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
  return (n / 1048576).toFixed(1) + " MB";
}

const MEDIA_EXT = ["mp4", "gif", "png", "jpg", "jpeg", "svg", "webp"];
const CODE_EXT = ["py", "xml", "json", "yml", "yaml", "txt", "csv", "sh", "toml", "cfg", "ini", "js", "css"];

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
  } else if (ext === "md") {
    body = md(text);
  } else if (CODE_EXT.includes(ext)) {
    body = `<pre class="code">${esc(text)}</pre>`;
  } else {
    body = `<pre class="code">${esc(text)}</pre>`;
  }
  mainEl.innerHTML = `<h2>${esc(label)}</h2><div class="card">${body}</div>`;
}

// ---------------- project list ----------------
async function loadProjects() {
  const r = await fetch("/api/projects");
  projects = await r.json();
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
    <div class="card" id="progress-view">${md(data.progress || "（无 PROGRESS.md）")}</div>
    <div class="card"><h3>⚡ 常用命令</h3><div id="commands"></div></div>
    <div class="card"><h3>🎬 产出（视频 / 图表）</h3><div class="gallery" id="gallery"></div></div>
    <div class="card"><h3>📂 全部文件</h3><div id="files"></div></div>`;
  const cmds = $("#commands");
  if (!data.commands.length) cmds.innerHTML = '<p class="hint">（无 commands.json）</p>';
  for (const c of data.commands) {
    const div = document.createElement("div");
    div.className = "command";
    div.innerHTML = `<div class="head"><span class="name">${esc(c.name)}</span><span class="status"></span></div>
      <div class="desc">${esc(c.desc || "")}</div><div class="cmdline">${esc(c.cmd)}</div>
      <div class="runbar"><button class="run-btn">▶ 运行</button></div>`;
    const btn = div.querySelector(".run-btn");
    btn.onclick = () => runCommand(name, c);
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
  // file browser
  const filesEl = $("#files");
  filesEl.innerHTML = '<p class="hint">加载中…</p>';
  const fr = await fetch("/api/project_files/" + encodeURIComponent(name));
  const files = await fr.json();
  if (!files.length) filesEl.innerHTML = '<p class="hint">（无文件）</p>';
  else {
    filesEl.innerHTML = fileGroupUI(files);
    filesEl.querySelectorAll(".file-link").forEach((el) => {
      el.onclick = (e) => {
        e.preventDefault();
        viewFile(el.dataset.url, el.dataset.name);
      };
    });
  }
}

// ---------------- command runner ----------------
async function runCommand(proj, cmdObj) {
  showConsole(cmdObj.name);
  const r = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project: proj, cmd: cmdObj.cmd, cwd: cmdObj.cwd || "" }),
  });
  const j = await r.json();
  if (!j.run_id) { $("#console-body").textContent = "启动失败: " + JSON.stringify(j); return; }
  currentRunId = j.run_id;
  $("#console-kill").disabled = false;
  pollTimer = setInterval(pollRun, 800);
}

function showConsole(title) {
  $("#console-title").textContent = "运行: " + title;
  $("#console-body").textContent = "";
  $("#console-overlay").classList.remove("hidden");
}

async function pollRun() {
  if (!currentRunId) return;
  const r = await fetch("/api/run/" + currentRunId);
  const j = await r.json();
  $("#console-body").textContent = j.output;
  $("#console-body").scrollTop = $("#console-body").scrollHeight;
  if (!j.running) {
    clearInterval(pollTimer);
    pollTimer = null;
    $("#console-body").textContent += `\n\n[进程结束 exit=${j.exit_code}]`;
    $("#console-kill").disabled = true;
  }
}

$("#console-close").onclick = () => {
  clearInterval(pollTimer);
  $("#console-overlay").classList.add("hidden");
};
$("#console-kill").onclick = async () => {
  if (currentRunId) await fetch("/api/run/" + currentRunId + "/kill", { method: "POST" });
};

// ---------------- global nav ----------------
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
  const mdOnly = (arr, prefix) => arr.filter((f) => f.ext === "md").map((f) => f.path);
  const rootMds = mdOnly(g.root, "root");
  const noteMds = mdOnly(g.note, "note");
  const docMds = mdOnly(g.docs, "docs");
  const baseUrl = (kind, path) => `/proj/_/${kind}/${encodeURIComponent(path)}`;
  for (const p of rootMds) {
    html += `<li><a class="file-link" data-url="${baseUrl("root", p)}" data-name="${esc(p)}">📄 ${esc(p)}</a></li>`;
  }
  if (noteMds.length) {
    html += `<li class="nav-sep">📓 学习笔记</li>`;
    for (const p of noteMds) {
      html += `<li><a class="file-link" data-url="${baseUrl("note", p)}" data-name="${esc(p)}">${esc(p)}</a></li>`;
    }
  }
  if (docMds.length) {
    html += `<li class="nav-sep">📚 文档</li>`;
    for (const p of docMds) {
      html += `<li><a class="file-link" data-url="${baseUrl("doc", p)}" data-name="${esc(p)}">${esc(p)}</a></li>`;
    }
  }
  wrap.innerHTML = html;
  wrap.querySelectorAll(".file-link").forEach((el) => {
    el.onclick = (e) => {
      e.preventDefault();
      viewFile(el.dataset.url, el.dataset.name);
    };
  });
}

$("#nav-report").onclick = (e) => {
  e.preventDefault();
  mainEl.innerHTML = `<h2>📊 推理报告</h2>
    <div class="card"><iframe src="/api/report" style="width:100%;height:78vh;border:0;"></iframe></div>`;
};
$("#nav-shutdown").onclick = async (e) => {
  e.preventDefault();
  if (!confirm("确定关闭本地 GUI 服务？关闭后需重新运行 python gui/server.py 启动。")) return;
  try { await fetch("/api/shutdown"); } catch (err) { /* server already gone */ }
  document.body.innerHTML = '<div style="padding:3rem;font-family:Microsoft YaHei"><h2>服务已关闭</h2><p>可关闭此标签页，或重新运行 <code>python gui/server.py</code> 再次启动。</p></div>';
};

loadProjects();
loadGlobalNav();
