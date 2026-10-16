"""Cars and pedestrians."""

from __future__ import annotations

from dataclasses import dataclass, field

from sim.geom import CAR_LENGTH, CAR_WIDTH


@dataclass
class Car:
    id: str
    name: str
    color: str
    brain: str
    seed: int | None
    axis: str
    lane_index: int
    target_lane_index: int
    x: float
    y: float
    heading: float
    speed: float
    target_speed: float
    cruise: float
    s: float
    stalled: bool = False
    crashed: bool = False
    hit_ped: bool = False
    entered_red: bool = False
    simple: bool = False
    model: object = None
    checkpoint: str | None = None
    uses_network: bool = False
    accel: float = 0.0
    steer: float = 0.0
    decision: dict | None = None
    history: list = field(default_factory=list)
    length: float = CAR_LENGTH
    width: float = CAR_WIDTH

    @property
    def vx(self) -> float:
        import math

        return self.speed * math.cos(self.heading)

    @property
    def vy(self) -> float:
        import math

        return self.speed * math.sin(self.heading)


@dataclass
class Pedestrian:
    id: str
    kind: str
    name: str
    x: float
    y: float
    heading: float
    speed: float
    path: list[tuple[float, float]]
    path_i: int = 0
    moving: bool = False
    hit: bool = False
    walk_phase: str | None = None
    last_gen: int = -1
    cruise: float = 1.55
