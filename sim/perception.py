"""What a car perceives along its own path: leaders, people, and nearby actors."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from sim.geom import HALF_ANGLE, MAX_SPEED, rel_point, wrap
from sim.legacy.perception import N_PED, N_VEH, OBS_DIM
from sim.network import LANE_LAT, NETWORK

SEE_RANGE = 55.0
LEAD_LAT = 2.1
LEAD_HEADING = math.radians(55)
PED_HORIZON = 4.0
PED_LAT = 2.5
PED_CLEAR = 1.2


@dataclass
class Leader:
    kind: str
    id: str | None
    name: str
    gap: float
    speed: float
    d: float
    reason: str

    def to_json(self) -> dict:
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "gap": round(self.gap, 2),
            "speed": round(self.speed, 2),
            "reason": self.reason,
        }


def find_leader(world, car, trace, exclude: set[str] | None = None) -> Leader | None:
    """Nearest car whose body lies on the trace ahead and points the same way."""
    if not trace.xs:
        return None
    arr = trace.arr()
    best = None
    reach = trace.length + car.length
    for other in world.cars:
        if other is car or other.arrived:
            continue
        if exclude and other.id in exclude:
            continue
        dx, dy = other.x - car.x, other.y - car.y
        if dx * dx + dy * dy > (reach + 6) ** 2:
            continue
        # Behind the ego center: not a leader.
        if dx * math.cos(car.heading) + dy * math.sin(car.heading) < 0.5 and car.leg == "link":
            continue
        d2 = (arr[:, 0] - other.x) ** 2 + (arr[:, 1] - other.y) ** 2
        k = int(np.argmin(d2))
        lat = math.sqrt(float(d2[k]))
        threshold = LEAD_LAT
        # A car claiming this lane counts at once (cut-in).
        if other.leg == "link" and car.leg == "link" and other.link == car.link and other.target_lane == car.target_lane:
            threshold = 3.0
        if lat > threshold:
            continue
        if abs(wrap(other.heading - trace.hs[k])) > LEAD_HEADING:
            continue
        d = trace.ds[k]
        if d <= 0.3 and k == 0:
            continue
        gap = d - car.length / 2 - other.length / 2
        if best is None or gap < best.gap:
            reason = "stalled" if other.stalled else ("crashed" if other.crashed else "car ahead")
            best = Leader("car", other.id, other.name, gap, other.speed, d, reason)
    return best


def ped_future(ped, horizon: float = PED_HORIZON, step: float = 0.5) -> list[tuple[float, float, float]]:
    """(x, y, t) samples of where the person will be."""
    out = [(ped.x, ped.y, 0.0)]
    if ped.hit or not ped.moving or ped.path_i >= len(ped.path) - 1:
        return out
    x, y, i, t = ped.x, ped.y, ped.path_i, 0.0
    speed = max(ped.cruise, 0.3)
    while t < horizon and i < len(ped.path) - 1:
        tx, ty = ped.path[i + 1]
        dist = math.hypot(tx - x, ty - y)
        adv = speed * step
        if dist <= adv:
            x, y = tx, ty
            i += 1
            t += dist / speed
        else:
            x += (tx - x) / dist * adv
            y += (ty - y) / dist * adv
            t += step
        out.append((x, y, t))
    return out


def ped_conflict(world, car, trace) -> Leader | None:
    """First point on the trace that a person stands on or will walk through."""
    if not trace.xs:
        return None
    arr = trace.arr()
    best = None
    for ped in world.peds:
        # A walker waiting at the curb is on the sidewalk, not in the road.
        if ped.kind == "walker" and not ped.moving and not ped.hit:
            continue
        dx, dy = ped.x - car.x, ped.y - car.y
        if dx * dx + dy * dy > (trace.length + 12) ** 2:
            continue
        pts = ped_future(ped)
        p = np.asarray([(px, py) for px, py, _ in pts])
        d2 = ((arr[None, :, :] - p[:, None, :]) ** 2).sum(axis=2)
        hits = np.argwhere(d2 < PED_LAT * PED_LAT)
        if hits.size == 0:
            continue
        k = int(hits[:, 1].min())
        d = trace.ds[k]
        if d < -1:
            continue
        gap = d - car.length / 2 - PED_CLEAR
        if best is None or gap < best.gap:
            reason = "walking across" if ped.moving else "standing in the lane"
            best = Leader("ped", ped.id, ped.name, gap, 0.0, d, reason)
    return best


def nearby(world, car) -> tuple[list[dict], int]:
    seen = []
    hidden = 0
    for other in world.cars:
        if other is car or other.arrived:
            continue
        dist = math.hypot(other.x - car.x, other.y - car.y)
        if dist > SEE_RANGE:
            continue
        rx, ry = rel_point(car.x, car.y, car.heading, other.x, other.y)
        if rx < 0.2 or abs(math.atan2(ry, rx)) > HALF_ANGLE:
            hidden += 1
            continue
        rate = ((other.vx - car.vx) * (other.x - car.x) + (other.vy - car.vy) * (other.y - car.y)) / max(dist, 1e-3)
        seen.append({"kind": "car", "id": other.id, "name": other.name, "distance": round(dist, 2), "rel_speed": round(rate, 2)})
    for ped in world.peds:
        dist = math.hypot(ped.x - car.x, ped.y - car.y)
        if dist > SEE_RANGE:
            continue
        rx, ry = rel_point(car.x, car.y, car.heading, ped.x, ped.y)
        if rx < 0.2 or abs(math.atan2(ry, rx)) > HALF_ANGLE:
            hidden += 1
            continue
        seen.append({"kind": "pedestrian", "id": ped.id, "name": ped.name, "distance": round(dist, 2), "rel_speed": round(-car.speed, 2)})
    seen.sort(key=lambda row: row["distance"])
    return seen, hidden


def obs_vector(world, car, color: str | None, dist_stop: float) -> np.ndarray:
    """The training observation, rebuilt in the car's own frame so PPO weights still apply."""
    if car.leg == "link":
        link = NETWORK.links[car.link]
        lane_off = LANE_LAT.get(car.lane, 1.75) - car.lat
        head_err = wrap(link.heading - car.heading)
    else:
        lane_off, head_err = 0.0, 0.0
    vals = [car.speed / MAX_SPEED, lane_off / 3.5, head_err / math.pi, max(-1.5, min(1.5, dist_stop / 40.0))]
    fx, fy = math.cos(car.heading), math.sin(car.heading)
    lx, ly = -fy, fx
    vehs = []
    for other in world.cars:
        if other is car or other.arrived:
            continue
        rx, ry = rel_point(car.x, car.y, car.heading, other.x, other.y)
        if rx > 0.2 and math.hypot(rx, ry) <= 36.0 and abs(math.atan2(ry, rx)) <= HALF_ANGLE:
            vehs.append((math.hypot(rx, ry), other, rx, ry))
    vehs.sort(key=lambda row: row[0])
    for k in range(N_VEH):
        if k >= len(vehs):
            vals.extend([0.0] * 6)
            continue
        _, other, rx, ry = vehs[k]
        dvx, dvy = other.vx - car.vx, other.vy - car.vy
        vals.extend([1.0, rx / 36.0, ry / 36.0, (dvx * fx + dvy * fy) / MAX_SPEED, (dvx * lx + dvy * ly) / MAX_SPEED, wrap(other.heading - car.heading) / math.pi])
    peds = []
    for ped in world.peds:
        rx, ry = rel_point(car.x, car.y, car.heading, ped.x, ped.y)
        if rx > 0.2 and math.hypot(rx, ry) <= 36.0 and abs(math.atan2(ry, rx)) <= HALF_ANGLE:
            peds.append((math.hypot(rx, ry), ped, rx, ry))
    peds.sort(key=lambda row: row[0])
    for k in range(N_PED):
        if k >= len(peds):
            vals.extend([0.0] * 5)
            continue
        _, ped, rx, ry = peds[k]
        moving = ped.moving and not ped.hit
        pvx = ped.speed * math.cos(ped.heading) if moving else 0.0
        pvy = ped.speed * math.sin(ped.heading) if moving else 0.0
        vals.extend([1.0, rx / 36.0, ry / 36.0, ((pvx - car.vx) * fx + (pvy - car.vy) * fy) / MAX_SPEED, ((pvx - car.vx) * lx + (pvy - car.vy) * ly) / MAX_SPEED])
    vals.extend({"red": [1.0, 0.0, 0.0], "yellow": [0.0, 1.0, 0.0], "green": [0.0, 0.0, 1.0]}.get(color or "", [0.0, 0.0, 0.0]))
    vec = np.asarray(vals, dtype=np.float32)
    assert vec.shape == (OBS_DIM,)
    return vec
