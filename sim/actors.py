"""Cars and pedestrians on the road network."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from sim.geom import CAR_LENGTH, CAR_WIDTH


@dataclass
class Car:
    id: str
    name: str
    color: str
    brain: str
    seed: int | None
    x: float
    y: float
    heading: float
    speed: float
    route: list[str]
    goal_s: float
    leg: str = "link"
    link: str = ""
    connector: str | None = None
    s: float = 0.0
    lat: float = 0.0
    t: float = 0.0
    lane: int = 0
    target_lane: int = 0
    route_i: int = 0
    stalled: bool = False
    crashed: bool = False
    hit_ped: bool = False
    arrived: bool = False
    arrived_tick: int | None = None
    user: bool = False
    tracked: bool = False
    goal_stop: bool = False
    named: bool = False
    model: object = None
    checkpoint: str | None = None
    uses_network: bool = False
    accel: float = 0.0
    steer: float = 0.0
    decision: dict | None = None
    history: list = field(default_factory=list)
    length: float = CAR_LENGTH
    width: float = CAR_WIDTH
    indicator: str | None = None
    badge: str | None = None
    binding: str | None = None
    wait: float = 0.0
    stopped_for: float = 0.0
    lane_lock: int = 0
    lc_start_tick: int | None = None
    start_tick: int = 0
    start_label: str = ""
    dest_label: str = ""
    stops: int = 0
    overtakes: int = 0
    replans: list = field(default_factory=list)
    overtaking: str | None = None
    entered_red: bool = False
    crash_tick: int | None = None
    was_stopped: bool = False
    note: str | None = None
    note_until: int = 0
    trace: object = None
    pred: object = None

    @property
    def vx(self) -> float:
        return self.speed * math.cos(self.heading)

    @property
    def vy(self) -> float:
        return self.speed * math.sin(self.heading)

    @property
    def active(self) -> bool:
        return not self.arrived


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
    node: str | None = None
    last_gen: int = -1
    cruise: float = 1.55
    blocked_by: str | None = None
    blocked_ticks: int = 0
    hit_tick: int | None = None
