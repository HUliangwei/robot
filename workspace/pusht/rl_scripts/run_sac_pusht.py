"""SAC on PushT 冒烟脚本：learner + actor 双进程 + 看门狗。

lerobot 0.6.1 的 RL 是 HILSerl 架构：learner 起 gRPC 服务，actor 连接并交互。
本脚本按顺序启动 learner -> 等端口就绪 -> 启动 actor -> 等 actor 跑完
（policy.online_steps 次交互）-> 给 learner 一点时间冲刷 replay 并落盘 checkpoint
-> 终止 learner -> 输出 checkpoint 列表。

注意（Windows 教训）：子进程 stdout 不要用管道转发 —— learner/actor 的 logging
StreamHandler 会因管道不被排空而阻塞整条链路。这里让子进程直接写文件
（rl_scripts/logs/ 下的 console 副本；learner/actor 自身还在 output_dir/logs/
写详细日志），监督器只轮询文件/端口并向自己的 stdout 打印关键事件。

用法:
  python run_sac_pusht.py --config_path rl_configs/sac_pusht_smoke.json --clean
"""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.dirname(SCRIPT_DIR)  # workspace/libero（output_dir 的基准目录）
PY = sys.executable
LOG_ROOT = os.path.join(SCRIPT_DIR, "logs")


def wait_port(port: int, timeout: float = 240) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except OSError:
            time.sleep(1.0)
    return False


def kill_tree(proc: subprocess.Popen, name: str) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=15)
        print(f"[supervisor] 已终止 {name} (pid={proc.pid})", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[supervisor] 终止 {name} 失败: {e}", flush=True)


def tail(path: str, n: int = 40) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except OSError:
        return ""


def last_meaningful(path: str) -> str:
    """抓日志里最后一条有意义的进度行（奖励/优化步/交互步），跳过噪音。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return ""
    for line in reversed(lines):
        s = line.strip()
        if not s:
            continue
        if any(k in s for k in ("Episode", "Optimization step", "episode", "Global step", "reward")):
            return s
        # 兜底：不在黑名单里的最后一条非空行
    for line in reversed(lines):
        if line.strip():
            return line.strip()
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config_path", default=os.path.join(HERE, "rl_configs", "sac_pusht_smoke.json"))
    ap.add_argument("--learner_port", type=int, default=50051)
    ap.add_argument("--settle_s", type=float, default=20.0, help="actor 结束后再等 learner 冲刷多少秒")
    ap.add_argument("--max_wait_s", type=float, default=1200.0, help="actor 最长运行时间")
    ap.add_argument("--progress_interval_s", type=float, default=10.0, help="打印进度的时间间隔（秒）")
    ap.add_argument("--clean", action="store_true", help="清空已有 output_dir 再跑")
    args = ap.parse_args()

    cfg = json.load(open(args.config_path, encoding="utf-8"))
    resume = bool(cfg.get("resume"))
    out_dir = os.path.normpath(os.path.join(HERE, cfg.get("output_dir", "outputs/train/sac_pusht_smoke")))
    if not out_dir.startswith(os.path.normpath(HERE)):
        print(f"[supervisor] 错误: output_dir 必须在 {HERE} 内")
        return 1
    if args.clean and os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
        print(f"[supervisor] 已清空 {out_dir}", flush=True)
    if not resume and os.path.exists(os.path.join(out_dir, "checkpoints", "last")):
        print(f"[supervisor] 错误: {out_dir} 已有 checkpoint，请用 --clean 覆盖重训，或改为续训（resume=true）")
        return 1
    if resume and not os.path.exists(os.path.join(out_dir, "checkpoints", "last")):
        print(f"[supervisor] 错误: 续训（resume=true）需要在 {out_dir} 存在 checkpoints/last，先完成一次训练")
        return 1
    # 注意：不要预先创建 out_dir —— learner validate() 要求目录不存在（resume=False）

    stamp = time.strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join(LOG_ROOT, f"{stamp}_{os.path.basename(out_dir)}")
    os.makedirs(log_dir, exist_ok=True)
    log_learner = os.path.join(log_dir, "learner_console.log")
    log_actor = os.path.join(log_dir, "actor_console.log")

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # 实时可视化：把 stream_dir 透传给 actor 子进程（actor 内部按 env.rl 写帧）
    stream_dir = cfg.get("stream_dir") or ""
    if stream_dir:
        env["RL_STREAM_DIR"] = stream_dir.replace("\\", "/").strip("/")

    learner_log = os.path.join(out_dir, "logs", f"learner_{cfg.get('job_name', 'rl')}.log")
    actor_log = os.path.join(out_dir, "logs", f"actor_{cfg.get('job_name', 'rl')}.log")

    print(f"[supervisor] 启动 learner: python -m lerobot.rl.learner --config_path {args.config_path}", flush=True)
    with open(log_learner, "w", encoding="utf-8") as lf:
        learner = subprocess.Popen(
            [PY, "-u", "-m", "lerobot.rl.learner", "--config_path", args.config_path],
            cwd=HERE, env=env, stdout=lf, stderr=subprocess.STDOUT,
        )
    if not wait_port(args.learner_port, timeout=240):
        print("[supervisor] learner 未在 240s 内就绪（gRPC 端口未监听）", flush=True)
        print("---- learner 详细日志尾部（output_dir/logs）----")
        print(tail(learner_log))
        kill_tree(learner, "learner")
        return 1
    print(f"[supervisor] learner gRPC 端口 {args.learner_port} 就绪 (pid={learner.pid})", flush=True)

    print(f"[supervisor] 启动 actor: python -m lerobot.rl.actor --config_path {args.config_path}", flush=True)
    with open(log_actor, "w", encoding="utf-8") as af:
        actor = subprocess.Popen(
            [PY, "-u", "-m", "lerobot.rl.actor", "--config_path", args.config_path],
            cwd=HERE, env=env, stdout=af, stderr=subprocess.STDOUT,
        )

    t0 = time.time()
    actor_ok = False
    last_progress = 0.0
    try:
        while time.time() - t0 < args.max_wait_s:
            if learner.poll() is not None:
                print("[supervisor] learner 提前退出！", flush=True)
                print("---- learner 详细日志尾部 ----")
                print(tail(learner_log))
                print("---- actor 日志尾部 ----")
                print(tail(actor_log))
                kill_tree(actor, "actor")
                return 1
            if actor.poll() is not None:
                actor_ok = actor.returncode == 0
                break
            # 每 progress_interval_s 汇报一次进度（抓最后一条含奖励/优化步的行）
            if time.time() - last_progress > args.progress_interval_s:
                last_progress = time.time()
                lines = last_meaningful(learner_log) or last_meaningful(log_learner)
                alines = last_meaningful(actor_log) or last_meaningful(log_actor)
                el = int(time.time() - t0)
                print(f"[supervisor] +{el}s | learner: {lines[:140]}", flush=True)
                print(f"[supervisor] +{el}s | actor  : {alines[:140]}", flush=True)
            time.sleep(2.0)
    except KeyboardInterrupt:
        print("[supervisor] 收到 Ctrl+C，清理…", flush=True)
        kill_tree(actor, "actor")
        kill_tree(learner, "learner")
        return 130

    if not actor_ok:
        print("[supervisor] actor 未在预期时间内完成或异常退出", flush=True)
        print("---- actor 日志尾部 ----")
        print(tail(actor_log))
        print("---- learner 详细日志尾部 ----")
        print(tail(learner_log))
        kill_tree(actor, "actor")
        kill_tree(learner, "learner")
        return 1

    print(f"[supervisor] actor 已跑完 (returncode={actor.returncode})，"
          f"再等 {args.settle_s:.0f}s 让 learner 冲刷 replay 并落盘 checkpoint…", flush=True)
    time.sleep(args.settle_s)
    kill_tree(learner, "learner")

    ck_dir = os.path.join(out_dir, "checkpoints")
    checkpoints = sorted(d for d in os.listdir(ck_dir) if d.isdigit()) if os.path.isdir(ck_dir) else []
    print(f"[supervisor] 完成。output_dir={out_dir}", flush=True)
    print(f"[supervisor] checkpoints: {checkpoints}", flush=True)
    print("---- learner 详细日志尾部 ----")
    print(tail(learner_log))
    print("---- actor 日志尾部 ----")
    print(tail(actor_log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
