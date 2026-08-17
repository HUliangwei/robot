"""robot GUI server — dependency-free local dashboard.

Run:  python gui/server.py [--port 8765]
Then open http://127.0.0.1:8765

Features:
  - project list (scans workspace/*/ for commands.json + PROGRESS.md)
  - view PROGRESS.md (rendered client-side)
  - run project commands with live output (subprocess -> log file -> poll)
  - browse project artifacts (videos/gifs/charts)
  - embed docs/inference_report.html
"""
import json
import os
import shlex
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

ROBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # robot/
WORKSPACE = os.path.join(ROBOT, "workspace")
DOCS = os.path.join(ROBOT, "docs")
RUNS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".runs")
os.makedirs(RUNS_DIR, exist_ok=True)

runs = {}          # run_id -> {"proc", "log", "started"}
run_lock = threading.Lock()
ARTIFACT_EXTS = (".mp4", ".gif", ".png", ".jpg")
SERVER = None      # set in main(); used by /api/shutdown


def find_projects():
    projects = []
    if not os.path.isdir(WORKSPACE):
        return projects
    for name in sorted(os.listdir(WORKSPACE)):
        base = os.path.join(WORKSPACE, name)
        if not os.path.isdir(base):
            continue
        cfg = os.path.join(base, "commands.json")
        prog = os.path.join(base, "PROGRESS.md")
        if not (os.path.exists(cfg) or os.path.exists(prog)):
            continue
        info = {"name": name, "has_commands": os.path.exists(cfg), "has_progress": os.path.exists(prog)}
        if os.path.exists(cfg):
            try:
                info["meta"] = json.load(open(cfg, encoding="utf-8"))
            except Exception:
                info["meta"] = {}
        if os.path.exists(prog):
            lines = open(prog, encoding="utf-8").read().splitlines()
            # find the first H1 and the "当前状态" H2, take 2-3 lines after it
            snippet = []
            for i, ln in enumerate(lines):
                if ln.startswith("## 当前状态"):
                    snippet = [l.strip() for l in lines[i + 1 : i + 5] if l.strip()]
                    break
            info["snippet"] = " ".join(snippet)[:220]
        projects.append(info)
    return projects


def artifacts_for(name):
    base = os.path.join(WORKSPACE, name, "outputs")
    found = []
    if not os.path.isdir(base):
        return found
    for root, _, files in os.walk(base):
        for f in files:
            if f.lower().endswith(ARTIFACT_EXTS) and "eval_step" not in root:
                rel = os.path.relpath(os.path.join(root, f), base)
                if "checkpoints" in rel:
                    continue
                found.append({"name": rel, "url": f"/proj/{name}/out/{rel.replace(os.sep, '/')}"})
    found.sort(key=lambda a: a["name"])
    return found


def start_run(proj_name, cmd, cwd):
    meta_path = os.path.join(WORKSPACE, proj_name, "commands.json")
    meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
    py = meta.get("python", "python")
    hf_home = meta.get("hf_home", os.path.join(ROBOT, "datasets"))
    # prepend python for "python ..." style commands
    parts = shlex.split(cmd)
    if parts and parts[0] in ("python", "python.exe"):
        parts[0] = py
    full = parts if parts else [cmd]
    resolved_cwd = os.path.join(ROBOT, cwd) if cwd else os.path.join(WORKSPACE, proj_name)
    os.makedirs(resolved_cwd, exist_ok=True)
    run_id = f"{int(time.time() * 1000)}"
    log = os.path.join(RUNS_DIR, f"{run_id}.log")
    env = dict(os.environ)
    env["HF_HOME"] = hf_home
    env.setdefault("HF_HUB_CACHE", os.path.join(hf_home, "hub"))
    with open(log, "w", encoding="utf-8") as lf:
        proc = subprocess.Popen(full, cwd=resolved_cwd, stdout=lf, stderr=subprocess.STDOUT, env=env)
    with run_lock:
        runs[run_id] = {"proc": proc, "log": log, "cmd": cmd, "started": time.time()}
    return run_id


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static(self, rel, ctype):
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)
        if os.path.exists(p) and os.path.isfile(p):
            self._send(200, open(p, "rb").read(), ctype)
        else:
            self._send(404, "not found", "text/plain")

    def do_GET(self):
        u = urlparse(self.path)
        path = unquote(u.path)
        if path in ("/", "/index.html"):
            return self._static("index.html", "text/html; charset=utf-8")
        if path == "/app.js":
            return self._static("app.js", "application/javascript; charset=utf-8")
        if path == "/style.css":
            return self._static("style.css", "text/css; charset=utf-8")
        if path == "/api/projects":
            return self._send(200, json.dumps(find_projects(), ensure_ascii=False))
        if path.startswith("/api/project/"):
            name = path.split("/")[3]
            base = os.path.join(WORKSPACE, name)
            progress = ""
            pp = os.path.join(base, "PROGRESS.md")
            if os.path.exists(pp):
                progress = open(pp, encoding="utf-8").read()
            commands = []
            cp = os.path.join(base, "commands.json")
            if os.path.exists(cp):
                commands = json.load(open(cp, encoding="utf-8")).get("commands", [])
            return self._send(
                200, json.dumps({"name": name, "progress": progress, "commands": commands,
                                 "artifacts": artifacts_for(name)}, ensure_ascii=False)
            )
        if path.startswith("/proj/"):
            # serve project outputs / docs statically
            parts = path.split("/")[2:]  # [name, out|doc, ...]
            name = parts[0]
            kind = parts[1] if len(parts) > 1 else ""
            if kind == "out":
                rel = "/".join(parts[2:])
                fp = os.path.join(WORKSPACE, name, "outputs", rel)
            elif kind == "doc":
                rel = "/".join(parts[2:])
                fp = os.path.join(DOCS, rel)
            else:
                fp = None
            if fp and os.path.exists(fp) and os.path.isfile(fp):
                ext = os.path.splitext(fp)[1].lower()
                ctype = {"mp4": "video/mp4", "gif": "image/gif", "png": "image/png",
                         "jpg": "image/jpeg", "html": "text/html; charset=utf-8"}.get(ext, "application/octet-stream")
                with open(fp, "rb") as f:
                    data = f.read()
                if ext == "html":
                    data = data.replace(b'<img src="viz/', b'<img src="/proj/_/doc/viz/')
                return self._send(200, data, ctype)
            return self._send(404, "not found", "text/plain")
        if path.startswith("/api/run/"):
            run_id = path.split("/")[3]
            with run_lock:
                r = runs.get(run_id)
            if not r:
                return self._send(404, json.dumps({"error": "no such run"}))
            out = ""
            if os.path.exists(r["log"]):
                out = open(r["log"], encoding="utf-8", errors="replace").read()[-60000:]
            alive = r["proc"].poll() is None
            code = None if alive else r["proc"].returncode
            return self._send(200, json.dumps({"running": alive, "exit_code": code, "output": out}, ensure_ascii=False))
        if path.startswith("/api/report"):
            fp = os.path.join(DOCS, "inference_report.html")
            if os.path.exists(fp):
                data = open(fp, "rb").read().replace(b'<img src="viz/', b'<img src="/proj/_/doc/viz/')
                return self._send(200, data, "text/html; charset=utf-8")
            return self._send(404, "no report", "text/plain")
        if u.path == "/api/shutdown":
            def _stop():
                time.sleep(0.3)
                try:
                    SERVER.shutdown()
                except Exception:
                    pass
            threading.Thread(target=_stop, daemon=True).start()
            return self._send(200, json.dumps({"ok": True, "msg": "服务即将关闭"}))
        return self._send(404, "not found", "text/plain")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/api/run":
            ln = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(ln) or b"{}")
            try:
                run_id = start_run(body["project"], body["cmd"], body.get("cwd", ""))
                return self._send(200, json.dumps({"run_id": run_id}))
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}))
        if u.path.startswith("/api/run/"):
            parts = u.path.split("/")
            run_id = parts[3]
            action = parts[4] if len(parts) > 4 else ""
            with run_lock:
                r = runs.get(run_id)
            if not r:
                return self._send(404, json.dumps({"error": "no such run"}))
            if action == "kill" and r["proc"].poll() is None:
                try:
                    r["proc"].kill()
                except Exception:
                    pass
            return self._send(200, json.dumps({"ok": True}))
        return self._send(404, "not found", "text/plain")


def main():
    import argparse
    import socket

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    # auto-avoid busy ports (Videoto3D uses 8765; try start..start+19)
    global SERVER
    port = args.port
    srv = None
    for p in range(port, port + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            port = p
            break
        except OSError:
            continue
    if srv is None:
        print(f"error: no free port in [{port}, {port + 19}]", flush=True)
        return
    SERVER = srv

    url = f"http://127.0.0.1:{port}"
    print(f"robot GUI: {url}  (Videoto3D 默认占用 8765，本服务自动避让)", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
