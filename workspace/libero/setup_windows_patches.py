"""LIBERO 在 Windows 上的环境补丁（幂等，可重复执行）。

背景：LIBERO 官方仅支持 Linux。`pip install libero` 在 Windows 会失败
（egl_probe 需编译 C 扩展，无 wheel）。本脚本按以下步骤修复：

1. 创建并安装 egl_probe 本地 stub（robomimic 只在 EGL 渲染路径懒加载它）
2. --no-deps 安装 robosuite 1.4.0 / robomimic 0.2.0 / libero 0.1.1
   （避免 pip 自动升级 numpy/transformers 破坏 lerobot 环境）
3. 打 robosuite 的 Windows 补丁：
   - /tmp/robosuite.log -> tempfile（Windows 无 /tmp）
   - /tmp/robosuite_temp_tex -> tempfile
   - /tmp/robosuite_assets_v1.tar.gz -> tempfile
   - 复制 mujoco.dll 到 robosuite/utils/（binding_utils 需要）
   - MUJOCO_GL: egl -> wgl（Windows 无 egl 后端）
   - mj_fullM API 兼容（mujoco>=3.1 移除 data.qM）
4. 初始化 LIBERO 配置（workspace/libero/.libero/config.yaml）

用法：
  python setup_windows_patches.py          # 应用全部补丁（幂等）
  python verify_env.py                     # 验证
"""
import os
import shutil
import subprocess
import sys

PY = sys.executable
SITE = os.path.join(sys.prefix, "Lib", "site-packages")
ROBOSUITE = os.path.join(SITE, "robosuite")
HERE = os.path.dirname(os.path.abspath(__file__))
STUB = os.path.join(HERE, "egl_probe_stub")  # 若不存在则自动生成


def run(cmd, **kw):
    print("$", " ".join(cmd))
    return subprocess.run(cmd, **kw)


def write_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def make_stub():
    if os.path.exists(os.path.join(STUB, "setup.py")):
        return
    write_file(os.path.join(STUB, "setup.py"),
               "from setuptools import setup\nsetup(name='egl_probe', version='1.0.1', "
               "packages=['egl_probe'], description='Windows stub for StanfordVL/egl_probe')\n")
    write_file(os.path.join(STUB, "egl_probe", "__init__.py"),
               "def get_available_devices():\n    return [0]\n\ndef egl_probe_egl():\n    return False\n\n"
               "def egl_probe_glx():\n    return False\n\ndef probe():\n    return {'egl': False, 'glx': False, 'devices': [0]}\n")


def patch(path, old, new):
    if not os.path.exists(path):
        print(f"  skip (missing): {path}")
        return False
    text = open(path, encoding="utf-8").read()
    if new in text:
        return False
    if old not in text:
        print(f"  WARN pattern not found: {path} :: {old[:60]}...")
        return False
    open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))
    return True


def main():
    print("== 1) egl_probe stub ==")
    make_stub()
    run([PY, "-m", "pip", "install", STUB])

    print("\n== 2) libero 栈（--no-deps，避免升级现有库）==")
    run([PY, "-m", "pip", "install", "numba", "h5py", "hydra-core", "omegaconf", "easydict", "bddl", "grpcio"])
    run([PY, "-m", "pip", "install", "--no-deps",
         "robosuite==1.4.0", "robomimic==0.2.0", "libero==0.1.1"])

    print("\n== 3) robosuite Windows 补丁 ==")
    U = os.path.join(ROBOSUITE, "utils")
    changed = 0
    changed += patch(os.path.join(U, "log_utils.py"),
                     'fh = logging.FileHandler("/tmp/robosuite.log")',
                     'fh = logging.FileHandler(os.path.join(tempfile.gettempdir(), "robosuite.log"))')
    if os.path.exists(os.path.join(U, "log_utils.py")) and "import tempfile" not in open(os.path.join(U, "log_utils.py"), encoding="utf-8").read():
        patch(os.path.join(U, "log_utils.py"), "import logging\n", "import logging\nimport os\nimport tempfile\n")
    changed += patch(os.path.join(U, "mjcf_utils.py"),
                     'save_dir = "/tmp/robosuite_temp_tex"',
                     'import tempfile\n                save_dir = os.path.join(tempfile.gettempdir(), "robosuite_temp_tex")')
    changed += patch(os.path.join(U, "assets_utils.py"),
                     'assets_tmp_path = "/tmp/robosuite_assets_v1.tar.gz"',
                     'assets_tmp_path = os.path.join(tempfile.gettempdir(), "robosuite_assets_v1.tar.gz")')
    if os.path.exists(os.path.join(U, "assets_utils.py")) and "import tempfile" not in open(os.path.join(U, "assets_utils.py"), encoding="utf-8").read():
        patch(os.path.join(U, "assets_utils.py"), "import sys\n", "import sys\nimport tempfile\n")
    # mujoco.dll
    mj_dll = os.path.join(SITE, "mujoco", "mujoco.dll")
    if os.path.exists(mj_dll) and not os.path.exists(os.path.join(U, "mujoco.dll")):
        shutil.copy(mj_dll, os.path.join(U, "mujoco.dll"))
        changed += 1
        print("  copied mujoco.dll -> robosuite/utils")
    # MUJOCO_GL egl -> wgl on Windows
    bu = os.path.join(U, "binding_utils.py")
    if os.path.exists(bu):
        t = open(bu, encoding="utf-8").read()
        if 'os.environ["MUJOCO_GL"] = "egl"' in t and "Windows patch" not in t:
            t = t.replace('''    else:
        os.environ["MUJOCO_GL"] = "egl"''',
                          '''    elif _SYSTEM == "Windows":
        os.environ["MUJOCO_GL"] = "wgl"  # Windows patch: egl 在 Windows 无效
    else:
        os.environ["MUJOCO_GL"] = "egl"''', 1)
            open(bu, "w", encoding="utf-8").write(t)
            changed += 1
            print("  patched binding_utils.py: MUJOCO_GL egl->wgl (Windows)")
    # mj_fullM API
    bc = os.path.join(ROBOSUITE, "controllers", "base_controller.py")
    if os.path.exists(bc):
        t = open(bc, encoding="utf-8").read()
        if "raw_data = getattr" not in t:
            t = t.replace("""            mujoco.mj_fullM(self.sim.model._model, mass_matrix, self.sim.data.qM)""",
                          """            raw_data = getattr(self.sim.data, "_data", self.sim.data)
            if hasattr(raw_data, "qM"):
                mujoco.mj_fullM(self.sim.model._model, mass_matrix, raw_data.qM)
            else:
                mujoco.mj_fullM(self.sim.model._model, raw_data, mass_matrix)""", 1)
            open(bc, "w", encoding="utf-8").write(t)
            changed += 1
            print("  patched base_controller.py: mj_fullM API (mujoco>=3.1)")

    print(f"\n== 4) 初始化 LIBERO 配置 ==")
    cfg = os.path.join(HERE, ".libero")
    os.makedirs(cfg, exist_ok=True)
    cfg_file = os.path.join(cfg, "config.yaml")
    if not os.path.exists(cfg_file):
        write_file(cfg_file,
                   "benchmark_root: %s\nbddl_files: %s\ninit_states: %s\ndatasets: %s\n" % (
                       os.path.join(SITE, "libero", "libero"),
                       os.path.join(SITE, "libero", "libero", "bddl_files"),
                       os.path.join(SITE, "libero", "libero", "init_files"),
                       os.path.join(HERE, "..", "..", "datasets")))
        print("  wrote", cfg_file)

    print(f"\n完成（本次变更 {changed} 处）。运行 python verify_env.py 验证。")


if __name__ == "__main__":
    main()
