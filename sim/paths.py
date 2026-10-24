"""Path traces: where a car will drive along its route over the next stretch.

A trace is sampled every meter from the car's center. Lane changes blend the
lateral offset with a smoothstep over a speed-dependent distance. The trace
also records where the stop line, the turn connector, and the goal fall.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from sim.network import LANE_LAT, NETWORK, Network
from sim.routes import required_lane

STEP = 1.0


@dataclass
class Trace:
    xs: list[float] = field(default_factory=list)
    ys: list[float] = field(default_factory=list)
    hs: list[float] = field(default_factory=list)
    ds: list[float] = field(default_factory=list)
    lane_end: int | None = None
    stop_d: float | None = None
    stop_link: str | None = None
    node: str | None = None
    connector: str | None = None
    conn_d: float | None = None
    exit_d: float | None = None
    out_link: str | None = None
    end_d: float | None = None
    wrong_lane: bool = False
    _arr: np.ndarray | None = None

    def add(self, x: float, y: float, h: float) -> None:
        if self.xs:
            d = self.ds[-1] + math.hypot(x - self.xs[-1], y - self.ys[-1])
        else:
            d = 0.0
        self.xs.append(x)
        self.ys.append(y)
        self.hs.append(h)
        self.ds.append(d)

    @property
    def length(self) -> float:
        return self.ds[-1] if self.ds else 0.0

    def arr(self) -> np.ndarray:
        if self._arr is None:
            self._arr = np.column_stack([self.xs, self.ys]) if self.xs else np.zeros((0, 2))
        return self._arr

    def pose_at(self, d: float) -> tuple[float, float, float]:
        if not self.xs:
            return 0.0, 0.0, 0.0
        if d <= 0:
            return self.xs[0], self.ys[0], self.hs[0]
        if d >= self.ds[-1]:
            # Extrapolate straight past the end so a rollout never freezes.
            extra = d - self.ds[-1]
            h = self.hs[-1]
            return self.xs[-1] + math.cos(h) * extra, self.ys[-1] + math.sin(h) * extra, h
        lo, hi = 0, len(self.ds) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.ds[mid] <= d:
                lo = mid
            else:
                hi = mid
        seg = self.ds[hi] - self.ds[lo] or 1e-6
        f = (d - self.ds[lo]) / seg
        return (
            self.xs[lo] + (self.xs[hi] - self.xs[lo]) * f,
            self.ys[lo] + (self.ys[hi] - self.ys[lo]) * f,
            self.hs[lo] if f < 0.5 else self.hs[hi],
        )

    def points(self, every: int = 3) -> list[list[float]]:
        out = [[round(self.xs[i], 2), round(self.ys[i], 2)] for i in range(0, len(self.xs), every)]
        if self.xs and (len(self.xs) - 1) % every:
            out.append([round(self.xs[-1], 2), round(self.ys[-1], 2)])
        return out


def lane_change_distance(speed: float) -> float:
    return max(12.0, 2.2 * speed + 6.0)


def _smooth(f: float) -> float:
    f = max(0.0, min(1.0, f))
    return f * f * (3 - 2 * f)


def build(car, target_lane: int, max_d: float = 60.0, net: Network = NETWORK) -> Trace:
    tr = Trace()
    route = car.route
    i = car.route_i
    if car.leg == "connector" and car.connector:
        conn = net.connectors[car.connector]
        tr.node = conn.node
        tr.connector = conn.id
        tr.conn_d = -car.t
        t = car.t
        while t < conn.length:
            x, y, h = conn.at(t)
            tr.add(x, y, h)
            t += STEP
        x, y, h = conn.at(conn.length)
        tr.add(x, y, h)
        tr.exit_d = tr.length
        tr.out_link = conn.link_out
        i += 1
        _follow(tr, route, i, net.links[conn.link_out].start_s, LANE_LAT[conn.lane_out], conn.lane_out, max_d, car, net, first=False)
        return tr
    lat_t = LANE_LAT.get(target_lane, LANE_LAT[0])
    _follow(tr, route, i, car.s, car.lat, target_lane, max_d, car, net, first=True, lat_target=lat_t)
    return tr


def _follow(tr: Trace, route, i, s0, lat0, lane, max_d, car, net: Network, first: bool, lat_target=None) -> None:
    lat_target = LANE_LAT.get(lane, lat0) if lat_target is None else lat_target
    blend = lane_change_distance(car.speed)
    while i < len(route) and tr.length < max_d:
        link = net.links[route[i]]
        last = i == len(route) - 1
        s_end = car.goal_s if last else link.stop_s
        s = s0
        while True:
            f = (s - s0) / blend if first else 1.0
            lat = lat0 + (lat_target - lat0) * _smooth(f)
            x, y = link.point(s, lat)
            # Heading follows the lateral slope while blending.
            dlat = 0.0
            if first and 0 < f < 1:
                dlat = (lat_target - lat0) * 6 * f * (1 - f) / blend
            h = link.heading - math.atan(dlat)
            tr.add(x, y, h)
            if s >= s_end or tr.length >= max_d:
                break
            s = min(s_end, s + STEP)
        if last:
            if s >= s_end:
                tr.end_d = tr.length
            return
        if tr.length >= max_d and s < s_end:
            return
        need = required_lane(route, i, net)
        lane_end = lane if lane in (0, 1) else 1
        if first:
            tr.lane_end = lane_end
            tr.stop_d = tr.length
            tr.stop_link = link.id
            tr.node = link.to
        conn = net.connector_for(link.id, route[i + 1], lane_end)
        if conn is None or (need is not None and need != lane_end):
            if first:
                tr.wrong_lane = True
            return
        if first:
            tr.connector = conn.id
            tr.conn_d = tr.length
        t = STEP
        while t < conn.length:
            x, y, h = conn.at(t)
            tr.add(x, y, h)
            t += STEP
        x, y, h = conn.at(conn.length)
        tr.add(x, y, h)
        if first:
            tr.exit_d = tr.length
            tr.out_link = conn.link_out
        first = False
        i += 1
        lane = conn.lane_out
        s0 = net.links[conn.link_out].start_s
        lat0 = LANE_LAT[lane]
        lat_target = lat0
        if tr.length >= max_d:
            return
