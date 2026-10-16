"""Kinematic bicycle, the highway-env driving contract."""

from __future__ import annotations

import math

from sim.geom import DT, MAX_SPEED, MAX_STEER, WHEELBASE, wrap


def step_bicycle(
    x: float,
    y: float,
    heading: float,
    speed: float,
    accel: float,
    steer: float,
    dt: float = DT,
) -> tuple[float, float, float, float]:
    steer = max(-MAX_STEER, min(MAX_STEER, steer))
    speed = max(0.0, min(MAX_SPEED, speed))
    nx = x + speed * math.cos(heading) * dt
    ny = y + speed * math.sin(heading) * dt
    nh = wrap(heading + speed * math.tan(steer) / WHEELBASE * dt)
    ns = max(0.0, min(MAX_SPEED, speed + accel * dt))
    return nx, ny, nh, ns
