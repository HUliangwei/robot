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
import re
import shlex
import subprocess
import sys
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

# directories / extensions excluded from the file browser (heavy weights, caches, vcs)
FILE_EXCLUDE_DIRS = {"__pycache__", ".git", ".vscode", ".idea", ".runs", ".cache",
                     "checkpoints", "training_state", "eval_step", "wandb", "runs"}
FILE_EXCLUDE_EXTS = {".safetensors", ".pyc", ".log", ".pt", ".pth", ".bin", ".onnx"}
TEXT_EXTS = {".md", ".txt", ".py", ".ipynb", ".xml", ".json", ".yml", ".yaml", ".csv", ".html", ".css", ".js", ".sh", ".toml", ".cfg", ".ini"}


def list_files(base, prefix="", max_depth=None):
    """Return [{path, size}] for all browsable files under base (sorted).

    max_depth: limit recursion depth (1 = only files directly in base).
    """
    found = []
    if not os.path.isdir(base):
        return found
    for root, dirs, files in os.walk(base):
        if max_depth is not None:
            depth = root[len(base.rstrip(os.sep)) + 1:].count(os.sep) + 1
            if depth >= max_depth:
                dirs[:] = []
        dirs[:] = [d for d in dirs if d not in FILE_EXCLUDE_DIRS]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in FILE_EXCLUDE_EXTS:
                continue
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, base).replace(os.sep, "/")
            if prefix:
                rel = prefix + "/" + rel
            try:
                size = os.path.getsize(fp)
            except OSError:
                size = 0
            found.append({"path": rel, "size": size, "ext": ext.lstrip(".")})
    found.sort(key=lambda a: a["path"])
    return found


def safe_join(base, rel):
    """Join base + rel, rejecting path traversal outside base."""
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        return None
    fp = os.path.realpath(os.path.join(base, rel))
    base_r = os.path.realpath(base)
    if not (fp == base_r or fp.startswith(base_r + os.sep)):
        return None
    return fp


def content_type_for(fp, ext=None):
    ext = (ext or os.path.splitext(fp)[1].lower()).lstrip(".")
    return {
        "mp4": "video/mp4", "gif": "image/gif", "png": "image/png", "jpg": "image/jpeg",
        "jpeg": "image/jpeg", "svg": "image/svg+xml", "webp": "image/webp",
        "html": "text/html; charset=utf-8", "md": "text/markdown; charset=utf-8",
        "txt": "text/plain; charset=utf-8", "py": "text/x-python; charset=utf-8",
        "xml": "text/xml; charset=utf-8", "json": "application/json; charset=utf-8",
        "yml": "text/yaml; charset=utf-8", "yaml": "text/yaml; charset=utf-8",
        "csv": "text/csv; charset=utf-8", "css": "text/css; charset=utf-8",
        "js": "application/javascript; charset=utf-8", "ipynb": "application/json; charset=utf-8",
    }.get(ext, "application/octet-stream")


# ---------------------------------------------------------------- datasets / models / metrics

def hub_dirs(kind):
    """Yield (repo_id, snapshot_dir) for cached HF repos of a kind ('models' | 'datasets')."""
    base = os.path.join(os.environ.get("HF_HOME", os.path.join(ROBOT, "datasets")), "hub")
    prefix = f"{kind}--"
    if not os.path.isdir(base):
        return
    for d in sorted(os.listdir(base)):
        if not d.startswith(prefix):
            continue
        repo_id = d[len(prefix):].replace("--", "/")
        snap = os.path.join(base, d, "snapshots")
        if os.path.isdir(snap):
            snaps = sorted(os.listdir(snap))
            if snaps:
                yield repo_id, os.path.join(snap, snaps[-1])


def scan_datasets():
    out = []
    seen = set()
    for repo_id, snap in hub_dirs("datasets"):
        seen.add(repo_id)
        info = {}
        fp = os.path.join(snap, "meta", "info.json")
        if os.path.exists(fp):
            try:
                info = json.load(open(fp, encoding="utf-8"))
            except Exception:
                pass
        sz = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(snap) for f in fs)
        out.append({
            "repo_id": repo_id, "source": "hf-cache", "size_mb": round(sz / 1e6, 1),
            "episodes": info.get("total_episodes"), "frames": info.get("total_frames"),
            "fps": info.get("fps"), "features": list((info.get("features") or {}).keys()),
            "robot": info.get("robot_type"),
        })
    # local lerobot-format datasets under datasets/lerobot
    lroot = os.path.join(ROBOT, "datasets", "lerobot")
    if os.path.isdir(lroot):
        for name in sorted(os.listdir(lroot)):
            if name.startswith(".") or name == "hub":
                continue
            base = os.path.join(lroot, name)
            if not os.path.isdir(base) or name in seen or name.startswith("."):
                continue
            info = {}
            fp = os.path.join(base, "meta", "info.json")
            if os.path.exists(fp):
                try:
                    info = json.load(open(fp, encoding="utf-8"))
                except Exception:
                    pass
            sz = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(base) for f in fs)
            out.append({
                "repo_id": f"lerobot/{name}", "source": "local", "size_mb": round(sz / 1e6, 1),
                "episodes": info.get("total_episodes"), "frames": info.get("total_frames"),
                "fps": info.get("fps"), "features": list((info.get("features") or {}).keys()),
                "robot": info.get("robot_type"),
            })
    return sorted(out, key=lambda d: d["repo_id"])


def scan_models():
    out = []
    for repo_id, snap in hub_dirs("models"):
        cfg_path = os.path.join(snap, "config.json")
        if not os.path.exists(cfg_path):
            continue
        try:
            cfg = json.load(open(cfg_path, encoding="utf-8"))
        except Exception:
            continue
        ptype = cfg.get("type") or cfg.get("policy_type") or "?"
        if ptype == "?" and str(cfg.get("model_type", "")).lower().startswith("smolvlm"):
            ptype = "vlm"  # 基础视觉-语言模型（SmolVLA 的骨干）
        entry = {
            "name": repo_id, "source": "hf-cache", "type": ptype, "path": snap,
            "chunk_size": cfg.get("chunk_size"), "n_obs_steps": cfg.get("n_obs_steps"),
            "vision_backbone": cfg.get("vision_backbone"), "model_id": cfg.get("model_id"),
            "params_M": None, "input_features": list((cfg.get("input_features") or {}).keys()),
        }
        out.append(entry)
    # local trained checkpoints: workspace/*/outputs/train/*/checkpoints/*/pretrained_model
    for proj in os.listdir(WORKSPACE):
        tdir = os.path.join(WORKSPACE, proj, "outputs", "train")
        if not os.path.isdir(tdir):
            continue
        for run in sorted(os.listdir(tdir)):
            ckpts = os.path.join(tdir, run, "checkpoints")
            if not os.path.isdir(ckpts):
                continue
            for ck in sorted(os.listdir(ckpts)):
                pm = os.path.join(ckpts, ck, "pretrained_model")
                cfg_path = os.path.join(pm, "config.json")
                if not os.path.exists(cfg_path):
                    continue
                try:
                    cfg = json.load(open(cfg_path, encoding="utf-8"))
                except Exception:
                    continue
                out.append({
                    "name": f"{proj}/{run}/{ck}", "source": "local", "type": cfg.get("type", "?"),
                    "path": pm, "chunk_size": cfg.get("chunk_size"), "n_obs_steps": cfg.get("n_obs_steps"),
                    "vision_backbone": cfg.get("vision_backbone"), "model_id": cfg.get("model_id"),
                    "params_M": None, "input_features": list((cfg.get("input_features") or {}).keys()),
                })
    return sorted(out, key=lambda m: m["name"])


def find_metrics():
    """Scan projects for metrics.json / metrics.txt and extract summaries."""
    out = []
    for proj in sorted(os.listdir(WORKSPACE)):
        base = os.path.join(WORKSPACE, proj, "outputs")
        if not os.path.isdir(base):
            continue
        for root, _, files in os.walk(base):
            for f in files:
                if f not in ("metrics.json", "metrics.txt"):
                    continue
                fp = os.path.join(root, f)
                rel = os.path.relpath(fp, os.path.join(WORKSPACE, proj)).replace(os.sep, "/")
                summ = {}
                try:
                    if f.endswith(".json"):
                        data = json.load(open(fp, encoding="utf-8"))
                        for k in ("success_rate", "mean_max_coverage", "mean_sum_reward", "pc_success",
                                  "avg_sum_reward", "max_rewards", "n_episodes", "env", "model", "steps"):
                            if isinstance(data, dict) and k in data:
                                summ[k] = data[k]
                        if isinstance(data, dict) and data.get("episodes") and f.endswith(".json"):
                            eps = data["episodes"]
                            if isinstance(eps, list) and eps and isinstance(eps[0], dict):
                                for k in ("max_coverage", "success", "steps", "final_coverage"):
                                    if k in eps[0]:
                                        summ["ep0_" + k] = eps[0][k]
                    else:
                        summ["raw"] = open(fp, encoding="utf-8", errors="replace").read()[:800]
                except Exception:
                    summ = {"error": "parse failed"}
                out.append({"project": proj, "rel": rel, "summary": summ})
    return out


def build_train_cmd(b):
    """Generate a lerobot_train command from the training form. Returns (cmd, project, cwd)."""
    dataset = (b.get("dataset") or "").strip()
    policy = (b.get("policy") or "act").strip()
    steps = int(b.get("steps") or 5000)
    batch = int(b.get("batch_size") or 8)
    chunk = b.get("chunk_size")
    save_freq = b.get("save_freq")
    outdir = (b.get("output_dir") or "").strip() or "outputs/train/tmp"  # 默认临时目录，下次训练覆盖
    outdir = outdir.replace("\\", "/").strip("/")
    if outdir.startswith(".."):
        raise ValueError("输出目录必须是项目内相对路径（不允许 ..）")
    env_task = (b.get("env_task") or "").strip()
    project = "libero" if "libero" in dataset else "embodied_learning"
    if project == "libero":
        task_arg = f"--env.type=libero --env.task={env_task or 'libero_spatial'} --env.task_ids=[0] "
        root = "--dataset.root=D:/Desktop/robot/datasets "
    else:
        task_arg, root = "", ""
    extra = ""
    if chunk:
        extra += f"--policy.chunk_size={chunk} "
    if save_freq:
        extra += f"--save_freq={save_freq} "
    cmd = (f"python -m lerobot.scripts.lerobot_train {task_arg}--dataset.repo_id={dataset} {root}"
           f"--policy.type={policy} --policy.push_to_hub=false "
           f"--output_dir={outdir} --steps={steps} --batch_size={batch} "
           f"{extra}--eval_steps=0 --env_eval_freq=0 --wandb.enable=false")
    cwd = f"workspace/{project}"
    return cmd, project, cwd


def build_infer_cmd(b):
    """Generate an inference/eval command. Returns (cmd, project, cwd, out_root).

    out_root: 产出视频所在相对根目录（相对项目 cwd），供前端完成后展示。
    - pusht: 用户指定 outdir（限制为项目内相对路径）
    - libero: lerobot_eval 固定写到 <cwd>/outputs/eval/<时间戳>_<模型>/
    """
    env_kind = (b.get("env") or "libero").strip()
    policy = (b.get("policy_path") or "").strip().replace("\\", "/")  # shlex 会吃反斜杠，统一正斜杠
    episodes = int(b.get("episodes") or 3)
    outdir = (b.get("outdir") or "").strip() or "outputs/rollout_gui"
    outdir = outdir.replace("\\", "/").strip("/")
    if outdir.startswith(".."):
        raise ValueError("输出目录必须是项目内相对路径（不允许 ..）")
    if env_kind in ("official", "mujoco"):
        project = "embodied_learning"
        cwd = "workspace/embodied_learning/mujoco_basics/pusht"
        cmd = (f"python run_pusht_rollout.py --env {env_kind} --n_episodes {episodes} "
               f"--policy-path {policy} --outdir ../../{outdir}")
        out_root = outdir
    else:  # libero
        project = "libero"
        cwd = "workspace/libero"
        task = (b.get("task") or "libero_spatial").strip()
        task_id = b.get("task_ids") or "[0]"
        cmd = (f"python -m lerobot.scripts.lerobot_eval --env.type=libero --env.task={task} "
               f"--env.task_ids={task_id} --env.max_parallel_tasks=1 --eval.use_async_envs=false "
               f"--eval.batch_size=1 --policy.path={policy} --eval.n_episodes={episodes}")
        out_root = "outputs/eval"  # lerobot_eval 固定输出（含时间戳子目录）
    return cmd, project, cwd, out_root


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
    # python stdout 重定向到文件时默认块缓冲，导致 GUI 轮询读不到实时输出 -> 强制无缓冲
    env.setdefault("PYTHONUNBUFFERED", "1")
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
            if not os.path.isdir(base):
                return self._send(404, json.dumps({"error": "no such project"}))
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
        if path.startswith("/api/project_files/"):
            name = path.split("/")[3]
            base = os.path.join(WORKSPACE, name)
            if not os.path.isdir(base):
                return self._send(404, json.dumps({"error": "no such project"}))
            return self._send(200, json.dumps(list_files(base), ensure_ascii=False))
        if path == "/api/global_files":
            return self._send(200, json.dumps({
                "root": list_files(ROBOT, max_depth=1),
                "note": list_files(os.path.join(ROBOT, "note")),
                "docs": list_files(DOCS),
            }, ensure_ascii=False))
        if path == "/api/datasets":
            return self._send(200, json.dumps(scan_datasets(), ensure_ascii=False))
        if path == "/api/models":
            return self._send(200, json.dumps(scan_models(), ensure_ascii=False))
        if path == "/api/analysis":
            return self._send(200, json.dumps(find_metrics(), ensure_ascii=False))
        if path.startswith("/api/dataset_detail"):
            q = urlparse(self.path).query
            import urllib.parse

            repo = urllib.parse.parse_qs(q).get("repo_id", [""])[0]
            info, stats = {}, {}
            for repo_id, snap in hub_dirs("datasets"):
                if repo_id == repo:
                    for name, d in (("meta/info.json", info), ("meta/stats.json", stats)):
                        fp = os.path.join(snap, name)
                        if os.path.exists(fp):
                            try:
                                d.update(json.load(open(fp, encoding="utf-8")))
                            except Exception:
                                pass
            if not info and not stats:
                return self._send(404, json.dumps({"error": "dataset not found"}))
            return self._send(200, json.dumps({"repo_id": repo, "info": info, "stats": stats}, ensure_ascii=False))
        if path.startswith("/api/models_config"):
            q = urlparse(self.path).query
            import urllib.parse

            p = urllib.parse.parse_qs(q).get("path", [""])[0]
            if ".." in p.split("/"):
                return self._send(400, json.dumps({"error": "bad path"}))
            cfg_fp = os.path.join(p, "config.json")
            if not os.path.exists(cfg_fp):
                return self._send(404, json.dumps({"error": "config not found"}))
            try:
                return self._send(200, json.dumps(json.load(open(cfg_fp, encoding="utf-8")), ensure_ascii=False))
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}))
        if path.startswith("/proj/"):
            # serve project / repo files statically
            parts = path.split("/")[2:]  # [name, out|doc|file|root|note, ...]
            name = parts[0]
            kind = parts[1] if len(parts) > 1 else ""
            rel = "/".join(parts[2:])
            if kind == "out":
                fp = safe_join(os.path.join(WORKSPACE, name, "outputs"), rel)
            elif kind == "doc":
                fp = safe_join(DOCS, rel)
            elif kind == "file":
                fp = safe_join(os.path.join(WORKSPACE, name), rel)
            elif kind == "root":
                fp = safe_join(ROBOT, rel)
            elif kind == "note":
                fp = safe_join(os.path.join(ROBOT, "note"), rel)
            else:
                fp = None
            if fp and os.path.exists(fp) and os.path.isfile(fp):
                ext = os.path.splitext(fp)[1].lower()
                with open(fp, "rb") as f:
                    data = f.read()
                if ext == ".html":
                    data = data.replace(b'<img src="viz/', b'<img src="/proj/_/doc/viz/')
                return self._send(200, data, content_type_for(fp, ext))
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
        if u.path == "/api/models/import":
            ln = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(ln) or b"{}")
            repo = (body.get("repo_id") or "").strip()
            if not repo:
                return self._send(400, json.dumps({"error": "缺少 repo_id"}))
            import shlex as _shlex

            # 用 huggingface_hub 的 snapshot_download 下载（经代理 + 禁 xet 更稳）
            cmd = ("python -c \"import os; from huggingface_hub import snapshot_download; "
                   f"print('OK:', snapshot_download('{repo}'))\"")
            try:
                run_id = start_run("libero", cmd, "workspace/libero")
                return self._send(200, json.dumps({"run_id": run_id, "cmd": cmd}))
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}))
        if u.path == "/api/models/delete":
            ln = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(ln) or b"{}")
            p = (body.get("path") or "").strip()
            base_hub = os.path.join(os.environ.get("HF_HOME", os.path.join(ROBOT, "datasets")), "hub")
            target = None
            if "models--" in p:
                # HF 缓存：定位到 models--<org>--<name> 仓库根
                idx = p.find("models--")
                end = p.find(os.sep, idx)
                target = p[: end] if end > 0 else p
            elif "checkpoints" in p and p.startswith(os.path.join(WORKSPACE, "embodied_learning", "outputs")):
                # 本地 checkpoint：.../checkpoints/<step>/pretrained_model -> .../checkpoints/<step>
                target = os.path.dirname(os.path.dirname(p))
            if target is None or not target.startswith(base_hub) and not target.startswith(os.path.join(WORKSPACE, "embodied_learning", "outputs")):
                return self._send(400, json.dumps({"error": "只允许删除模型缓存或本地 checkpoint"}))
            import shutil

            if os.path.isdir(target):
                shutil.rmtree(target)
                return self._send(200, json.dumps({"ok": True, "deleted": target}))
            return self._send(400, json.dumps({"error": "路径不存在"}))
        if u.path == "/api/create_project":
            ln = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(ln) or b"{}")
            name = (body.get("name") or "").strip()
            desc = (body.get("desc") or "新小项目").strip()
            if not re.fullmatch(r"[A-Za-z0-9_\-]+", name or ""):
                return self._send(400, json.dumps({"error": "项目名只能含字母数字下划线"}))
            base = os.path.join(WORKSPACE, name)
            if os.path.exists(base):
                return self._send(400, json.dumps({"error": "项目已存在"}))
            os.makedirs(base, exist_ok=True)
            open(os.path.join(base, "README.md"), "w", encoding="utf-8").write(
                f"# {name} — 新小项目\n\n> {desc}\n\n## 状态\n\n待补充：数据集 / 模型 / 训练 / 推理 / 仿真 / 分析\n")
            open(os.path.join(base, "PROGRESS.md"), "w", encoding="utf-8").write(
                f"# PROGRESS — {name}\n\n## 项目一句话\n\n{desc}\n\n## 当前状态\n\n| 阶段 | 状态 | 说明 |\n|---|---|---|\n| 骨架 | ✅ | README / PROGRESS / commands |\n\n## 更新日志\n\n- 2026-08-17：创建项目骨架\n")
            open(os.path.join(base, "commands.json"), "w", encoding="utf-8").write(
                json.dumps({"project": name, "description": desc,
                            "python": os.path.join(sys.prefix, "python.exe"),
                            "hf_home": os.path.join(ROBOT, "datasets"),
                            "commands": [{"name": "环境自检", "cmd": "python -c \"print('hello')\"",
                                          "cwd": f"workspace/{name}", "desc": "骨架占位命令"}]},
                           ensure_ascii=False, indent=2))
            return self._send(200, json.dumps({"ok": True, "name": name}))
        if u.path == "/api/datasets/import":
            ln = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(ln) or b"{}")
            repo = (body.get("repo_id") or "").strip()
            if not repo:
                return self._send(400, json.dumps({"error": "缺少 repo_id"}))
            cmd = f"python -m lerobot.scripts.lerobot_info --dataset.repo_id={repo}"
            try:
                run_id = start_run("libero", cmd, "workspace/libero")
                return self._send(200, json.dumps({"run_id": run_id, "cmd": cmd}))
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}))
        if u.path == "/api/train":
            ln = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(ln) or b"{}")
            try:
                cmd, proj, cwd = build_train_cmd(body)
                run_id = start_run(proj, cmd, cwd)
                return self._send(200, json.dumps({"run_id": run_id, "project": proj, "cmd": cmd, "cwd": cwd}))
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}))
        if u.path == "/api/infer":
            ln = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(ln) or b"{}")
            try:
                cmd, proj, cwd, out_root = build_infer_cmd(body)
                run_id = start_run(proj, cmd, cwd)
                return self._send(200, json.dumps({"run_id": run_id, "project": proj, "cmd": cmd, "cwd": cwd, "out_root": out_root}))
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}))
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
