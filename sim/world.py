"""The town: a 2x2 grid of signalized intersections, cars on routes, and walkers."""

from __future__ import annotations

import math
import random

from sim import paths, planner
from sim.actors import Car, Pedestrian
from sim.commands import apply as apply_command
from sim.geom import DT, HISTORY, MAX_SPEED
from sim.idm import hard_limit, style_for
from sim.kinematics import step_bicycle
from sim.network import LANE_LAT, NETWORK, SIGNAL_OFFSET, SOLID_ZONE, STUBS
from sim.routes import describe, plan, required_lane
from sim.signals import PHASE_LABEL, Signal

MAX_CARS = 24
MIN_CARS = 4
DEFAULT_CARS = 12
STALL_REROUTE = 6.0
REMOVE_AFTER = 30
CLEAR_AFTER = 200

NAMED = [
    dict(id="ada", name="Ada", color="#2dd4bf", brain="cautious", seed=None, start="W1", dest="E2", s=40, lane=0, speed=7.0),
    dict(id="rex", name="Rex", color="#fb923c", brain="impatient", seed=None, start="S2", dest="W1", s=50, lane=1, speed=10.0),
    dict(id="mina", name="Mina", color="#60a5fa", brain="careful", seed=0, start="E1", dest="S1", s=30, lane=0, speed=8.0),
    dict(id="theo", name="Theo", color="#a78bfa", brain="careful", seed=1, start="N1", dest="E2", s=60, lane=0, speed=8.0),
    dict(id="jules", name="Jules", color="#f87171", brain="hurried", seed=0, start="W1", dest="N2", s=22, lane=1, speed=9.0),
    dict(id="nova", name="Nova", color="#facc15", brain="hurried", seed=1, start="S1", dest="E1", s=30, lane=0, speed=10.0),
]
EXTRA_COLORS = ["#94a3b8", "#f472b6", "#34d399", "#c084fc", "#fbbf24", "#38bdf8", "#e879f9", "#a3e635", "#fda4af", "#5eead4", "#fdba74", "#93c5fd"]
TRIP_COLORS = ["#ffffff", "#22d3ee", "#f0abfc", "#bef264", "#fde047", "#fca5a5"]
BRAINS = ["cautious", "careful", "impatient", "hurried"]


class World:
    def __init__(self, seed: int = 7, fleet: str = "town", load_policies: bool = True, n_cars: int = DEFAULT_CARS) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.tick = 0
        self.wet = False
        self.log: list[dict] = []
        self.jay_seq = 0
        self.trip_seq = 0
        self.extra_seq = 0
        self.signals: dict[str, Signal] = {}
        for nid, offset in SIGNAL_OFFSET.items():
            sig = Signal()
            for _ in range(offset):
                sig.advance()
            self.signals[nid] = sig
        self.peds: list[Pedestrian] = []
        self.cars: list[Car] = []
        self.ped_pred: dict[str, list[tuple[float, float]]] = {}
        self.notices: list[dict] = []
        self.notice_seq = 0
        self.stats = {"arrivals": 0, "crashes": 0, "ped_hits": 0, "trips_done": 0}
        self.stall_since: dict[str, int] = {}
        self.last_spawned: str | None = None
        self.target_size = n_cars
        self.allow_respawn = fleet == "town"
        if fleet == "town":
            self._build_town(load_policies, n_cars)
            self._build_walkers()
            self.preview()

    # ------------------------------------------------------------------ basics

    def car(self, car_id: str | None) -> Car | None:
        if car_id is None:
            return None
        for car in self.cars:
            if car.id == car_id:
                return car
        return None

    def ped(self, ped_id: str) -> Pedestrian | None:
        for ped in self.peds:
            if ped.id == ped_id:
                return ped
        return None

    def apply(self, cmd: dict, record: bool = True) -> str:
        return apply_command(self, cmd, record=record)

    def notice(self, text: str, kind: str = "info", car: str | None = None) -> None:
        self.notice_seq += 1
        self.notices.append({"id": self.notice_seq, "tick": self.tick, "kind": kind, "text": text, "car": car})
        if len(self.notices) > 12:
            del self.notices[:-12]

    def active_cars(self) -> list[Car]:
        return [c for c in self.cars if not c.arrived]

    # ------------------------------------------------------------------ town

    def _build_town(self, load_policies: bool, n_cars: int) -> None:
        from sim.policies import checkpoint_file, load_checkpoint

        for spec in NAMED:
            car = self._new_car(spec["id"], spec["name"], spec["color"], spec["brain"], spec["seed"])
            car.named = True
            if spec["brain"] in ("careful", "hurried") and spec["seed"] is not None:
                path = checkpoint_file(spec["brain"], spec["seed"])
                car.checkpoint = path.stem
                if load_policies:
                    try:
                        car.model = load_checkpoint(path)
                        car.uses_network = True
                    except Exception:
                        car.model = None
                        car.uses_network = False
            entry = NETWORK.entry_link(spec["start"])
            self._place(car, entry.id, float(spec["s"]), spec["lane"], spec["start"], spec["dest"], spec["speed"])
            self.cars.append(car)
        while len(self.cars) < n_cars:
            if not self._add_background():
                break

    def _new_car(self, cid, name, color, brain, seed=None) -> Car:
        return Car(id=cid, name=name, color=color, brain=brain, seed=seed, x=0.0, y=0.0, heading=0.0, speed=0.0, route=[], goal_s=0.0)

    def _place(self, car: Car, link_id: str, s: float, lane: int | None, start_label: str, dest: str, speed: float) -> bool:
        exit_link = NETWORK.exit_link(dest)
        res = plan(link_id, s, exit_link.id, exit_link.length - 1.0, world=self)
        if not res.ok:
            return False
        if lane is None:
            need = required_lane(res.links, 0)
            lane = need if need is not None else self.rng.choice([0, 1])
        start = STUBS[start_label][0] if start_label in STUBS else start_label
        self._place_route(car, link_id, s, lane, res, start, STUBS[dest][0], speed)
        car.goal_stop = False
        car.tracked = False
        return True

    def _place_route(self, car: Car, link_id: str, s: float, lane: int, res, start_label: str, dest_label: str, speed: float) -> None:
        link = NETWORK.links[link_id]
        car.route = list(res.links)
        car.goal_s = res.goal_s
        car.route_i = 0
        car.leg, car.link, car.connector = "link", link_id, None
        car.s, car.lat, car.t = s, LANE_LAT[lane], 0.0
        car.lane = car.target_lane = lane
        car.x, car.y = link.point(s, car.lat)
        car.heading = link.heading
        st = style_for(car.brain, self.wet)
        car.speed = min(speed, st.v0)
        car.arrived = False
        car.arrived_tick = None
        car.start_tick = self.tick
        car.start_label = start_label
        car.dest_label = dest_label
        car.stops = car.overtakes = 0
        car.replans = []
        car.overtaking = None
        car.wait = 0.0
        car.was_stopped = False
        car.lc_start_tick = None
        car.history = []
        car.trace = None
        car.pred = None

    def _clear_at(self, link_id: str, s: float, lane: int, radius: float = 12.0, ignore: Car | None = None) -> bool:
        x, y = NETWORK.links[link_id].point(s, LANE_LAT[lane])
        for other in self.cars:
            if other is ignore or other.arrived:
                continue
            if math.hypot(other.x - x, other.y - y) < radius:
                return False
        return True

    def _pick_trip(self, avoid_start: str | None = None) -> tuple[str, str, int] | None:
        stubs = sorted(STUBS)
        for _ in range(12):
            start = self.rng.choice(stubs)
            if start == avoid_start:
                continue
            dest = self.rng.choice([s for s in stubs if s != start])
            entry = NETWORK.entry_link(start)
            lane = self.rng.choice([0, 1])
            if self._clear_at(entry.id, 4.0, lane, 13.0):
                return start, dest, lane
        return None

    def _add_background(self) -> bool:
        self.extra_seq += 1
        n = self.extra_seq
        brain = BRAINS[(n + 1) % len(BRAINS)]
        car = self._new_car(f"car-{n}", f"Car {n + 6}", EXTRA_COLORS[(n - 1) % len(EXTRA_COLORS)], brain)
        # Spread the starting fleet along entry links, not only at the edge.
        for _ in range(20):
            start = self.rng.choice(sorted(STUBS))
            dest = self.rng.choice([s for s in sorted(STUBS) if s != start])
            entry = NETWORK.entry_link(start)
            s = 4.0 if self.tick > 0 else self.rng.uniform(4.0, 80.0)
            lane = self.rng.choice([0, 1])
            if not self._clear_at(entry.id, s, lane, 14.0):
                continue
            if self._place(car, entry.id, s, lane, start, dest, self.rng.uniform(6.0, 10.0)):
                self.cars.append(car)
                return True
        return False

    def _respawn(self, car: Car) -> None:
        pick = self._pick_trip()
        if pick is None:
            car.arrived = True
            return
        start, dest, lane = pick
        entry = NETWORK.entry_link(start)
        self._place(car, entry.id, 4.0, lane, start, dest, 8.0)

    def _build_walkers(self) -> None:
        for cw in NETWORK.crosswalks:
            a, b = cw.a, cw.b
            self.peds.append(
                Pedestrian(
                    id=f"walker-{cw.id}",
                    kind="walker",
                    name="Walker",
                    x=a[0],
                    y=a[1],
                    heading=math.atan2(b[1] - a[1], b[0] - a[0]),
                    speed=0.0,
                    path=[a, b],
                    walk_phase=cw.walk_phase,
                    node=cw.node,
                    cruise=1.55,
                )
            )

    # ------------------------------------------------------------------ tick

    def _prepare(self) -> None:
        for car in self.cars:
            if car.arrived:
                car.trace = None
                car.pred = None
                continue
            max_d = max(45.0, car.speed * planner.HORIZON + 30.0)
            car.trace = paths.build(car, car.target_lane, max_d)
            if car.stalled or car.crashed or car.speed < 0.05:
                car.pred = [(car.x, car.y, car.heading)] * (planner.STEPS + 1)
            else:
                car.pred = [car.trace.pose_at(car.speed * k * planner.ROLL_DT) for k in range(planner.STEPS + 1)]
        self.ped_pred = {}
        for ped in self.peds:
            pts = []
            x, y, i = ped.x, ped.y, ped.path_i
            moving = ped.moving and not ped.hit
            for k in range(planner.STEPS + 1):
                pts.append((x, y))
                if not moving or i >= len(ped.path) - 1:
                    continue
                tx, ty = ped.path[i + 1]
                dist = math.hypot(tx - x, ty - y)
                adv = ped.cruise * planner.ROLL_DT
                if dist <= adv:
                    x, y, i = tx, ty, i + 1
                else:
                    x += (tx - x) / dist * adv
                    y += (ty - y) / dist * adv
            self.ped_pred[ped.id] = pts

    def preview(self) -> None:
        self._prepare()
        for car in self.cars:
            if car.arrived:
                continue
            _a, _s, frame, _c = planner.decide(self, car)
            car.decision = frame

    def step(self) -> None:
        self._prepare()
        self._start_walkers()
        self._move_peds()
        hard = hard_limit(self.wet)
        plans = {}
        for car in self.cars:
            if car.arrived:
                continue
            accel, steer, frame, chosen = planner.decide(self, car)
            car.decision = frame
            plans[car.id] = (accel, steer)
        for car in self.cars:
            if car.arrived or car.id not in plans:
                continue
            accel, steer = plans[car.id]
            if car.crashed:
                car.speed = 0.0
                car.accel = 0.0
                continue
            accel = max(-hard, min(hard, accel))
            car.x, car.y, car.heading, car.speed = step_bicycle(car.x, car.y, car.heading, car.speed, accel, steer)
            car.accel, car.steer = accel, steer
            self._advance_leg(car)
            self._trip_bookkeeping(car)
        self._collisions()
        if self.tick % 10 == 0:
            self._reroute_checks()
        self._lifecycle()
        for sig in self.signals.values():
            sig.advance()
        self.tick += 1

    def _advance_leg(self, car: Car) -> None:
        if car.leg == "link":
            link = NETWORK.links[car.link]
            car.s, car.lat = link.locate(car.x, car.y)
            if abs(car.lat - LANE_LAT.get(car.target_lane, car.lat)) < 0.5:
                if car.lane != car.target_lane:
                    car.lane_lock = 0
                car.lane = car.target_lane
            if car.lane_lock > 0:
                car.lane_lock -= 1
            # Stopped half way across near the line: settle into the lane the car is in.
            if car.target_lane != car.lane and car.speed < 0.5 and link.stop_s - car.s < SOLID_ZONE + 3:
                car.target_lane = car.lane = (1 if car.lat < 3.5 else 0) if car.lat > 0 else -1
            last = car.route_i >= len(car.route) - 1
            if last:
                if car.goal_stop:
                    if car.s >= car.goal_s - 1.5 and car.speed < 0.6 or car.s >= car.goal_s + 2.0:
                        self._arrive(car)
                elif car.s >= car.goal_s:
                    self._arrive(car)
                return
            if car.s >= link.stop_s:
                lane_now = 1 if car.lat < 3.5 else 0
                conn = NETWORK.connector_for(link.id, car.route[car.route_i + 1], lane_now)
                if conn is None:
                    conn = self._fallback_connector(car, link.id, lane_now)
                car.leg = "connector"
                car.connector = conn.id
                car.t = self._project(conn, car.x, car.y, 0.0)
                car.lane = car.target_lane = lane_now
        else:
            conn = NETWORK.connectors[car.connector]
            car.t = self._project(conn, car.x, car.y, car.t)
            if car.t >= conn.length - 0.05:
                out = NETWORK.links[conn.link_out]
                car.leg = "link"
                car.connector = None
                car.link = out.id
                car.route_i += 1
                car.s, car.lat = out.locate(car.x, car.y)
                car.lane = car.target_lane = conn.lane_out

    def _fallback_connector(self, car: Car, link_id: str, lane: int):
        allowed = {lo for man, lo in NETWORK.successors(link_id) if NETWORK.connector_for(link_id, lo, lane)}
        dest = car.route[-1]
        res = plan(link_id, car.s, dest, car.goal_s, world=self, allowed_first=allowed)
        if res.ok:
            car.route = car.route[: car.route_i] + res.links
            self._replanned(car, "Reached the line in the wrong lane; took the move this lane allows")
        else:
            nxt = next(iter(sorted(allowed)))
            car.route = car.route[: car.route_i + 1] + [nxt]
            car.goal_s = NETWORK.links[nxt].length - 1.0
        return NETWORK.connector_for(link_id, car.route[car.route_i + 1], lane)

    def _project(self, conn, x: float, y: float, t_hint: float) -> float:
        best = None
        pts, cum = conn.points, conn.cum
        for i in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            vx, vy = x1 - x0, y1 - y0
            seg2 = vx * vx + vy * vy or 1e-9
            f = ((x - x0) * vx + (y - y0) * vy) / seg2
            last = i == len(pts) - 2
            f = max(0.0, f if last else min(1.0, f))
            px, py = x0 + vx * min(f, 1.0), y0 + vy * min(f, 1.0)
            d = (px - x) ** 2 + (py - y) ** 2
            t = cum[i] + f * math.sqrt(seg2)
            if best is None or d < best[0] - 1e-9:
                best = (d, t)
        return max(t_hint, best[1]) if best else t_hint

    def _arrive(self, car: Car) -> None:
        elapsed = (self.tick - car.start_tick) * DT
        self.stats["arrivals"] += 1
        if car.user:
            car.arrived = True
            car.arrived_tick = self.tick
            car.speed = 0.0
            self.stats["trips_done"] += 1
            self.notice(
                f"{car.name} arrived in {elapsed:.0f} s, {car.stops} stop{'s' if car.stops != 1 else ''}, {car.overtakes} overtake{'s' if car.overtakes != 1 else ''}",
                "arrival",
                car.id,
            )
            return
        if car.tracked:
            self.notice(f"{car.name} reached {car.dest_label} in {elapsed:.0f} s", "arrival", car.id)
        if self.allow_respawn:
            self._respawn(car)
        else:
            car.arrived = True
            car.arrived_tick = self.tick

    def _trip_bookkeeping(self, car: Car) -> None:
        if car.speed < 0.3:
            if not car.was_stopped and car.wait == 0.0:
                car.stops += 1
            car.was_stopped = True
            car.wait += DT
        else:
            if car.speed > 1.0:
                car.was_stopped = False
            car.wait = 0.0
        if car.overtaking:
            other = self.car(car.overtaking)
            if other is None or other.arrived:
                car.overtaking = None
            else:
                fx, fy = math.cos(car.heading), math.sin(car.heading)
                if (other.x - car.x) * fx + (other.y - car.y) * fy < -car.length:
                    car.overtakes += 1
                    car.overtaking = None
        if car.decision is not None:
            car.decision["accel"] = round(float(car.accel), 3)
            car.decision["steering_deg"] = round(math.degrees(car.steer), 2)
        car.history.append({"t": round((self.tick + 1) * DT, 2), "speed": round(car.speed, 3), "action": (car.decision or {}).get("meta_action", "KEEP"), "badge": car.badge})
        if len(car.history) > HISTORY:
            del car.history[:-HISTORY]
        if car.decision is not None:
            car.decision["history"] = list(car.history)
        car.indicator = self._indicator(car)

    def _indicator(self, car: Car) -> str | None:
        if car.stalled:
            return "hazard"
        if car.leg == "link" and car.target_lane != car.lane:
            return "left" if LANE_LAT.get(car.target_lane, 0) < LANE_LAT.get(car.lane, 0) else "right"
        if car.leg == "connector" and car.connector:
            man = NETWORK.connectors[car.connector].maneuver
            return man if man != "straight" else None
        if car.leg == "link" and car.trace is not None and car.trace.stop_d is not None and car.trace.stop_d < 45:
            mans = car.route_i + 1 < len(car.route)
            if mans:
                from sim.network import maneuver_between

                man = maneuver_between(NETWORK.links[car.route[car.route_i]].axis, NETWORK.links[car.route[car.route_i + 1]].axis)
                return man if man in ("left", "right") else None
        return None

    def _replanned(self, car: Car, reason: str) -> None:
        car.replans.append({"t": round(self.tick * DT, 1), "reason": reason, "route": describe(car.route[car.route_i :])})
        if car.user:
            self.notice(f"{car.name}: {reason}", "info", car.id)

    def _reroute_checks(self) -> None:
        stalled_links: dict[str, list[Car]] = {}
        for car in self.cars:
            if car.arrived or not (car.stalled or car.crashed):
                self.stall_since.pop(car.id, None)
                continue
            self.stall_since.setdefault(car.id, self.tick)
            if (self.tick - self.stall_since[car.id]) * DT < STALL_REROUTE:
                continue
            if car.leg == "link":
                stalled_links.setdefault(car.link, []).append(car)
            elif car.connector:
                conn = NETWORK.connectors[car.connector]
                stalled_links.setdefault(conn.link_out, []).append(car)
        for car in self.cars:
            if car.arrived or car.stalled or car.crashed:
                continue
            self._missed_lane(car)
            if not stalled_links:
                continue
            ahead = car.route[car.route_i + 1 :]
            hit = next((lid for lid in ahead if lid in stalled_links), None)
            if hit is None:
                continue
            self._reroute(car, f"{stalled_links[hit][0].name} is stalled on the {NETWORK.links[hit].frm}–{NETWORK.links[hit].to} road", avoid={hit})

    def _reroute(self, car: Car, reason: str, avoid: set[str] | None = None) -> bool:
        if car.leg == "connector":
            conn = NETWORK.connectors[car.connector]
            base = conn.link_out
            start_s = NETWORK.links[base].start_s
            keep = car.route[: car.route_i + 1]
        else:
            base = car.link
            start_s = car.s
            keep = car.route[: car.route_i]
        allowed = None
        if car.leg == "link":
            link = NETWORK.links[car.link]
            d_line = link.stop_s - car.s - car.length / 2
            if d_line < SOLID_ZONE + 4:
                allowed = {lo for _m, lo in NETWORK.successors(base) if NETWORK.connector_for(base, lo, car.lane if car.lane in (0, 1) else 1)}
        goal_link = car.route[-1]
        avoid = {a for a in (avoid or set()) if a != goal_link}
        res = plan(base, start_s, goal_link, car.goal_s, world=self, allowed_first=allowed, avoid=avoid)
        if not res.ok:
            return False
        new = keep + res.links
        if new == car.route:
            return False
        car.route = new
        self._replanned(car, reason)
        return True

    def _missed_lane(self, car: Car) -> None:
        if car.leg != "link":
            return
        need = required_lane(car.route, car.route_i)
        if need is None or car.target_lane == need:
            return
        link = NETWORK.links[car.link]
        d_line = link.stop_s - car.s - car.length / 2
        if d_line >= SOLID_ZONE:
            return
        lane = car.target_lane if car.target_lane in (0, 1) else 1
        allowed = {lo for _m, lo in NETWORK.successors(link.id) if NETWORK.connector_for(link.id, lo, lane)}
        res = plan(link.id, car.s, car.route[-1], car.goal_s, world=self, allowed_first=allowed)
        if res.ok:
            old = describe(car.route[car.route_i : car.route_i + 2])
            car.route = car.route[: car.route_i] + res.links
            self._replanned(car, f"Missed the lane for the {old}; took the move lane {lane} allows and re-planned")

    def _lifecycle(self) -> None:
        for ped in list(self.peds):
            if ped.hit and ped.hit_tick is not None and self.tick - ped.hit_tick >= CLEAR_AFTER:
                if ped.kind == "walker":
                    ped.hit = False
                    ped.hit_tick = None
                    ped.moving = False
                    ped.path_i = 0
                    ped.x, ped.y = ped.path[0]
                else:
                    self.peds = [p for p in self.peds if p is not ped]
        keep = []
        for car in self.cars:
            if car.arrived and car.user and car.arrived_tick is not None and self.tick - car.arrived_tick >= REMOVE_AFTER:
                continue
            if car.crashed and car.crash_tick is not None and self.tick - car.crash_tick >= CLEAR_AFTER:
                car.crashed = car.hit_ped = car.stalled = False
                car.crash_tick = None
                if car.user:
                    self.notice(f"{car.name} was towed away after the crash", "info", car.id)
                    continue
                self._respawn(car)
            if car.arrived and not car.user and self.allow_respawn:
                self._respawn(car)
            keep.append(car)
        self.cars = keep
        if self.allow_respawn:
            background = [c for c in self.cars if not c.user]
            if len(background) < self.target_size and len(self.cars) < MAX_CARS and self.tick % 20 == 0:
                self._add_background()

    # ------------------------------------------------------------------ walkers

    def _start_walkers(self) -> None:
        for ped in self.peds:
            if ped.kind != "walker" or ped.hit or ped.moving:
                continue
            sig = self.signals[ped.node]
            if sig.phase != ped.walk_phase or ped.last_gen == sig.green_gen:
                continue
            if sig.remaining < 90:
                continue
            if self._crosswalk_busy(ped):
                continue
            ped.moving = True
            ped.speed = ped.cruise
            ped.last_gen = sig.green_gen

    def _crosswalk_busy(self, ped: Pedestrian) -> bool:
        x0, y0 = ped.path[0]
        x1, y1 = ped.path[-1]
        vx, vy = x1 - x0, y1 - y0
        length2 = vx * vx + vy * vy or 1.0
        for car in self.cars:
            if car.arrived:
                continue
            t = max(0.0, min(1.0, ((car.x - x0) * vx + (car.y - y0) * vy) / length2))
            px, py = x0 + vx * t, y0 + vy * t
            if math.hypot(car.x - px, car.y - py) < 3.4:
                return True
        return False

    def _move_peds(self) -> None:
        for ped in self.peds:
            if ped.hit or not ped.moving:
                if not ped.moving:
                    ped.speed = 0.0
                continue
            if ped.path_i >= len(ped.path) - 1:
                self._ped_arrive(ped)
                continue
            tx, ty = ped.path[ped.path_i + 1]
            dx, dy = tx - ped.x, ty - ped.y
            dist = math.hypot(dx, dy)
            if dist < 1e-4:
                ped.path_i += 1
                continue
            ped.heading = math.atan2(dy, dx)
            step = ped.cruise * DT
            nx = tx if step >= dist else ped.x + dx / dist * step
            ny = ty if step >= dist else ped.y + dy / dist * step
            probe = Pedestrian(id=ped.id, kind=ped.kind, name=ped.name, x=nx, y=ny, heading=ped.heading, speed=ped.speed, path=ped.path)
            blocker = next((car for car in self.cars if not car.arrived and not car.crashed and _ped_hit(car, probe, radius=0.7)), None)
            if blocker is not None:
                ped.blocked_ticks = ped.blocked_ticks + 1 if ped.blocked_by == blocker.id else 1
                ped.blocked_by = blocker.id
                # A person waits for a moving car, but walks around one that sits still.
                if blocker.speed > 0.3 or ped.blocked_ticks < 15:
                    ped.speed = 0.0
                    continue
            else:
                ped.blocked_by = None
                ped.blocked_ticks = 0
            ped.speed = ped.cruise
            ped.x, ped.y = nx, ny
            if step >= dist:
                ped.path_i += 1
                if ped.path_i >= len(ped.path) - 1:
                    self._ped_arrive(ped)

    def _ped_arrive(self, ped: Pedestrian) -> None:
        ped.moving = False
        ped.speed = 0.0
        if ped.kind == "walker" and len(ped.path) >= 2:
            ped.path = list(reversed(ped.path))
            ped.path_i = 0
            ped.x, ped.y = ped.path[0]
        elif ped.kind == "jaywalker":
            self.peds = [p for p in self.peds if p is not ped]

    # ------------------------------------------------------------------ crashes

    def _collisions(self) -> None:
        live = [c for c in self.cars if not c.arrived]
        for i, car in enumerate(live):
            for other in live[i + 1 :]:
                if car.crashed and other.crashed:
                    continue
                if abs(car.x - other.x) > 8 or abs(car.y - other.y) > 8:
                    continue
                if _boxes_overlap(car, other):
                    for c in (car, other):
                        if not c.crashed:
                            self.stats["crashes"] += 1
                            c.crash_tick = self.tick
                        c.crashed = True
                        c.speed = 0.0
                    self.notice(f"{car.name} and {other.name} crashed", "error", car.id)
            if car.crashed:
                continue
            if car.speed < 0.3:
                continue
            for ped in self.peds:
                if ped.hit:
                    continue
                if abs(ped.x - car.x) > 5 or abs(ped.y - car.y) > 5:
                    continue
                if _ped_hit(car, ped):
                    ped.hit_tick = self.tick
                    car.crash_tick = self.tick
                    car.crashed = True
                    car.hit_ped = True
                    car.speed = 0.0
                    ped.hit = True
                    ped.moving = False
                    ped.speed = 0.0
                    self.stats["ped_hits"] += 1
                    self.notice(f"{car.name} hit a {ped.name.lower()}", "error", car.id)

    # ------------------------------------------------------------------ io

    def export_log(self) -> dict:
        return {
            "seed": self.seed,
            "policies": {car.id: car.checkpoint for car in self.cars if car.named},
            "commands": [dict(entry) for entry in self.log],
            "steps": self.tick,
        }

    def reset_keeping_models(self) -> "World":
        fresh = World(seed=self.seed, fleet="town", load_policies=False, n_cars=self.target_size)
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
        hard = hard_limit(self.wet)
        cars = []
        for car in self.cars:
            frame = car.decision or {"sentence": "Waiting for the first tick.", "meta_action": "KEEP"}
            dest = None
            if car.route:
                last = NETWORK.links[car.route[-1]]
                dx, dy = last.point(car.goal_s, LANE_LAT[0] - 1.75)
                dest = [round(dx, 2), round(dy, 2)]
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
                    "arrived": car.arrived,
                    "user": car.user,
                    "named": car.named,
                    "brain": car.brain,
                    "lane": car.lane,
                    "target_lane": car.target_lane,
                    "leg": car.leg,
                    "link": car.link if car.leg == "link" else None,
                    "connector": car.connector,
                    "indicator": car.indicator,
                    "badge": car.badge,
                    "from": car.start_label,
                    "to": car.dest_label,
                    "dest": dest,
                    "decision": frame,
                }
            )
        peds = [
            {
                "id": p.id,
                "kind": p.kind,
                "name": p.name,
                "x": round(p.x, 3),
                "y": round(p.y, 3),
                "heading": round(p.heading, 4),
                "hit": p.hit,
                "moving": p.moving,
                "path": [[round(x, 2), round(y, 2)] for x, y in p.path],
            }
            for p in self.peds
        ]
        signals = []
        for nid, sig in self.signals.items():
            lamps = []
            for lid in NETWORK.in_links[nid]:
                link = NETWORK.links[lid]
                x, y = link.point(link.stop_s, 3.5)
                lamps.append({"link": lid, "axis": link.axis, "x": round(x, 2), "y": round(y, 2), "color": sig.color_for_axis(link.axis)})
            signals.append(
                {
                    "node": nid,
                    "name": NETWORK.nodes[nid].name,
                    "phase": sig.phase,
                    "label": PHASE_LABEL.get(sig.phase, sig.phase),
                    "remaining": None if sig.phase == "all_red" else round(sig.remaining * DT, 2),
                    "lamps": lamps,
                }
            )
        user_cars = [c for c in self.cars if c.user]
        return {
            "tick": self.tick,
            "time": round(self.tick * DT, 2),
            "paused": paused,
            "speed": rate,
            "seed": self.seed,
            "wet": self.wet,
            "limits": {"accel": hard, "brake": hard, "max_speed": MAX_SPEED},
            "signals": signals,
            "cars": cars,
            "pedestrians": peds,
            "log": [{"index": i, "tick": e["tick"], "time": e["time"], "label": e["label"]} for i, e in enumerate(self.log)],
            "notices": list(self.notices),
            "stats": dict(self.stats),
            "fleet": {"size": self.target_size, "total": len(self.cars), "user": len(user_cars), "max": MAX_CARS, "min": MIN_CARS},
            "last_spawned": self.last_spawned,
            "all_crashed": bool(self.cars) and all(c.crashed for c in self.cars if not c.arrived),
            "train": train
            or {"running": False, "mix": None, "step": 0, "budget": 0, "reward": None, "crash_rate": None, "ready": False, "checkpoint": None, "error": None},
        }


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
    return [(car.x + c * lx - s * ly, car.y + s * lx + c * ly) for lx, ly in ((hl, hw), (hl, -hw), (-hl, -hw), (-hl, hw))]


def _axes(pts):
    out = []
    for i in range(2):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % 4]
        out.append((-(y2 - y1), x2 - x1))
    return out


def _project(pts, axis):
    vals = [p[0] * axis[0] + p[1] * axis[1] for p in pts]
    return min(vals), max(vals)


def _ped_hit(car: Car, ped: Pedestrian, radius: float = 0.45) -> bool:
    dx, dy = ped.x - car.x, ped.y - car.y
    c, s = math.cos(car.heading), math.sin(car.heading)
    lx = dx * c + dy * s
    ly = -dx * s + dy * c
    return abs(lx) <= car.length / 2 + radius and abs(ly) <= car.width / 2 + radius
