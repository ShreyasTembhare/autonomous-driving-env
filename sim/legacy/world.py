"""The crossing: six cars, a phase cycle, pedestrians, and live surprises."""

from __future__ import annotations

import math

from sim.legacy.actors import Car, Pedestrian
from sim.legacy.commands import apply as apply_command
from sim.legacy.decision import accel_limit, apply_forced, decide, integrate, simple_drive
from sim.geom import (
    BOX,
    DT,
    HALF_LEN,
    HISTORY,
    LATERAL,
    ROAD_EDGE,
    SIGNAL_POS,
    CROSSWALK,
    STOP_LINE,
    dist_to_stop,
    lateral_of,
    measure_s,
    pose,
)
from sim.signals import PHASE_LABEL, Signal

TOWN = [
    dict(id="ada", name="Ada", color="#2dd4bf", brain="cautious", seed=None, axis="east", lane=0, s=-40, speed=7.5),
    dict(id="rex", name="Rex", color="#fb923c", brain="impatient", seed=None, axis="north", lane=1, s=-34, speed=11.0),
    dict(id="mina", name="Mina", color="#60a5fa", brain="careful", seed=0, axis="west", lane=0, s=-36, speed=8.0),
    dict(id="theo", name="Theo", color="#a78bfa", brain="careful", seed=1, axis="south", lane=0, s=-40, speed=8.0),
    dict(id="jules", name="Jules", color="#f87171", brain="hurried", seed=0, axis="east", lane=1, s=-30, speed=8.0),
    dict(id="nova", name="Nova", color="#facc15", brain="hurried", seed=1, axis="north", lane=0, s=-48, speed=12.0),
]


class World:
    def __init__(self, seed: int = 7, fleet: str = "town", load_policies: bool = True) -> None:
        self.seed = seed
        self.tick = 0
        self.wet = False
        self.log: list[dict] = []
        self.jay_seq = 0
        self.signal = Signal()
        self.peds: list[Pedestrian] = []
        self.cars: list[Car] = []
        self.allow_respawn = fleet == "town"
        self._colors: dict[str, str] = {}
        if fleet == "town":
            self._build_town(load_policies)
            self._build_walkers()
            self.preview()

    def car(self, car_id: str) -> Car | None:
        for car in self.cars:
            if car.id == car_id:
                return car
        return None

    def apply(self, cmd: dict, record: bool = True) -> str:
        return apply_command(self, cmd, record=record)

    def preview(self) -> None:
        for car in self.cars:
            if car.simple:
                continue
            _accel, _steer, frame = decide(self, car, commit=False)
            car.decision = frame

    def step(self, forced: dict | None = None, filters: bool = True) -> None:
        forced = forced or {}
        self._colors = {car.id: self.signal.color_for_axis(car.axis) for car in self.cars}
        self._start_walkers()
        self._move_peds()
        limit = accel_limit(self)
        for car in self.cars:
            car.entered_red = False
            old_s = car.s
            if car.crashed:
                car.speed = 0.0
                if not car.simple:
                    _a, _s, frame = decide(self, car, commit=False)
                    car.decision = frame
                continue
            if car.id in forced:
                accel, steer = apply_forced(self, car, forced[car.id])
            elif car.simple:
                accel, steer = simple_drive(self, car)
            elif not filters:
                accel, steer = simple_drive(self, car)
            else:
                accel, steer, frame = decide(self, car, commit=True)
                car.decision = frame
            if car.stalled and car.id not in forced:
                accel = -limit if car.speed > 0.2 else 0.0
                steer = 0.0
            integrate(car, accel, steer, limit)
            car.s = measure_s(car.axis, car.x, car.y)
            target_lat = LATERAL[car.axis][car.target_lane_index]
            if abs(lateral_of(car.axis, car.x, car.y) - target_lat) < 0.45:
                car.lane_index = car.target_lane_index
            old_dist = STOP_LINE - (old_s + HALF_LEN)
            new_dist = dist_to_stop(car.s)
            car.entered_red = old_dist > 0.05 and new_dist <= 0.05 and self._colors.get(car.id) == "red"
            action = "IDLE"
            if car.decision:
                action = car.decision.get("meta_action", "IDLE")
                car.decision["accel"] = round(float(car.accel), 3)
                car.decision["steering_deg"] = round(math.degrees(car.steer), 2)
            car.history.append({"t": round((self.tick + 1) * DT, 2), "speed": round(car.speed, 3), "action": action})
            if len(car.history) > HISTORY:
                del car.history[:-HISTORY]
            if car.decision is not None:
                car.decision["history"] = list(car.history)
        self._collisions()
        if self.allow_respawn:
            for car in self.cars:
                self._respawn(car)
        self.signal.advance()
        self.tick += 1

    def export_log(self) -> dict:
        return {
            "seed": self.seed,
            "policies": {car.id: car.checkpoint for car in self.cars},
            "commands": [dict(entry) for entry in self.log],
            "steps": self.tick,
        }

    def reset_keeping_models(self) -> "World":
        fresh = World(seed=self.seed, fleet="town", load_policies=False)
        by_id = {car.id: car for car in self.cars}
        for car in fresh.cars:
            prev = by_id.get(car.id)
            if prev is None:
                continue
            car.model = prev.model
            car.checkpoint = prev.checkpoint
            car.uses_network = prev.uses_network
        fresh.preview()
        return fresh

    def snapshot(self, paused: bool = False, rate: float = 1.0, train: dict | None = None) -> dict:
        limit = accel_limit(self)
        cars = []
        for car in self.cars:
            decision = car.decision or {
                "sentence": "Waiting for the first tick.",
                "meta_action": "IDLE",
                "seen": [],
                "hidden_count": 0,
                "constraints": [],
                "options": [],
                "filter": None,
                "uses_network": False,
                "brain": car.brain,
                "brain_label": car.brain.title(),
                "model": {"loaded": False, "text": "No frame yet."},
                "history": [],
                "accel": 0,
                "steering_deg": 0,
                "target_speed": car.target_speed,
                "limits": {"accel_min": -limit, "accel_max": limit, "steer_deg": 45, "wet": self.wet},
                "cone": {"range": 36, "half_angle": 0.733},
            }
            cars.append(
                {
                    "id": car.id,
                    "name": car.name,
                    "color": car.color,
                    "x": round(car.x, 3),
                    "y": round(car.y, 3),
                    "heading": round(car.heading, 4),
                    "speed": round(car.speed, 3),
                    "length": car.length,
                    "width": car.width,
                    "stalled": car.stalled,
                    "crashed": car.crashed,
                    "axis": car.axis,
                    "lane": car.lane_index,
                    "decision": decision,
                }
            )
        peds = []
        for ped in self.peds:
            peds.append(
                {
                    "id": ped.id,
                    "kind": ped.kind,
                    "name": ped.name,
                    "x": round(ped.x, 3),
                    "y": round(ped.y, 3),
                    "heading": round(ped.heading, 4),
                    "hit": ped.hit,
                    "path": [[round(x, 2), round(y, 2)] for x, y in ped.path],
                }
            )
        approaches = self.signal.approach_colors()
        lamps = []
        for axis, (x, y) in SIGNAL_POS.items():
            lamps.append(
                {
                    "axis": axis,
                    "x": x,
                    "y": y,
                    "color": self.signal.color_for_axis(axis),
                }
            )
        return {
            "tick": self.tick,
            "time": round(self.tick * DT, 2),
            "paused": paused,
            "speed": rate,
            "seed": self.seed,
            "wet": self.wet,
            "limits": {"accel": limit, "brake": limit},
            "signal": {
                "phase": self.signal.phase,
                "label": PHASE_LABEL.get(self.signal.phase, self.signal.phase),
                "remaining": round(self.signal.remaining * DT, 2),
                "approaches": approaches,
                "lamps": lamps,
            },
            "map": {"stop": abs(STOP_LINE), "edge": ROAD_EDGE, "box": BOX, "crosswalk": CROSSWALK},
            "cars": cars,
            "pedestrians": peds,
            "log": [
                {"index": i, "tick": entry["tick"], "time": entry["time"], "label": entry["label"]}
                for i, entry in enumerate(self.log)
            ],
            "all_crashed": bool(self.cars) and all(car.crashed for car in self.cars),
            "train": train
            or {
                "running": False,
                "mix": None,
                "step": 0,
                "budget": 0,
                "reward": None,
                "crash_rate": None,
                "ready": False,
                "checkpoint": None,
                "error": None,
            },
        }

    def _build_town(self, load_policies: bool) -> None:
        from sim.policies import checkpoint_file, load_checkpoint

        for spec in TOWN:
            x, y, heading = pose(spec["axis"], spec["lane"], spec["s"])
            checkpoint = None
            model = None
            uses_network = False
            if spec["brain"] in ("careful", "hurried") and spec["seed"] is not None:
                path = checkpoint_file(spec["brain"], spec["seed"])
                checkpoint = path.stem
                if load_policies and path.exists():
                    try:
                        model = load_checkpoint(path)
                        uses_network = True
                    except Exception:
                        model = None
                        uses_network = False
            self.cars.append(
                Car(
                    id=spec["id"],
                    name=spec["name"],
                    color=spec["color"],
                    brain=spec["brain"],
                    seed=spec["seed"],
                    axis=spec["axis"],
                    lane_index=spec["lane"],
                    target_lane_index=spec["lane"],
                    x=x,
                    y=y,
                    heading=heading,
                    speed=spec["speed"],
                    target_speed=spec["speed"],
                    cruise=spec["speed"],
                    s=spec["s"],
                    model=model,
                    checkpoint=checkpoint,
                    uses_network=uses_network,
                )
            )

    def _build_walkers(self) -> None:
        specs = [
            ("walker-west", "Walker", [(-CROSSWALK, -8.4), (-CROSSWALK, 8.4)], "ns_green"),
            ("walker-east", "Walker", [(CROSSWALK, -8.4), (CROSSWALK, 8.4)], "ns_green"),
            ("walker-south", "Walker", [(-8.4, -CROSSWALK), (8.4, -CROSSWALK)], "ew_green"),
            ("walker-north", "Walker", [(-8.4, CROSSWALK), (8.4, CROSSWALK)], "ew_green"),
        ]
        for pid, name, path, phase in specs:
            dx, dy = path[1][0] - path[0][0], path[1][1] - path[0][1]
            self.peds.append(
                Pedestrian(
                    id=pid,
                    kind="walker",
                    name=name,
                    x=path[0][0],
                    y=path[0][1],
                    heading=math.atan2(dy, dx),
                    speed=0.0,
                    path=path,
                    walk_phase=phase,
                    cruise=1.55,
                )
            )

    def _start_walkers(self) -> None:
        phase = self.signal.phase
        gen = self.signal.green_gen
        for ped in self.peds:
            if ped.kind != "walker" or ped.hit or ped.moving:
                continue
            if phase != ped.walk_phase or ped.last_gen == gen:
                continue
            if self._crosswalk_busy(ped):
                continue
            ped.moving = True
            ped.speed = ped.cruise
            ped.last_gen = gen

    def _crosswalk_busy(self, ped: Pedestrian) -> bool:
        x0, y0 = ped.path[0]
        x1, y1 = ped.path[-1]
        for car in self.cars:
            if car.speed < 0.4:
                continue
            # Distance from the car to the crosswalk segment.
            vx, vy = x1 - x0, y1 - y0
            length = math.hypot(vx, vy) or 1.0
            t = max(0.0, min(1.0, ((car.x - x0) * vx + (car.y - y0) * vy) / (length * length)))
            px, py = x0 + vx * t, y0 + vy * t
            if math.hypot(car.x - px, car.y - py) < 3.2:
                return True
        return False

    def _move_peds(self) -> None:
        for ped in self.peds:
            if ped.hit or not ped.moving:
                ped.speed = 0.0 if not ped.moving else ped.speed
                continue
            if ped.path_i >= len(ped.path) - 1:
                self._arrive(ped)
                continue
            tx, ty = ped.path[ped.path_i + 1]
            dx, dy = tx - ped.x, ty - ped.y
            dist = math.hypot(dx, dy)
            if dist < 1e-4:
                ped.path_i += 1
                continue
            ped.heading = math.atan2(dy, dx)
            step = ped.speed * DT
            # A person already on the path stops short of a car. A car that
            # drives into them still collides; this only refuses the step.
            nx = tx if step >= dist else ped.x + dx / dist * step
            ny = ty if step >= dist else ped.y + dy / dist * step
            probe = Pedestrian(
                id=ped.id,
                kind=ped.kind,
                name=ped.name,
                x=nx,
                y=ny,
                heading=ped.heading,
                speed=ped.speed,
                path=ped.path,
            )
            if any(not car.crashed and _ped_hit(car, probe, radius=0.7) for car in self.cars):
                ped.speed = 0.0
                continue
            ped.speed = ped.cruise
            if step >= dist:
                ped.x, ped.y = tx, ty
                ped.path_i += 1
                if ped.path_i >= len(ped.path) - 1:
                    self._arrive(ped)
            else:
                ped.x += dx / dist * step
                ped.y += dy / dist * step

    def _arrive(self, ped: Pedestrian) -> None:
        ped.moving = False
        ped.speed = 0.0
        if ped.kind == "walker" and len(ped.path) >= 2:
            ped.path = list(reversed(ped.path))
            ped.path_i = 0
            ped.x, ped.y = ped.path[0]

    def _respawn(self, car: Car) -> None:
        if car.crashed or car.stalled or car.s < 52:
            return
        for back in (48.0, 64.0, 80.0):
            nx, ny, nh = pose(car.axis, car.lane_index, -back)
            blocked = False
            for other in self.cars:
                if other is car:
                    continue
                if math.hypot(other.x - nx, other.y - ny) < 11:
                    blocked = True
                    break
            if blocked:
                continue
            car.x, car.y, car.heading = nx, ny, nh
            car.s = -back
            car.speed = min(car.cruise, 8.0)
            car.target_speed = min(car.cruise, 9.0)
            car.target_lane_index = car.lane_index
            car.lane_index = car.lane_index
            return
        car.speed = 0.0
        car.target_speed = 0.0

    def _collisions(self) -> None:
        for i, car in enumerate(self.cars):
            for other in self.cars[i + 1 :]:
                if car.crashed and other.crashed:
                    continue
                if math.hypot(car.x - other.x, car.y - other.y) > 8:
                    continue
                if _boxes_overlap(car, other):
                    car.crashed = True
                    other.crashed = True
                    car.speed = 0.0
                    other.speed = 0.0
            if car.crashed:
                continue
            for ped in self.peds:
                if ped.hit:
                    continue
                if _ped_hit(car, ped):
                    car.crashed = True
                    car.hit_ped = True
                    car.speed = 0.0
                    ped.hit = True
                    ped.moving = False
                    ped.speed = 0.0

    def configure_training(self, mix: str, rng) -> None:
        """One ego and a few scripted actors. Used by the Gymnasium env."""
        self.cars.clear()
        self.peds.clear()
        self.allow_respawn = False
        self.log.clear()
        self.wet = False
        axis = str(rng.choice(["east", "west", "north", "south"]))
        lane = int(rng.integers(0, 2))
        s = float(rng.uniform(-40, -18))
        speed = float(rng.uniform(4.0, 11.0))
        self.cars.append(_make(axis, lane, s, speed, "ego", mix, simple=False))
        if float(rng.random()) < 0.55:
            lead_s = s + float(rng.uniform(9.0, 22.0))
            lead_speed = float(rng.uniform(0.0, max(1.0, speed - 1.0)))
            self.cars.append(_make(axis, lane, lead_s, lead_speed, "lead", "cautious", simple=True))
        if float(rng.random()) < 0.35:
            cross_axis = "north" if axis in ("east", "west") else "east"
            cross_s = float(rng.uniform(-6.0, 6.0))
            self.cars.append(_make(cross_axis, int(rng.integers(0, 2)), cross_s, 6.0, "cross", "cautious", simple=True))
        if float(rng.random()) < 0.7:
            ahead = s + float(rng.uniform(7.0, 16.0))
            sx, sy, _ = pose(axis, lane, ahead)
            if axis in ("east", "west"):
                path = [(sx, sy - 5.5), (sx, sy + 5.5)]
            else:
                path = [(sx - 5.5, sy), (sx + 5.5, sy)]
            dx, dy = path[1][0] - path[0][0], path[1][1] - path[0][1]
            self.peds.append(
                Pedestrian(
                    id="train-ped",
                    kind="jaywalker",
                    name="Pedestrian",
                    x=path[0][0],
                    y=path[0][1],
                    heading=math.atan2(dy, dx),
                    speed=1.4,
                    path=path,
                    moving=True,
                    cruise=1.4,
                )
            )
        phases = ["ns_green", "ns_yellow", "ew_green", "ew_yellow", "all_red"]
        phase = str(rng.choice(phases, p=[0.34, 0.1, 0.34, 0.1, 0.12]))
        self.signal.set_phase(phase, int(rng.integers(15, 110)))


def _make(axis: str, lane: int, s: float, speed: float, car_id: str, brain: str, simple: bool) -> Car:
    x, y, heading = pose(axis, lane, s)
    return Car(
        id=car_id,
        name=car_id,
        color="#dddddd",
        brain=brain,
        seed=None,
        axis=axis,
        lane_index=lane,
        target_lane_index=lane,
        x=x,
        y=y,
        heading=heading,
        speed=speed,
        target_speed=speed,
        cruise=max(speed, 6.0),
        s=s,
        simple=simple,
    )


def _boxes_overlap(a: Car, b: Car) -> bool:
    pa = _corners(a)
    pb = _corners(b)
    for axis in _axes(pa) + _axes(pb):
        mina, maxa = _project(pa, axis)
        minb, maxb = _project(pb, axis)
        if maxa < minb or maxb < mina:
            return False
    return True


def _corners(car: Car) -> list[tuple[float, float]]:
    hl, hw = car.length / 2, car.width / 2
    c, s = math.cos(car.heading), math.sin(car.heading)
    pts = []
    for lx, ly in ((hl, hw), (hl, -hw), (-hl, -hw), (-hl, hw)):
        pts.append((car.x + c * lx - s * ly, car.y + s * lx + c * ly))
    return pts


def _axes(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = []
    for i in range(2):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % 4]
        ex, ey = x2 - x1, y2 - y1
        out.append((-ey, ex))
    return out


def _project(pts: list[tuple[float, float]], axis: tuple[float, float]) -> tuple[float, float]:
    vals = [p[0] * axis[0] + p[1] * axis[1] for p in pts]
    return min(vals), max(vals)


def _ped_hit(car: Car, ped: Pedestrian, radius: float = 0.45) -> bool:
    dx, dy = ped.x - car.x, ped.y - car.y
    c, s = math.cos(car.heading), math.sin(car.heading)
    lx = dx * c + dy * s
    ly = -dx * s + dy * c
    return abs(lx) <= car.length / 2 + radius and abs(ly) <= car.width / 2 + radius
