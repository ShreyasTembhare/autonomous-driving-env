"""Forward-cone perception. Anything outside the cone is absent and counted as hidden."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from sim.actors import Car, Pedestrian
from sim.geom import (
    ACTIONS,
    HALF_ANGLE,
    HALF_LEN,
    LATERAL,
    MAX_SPEED,
    RANGE,
    STOP_LINE,
    dist_to_stop,
    forward,
    in_cone,
    lateral_of,
    left_error,
    left_normal,
    measure_s,
    rel_point,
    wrap,
)
from sim.signals import Signal

N_VEH = 4
N_PED = 3
OBS_DIM = 4 + 6 * N_VEH + 5 * N_PED + 3


@dataclass
class Sense:
    vector: np.ndarray
    groups: list[dict]
    seen: list[dict]
    hidden_count: int
    hidden_ids: list[str]
    signal_color: str | None
    signal_distance: float | None
    ped_ttc: float | None
    car_ttc: float | None
    phase_remaining: float
    gap_here: float
    gap_left: float | None
    gap_right: float | None
    dist_stop: float
    before_stop: bool
    can_left: bool
    can_right: bool
    left_reason: str | None
    right_reason: str | None


def _gap(ego: Car, lane_index: int | None, cars: list[Car], peds: list[Pedestrian]) -> float | None:
    if lane_index is None or lane_index not in LATERAL[ego.axis]:
        return None
    lat = LATERAL[ego.axis][lane_index]
    best = 80.0
    for other in cars:
        if other.id == ego.id or other.axis != ego.axis:
            continue
        if abs(lateral_of(ego.axis, other.x, other.y) - lat) > 1.5:
            continue
        ds = other.s - ego.s
        if ds <= 0.4:
            continue
        best = min(best, ds - ego.length)
    for ped in peds:
        if ped.hit:
            continue
        if abs(lateral_of(ego.axis, ped.x, ped.y) - lat) > 1.6:
            continue
        ds = measure_s(ego.axis, ped.x, ped.y) - ego.s
        if ds <= 0.3:
            continue
        best = min(best, ds - HALF_LEN)
    return best


def _ped_ttc(ego: Car, ped: Pedestrian) -> float | None:
    rx, ry = rel_point(ego.x, ego.y, ego.heading, ped.x, ped.y)
    if not in_cone(rx, ry):
        return None
    if ego.speed < 0.4:
        return None
    t = rx / ego.speed
    moving = ped.moving and not ped.hit and ped.speed > 0.05
    pvx = ped.speed * math.cos(ped.heading) if moving else 0.0
    pvy = ped.speed * math.sin(ped.heading) if moving else 0.0
    fx = ped.x + pvx * t
    fy = ped.y + pvy * t
    ex = ego.x + ego.speed * math.cos(ego.heading) * t
    ey = ego.y + ego.speed * math.sin(ego.heading) * t
    if math.hypot(fx - ex, fy - ey) < 1.7 and t < 2.2:
        return t
    if abs(ry) < 1.8 and t < 2.0:
        return t
    return None


def _lead_ttc(ego: Car, cars: list[Car]) -> float | None:
    best = None
    my_lat = lateral_of(ego.axis, ego.x, ego.y)
    for other in cars:
        if other.id == ego.id or other.axis != ego.axis:
            continue
        if abs(lateral_of(ego.axis, other.x, other.y) - my_lat) > 1.6:
            continue
        gap = (other.s - ego.s) - ego.length
        if gap <= 0.2:
            continue
        closing = ego.speed - other.speed
        if closing <= 0.4:
            continue
        t = gap / closing
        if best is None or t < best:
            best = t
    return best


def _cross_ttc(ego: Car, cars: list[Car]) -> float | None:
    # Already through the stop line: finish the crossing instead of yielding.
    if ego.s > STOP_LINE + 0.5:
        return None
    best = None
    ego_road = ego.axis in ("east", "west")
    for other in cars:
        if other.id == ego.id or other.crashed:
            continue
        other_road = other.axis in ("east", "west")
        if other_road == ego_road:
            continue
        if not (-9.0 <= other.s <= 12.0):
            continue
        if ego.s < -28:
            continue
        # Someone is in the box. Time until we would enter.
        t = max(0.2, (-STOP_LINE - ego.s) / max(ego.speed, 1.0))
        if best is None or t < best:
            best = t
    return best


CAR_TTC_HORIZON = 1.5


def _range_rate(ego: Car, px: float, py: float, svx: float, svy: float) -> tuple[float, float]:
    dx, dy = px - ego.x, py - ego.y
    dist = math.hypot(dx, dy)
    if dist < 1e-4:
        return 0.0, 0.0
    rate = ((svx - ego.vx) * dx + (svy - ego.vy) * dy) / dist
    return dist, rate


def sense(world, ego: Car) -> Sense:
    cars: list[Car] = world.cars
    peds: list[Pedestrian] = world.peds
    signal: Signal = world.signal

    dist_stop = dist_to_stop(ego.s)
    before = dist_stop > 0.05
    can_left = ego.lane_index < 1
    can_right = ego.lane_index > 0
    left_reason = None if can_left else "Already in the leftmost lane"
    right_reason = None if can_right else "Already in the rightmost lane"

    seen: list[dict] = []
    hidden_ids: list[str] = []

    veh_rows = []
    for other in cars:
        if other.id == ego.id:
            continue
        rx, ry = rel_point(ego.x, ego.y, ego.heading, other.x, other.y)
        dist, rate = _range_rate(ego, other.x, other.y, other.vx, other.vy)
        if in_cone(rx, ry):
            seen.append(
                {
                    "kind": "car",
                    "id": other.id,
                    "name": other.name,
                    "distance": dist,
                    "rel_speed": rate,
                    "rx": rx,
                    "ry": ry,
                    "heading": other.heading,
                    "vx": other.vx,
                    "vy": other.vy,
                }
            )
            veh_rows.append(other)
        else:
            hidden_ids.append(other.id)

    ped_rows = []
    ped_ttc = None
    for ped in peds:
        rx, ry = rel_point(ego.x, ego.y, ego.heading, ped.x, ped.y)
        moving = ped.moving and not ped.hit
        pvx = ped.speed * math.cos(ped.heading) if moving else 0.0
        pvy = ped.speed * math.sin(ped.heading) if moving else 0.0
        dist, rate = _range_rate(ego, ped.x, ped.y, pvx, pvy)
        ttc = None if ped.hit else _ped_ttc(ego, ped)
        if ttc is not None and (ped_ttc is None or ttc < ped_ttc):
            ped_ttc = ttc
        if in_cone(rx, ry):
            seen.append(
                {
                    "kind": "pedestrian",
                    "id": ped.id,
                    "name": ped.name,
                    "distance": dist,
                    "rel_speed": rate,
                    "rx": rx,
                    "ry": ry,
                    "vx": pvx,
                    "vy": pvy,
                }
            )
            ped_rows.append(ped)
        else:
            hidden_ids.append(ped.id)

    sx, sy = SIGNAL_POS_OF(ego.axis)
    srx, sry = rel_point(ego.x, ego.y, ego.heading, sx, sy)
    # The head sits between the two lanes, so in the last few meters the bearing
    # can leave a narrow cone even though the driver is still looking at that light.
    # Keep it visible until the bumper reaches the line.
    center_before = ego.s < STOP_LINE + 0.4
    signal_seen = in_cone(srx, sry) or (center_before and -1.5 < srx < 16.0 and abs(sry) < 5.5)
    color = signal.color_for_axis(ego.axis) if signal_seen else None
    sig_dist = math.hypot(srx, sry)
    if signal_seen:
        seen.append(
            {
                "kind": "signal",
                "id": f"signal-{ego.axis}",
                "name": f"{ego.axis.title()} signal",
                "distance": sig_dist,
                "rel_speed": -ego.speed,
                "color": color,
            }
        )
    else:
        hidden_ids.append(f"signal-{ego.axis}")

    seen.sort(key=lambda row: row["distance"])
    veh_rows.sort(key=lambda other: math.hypot(other.x - ego.x, other.y - ego.y))
    ped_rows.sort(key=lambda ped: math.hypot(ped.x - ego.x, ped.y - ego.y))

    lead = _lead_ttc(ego, cars)
    cross = _cross_ttc(ego, cars)
    car_ttc = lead
    if cross is not None and (car_ttc is None or cross < car_ttc):
        car_ttc = cross

    vector, groups = _vector(ego, veh_rows, ped_rows, color, dist_stop, before)
    return Sense(
        vector=vector,
        groups=groups,
        seen=_public_seen(seen),
        hidden_count=len(hidden_ids),
        hidden_ids=hidden_ids,
        signal_color=color,
        signal_distance=sig_dist if signal_seen else None,
        ped_ttc=ped_ttc,
        car_ttc=car_ttc,
        phase_remaining=signal.remaining * 0.1,
        gap_here=_gap(ego, ego.lane_index, cars, peds) or 80.0,
        gap_left=_gap(ego, ego.lane_index + 1, cars, peds) if can_left else None,
        gap_right=_gap(ego, ego.lane_index - 1, cars, peds) if can_right else None,
        dist_stop=dist_stop,
        before_stop=before,
        can_left=can_left,
        can_right=can_right,
        left_reason=left_reason,
        right_reason=right_reason,
    )


def SIGNAL_POS_OF(axis: str) -> tuple[float, float]:
    from sim.geom import SIGNAL_POS

    return SIGNAL_POS[axis]


def _public_seen(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        item = {
            "kind": row["kind"],
            "id": row["id"],
            "name": row["name"],
            "distance": round(float(row["distance"]), 2),
            "rel_speed": round(float(row["rel_speed"]), 2),
        }
        if row["kind"] == "signal":
            item["color"] = row["color"]
        out.append(item)
    return out


def _vector(ego: Car, vehs: list[Car], peds: list[Pedestrian], color: str | None, dist_stop: float, before: bool):
    lane_off = left_error(ego.axis, ego.x, ego.y, LATERAL[ego.axis][ego.lane_index])
    head_err = wrap(HEADING_OF(ego.axis) - ego.heading)
    ego_vals = [
        ego.speed / MAX_SPEED,
        lane_off / 3.5,
        head_err / math.pi,
        max(-1.5, min(1.5, dist_stop / 40.0)),
    ]
    groups = [
        {
            "name": "Ego",
            "blocks": [
                {
                    "title": ego.name,
                    "rows": [
                        {"label": "Speed", "text": f"{ego.speed:.1f} m/s", "net": round(ego_vals[0], 3)},
                        {
                            "label": "Lane offset",
                            "text": _offset_text(lane_off),
                            "net": round(ego_vals[1], 3),
                        },
                        {
                            "label": "Heading error",
                            "text": f"{math.degrees(head_err):.0f}°",
                            "net": round(ego_vals[2], 3),
                        },
                        {
                            "label": "Distance to stop line",
                            "text": "past the line" if not before else f"{dist_stop:.1f} m",
                            "net": round(ego_vals[3], 3),
                        },
                    ],
                }
            ],
        }
    ]

    veh_feats: list[float] = []
    veh_blocks = []
    fx, fy = forward(ego.heading)
    lx, ly = left_normal(ego.heading)
    for index in range(N_VEH):
        if index >= len(vehs):
            veh_feats.extend([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
            veh_blocks.append({"title": "Empty slot", "rows": [{"label": "Presence", "text": "none", "net": 0.0}]})
            continue
        other = vehs[index]
        rx, ry = rel_point(ego.x, ego.y, ego.heading, other.x, other.y)
        dvx, dvy = other.vx - ego.vx, other.vy - ego.vy
        v_fwd = dvx * fx + dvy * fy
        v_left = dvx * lx + dvy * ly
        h_rel = wrap(other.heading - ego.heading)
        feats = [
            1.0,
            rx / RANGE,
            ry / RANGE,
            v_fwd / MAX_SPEED,
            v_left / MAX_SPEED,
            h_rel / math.pi,
        ]
        veh_feats.extend(feats)
        veh_blocks.append(
            {
                "title": other.name,
                "rows": [
                    {"label": "Presence", "text": "in view", "net": 1.0},
                    {"label": "Relative forward", "text": f"{rx:.1f} m", "net": round(feats[1], 3)},
                    {"label": "Relative lateral", "text": f"{ry:.1f} m", "net": round(feats[2], 3)},
                    {"label": "Relative vx", "text": f"{v_fwd:.1f} m/s", "net": round(feats[3], 3)},
                    {"label": "Relative vy", "text": f"{v_left:.1f} m/s", "net": round(feats[4], 3)},
                    {"label": "Relative heading", "text": f"{math.degrees(h_rel):.0f}°", "net": round(feats[5], 3)},
                ],
            }
        )
    groups.append({"name": "Nearest vehicles", "blocks": veh_blocks})

    ped_feats: list[float] = []
    ped_blocks = []
    for index in range(N_PED):
        if index >= len(peds):
            ped_feats.extend([0.0, 0.0, 0.0, 0.0, 0.0])
            ped_blocks.append({"title": "Empty slot", "rows": [{"label": "Presence", "text": "none", "net": 0.0}]})
            continue
        ped = peds[index]
        rx, ry = rel_point(ego.x, ego.y, ego.heading, ped.x, ped.y)
        moving = ped.moving and not ped.hit
        pvx = ped.speed * math.cos(ped.heading) if moving else 0.0
        pvy = ped.speed * math.sin(ped.heading) if moving else 0.0
        v_fwd = (pvx - ego.vx) * fx + (pvy - ego.vy) * fy
        v_left = (pvx - ego.vx) * lx + (pvy - ego.vy) * ly
        feats = [1.0, rx / RANGE, ry / RANGE, v_fwd / MAX_SPEED, v_left / MAX_SPEED]
        ped_feats.extend(feats)
        ped_blocks.append(
            {
                "title": ped.name,
                "rows": [
                    {"label": "Presence", "text": "in view", "net": 1.0},
                    {"label": "Relative forward", "text": f"{rx:.1f} m", "net": round(feats[1], 3)},
                    {"label": "Relative lateral", "text": f"{ry:.1f} m", "net": round(feats[2], 3)},
                    {"label": "Relative vx", "text": f"{v_fwd:.1f} m/s", "net": round(feats[3], 3)},
                    {"label": "Relative vy", "text": f"{v_left:.1f} m/s", "net": round(feats[4], 3)},
                ],
            }
        )
    groups.append({"name": "Nearest pedestrian", "blocks": ped_blocks})

    one_hot = {"red": [1.0, 0.0, 0.0], "yellow": [0.0, 1.0, 0.0], "green": [0.0, 0.0, 1.0]}.get(
        color or "", [0.0, 0.0, 0.0]
    )
    groups.append(
        {
            "name": "Signal",
            "blocks": [
                {
                    "title": "Not in view" if color is None else color,
                    "rows": [
                        {"label": "Red", "text": "yes" if color == "red" else "no", "net": one_hot[0]},
                        {"label": "Yellow", "text": "yes" if color == "yellow" else "no", "net": one_hot[1]},
                        {"label": "Green", "text": "yes" if color == "green" else "no", "net": one_hot[2]},
                    ],
                }
            ],
        }
    )
    vector = np.asarray(ego_vals + veh_feats + ped_feats + one_hot, dtype=np.float32)
    assert vector.shape == (OBS_DIM,), vector.shape
    return vector, groups


def HEADING_OF(axis: str) -> float:
    from sim.geom import HEADING

    return HEADING[axis]


def _offset_text(meters: float) -> str:
    if abs(meters) < 0.15:
        return "centered"
    side = "left" if meters > 0 else "right"
    return f"{abs(meters):.1f} m {side}"


# Imported names used by the decision stack's action list stay available here
# so a reader can see the observation lines up with the five meta-actions.
_ = ACTIONS
