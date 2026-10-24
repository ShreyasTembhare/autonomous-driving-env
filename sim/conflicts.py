"""Conflict points inside each box and the right-of-way rules that use them.

Two connectors conflict when their centerlines come within CONFLICT_DIST.
For each pair the table stores the arc length on each connector at the
closest approach. A car yields by placing a virtual stopped leader before
that point (inside the box for a permissive left) or at the stop line.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from sim.network import NETWORK, OPPOSITE, Network

CONFLICT_DIST = 2.6
YIELD_MARGIN = 3.2
DEADLOCK_WAIT = 8.0


def _table(net: Network) -> dict[str, dict[str, tuple[float, float]]]:
    by_node: dict[str, list] = {}
    for conn in net.connectors.values():
        by_node.setdefault(conn.node, []).append(conn)
    table: dict[str, dict[str, tuple[float, float]]] = {}
    for conns in by_node.values():
        for a in conns:
            for b in conns:
                if a.id == b.id or a.link_in == b.link_in:
                    continue
                best = None
                for ia, (ax, ay) in enumerate(a.points):
                    for ib, (bx, by) in enumerate(b.points):
                        d = math.hypot(ax - bx, ay - by)
                        if best is None or d < best[0]:
                            best = (d, a.cum[ia], b.cum[ib])
                if best and best[0] < CONFLICT_DIST:
                    table.setdefault(a.id, {})[b.id] = (best[1], best[2])
    return table


CONFLICTS = _table(NETWORK)


@dataclass
class Yield:
    other: str
    name: str
    reason: str
    d_point: float
    eta_self: float | None
    eta_other: float | None
    gap_accept: float | None
    verdict: str
    rule: str

    def to_json(self) -> dict:
        return {
            "with": self.other,
            "name": self.name,
            "reason": self.reason,
            "d_point": round(self.d_point, 2),
            "eta_self": None if self.eta_self is None or math.isinf(self.eta_self) else round(self.eta_self, 2),
            "eta_other": None if self.eta_other is None or math.isinf(self.eta_other) else round(self.eta_other, 2),
            "gap_accept": self.gap_accept,
            "verdict": self.verdict,
            "rule": self.rule,
        }


def _plan_of(world, car):
    """Connector the car is on or about to drive, and its distance along it."""
    tr = car.trace
    if tr is None or tr.connector is None:
        return None, None, False
    if car.leg == "connector":
        return tr.connector, car.t, True
    return tr.connector, -(tr.conn_d or 0.0), False


def _signal_color(world, car) -> str | None:
    if car.leg != "link":
        return None
    link = NETWORK.links[car.link]
    if not link.signalized_end:
        return None
    return world.signals[link.to].color_for_axis(link.axis)


def evaluate(world, car, trace, style, hard: float) -> tuple[list[Yield], list[Yield]]:
    """Return (binding yields, all checked conflicts) for the car's planned connector."""
    conn_id = trace.connector
    if conn_id is None or conn_id not in CONFLICTS:
        return [], []
    conn = NETWORK.connectors[conn_id]
    in_box = car.leg == "connector"
    my_t = car.t if in_box else -(trace.conn_d or 0.0)
    rows: list[Yield] = []
    binding: list[Yield] = []
    my_wait = car.wait
    for other in world.cars:
        if other is car or other.arrived or other.trace is None:
            continue
        o_conn, o_t, o_in_box = _plan_of(world, other)
        if o_conn is None or o_conn not in CONFLICTS[conn_id]:
            continue
        if not o_in_box and (other.trace.conn_d or 99.0) > 45.0:
            continue
        te, to = CONFLICTS[conn_id][o_conn]
        de = te - my_t
        do = to - o_t
        clear = other.length / 2 + 1.5
        if do < -clear or de < -(car.length / 2 + 0.5):
            continue
        other_conn = NETWORK.connectors[o_conn]
        eta_self = _eta(car, max(de, 0.0), world)
        eta_other = _eta(other, max(do, 0.0), world)
        verdict, rule, gap = _priority(world, car, conn, other, other_conn, in_box, o_in_box, de, do, eta_self, eta_other, style, hard, my_wait)
        row = Yield(other.id, other.name, other_conn.maneuver, de, eta_self, eta_other, gap, verdict, rule)
        rows.append(row)
        if verdict == "yield":
            binding.append(row)
    return binding, rows


def _eta(car, d: float, world) -> float:
    """Time to cover d from the current speed, accelerating at the driver's a_max."""
    if car.stalled or car.crashed:
        return math.inf
    if _signal_color(world, car) == "red":
        return d / max(car.speed, 0.5)
    from sim.idm import style_for

    a = style_for(car.brain, world.wet).a_max
    v = car.speed
    return (-v + math.sqrt(v * v + 2 * a * d)) / a


def _committed(car, d_to_point: float, hard: float, in_box: bool) -> bool:
    if not in_box:
        return False
    stop = car.speed * car.speed / (2 * max(hard, 0.5))
    return d_to_point < max(1.0, stop) or d_to_point < car.length / 2


def _priority(world, car, conn, other, other_conn, in_box, o_in_box, de, do, eta_self, eta_other, style, hard, my_wait):
    # Nobody drives into a conflict point another car's body is on, whoever has priority.
    if -(other.length / 2 + 1.5) < do < other.length / 2 + 0.5 and de > car.length / 2 + 0.3:
        return "yield", f"{other.name} is on the conflict point now.", None
    if _committed(car, de, hard, in_box):
        return "go", "Already committed to the box; finishing the move.", None
    if _committed(other, do, hard, o_in_box):
        return "yield", f"{other.name} is already crossing the conflict point.", None
    o_color = _signal_color(world, other)
    if not o_in_box and o_color == "red" and other.trace.stop_d is not None:
        stop = other.speed * other.speed / (2 * max(hard, 0.5))
        if other.trace.stop_d - other.length / 2 > stop - 0.5:
            return "go", f"{other.name} has a red and can stop.", None
    if other.stalled or other.crashed:
        if do < other.length / 2 + 0.5 and do > -(other.length / 2 + 1.5):
            return "yield", f"{other.name} is stopped across the path.", None
        return "go", f"{other.name} is stopped clear of the path.", None
    if _deadlock_turn(world, car, other, my_wait):
        if do > other.length / 2 + 1.0:
            return "go", "Deadlock rule: this car has waited longest, so it goes first.", None
    opposing = other_conn.link_in == NETWORK.links[conn.link_in].reverse or (
        NETWORK.links[other_conn.link_in].axis == OPPOSITE[NETWORK.links[conn.link_in].axis]
    )
    if conn.maneuver == "left" and opposing and other_conn.maneuver in ("straight", "right"):
        gap = style.gap_accept
        if eta_other < gap:
            return "yield", f"Permissive left: oncoming {other.name} arrives in {eta_other:.1f} s, under the {gap:.1f} s gap.", gap
        return "go", f"Permissive left: oncoming gap {eta_other:.1f} s is at least {gap:.1f} s.", gap
    if other_conn.maneuver == "left" and opposing and conn.maneuver in ("straight", "right"):
        return "go", f"{other.name} turns left across this lane and must yield.", None
    if o_in_box and not in_box:
        return "yield", f"{other.name} is in the box; cross traffic waits for it.", None
    if in_box and not o_in_box:
        return "go", "This car is in the box; the other car waits.", None
    if eta_self < eta_other - 0.3:
        return "go", "Reaches the conflict point first.", None
    if eta_other < eta_self - 0.3:
        return "yield", f"{other.name} reaches the conflict point first.", None
    if car.id < other.id:
        return "go", "Tie broken by order.", None
    return "yield", "Tie broken by order.", None


def _deadlock_turn(world, car, other, my_wait: float) -> bool:
    if my_wait < DEADLOCK_WAIT or other.speed > 0.3:
        return False
    node = car.trace.node if car.trace else None
    longest = max(
        (c.wait for c in world.cars if c.trace is not None and c.trace.node == node and c.speed < 0.3 and not c.stalled),
        default=0.0,
    )
    return my_wait >= longest - 1e-6
