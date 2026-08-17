"""MuJoCo re-implementation of the PushT environment, observation/action compatible
with gym_pusht (gym_pusht/PushT-v0, obs_type="pixels_agent_pos") so that a LeRobot
policy trained on the lerobot/pusht dataset can be evaluated in MuJoCo directly.

Semantics copied from gym_pusht (https://github.com/huggingface/gym-pusht):
- canvas 512x512, agent = circle r=15 (PD driven toward action target in [0,512]^2)
- T block = head 120x30 + stem 30x90, COM at (0,45) below the junction
- goal pose (256, 256, pi/4), success = coverage > 0.95, episode length 300
- obs: pixels (96,96,3) uint8 (top-down, pygame y-down) + agent_pos (2,)
"""
from __future__ import annotations

import os
from typing import Any

import cv2
import gymnasium as gym
import mujoco
import numpy as np
import shapely.geometry as sg
from gymnasium import spaces

XML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pusht_mujoco.xml")

SUCCESS_THRESHOLD = 0.95
EPISODE_LENGTH = 300
K_P, K_V, DT = 100.0, 20.0, 0.01
N_SUBSTEPS = int(1 / (DT * 10))  # 10, like gym_pusht (control_hz=10)

T_HEAD = np.array([(-60, 30), (60, 30), (60, 0), (-60, 0)], dtype=float)
T_STEM = np.array([(-15, 30), (-15, 120), (15, 120), (15, 30)], dtype=float)
GOAL_POSE = np.array([256.0, 256.0, np.pi / 4])


def _rot(angle: float) -> np.ndarray:
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s], [s, c]])


def tee_polygon(pose: np.ndarray) -> sg.MultiPolygon:
    """T-block geometry in world coords given pose [x, y, angle].

    The T is two rectangles (head 120x30 + stem 30x90), matching gym_pusht's
    two pymunk Poly shapes (which pymunk_to_shapely merges into a MultiPolygon).
    A single 8-vertex Polygon would be self-intersecting/invalid.
    """
    R = _rot(pose[2])
    polys = []
    for verts in (T_HEAD, T_STEM):
        pts = [tuple(R @ v + pose[:2]) for v in verts]
        polys.append(sg.Polygon(pts))
    return sg.MultiPolygon(polys)


class MujocoPushtEnv(gym.Env):
    metadata = {"render_modes": ["rgb_array"], "render_fps": 10}

    def __init__(self, observation_width: int = 96, observation_height: int = 96, render_width: int = 512):
        super().__init__()
        self.observation_width = observation_width
        self.observation_height = observation_height
        self.render_width = render_width

        self.observation_space = spaces.Dict(
            {
                "pixels": spaces.Box(
                    low=0, high=255, shape=(self.observation_height, self.observation_width, 3), dtype=np.uint8
                ),
                "agent_pos": spaces.Box(low=np.zeros(2, dtype=np.float32), high=np.full(2, 512.0, dtype=np.float32), dtype=np.float32),
            }
        )
        self.action_space = spaces.Box(low=np.zeros(2, dtype=np.float32), high=np.full(2, 512.0, dtype=np.float32), dtype=np.float32)

        self.model = mujoco.MjModel.from_xml_path(XML_PATH)
        self.data = mujoco.MjData(self.model)
        self._renderer: mujoco.Renderer | None = None

    # ------------------------------------------------------------------ obs
    def _get_render(self, width: int, height: int) -> np.ndarray:
        """Render top-down RGB image (pygame y-down)."""
        # always render at full resolution, then resize (matches gym_pusht's render-then-resize)
        if self._renderer is None or self._renderer.width != self.render_width:
            if self._renderer is not None:
                self._renderer.close()
            self._renderer = mujoco.Renderer(self.model, self.render_width, self.render_width)
            mujoco.mjv_defaultOption(self._renderer._scene_option)
            # disable specular highlights & shadows: flat pygame-like colors
            self._renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = 0
            self._renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 0
        mujoco.mj_forward(self.model, self.data)
        self._renderer.update_scene(
            data=self.data, camera="top", scene_option=self._renderer._scene_option
        )
        img = self._renderer.render()
        img = img[::-1]  # flip vertically: world +y appears downward (pygame convention)
        if (height, width) != img.shape[:2]:
            img = cv2.resize(img, (width, height))
        return img

    def _get_obs(self) -> dict[str, np.ndarray]:
        img = self._get_render(self.observation_width, self.observation_height)
        return {
            "pixels": img.astype(np.uint8),
            "agent_pos": np.array(self.data.qpos[0:2], dtype=np.float32),
        }

    # ------------------------------------------------------------- geometry
    def _get_coverage(self) -> float:
        block_pose = self.data.qpos[3:6]
        block_geom = tee_polygon(block_pose)
        goal_geom = tee_polygon(GOAL_POSE)
        inter = block_geom.intersection(goal_geom).area
        return inter / goal_geom.area

    # ---------------------------------------------------------------- step
    def step(self, action: np.ndarray):
        action = np.asarray(action, dtype=float)
        agent_pos = self.data.qpos[0:2].copy()
        agent_vel = self.data.qvel[0:2].copy()
        for _ in range(N_SUBSTEPS):
            acc = K_P * (action - agent_pos) + K_V * (0.0 - agent_vel)
            agent_vel = agent_vel + acc * DT
            agent_pos = agent_pos + agent_vel * DT
            self.data.qpos[0:3] = [agent_pos[0], agent_pos[1], 0.0]
            self.data.qvel[0:3] = [agent_vel[0], agent_vel[1], 0.0]
            mujoco.mj_step(self.model, self.data)

        coverage = self._get_coverage()
        reward = float(np.clip(coverage / SUCCESS_THRESHOLD, 0.0, 1.0))
        terminated = bool(coverage > SUCCESS_THRESHOLD)
        observation = self._get_obs()
        info = {
            "is_success": terminated,
            "coverage": float(coverage),
            "block_pose": self.data.qpos[3:6].copy(),
            "goal_pose": GOAL_POSE.copy(),
        }
        return observation, reward, terminated, False, info

    # --------------------------------------------------------------- reset
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        if options is not None and options.get("reset_to_state") is not None:
            state = np.array(options["reset_to_state"], dtype=float)
        else:
            state = np.array(
                [
                    self.np_random.integers(50, 450),
                    self.np_random.integers(50, 450),
                    self.np_random.integers(100, 400),
                    self.np_random.integers(100, 400),
                    self.np_random.uniform(-np.pi, np.pi),
                ]
            )
        self.data.qpos[0:6] = [state[0], state[1], 0.0, state[2], state[3], state[4]]
        self.data.qvel[0:6] = 0.0
        mujoco.mj_forward(self.model, self.data)
        # settle overlapping spawn states (pymunk resolves these on its first step)
        for _ in range(10):
            mujoco.mj_step(self.model, self.data)
        observation = self._get_obs()
        info = {"is_success": False, "coverage": 0.0, "block_pose": self.data.qpos[3:6].copy(), "goal_pose": GOAL_POSE.copy()}
        return observation, info

    # -------------------------------------------------------------- render
    def render(self):
        return self._get_render(self.render_width, self.render_width)

    def close(self):
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None


if __name__ == "__main__":
    # quick self-check
    env = MujocoPushtEnv()
    obs, info = env.reset(seed=0)
    print("obs keys:", obs.keys(), "pixels:", obs["pixels"].shape, obs["pixels"].dtype, "agent_pos:", obs["agent_pos"])
    total = 0.0
    for _ in range(50):
        a = np.random.uniform(50, 450, 2).astype(np.float32)
        obs, r, term, trunc, info = env.step(a)
        total += r
    print("50 random steps, sum reward:", round(total, 3), "final coverage:", round(info["coverage"], 3))
    env.close()
