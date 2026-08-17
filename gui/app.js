"use strict";

const $ = (s) => document.querySelector(s);
const listEl = $("#project-list");
const mainEl = $("#main");
let projects = [];
let current = null;
let pollTimer = null;
let currentRunId = null;

// ---------------- tiny markdown renderer ----------------
function md(text) {
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  let lines = text.split(/\r?\n/);
  let html = "";
  let inTable = false;
  const flushTable = () => { if (inTable) { html += "</table>"; inTable = false; } };
  for (let raw of lines) {
    const line = raw.trimEnd();
    const m = line.match(/^```/);
    if (m) { html += "<pre>"; continue; }
    if (line.startsWith("```")) { html += "</pre>"; continue; }
    if (html.endsWith("<pre>")) { html += esc(line) + "\n"; continue; }
    let t = esc(line)
      .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2">$1</a>');
    const h1 = line.match(/^# (.*)$/), h2 = line.match(/^## (.*)$/), h3 = line.match(/^### (.*)$/);
    if (h1) { flushTable(); html += `<h1>${esc(h1[1])}</h1>`; continue; }
    if (h2) { flushTable(); html += `<h2>${esc(h2[1])}</h2>`; continue; }
    if (h3) { flushTable(); html += `<h3>${esc(h3[1])}</h3>`; continue; }
    if (line.startsWith("|") && line.includes("|")) {
      if (!inTable) { html += "<table>"; inTable = true; }
      const cells = line.split("|").slice(1, -1).map((c) => c.trim());
      const isSep = cells.every((c) => /^:?-+:?$/.test(c));
      if (isSep) continue;
      const tag = html.endsWith("</table>") ? "tr" : "tr";
      html += "<tr>" + cells.map((c) => `<${tag === "tr" ? "td" : "td"}>${c}</td>`).join("") + "</tr>";
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
async function openProject(name) {
  current = name;
  document.querySelectorAll("#project-list li").forEach((li) => li.classList.remove("active"));
  const r = await fetch("/api/project/" + encodeURIComponent(name));
  const data = await r.json();
  mainEl.innerHTML = `<h2>📁 ${name}</h2>
    <div class="card" id="progress-view">${md(data.progress || "（无 PROGRESS.md）")}</div>
    <div class="card"><h3>⚡ 常用命令</h3><div id="commands"></div></div>
    <div class="card"><h3>🎬 产出（视频 / 图表）</h3><div class="gallery" id="gallery"></div></div>`;
  const cmds = $("#commands");
  if (!data.commands.length) cmds.innerHTML = '<p class="hint">（无 commands.json）</p>';
  for (const c of data.commands) {
    const div = document.createElement("div");
    div.className = "command";
    div.innerHTML = `<div class="head"><span class="name">${c.name}</span><span class="status"></span></div>
      <div class="desc">${c.desc || ""}</div><div class="cmdline">${c.cmd}</div>
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
$("#nav-report").onclick = (e) => {
  e.preventDefault();
  mainEl.innerHTML = `<h2>📊 推理报告</h2>
    <div class="card"><iframe src="/api/report" style="width:100%;height:78vh;border:0;"></iframe></div>`;
};
$("#nav-ai").onclick = (e) => {
  e.preventDefault();
  mainEl.innerHTML = `<h2>🤖 AI_CONTEXT.md</h2>
    <div class="card" id="progress-view"></div>`;
  fetch("/proj/_/doc/AI_CONTEXT.md").then((r) => r.text()).then((t) => {
    $("#progress-view").innerHTML = md(t);
  });
};
$("#nav-shutdown").onclick = async (e) => {
  e.preventDefault();
  if (!confirm("确定关闭本地 GUI 服务？关闭后需重新运行 python gui/server.py 启动。")) return;
  try { await fetch("/api/shutdown"); } catch (err) { /* server already gone */ }
  document.body.innerHTML = '<div style="padding:3rem;font-family:Microsoft YaHei"><h2>服务已关闭</h2><p>可关闭此标签页，或重新运行 <code>python gui/server.py</code> 再次启动。</p></div>';
};

loadProjects();
