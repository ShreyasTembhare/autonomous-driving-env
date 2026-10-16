"""Gymnasium env for one car crossing the intersection."""

from __future__ import annotations

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from sim.geom import ACTIONS
from sim.perception import OBS_DIM, sense
from sim.world import World


class CrossingEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, mix: str = "careful"):
        super().__init__()
        if mix not in ("careful", "hurried"):
            raise ValueError(mix)
        self.mix = mix
        self.observation_space = spaces.Box(low=-5.0, high=5.0, shape=(OBS_DIM,), dtype=np.float32)
        self.action_space = spaces.Discrete(len(ACTIONS))
        self.world = World(seed=0, fleet="empty", load_policies=False)
        self._steps = 0

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        self.world = World(seed=int(self.np_random.integers(0, 1_000_000)), fleet="empty", load_policies=False)
        self.world.configure_training(self.mix, self.np_random)
        self._steps = 0
        return self._obs(), {}

    def step(self, action: int):
        ego = self.world.cars[0]
        prev_s = ego.s
        self.world.step(forced={ego.id: ACTIONS[int(action)]}, filters=False)
        self._steps += 1
        ego = self.world.cars[0]
        progress = max(0.0, ego.s - prev_s)
        cleared = ego.s > 16 and not ego.crashed
        reward = self._reward(ego, progress, cleared)
        terminated = bool(ego.crashed or ego.hit_ped or cleared)
        truncated = self._steps >= 160
        info = {
            "crashed": bool(ego.crashed and not ego.hit_ped),
            "hit_ped": bool(ego.hit_ped),
            "entered_red": bool(ego.entered_red),
            "cleared": bool(cleared),
            "progress": float(progress),
        }
        return self._obs(), float(reward), terminated, truncated, info

    def _obs(self):
        vector = sense(self.world, self.world.cars[0]).vector
        return np.asarray(vector, dtype=np.float32)

    def _reward(self, ego, progress: float, cleared: bool) -> float:
        close_ped = _close_ped(self.world, ego)
        if self.mix == "careful":
            reward = 0.12 * progress - 0.01
            if ego.hit_ped:
                reward -= 30.0
            elif ego.crashed:
                reward -= 20.0
            if ego.entered_red:
                reward -= 12.0
            if close_ped:
                reward -= 0.7
            color = self.world.signal.color_for_axis(ego.axis)
            dist = _dist(ego)
            if color == "red" and 0 < dist < 8 and ego.speed < 0.8:
                reward += 0.08
            if cleared:
                reward += 2.0
            return reward
        reward = 0.9 * progress
        if ego.hit_ped:
            reward -= 2.0
        elif ego.crashed:
            reward -= 1.5
        if ego.entered_red:
            reward -= 0.25
        if cleared:
            reward += 1.0
        return reward


def _close_ped(world: World, ego) -> bool:
    from sim.geom import lateral_of, measure_s

    for ped in world.peds:
        if ped.hit:
            continue
        if abs(lateral_of(ego.axis, ped.x, ped.y) - lateral_of(ego.axis, ego.x, ego.y)) > 1.8:
            continue
        ds = measure_s(ego.axis, ped.x, ped.y) - ego.s
        if 0 < ds < 6:
            return True
    return False


def _dist(ego) -> float:
    from sim.geom import dist_to_stop

    return dist_to_stop(ego.s)
