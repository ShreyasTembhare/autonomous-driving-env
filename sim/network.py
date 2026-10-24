"""The road network: a 2x2 grid of signalized intersections with boundary stubs.

Every road has two lanes per direction. A directed link runs from one node's
center to the next. Its longitudinal coordinate s is 0 at the from-node and
`length` at the to-node. Lateral offsets are measured to the right of the
centerline: lane 0 is the outer (right) lane, lane 1 the inner lane, and
lane -1 the oncoming inner lane, used only for a last-resort pass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

SPACING = 120.0
EDGE = 180.0
STOP_BACK = 11.0
BOX = 7.0
ROAD_HALF = 7.0
CROSSWALK = 8.6
LANE_W = 3.5
LANE_LAT = {0: 5.25, 1: 1.75, -1: -1.75}
SOLID_ZONE = 12.0

DIRS = {"east": (1.0, 0.0), "west": (-1.0, 0.0), "north": (0.0, 1.0), "south": (0.0, -1.0)}
LEFT_OF = {"east": "north", "north": "west", "west": "south", "south": "east"}
RIGHT_OF = {v: k for k, v in LEFT_OF.items()}
OPPOSITE = {"east": "west", "west": "east", "north": "south", "south": "north"}

INTERSECTIONS = {
    "NW": (-60.0, 60.0),
    "NE": (60.0, 60.0),
    "SW": (-60.0, -60.0),
    "SE": (60.0, -60.0),
}
INTERSECTION_NAMES = {"NW": "Northwest", "NE": "Northeast", "SW": "Southwest", "SE": "Southeast"}
STUBS = {
    "W1": ("West 1", (-EDGE, 60.0)),
    "W2": ("West 2", (-EDGE, -60.0)),
    "E1": ("East 1", (EDGE, 60.0)),
    "E2": ("East 2", (EDGE, -60.0)),
    "N1": ("North 1", (-60.0, EDGE)),
    "N2": ("North 2", (60.0, EDGE)),
    "S1": ("South 1", (-60.0, -EDGE)),
    "S2": ("South 2", (60.0, -EDGE)),
}
ROADS = [
    ["W1", "NW", "NE", "E1"],
    ["W2", "SW", "SE", "E2"],
    ["S1", "SW", "NW", "N1"],
    ["S2", "SE", "NE", "N2"],
]

# Signal offsets in ticks, so a corridor sees a rough green wave.
SIGNAL_OFFSET = {"NW": 0, "NE": 40, "SW": 80, "SE": 120}


@dataclass
class Node:
    id: str
    kind: str
    name: str
    x: float
    y: float


@dataclass
class Link:
    id: str
    frm: str
    to: str
    axis: str
    x0: float
    y0: float
    length: float
    reverse: str = ""
    start_s: float = 0.0
    stop_s: float = 0.0
    signalized_end: bool = False

    @property
    def d(self) -> tuple[float, float]:
        return DIRS[self.axis]

    @property
    def heading(self) -> float:
        dx, dy = self.d
        return math.atan2(dy, dx)

    def point(self, s: float, lat: float) -> tuple[float, float]:
        dx, dy = self.d
        # Right normal of the travel direction.
        rx, ry = dy, -dx
        return self.x0 + dx * s + rx * lat, self.y0 + dy * s + ry * lat

    def locate(self, x: float, y: float) -> tuple[float, float]:
        dx, dy = self.d
        rx, ry = dy, -dx
        px, py = x - self.x0, y - self.y0
        return px * dx + py * dy, px * rx + py * ry


@dataclass
class Connector:
    id: str
    node: str
    link_in: str
    link_out: str
    lane_in: int
    lane_out: int
    maneuver: str
    points: list[tuple[float, float]]
    cum: list[float] = field(default_factory=list)

    @property
    def length(self) -> float:
        return self.cum[-1]

    def at(self, t: float) -> tuple[float, float, float]:
        t = max(0.0, min(self.length, t))
        pts, cum = self.points, self.cum
        lo, hi = 0, len(cum) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if cum[mid] <= t:
                lo = mid
            else:
                hi = mid
        seg = cum[hi] - cum[lo] or 1e-6
        f = (t - cum[lo]) / seg
        x0, y0 = pts[lo]
        x1, y1 = pts[hi]
        return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, math.atan2(y1 - y0, x1 - x0)


@dataclass
class Crosswalk:
    id: str
    node: str
    arm: str
    a: tuple[float, float]
    b: tuple[float, float]
    walk_phase: str


def maneuver_between(axis_in: str, axis_out: str) -> str | None:
    if axis_out == axis_in:
        return "straight"
    if axis_out == LEFT_OF[axis_in]:
        return "left"
    if axis_out == RIGHT_OF[axis_in]:
        return "right"
    return None


def _axis_between(a: tuple[float, float], b: tuple[float, float]) -> str:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) > abs(dy):
        return "east" if dx > 0 else "west"
    return "north" if dy > 0 else "south"


def _sample_arc(p0, d_in, p1, d_out, turn: str, n: int = 24) -> list[tuple[float, float]]:
    # Corner where the two lane lines meet; the arc is tangent to both.
    (x0, y0), (dx0, dy0) = p0, d_in
    (x1, y1), (dx1, dy1) = p1, d_out
    det = dx0 * (-dy1) - dy0 * (-dx1)
    t = ((x1 - x0) * (-dy1) - (y1 - y0) * (-dx1)) / det
    cx, cy = x0 + dx0 * t, y0 + dy0 * t
    r = math.hypot(cx - x0, cy - y0)
    nx, ny = (-dy0, dx0) if turn == "left" else (dy0, -dx0)
    ox, oy = x0 + nx * r, y0 + ny * r
    a0 = math.atan2(y0 - oy, x0 - ox)
    a1 = math.atan2(y1 - oy, x1 - ox)
    span = a1 - a0
    if turn == "left":
        while span <= 0:
            span += 2 * math.pi
    else:
        while span >= 0:
            span -= 2 * math.pi
    return [(ox + r * math.cos(a0 + span * i / n), oy + r * math.sin(a0 + span * i / n)) for i in range(n + 1)]


def _cumulative(points: list[tuple[float, float]]) -> list[float]:
    out = [0.0]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        out.append(out[-1] + math.hypot(x1 - x0, y1 - y0))
    return out


class Network:
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.links: dict[str, Link] = {}
        self.connectors: dict[str, Connector] = {}
        self.crosswalks: list[Crosswalk] = []
        self.out_links: dict[str, list[str]] = {}
        self.in_links: dict[str, list[str]] = {}
        self._build()

    def _build(self) -> None:
        for nid, (x, y) in INTERSECTIONS.items():
            self.nodes[nid] = Node(nid, "signal", INTERSECTION_NAMES[nid], x, y)
        for nid, (name, (x, y)) in STUBS.items():
            self.nodes[nid] = Node(nid, "stub", name, x, y)
        for road in ROADS:
            for a, b in zip(road, road[1:]):
                for frm, to in ((a, b), (b, a)):
                    na, nb = self.nodes[frm], self.nodes[to]
                    axis = _axis_between((na.x, na.y), (nb.x, nb.y))
                    length = math.hypot(nb.x - na.x, nb.y - na.y)
                    link = Link(
                        id=f"{frm}>{to}",
                        frm=frm,
                        to=to,
                        axis=axis,
                        x0=na.x,
                        y0=na.y,
                        length=length,
                        reverse=f"{to}>{frm}",
                        start_s=STOP_BACK if na.kind == "signal" else 0.0,
                        stop_s=length - STOP_BACK if nb.kind == "signal" else length,
                        signalized_end=nb.kind == "signal",
                    )
                    self.links[link.id] = link
                    self.out_links.setdefault(frm, []).append(link.id)
                    self.in_links.setdefault(to, []).append(link.id)
        for nid, node in self.nodes.items():
            if node.kind != "signal":
                continue
            for lin in self.in_links[nid]:
                li = self.links[lin]
                for lout in self.out_links[nid]:
                    lo = self.links[lout]
                    if lo.to == li.frm:
                        continue
                    man = maneuver_between(li.axis, lo.axis)
                    if man is None:
                        continue
                    lanes = {"straight": [(0, 0), (1, 1)], "left": [(1, 1)], "right": [(0, 0)]}[man]
                    for lane_in, lane_out in lanes:
                        p0 = li.point(li.stop_s, LANE_LAT[lane_in])
                        p1 = lo.point(lo.start_s, LANE_LAT[lane_out])
                        if man == "straight":
                            pts = [
                                (p0[0] + (p1[0] - p0[0]) * i / 12, p0[1] + (p1[1] - p0[1]) * i / 12)
                                for i in range(13)
                            ]
                        else:
                            pts = _sample_arc(p0, li.d, p1, lo.d, man)
                        cid = f"{lin}|{lout}|{lane_in}"
                        self.connectors[cid] = Connector(
                            cid, nid, lin, lout, lane_in, lane_out, man, pts, _cumulative(pts)
                        )
            for arm in ("west", "east", "north", "south"):
                dx, dy = DIRS[arm]
                cx, cy = node.x + dx * CROSSWALK, node.y + dy * CROSSWALK
                if arm in ("west", "east"):
                    a, b = (cx, cy - 8.4), (cx, cy + 8.4)
                    phase = "ns_green"
                else:
                    a, b = (cx - 8.4, cy), (cx + 8.4, cy)
                    phase = "ew_green"
                self.crosswalks.append(Crosswalk(f"{nid}-{arm}", nid, arm, a, b, phase))

    def connector_for(self, link_in: str, link_out: str, lane: int) -> Connector | None:
        return self.connectors.get(f"{link_in}|{link_out}|{lane}")

    def successors(self, link_id: str) -> list[tuple[str, str]]:
        link = self.links[link_id]
        if self.nodes[link.to].kind != "signal":
            return []
        out = []
        for lout in self.out_links[link.to]:
            lo = self.links[lout]
            if lo.to == link.frm:
                continue
            man = maneuver_between(link.axis, lo.axis)
            if man:
                out.append((man, lout))
        return out

    def entry_link(self, stub: str) -> Link:
        return self.links[self.out_links[stub][0]]

    def exit_link(self, stub: str) -> Link:
        return self.links[self.in_links[stub][0]]

    def arm_of(self, node: str, link_id: str) -> str:
        """Arm of `node` that a link touches, named by compass side."""
        link = self.links[link_id]
        other = link.frm if link.to == node else link.to
        n, o = self.nodes[node], self.nodes[other]
        return _axis_between((n.x, n.y), (o.x, o.y))

    def snap(self, x: float, y: float) -> tuple[Link, float, int] | None:
        """Nearest drivable lane position to a point."""
        best = None
        for link in self.links.values():
            s, lat = link.locate(x, y)
            if s < link.start_s or s > link.stop_s:
                continue
            for lane in (0, 1):
                err = abs(lat - LANE_LAT[lane])
                if err > LANE_W * 1.6:
                    continue
                if best is None or err < best[0]:
                    best = (err, link, s, lane)
        if best is None:
            return None
        return best[1], best[2], best[3]

    def to_json(self) -> dict:
        roads = []
        for road in ROADS:
            a, b = self.nodes[road[0]], self.nodes[road[-1]]
            roads.append({"a": [a.x, a.y], "b": [b.x, b.y]})
        stop_lines = []
        lamps = []
        for link in self.links.values():
            if not link.signalized_end:
                continue
            p0 = link.point(link.stop_s, 0.0)
            p1 = link.point(link.stop_s, ROAD_HALF)
            stop_lines.append({"link": link.id, "a": list(p0), "b": list(p1)})
            lamps.append({"link": link.id, "node": link.to, "axis": link.axis, "pos": list(link.point(link.stop_s, 3.5))})
        return {
            "bounds": {"min": [-EDGE, -EDGE], "max": [EDGE, EDGE]},
            "road_half": ROAD_HALF,
            "lane_w": LANE_W,
            "box": BOX,
            "roads": roads,
            "intersections": [
                {"id": n.id, "name": n.name, "x": n.x, "y": n.y}
                for n in self.nodes.values()
                if n.kind == "signal"
            ],
            "stubs": [
                {"id": n.id, "name": n.name, "x": n.x, "y": n.y, "entry": self.entry_link(n.id).id, "exit": self.exit_link(n.id).id}
                for n in self.nodes.values()
                if n.kind == "stub"
            ],
            "links": [
                {
                    "id": l.id,
                    "from": l.frm,
                    "to": l.to,
                    "axis": l.axis,
                    "a": list(l.point(l.start_s, 0.0)),
                    "b": list(l.point(l.stop_s, 0.0)),
                }
                for l in self.links.values()
            ],
            "stop_lines": stop_lines,
            "lamps": lamps,
            "crosswalks": [
                {"id": c.id, "node": c.node, "arm": c.arm, "a": list(c.a), "b": list(c.b)} for c in self.crosswalks
            ],
        }


NETWORK = Network()
