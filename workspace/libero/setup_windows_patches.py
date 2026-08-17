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


# gym_manipulator.py 中插入的 pusht 专用 action 步骤（存储归一化 teleop_action）
_PUSHT_TELEOP_STEP = '''@dataclass
class PushtTeleopActionProcessorStep(ComplementaryDataProcessorStep):
    """PushT: 把 *归一化* 的策略 action 存为 ``teleop_action``。

    gym-pusht 期望 [0, 512] 的绝对目标位置，而 tanh 高斯策略输出 (-1, 1)。
    actor 的 postprocessor 用 action 统计量（min=256, max=512 → env action = t*256+256）
    反归一化后再 env.step；replay buffer 必须存归一化值，这样 critic（batch 里的 action）
    与 actor（tanh 采样）处于同一尺度。
    """

    action_min: float = 256.0
    action_max: float = 512.0

    def complementary_data(self, complementary_data: dict) -> dict:
        action = self._current_transition.get(TransitionKey.ACTION)
        if isinstance(action, torch.Tensor):
            norm = (action - self.action_min) / (self.action_max - self.action_min)
            complementary_data[TELEOP_ACTION_KEY] = norm.detach().clone()
        return complementary_data

    def transform_features(self, features):
        return features
'''


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

    print("\n== 5) lerobot 0.6.1 RL: PushT 支持补丁 ==")
    LEROBOT = os.path.join(SITE, "lerobot")
    # 5.1) TrainPipelineConfig.validate(): RL 模式下 dataset 为 None（HILSerl 无需离线数据集）
    changed += patch(os.path.join(LEROBOT, "configs", "train.py"),
                     "        if isinstance(self.dataset.repo_id, list):",
                     "        if self.dataset is not None and isinstance(self.dataset.repo_id, list):")
    changed += patch(os.path.join(LEROBOT, "configs", "train.py"),
                     "        if self.eval_steps > 0 and self.dataset.eval_split == 0.0:",
                     "        if self.eval_steps > 0 and (self.dataset is None or self.dataset.eval_split == 0.0):")
    # 5.2) gym_manipulator: 让 HILSerl actor/learner 支持 PushtEnv（gym-pusht）
    GM = os.path.join(LEROBOT, "rl", "gym_manipulator.py")
    changed += patch(GM,
                     "from lerobot.teleoperators.utils import TeleopEvents\n",
                     "from lerobot.teleoperators.utils import TeleopEvents\n"
                     "from lerobot.processor.hil_processor import TELEOP_ACTION_KEY  # Windows patch: RL pusht\n")
    changed += patch(GM,
                     "    AddTeleopEventsAsInfoStep,\n    DataProcessorPipeline,",
                     "    AddTeleopEventsAsInfoStep,\n    ComplementaryDataProcessorStep,\n    DataProcessorPipeline,")
    changed += patch(GM,
                     "def make_robot_env(cfg: HILSerlRobotEnvConfig) -> tuple[gym.Env, Any]:",
                     _PUSHT_TELEOP_STEP + "\n\n\ndef make_robot_env(cfg: HILSerlRobotEnvConfig) -> tuple[gym.Env, Any]:")
    changed += patch(GM,
                     "    # Check if this is a GymHIL simulation environment\n    if cfg.name == \"gym_hil\":",
                     "    # PushT simulation (gym-pusht). Windows patch: HILSerl 只支持 gym_hil / 真机，\n"
                     "    # 这里为 PushtEnv 配置（type == \"pusht\"）提供一等支持。\n"
                     "    if getattr(cfg, \"type\", None) == \"pusht\":\n"
                     "        import gym_pusht  # noqa: F401  # 注册 \"gym_pusht/PushT-v0\"\n"
                     "        env = gym.make(cfg.gym_id, disable_env_checker=True, **cfg.gym_kwargs)\n"
                     "        return env, None\n"
                     "\n"
                     "    # Check if this is a GymHIL simulation environment\n    if cfg.name == \"gym_hil\":")
    changed += patch(GM,
                     "    terminate_on_success = (\n"
                     "        cfg.processor.reset.terminate_on_success if cfg.processor.reset is not None else True\n"
                     "    )",
                     "    if getattr(cfg, \"type\", None) == \"pusht\":\n"
                     "        env_pipeline_steps = [VanillaObservationProcessorStep()]\n"
                     "        action_pipeline_steps = [\n"
                     "            PushtTeleopActionProcessorStep(),\n"
                     "            Torch2NumpyActionProcessorStep(),\n"
                     "        ]\n"
                     "        return DataProcessorPipeline(\n"
                     "            steps=env_pipeline_steps, to_transition=identity_transition, to_output=identity_transition\n"
                     "        ), DataProcessorPipeline(\n"
                     "            steps=action_pipeline_steps, to_transition=identity_transition, to_output=identity_transition\n"
                     "        )\n"
                     "\n"
                     "    terminate_on_success = (\n"
                     "        cfg.processor.reset.terminate_on_success if cfg.processor.reset is not None else True\n"
                     "    )")
    # 5.3) actor: HILSerl 工作流里 learner 先启动已创建 output_dir，actor 的 validate()
    #     会因 "output dir already exists" 报错 —— actor 只用该目录写日志，放行。
    changed += patch(os.path.join(LEROBOT, "rl", "actor.py"),
                     "    try:\n"
                     "        cfg.validate()\n"
                     "    except FileExistsError:\n"
                     "        # Windows patch: learner 先启动已创建 output_dir，actor 只写日志，无需全新目录\n"
                     "        pass\n"
                     "    display_pid = False",
                     "    try:\n"
                     "        cfg.validate()\n"
                     "    except FileExistsError:\n"
                     "        # Windows patch: learner 先启动已创建 output_dir，actor 只写日志，无需全新目录\n"
                     "        pass\n"
                     "    # validate 提前中断时（上面吞掉 FileExistsError），补齐 algorithm.policy_config，\n"
                     "    # 否则 make_algorithm() 会报 'policy_config is None'\n"
                     "    if getattr(cfg.algorithm, \"policy_config\", None) is None:\n"
                     "        cfg.algorithm.policy_config = cfg.policy\n"
                     "    display_pid = False")
    # 5.4) transport: actor 传来的 transition 含 numpy 标量（gym-pusht reward 是 np.float64），
    #     torch 2.6+ torch.load 默认 weights_only=True 会拒绝 —— 本地可信管道回退到完整加载
    TU = os.path.join(LEROBOT, "transport", "utils.py")
    changed += patch(TU,
                     "def bytes_to_transitions(buffer: bytes) -> list[Transition]:\n"
                     "    bytes_buffer = io.BytesIO(buffer)\n"
                     "    bytes_buffer.seek(0)\n"
                     "    transitions = torch.load(bytes_buffer, weights_only=True)\n"
                     "    return transitions",
                     "def bytes_to_transitions(buffer: bytes) -> list[Transition]:\n"
                     "    bytes_buffer = io.BytesIO(buffer)\n"
                     "    bytes_buffer.seek(0)\n"
                     "    try:\n"
                     "        return torch.load(bytes_buffer, weights_only=True)\n"
                     "    except (pickle.UnpicklingError, RuntimeError):\n"
                     "        # Windows patch: transition 里含 numpy 标量（如 gym-pusht reward），\n"
                     "        # torch 2.6+ weights_only=True 拒绝；本地可信管道回退完整加载\n"
                     "        bytes_buffer.seek(0)\n"
                     "        return torch.load(bytes_buffer, weights_only=False)")
    changed += patch(TU,
                     "def bytes_to_state_dict(buffer: bytes) -> dict[str, torch.Tensor]:\n"
                     "    bytes_buffer = io.BytesIO(buffer)\n"
                     "    bytes_buffer.seek(0)\n"
                     "    return torch.load(bytes_buffer, weights_only=True)",
                     "def bytes_to_state_dict(buffer: bytes) -> dict[str, torch.Tensor]:\n"
                     "    bytes_buffer = io.BytesIO(buffer)\n"
                     "    bytes_buffer.seek(0)\n"
                     "    try:\n"
                     "        return torch.load(bytes_buffer, weights_only=True)\n"
                     "    except (pickle.UnpicklingError, RuntimeError):\n"
                     "        bytes_buffer.seek(0)\n"
                     "        return torch.load(bytes_buffer, weights_only=False)")
    # 5.5) ReplayBuffer: 默认关闭 DRQ 图像增强 —— DRQ 需要 torch.compile+triton，
    #     Windows 无 triton，producer 线程静默崩溃导致训练死锁
    BUF = os.path.join(LEROBOT, "rl", "buffer.py")
    changed += patch(BUF,
                     "        image_augmentation_function: Callable | None = None,\n"
                     "        use_drq: bool = True,\n"
                     "        storage_device: str = \"cpu\",",
                     "        image_augmentation_function: Callable | None = None,\n"
                     "        use_drq: bool = False,  # Windows patch: 默认关闭 DRQ 图像增强（torch.compile 需 triton）\n"
                     "        storage_device: str = \"cpu\",")
    changed += patch(BUF,
                     "        image_augmentation_function: Callable | None = None,\n"
                     "        use_drq: bool = True,\n"
                     "        storage_device: str = \"cpu\",\n"
                     "        optimize_memory: bool = False,\n"
                     "    ) -> \"ReplayBuffer\":",
                     "        image_augmentation_function: Callable | None = None,\n"
                     "        use_drq: bool = False,  # Windows patch: 默认关闭 DRQ（torch.compile 需 triton）\n"
                     "        storage_device: str = \"cpu\",\n"
                     "        optimize_memory: bool = False,\n"
                     "    ) -> \"ReplayBuffer\":")

    print(f"\n完成（本次变更 {changed} 处）。运行 python verify_env.py 验证。")


if __name__ == "__main__":
    main()
