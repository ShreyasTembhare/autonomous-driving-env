"""Routes from A to B: A* over directed links, with turn and congestion costs.

A route is a list of link ids. Between two consecutive links the car drives
the turn connector of the shared intersection. The last link ends at goal_s.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

from sim.network import LANE_LAT, NETWORK, Network, maneuver_between

FREE_SPEED = 12.0
TURN_PENALTY = {"straight": 0.0, "left": 6.0, "right": 3.0}
QUEUE_COST = 2.0
STALL_COST = 15.0
REQUIRED_LANE = {"left": 1, "right": 0, "straight": None}
MANEUVER_TEXT = {"straight": "straight", "left": "left turn", "right": "right turn"}


@dataclass
class Place:
    link: str
    s: float
    lane: int | None
    label: str


@dataclass
class RouteResult:
    ok: bool
    links: list[str]
    goal_s: float
    error: str | None = None
    cost: float = 0.0
    terms: list[dict] | None = None


def maneuvers(route: list[str], net: Network = NETWORK) -> list[str]:
    out = []
    for a, b in zip(route, route[1:]):
        out.append(maneuver_between(net.links[a].axis, net.links[b].axis) or "straight")
    return out


def required_lane(route: list[str], i: int, net: Network = NETWORK) -> int | None:
    if i + 1 >= len(route):
        return None
    man = maneuver_between(net.links[route[i]].axis, net.links[route[i + 1]].axis)
    return REQUIRED_LANE.get(man or "straight")


def link_load(world, net: Network = NETWORK) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    """Queue count, stall count, and stalled lanes per link from live traffic."""
    queue: dict[str, int] = {}
    stalls: dict[str, int] = {}
    lanes: dict[str, set] = {}
    if world is None:
        return queue, stalls, {}
    for car in world.cars:
        if car.arrived:
            continue
        links = []
        if car.leg == "link":
            links.append(car.link)
        elif car.connector:
            conn = net.connectors[car.connector]
            links.extend([conn.link_in, conn.link_out])
        for lid in links:
            if car.speed < 1.0:
                queue[lid] = queue.get(lid, 0) + 1
            if car.stalled or car.crashed:
                stalls[lid] = stalls.get(lid, 0) + 1
                lanes.setdefault(lid, set()).add(car.lane)
    blocked = {lid: len(v) for lid, v in lanes.items()}
    return queue, stalls, blocked


def link_cost(link_id: str, prev: str | None, queue, stalls, blocked, net: Network = NETWORK) -> float:
    link = net.links[link_id]
    cost = (link.stop_s - link.start_s) / FREE_SPEED
    if prev is not None:
        man = maneuver_between(net.links[prev].axis, link.axis) or "straight"
        cost += TURN_PENALTY[man]
    cost += QUEUE_COST * queue.get(link_id, 0)
    cost += STALL_COST * stalls.get(link_id, 0)
    if blocked.get(link_id, 0) >= 2:
        cost = math.inf
    return cost


def plan(
    start_link: str,
    start_s: float,
    goal_link: str,
    goal_s: float,
    world=None,
    allowed_first: set[str] | None = None,
    avoid: set[str] | None = None,
    net: Network = NETWORK,
) -> RouteResult:
    """A* over links. The start link is always the first entry of the route."""
    if start_link == goal_link and goal_s > start_s + 1.0:
        return RouteResult(True, [start_link], goal_s)
    queue, stalls, blocked = link_load(world, net)
    avoid = avoid or set()
    goal = net.links[goal_link]
    gx, gy = goal.point(goal.start_s, 0.0)

    def h(lid: str) -> float:
        link = net.links[lid]
        x, y = link.point(link.stop_s, 0.0)
        return math.hypot(gx - x, gy - y) / FREE_SPEED

    counter = 0
    frontier: list[tuple[float, int, str, tuple[str, ...]]] = []
    best: dict[str, float] = {}
    for man, nxt in net.successors(start_link):
        if allowed_first is not None and nxt not in allowed_first:
            continue
        if nxt in avoid:
            continue
        c = link_cost(nxt, start_link, queue, stalls, blocked, net)
        if math.isinf(c) and nxt != goal_link:
            continue
        counter += 1
        heapq.heappush(frontier, (c + h(nxt), counter, nxt, (start_link, nxt)))
        best[nxt] = min(best.get(nxt, math.inf), c)
    g_of = dict(best)
    while frontier:
        f, _, lid, path = heapq.heappop(frontier)
        g = f - h(lid)
        if lid == goal_link:
            return RouteResult(True, list(path), goal_s, cost=g)
        if g > g_of.get(lid, math.inf) + 1e-9:
            continue
        for man, nxt in net.successors(lid):
            if nxt in avoid:
                continue
            c = link_cost(nxt, lid, queue, stalls, blocked, net)
            if math.isinf(c) and nxt != goal_link:
                continue
            ng = g + c
            if ng < g_of.get(nxt, math.inf) - 1e-9 and len(path) < 16:
                g_of[nxt] = ng
                counter += 1
                heapq.heappush(frontier, (ng + h(nxt), counter, nxt, path + (nxt,)))
    reason = "No route reaches that destination."
    if any(v >= 2 for v in blocked.values()):
        names = [car.name for car in getattr(world, "cars", []) if car.stalled]
        if names:
            reason = f"No route: stalled {', '.join(names)} block every way through."
    return RouteResult(False, [], goal_s, error=reason)


def route_length(route: list[str], start_s: float, goal_s: float, net: Network = NETWORK) -> float:
    if not route:
        return 0.0
    if len(route) == 1:
        return max(0.0, goal_s - start_s)
    total = net.links[route[0]].stop_s - start_s
    for i, (a, b) in enumerate(zip(route, route[1:])):
        lane = REQUIRED_LANE.get(maneuver_between(net.links[a].axis, net.links[b].axis) or "straight")
        conn = net.connector_for(a, b, 0 if lane is None else lane)
        total += conn.length if conn else 22.0
        link_b = net.links[b]
        end = goal_s if i + 2 == len(route) else link_b.stop_s
        total += end - link_b.start_s
    return max(0.0, total)


def route_points(route: list[str], start_s: float, goal_s: float, lane: int = 0, step: float = 6.0, net: Network = NETWORK):
    """Polyline of the route along lane centers, for drawing and previews."""
    pts: list[tuple[float, float]] = []
    cur_lane = lane
    for i, lid in enumerate(route):
        link = net.links[lid]
        s0 = start_s if i == 0 else link.start_s
        s1 = goal_s if i == len(route) - 1 else link.stop_s
        need = required_lane(route, i, net)
        lane_end = cur_lane if need is None else need
        n = max(1, int((s1 - s0) / step))
        for k in range(n + 1):
            f = k / n
            # Move to the required lane over the middle of the link.
            blend = min(1.0, max(0.0, (f - 0.3) / 0.4))
            lat = LANE_LAT[cur_lane] + (LANE_LAT[lane_end] - LANE_LAT[cur_lane]) * blend
            pts.append(link.point(s0 + (s1 - s0) * f, lat))
        if i + 1 < len(route):
            conn = net.connector_for(lid, route[i + 1], lane_end)
            if conn:
                pts.extend(conn.points[1:-1:3])
                cur_lane = conn.lane_out
    return [[round(x, 1), round(y, 1)] for x, y in pts]


def describe(route: list[str], net: Network = NETWORK) -> str:
    mans = [m for m in maneuvers(route, net)]
    turns = [MANEUVER_TEXT[m] for m in mans if m != "straight"]
    if not turns:
        return "straight through"
    return ", then ".join(turns)


def resolve_place(spec, kind: str, world=None, net: Network = NETWORK) -> tuple[Place | None, str | None]:
    """Turn a start or destination spec into a lane position.

    A spec is a stub id ("W1"), "stub:W1", a dict {stub}, or a point {x, y}.
    """
    stub = None
    point = None
    if isinstance(spec, str):
        if spec.startswith("pt:"):
            try:
                xs, ys = spec[3:].split(",")
                point = (float(xs), float(ys))
            except ValueError:
                return None, "Could not read that map point."
        else:
            stub = spec.split(":", 1)[1] if spec.startswith("stub:") else spec
    elif isinstance(spec, dict):
        if spec.get("stub"):
            stub = str(spec["stub"])
        elif "x" in spec and "y" in spec:
            point = (float(spec["x"]), float(spec["y"]))
    if stub is not None:
        node = net.nodes.get(stub)
        if node is None or node.kind != "stub":
            return None, f"Unknown place {stub}."
        if kind == "start":
            link = net.entry_link(stub)
            return Place(link.id, 2.0, None, node.name), None
        link = net.exit_link(stub)
        return Place(link.id, link.length - 1.0, None, node.name), None
    if point is None:
        return None, "Pick a place on the map."
    snapped = net.snap(*point)
    if snapped is None:
        return None, "That point is not on a road. Click a lane."
    link, s, lane = snapped
    label = place_label(link.id, s, net)
    if kind == "start":
        # Starting on a segment puts the car 30 m before the next stop line.
        s = max(link.start_s + 1.0, min(s, link.stop_s - 30.0)) if link.signalized_end else s
    else:
        s = max(link.start_s + 4.0, min(s, link.stop_s - 2.0)) if link.signalized_end else min(s, link.length - 1.0)
    return Place(link.id, s, lane, label), None


def place_label(link_id: str, s: float, net: Network = NETWORK) -> str:
    link = net.links[link_id]
    a, b = net.nodes[link.frm], net.nodes[link.to]
    return f"{a.name} to {b.name} road"
