"""LIBERO 环境自检：验证 lerobot 内置 LIBERO 环境可用。

检查项：
1. libero 配置初始化（LIBERO_CONFIG_PATH -> workspace/libero/.libero/config.yaml）
2. lerobot.envs.libero 模块可导入
3. 可用 benchmark 套件列表
4. 创建 LIBERO-Spatial task 0（SyncVectorEnv, 1 env），reset + 3 随机步
"""
import os
import sys
import yaml

LIBERO_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".libero")
LIBERO_LIB = os.path.join(sys.prefix, "Lib", "site-packages", "libero", "libero")

# 必须在 import libero 之前设置（config 路径在模块导入时读取）
os.environ["LIBERO_CONFIG_PATH"] = LIBERO_CONFIG
os.makedirs(LIBERO_CONFIG, exist_ok=True)
cfg_file = os.path.join(LIBERO_CONFIG, "config.yaml")
if not os.path.exists(cfg_file):
    with open(cfg_file, "w", encoding="utf-8") as f:
        yaml.dump(
            {
                "benchmark_root": LIBERO_LIB,
                "bddl_files": os.path.join(LIBERO_LIB, "bddl_files"),
                "init_states": os.path.join(LIBERO_LIB, "init_files"),
                "datasets": os.path.join(os.path.dirname(LIBERO_CONFIG), "..", "..", "datasets"),
            },
            f,
        )
    print(f"已初始化 LIBERO 配置: {cfg_file}")


def main() -> int:
    print("== 1) 导入 lerobot.envs.libero ==")
    try:
        from lerobot.envs.libero import _get_suite  # noqa: PLC0415

        print("OK: lerobot.envs.libero 可导入")
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: 导入失败: {e}")
        return 1

    print("\n== 2) 可用 benchmark 套件 ==")
    try:
        from libero.libero import benchmark  # noqa: PLC0415

        names = sorted(benchmark.get_benchmark_dict().keys())
        print("OK:", names)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: {e}")
        return 1

    print("\n== 3) 创建 LIBERO-Spatial task 0（SyncVectorEnv x1）并随机 3 步 ==")
    try:
        import gymnasium as gym  # noqa: PLC0415
        from lerobot.envs.libero import create_libero_envs  # noqa: PLC0415

        envs = create_libero_envs(
            "libero_spatial", n_envs=1, env_cls=gym.vector.SyncVectorEnv,
            gym_kwargs={"task_ids": [0]},
        )
        env = envs["libero_spatial"][0]
        obs, info = env.reset(seed=0)
        print("obs keys:", sorted(obs.keys()))
        for i in range(3):
            action = env.action_space.sample()
            obs, rew, term, trunc, info = env.step(action)
        print("OK: 3 随机步无报错, obs:", {k: (v.shape if hasattr(v, "shape") else type(v).__name__) for k, v in obs.items()})
        env.close()
    except Exception as e:  # noqa: BLE001
        import traceback  # noqa: PLC0415

        traceback.print_exc()
        print(f"FAIL: 环境创建/step 失败: {e}")
        return 1

    print("\n[PASS] 环境验证通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
