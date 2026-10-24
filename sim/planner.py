"""Cost-based planner. Every number behind a decision goes into the frame.

Per tick, for each car:
1. Signal verdict for the next stop line (stop, go, committed).
2. Candidates: keep lane, change left, change right, pass on the center line.
3. For each candidate, virtual leaders on its path (car, stop line, yield
   point, person, box exit, goal) give an IDM acceleration.
4. A 4 s rollout per candidate scores safety, rules, progress, comfort, and
   route-lane urgency. MOBIL gates discretionary lane changes.
5. The lowest total wins. A shield clips braking to the hard limit.
6. Pure pursuit steers along the winning path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from sim import conflicts, paths
from sim.geom import ACTION_LABEL, CAR_LENGTH, MAX_STEER, WHEELBASE, closing_distance, stopping_distance
from sim.idm import IdmResult, Style, accel as idm_accel, formula as idm_formula, hard_limit, style_for
from sim.network import LANE_LAT, NETWORK, SOLID_ZONE
from sim.perception import Leader, find_leader, nearby, obs_vector, ped_conflict
from sim.routes import MANEUVER_TEXT, required_lane

HORIZON = 4.0
ROLL_DT = 0.2
STEPS = int(HORIZON / ROLL_DT)
BOX_CLEAR = 18.0
LINE_S0 = 1.0
TURN_SPEED = {"left": 7.0, "right": 5.0, "straight": 99.0}
W_COLLISION = 40.0
W_ROUTE = 60.0
W_NETWORK = 1.5
RULE_RED = 25.0
RULE_SOLID = 4.0
RULE_CENTER = 8.0
LANE_CHANGE_EFFORT = 0.4
MOBIL_THRESHOLD = 0.2
MANDATORY_WINDOW = 60.0
CENTER_WAIT = 5.0
QUEUE_KINDS = {"stop_line", "yield", "box_exit", "ped"}
DISC_OFF = 1.15
DISC_R = 1.05
PED_R = 0.45


@dataclass
class Constraint:
    kind: str
    id: str | None
    name: str
    reason: str
    gap: float
    lead_v: float
    s0: float | None
    idm: IdmResult | None = None

    def to_json(self, v: float, style: Style) -> dict:
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "reason": self.reason,
            "gap": round(self.gap, 2),
            "lead_v": round(self.lead_v, 2),
            "a": None if self.idm is None else round(self.idm.a, 3),
            "s_star": None if self.idm is None or self.idm.s_star is None else round(self.idm.s_star, 2),
            "formula": "" if self.idm is None else idm_formula(self.idm, v, style),
        }


@dataclass
class Candidate:
    key: str
    label: str
    lane: int
    trace: paths.Trace | None = None
    feasible: bool = True
    reason: str | None = None
    constraints: list[Constraint] = field(default_factory=list)
    binding: Constraint | None = None
    free: IdmResult | None = None
    a0: float = 0.0
    terms: list[dict] = field(default_factory=list)
    total: float = 0.0
    path: list[list[float]] = field(default_factory=list)
    ttc: float | None = None
    ttc_with: str | None = None
    ped_hit: bool = False
    progress: float = 0.0
    mobil: dict | None = None
    yields: list = field(default_factory=list)
    checked: list = field(default_factory=list)
    v0_eff: float = 0.0
    evasion: bool = False


# ---------------------------------------------------------------------------
# Signal


def signal_verdict(world, car, trace, style: Style, hard: float) -> dict | None:
    if car.leg != "link" or trace.stop_d is None:
        return None
    link = NETWORK.links[car.link]
    if not link.signalized_end:
        return None
    sig = world.signals[link.to]
    color = sig.color_for_axis(link.axis)
    remaining = sig.remaining * 0.1 if sig.phase != "all_red" else None
    d = trace.stop_d - car.length / 2
    v = car.speed
    req = v * v / (2 * max(d, 0.1)) if d > 0 else math.inf
    comfy = stopping_distance(v, style.b)
    hard_stop = stopping_distance(v, hard)
    t_clear = (max(d, 0.0) + BOX_CLEAR) / max(v, 0.5)
    if d <= -0.05:
        verdict, text = "past", "Front is past the line: finish crossing."
    elif color == "green":
        verdict, text = "go", "Green."
    elif color == "red":
        if d <= 0.3 or req <= hard:
            verdict = "stop"
            text = f"Red. Needs {req:.1f} m/s² to stop, within the {hard:.0f} m/s² limit: stop at the line."
        else:
            verdict = "committed"
            text = f"Red, but stopping needs {req:.1f} m/s², over the {hard:.0f} m/s² limit: continue."
    else:
        if t_clear <= (remaining or 0.0):
            verdict = "go"
            text = f"Yellow. Clears the box in {t_clear:.1f} s, within the {remaining:.1f} s left."
        elif req <= hard:
            verdict = "stop"
            text = f"Yellow. Clearing takes {t_clear:.1f} s but only {remaining:.1f} s is left; stopping needs {req:.1f} m/s²."
        else:
            verdict = "committed"
            text = f"Yellow. Cannot clear in time and cannot stop ({req:.1f} m/s² over {hard:.0f}): continue."
    return {
        "node": link.to,
        "node_name": NETWORK.nodes[link.to].name,
        "color": color,
        "remaining": None if remaining is None else round(remaining, 2),
        "dist": round(d, 2),
        "speed": round(v, 2),
        "t_clear": round(t_clear, 2),
        "t_clear_formula": f"({max(d, 0):.1f} + {BOX_CLEAR:.0f}) / {max(v, 0.5):.1f} = {t_clear:.1f} s",
        "stop_comfy": round(comfy, 2),
        "stop_hard": round(hard_stop, 2),
        "stop_formula": f"{v:.1f}² / (2×{style.b:.1f}) = {comfy:.1f} m comfortable; {v:.1f}² / (2×{hard:.0f}) = {hard_stop:.1f} m hard",
        "req_decel": None if math.isinf(req) else round(req, 2),
        "req_formula": "past the line" if math.isinf(req) else f"{v:.1f}² / (2×{max(d, 0.1):.1f}) = {req:.2f} m/s²",
        "hard": hard,
        "verdict": verdict,
        "text": text,
    }


# ---------------------------------------------------------------------------
# Constraints


def _box_exit_room(world, car, trace) -> tuple[bool, float]:
    if trace.out_link is None or car.leg != "link":
        return True, 99.0
    conn = NETWORK.connectors[trace.connector]
    out = NETWORK.links[trace.out_link]
    lat = LANE_LAT[conn.lane_out]
    rear = out.length
    claims = 0
    for other in world.cars:
        if other is car or other.arrived:
            continue
        if other.leg == "link" and other.link == out.id and abs(other.lat - lat) < 2.0:
            rear = min(rear, other.s - other.length / 2)
        elif other.leg == "connector" and other.connector and NETWORK.connectors[other.connector].link_out == out.id:
            if NETWORK.connectors[other.connector].lane_out == conn.lane_out and other.speed < 2.0:
                claims += 1
    room = rear - out.start_s - claims * (CAR_LENGTH + 2.0)
    return room >= car.length + 2.0, room


def _walker_in_exit_lane(walker, conn) -> bool:
    """Walker is on, or within 5 s of, the band of the lane the turn exits into."""
    from sim.perception import ped_future

    out = NETWORK.links[conn.link_out]
    lane_lat = LANE_LAT[conn.lane_out]
    for px, py, _t in ped_future(walker, horizon=5.0):
        _s, lat = out.locate(px, py)
        if lane_lat - 3.0 <= lat <= lane_lat + 3.0:
            return True
    return False


def _turn_v0(car, trace, style: Style) -> tuple[float, str | None]:
    v0 = style.v0
    note = None
    if trace.connector is None:
        return v0, None
    man = NETWORK.connectors[trace.connector].maneuver
    v_turn = TURN_SPEED[man]
    if v_turn >= v0:
        return v0, None
    if car.leg == "connector":
        return v_turn, f"{MANEUVER_TEXT[man]} speed cap {v_turn:.0f} m/s"
    dist = max(0.0, (trace.conn_d or 0.0) - car.length / 2)
    cap = math.sqrt(v_turn * v_turn + 2 * style.b * dist)
    if cap < v0:
        note = f"v0 = min({v0:.1f}, √({v_turn:.0f}² + 2×{style.b:.1f}×{dist:.0f})) = {cap:.1f} m/s for the {MANEUVER_TEXT[man]}"
        v0 = cap
    return v0, note


def build_constraints(world, car, cand: Candidate, verdict: dict | None, style: Style, hard: float, deadlock_ok=True):
    tr = cand.trace
    out: list[Constraint] = []
    lead = find_leader(world, car, tr)
    if lead is not None:
        out.append(Constraint("car", lead.id, lead.name, lead.reason, lead.gap, lead.speed, None))
    ped = ped_conflict(world, car, tr)
    if ped is not None:
        out.append(Constraint("ped", ped.id, ped.name, ped.reason, ped.gap, 0.0, 0.5))
    stop_gap = None if tr.stop_d is None else tr.stop_d - car.length / 2
    if verdict and verdict["verdict"] == "stop" and stop_gap is not None:
        out.append(Constraint("stop_line", f"signal-{verdict['node']}", f"{verdict['node_name']} stop line", f"{verdict['color']} light", stop_gap, 0.0, LINE_S0))
    if tr.wrong_lane and stop_gap is not None:
        out.append(Constraint("stop_line", None, "Stop line", "wrong lane for the route", stop_gap, 0.0, LINE_S0))
    can_stop_line = stop_gap is not None and stop_gap > 0 and (car.speed ** 2) / (2 * max(stop_gap, 0.1)) <= hard
    # Turning across a crosswalk with someone on it: wait at the line, not in the box.
    if car.leg == "link" and tr.connector and can_stop_line:
        conn = NETWORK.connectors[tr.connector]
        if conn.maneuver != "straight":
            arm = NETWORK.arm_of(conn.node, conn.link_out)
            walker = world.ped(f"walker-{conn.node}-{arm}")
            if walker is not None and walker.moving and not walker.hit and _walker_in_exit_lane(walker, conn):
                out.append(Constraint("ped", walker.id, "Walker", f"on the exit crosswalk, so the {conn.maneuver} turn waits", stop_gap, 0.0, LINE_S0))
    # Yield points.
    yields, rows = conflicts.evaluate(world, car, tr, style, hard)
    cand.yields, cand.checked = yields, rows
    for y in yields:
        point = y.d_point - conflicts.YIELD_MARGIN - car.length / 2
        inside = point
        permissive = y.rule.startswith("Permissive")
        if car.leg == "link" and stop_gap is not None and stop_gap > -0.05:
            # Waiting inside only makes sense past the near crosswalk.
            if permissive and verdict and verdict["color"] == "green" and inside > stop_gap + 6.0:
                gap = inside
            elif can_stop_line:
                gap = stop_gap
            else:
                gap = inside
        else:
            gap = inside
        if gap < 0.0:
            # Past the yield point but short of the conflict itself: stop now.
            if y.d_point <= car.length / 2:
                continue
            gap = 0.0
        out.append(Constraint("yield", y.other, y.name, y.rule, gap, 0.0, LINE_S0))
    # Room past the box.
    if car.leg == "link" and stop_gap is not None and stop_gap > -0.05 and tr.out_link is not None:
        ok, room = _box_exit_room(world, car, tr)
        if not ok and can_stop_line:
            out.append(Constraint("box_exit", None, "Box exit", f"only {room:.1f} m free past the box", stop_gap, 0.0, LINE_S0))
    # Destination in the middle of a road: stop there.
    if tr.end_d is not None and car.goal_stop:
        out.append(Constraint("goal", None, car.dest_label or "Destination", "trip ends here", tr.end_d - car.length / 2 + 0.5, 0.0, 0.3))
    v0, _note = _turn_v0(car, tr, style)
    cand.v0_eff = v0
    v = car.speed
    cand.free = idm_accel(v, v0, None, 0.0, style)
    best = None
    for c in out:
        c.idm = idm_accel(v, v0, max(c.gap, 0.05), c.lead_v, style, c.s0)
        if best is None or c.idm.a < best.idm.a:
            best = c
    cand.constraints = out
    cand.binding = best
    cand.a0 = cand.free.a if best is None else best.idm.a
    return cand


# ---------------------------------------------------------------------------
# Rollout


def _discs(x, y, h):
    c, s = math.cos(h), math.sin(h)
    return (x + c * DISC_OFF, y + s * DISC_OFF), (x - c * DISC_OFF, y - s * DISC_OFF)


def _overlap(a, b, r=2 * DISC_R) -> bool:
    for p in a:
        for q in b:
            if (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 < r * r:
                return True
    return False


def rollout(world, car, cand: Candidate, style: Style, hard: float, verdict: dict | None):
    tr = cand.trace
    d, v = 0.0, car.speed
    a_prev = car.accel
    accels, jerks = [], []
    poses = []
    statics = [c for c in cand.constraints if c.kind != "car"]
    lead = next((c for c in cand.constraints if c.kind == "car"), None)
    near = [o for o in world.cars if o is not car and not o.arrived and o.pred and (o.x - car.x) ** 2 + (o.y - car.y) ** 2 < 90 ** 2]
    ttc = None
    ttc_with = None
    ped_hit = False
    crossed_red = False
    stop_line_d = None if tr.stop_d is None else tr.stop_d - car.length / 2
    v0_base, _ = _turn_v0(car, tr, style)
    for k in range(1, STEPS + 1):
        if k == 1:
            a = cand.a0
        else:
            v0 = v0_base
            a = idm_accel(v, v0, None, 0.0, style).a
            for c in statics:
                g = c.gap - d
                a = min(a, idm_accel(v, v0, max(g, 0.05), 0.0, style, c.s0).a)
            if lead is not None:
                g = lead.gap + lead.lead_v * (k - 1) * ROLL_DT - d
                a = min(a, idm_accel(v, v0, max(g, 0.05), lead.lead_v, style).a)
        a = max(-hard, min(style.a_max, a))
        accels.append(a)
        jerks.append((a - a_prev) / ROLL_DT)
        a_prev = a
        nv = max(0.0, v + a * ROLL_DT)
        d += (v + nv) / 2 * ROLL_DT
        v = nv
        x, y, h = tr.pose_at(d)
        poses.append((x, y, h))
        if verdict and verdict["verdict"] == "stop" and stop_line_d is not None and d > stop_line_d + 0.5:
            crossed_red = True
        if ttc is None:
            mine = _discs(x, y, h)
            for o in near:
                ox, oy, oh = o.pred[k] if k < len(o.pred) else o.pred[-1]
                if (ox - x) ** 2 + (oy - y) ** 2 > 36:
                    continue
                if _overlap(mine, _discs(ox, oy, oh)):
                    ttc = k * ROLL_DT
                    ttc_with = o.name
                    break
        if not ped_hit:
            for ped_pos in world.ped_pred.values():
                px, py = ped_pos[k] if k < len(ped_pos) else ped_pos[-1]
                if (px - x) ** 2 + (py - y) ** 2 > 16:
                    continue
                for q in _discs(x, y, h):
                    if (q[0] - px) ** 2 + (q[1] - py) ** 2 < (DISC_R + PED_R) ** 2:
                        ped_hit = True
                        break
                if ped_hit:
                    break
    cand.ttc, cand.ttc_with, cand.ped_hit = ttc, ttc_with, ped_hit
    cand.progress = d
    cand.path = [[round(p[0], 2), round(p[1], 2)] for p in poses[::2]] + ([[round(poses[-1][0], 2), round(poses[-1][1], 2)]] if poses else [])
    if cand.path:
        cand.path.insert(0, [round(car.x, 2), round(car.y, 2)])
    return accels, jerks, crossed_red


# ---------------------------------------------------------------------------
# MOBIL


def _neighbors(world, car, lane: int):
    """Nearest car ahead and behind in a lane of the car's link."""
    lat = LANE_LAT[lane]
    ahead = behind = None
    for other in world.cars:
        if other is car or other.arrived or other.leg != "link" or other.link != car.link:
            continue
        if abs(other.lat - lat) > 1.9 and other.target_lane != lane:
            continue
        ds = other.s - car.s
        if ds >= 0:
            if ahead is None or ds < ahead[0]:
                ahead = (ds, other)
        else:
            if behind is None or -ds < behind[0]:
                behind = (-ds, other)
    return ahead, behind


def _follower_accel(world, follower, gap, lead_v) -> float:
    st = style_for(follower.brain, world.wet)
    return idm_accel(follower.speed, st.v0, max(gap, 0.05), lead_v, st).a


def _follower_now(world, follower) -> float:
    d = follower.decision or {}
    a = (d.get("idm") or {}).get("a")
    if a is None:
        st = style_for(follower.brain, world.wet)
        return idm_accel(follower.speed, st.v0, None, 0.0, st).a
    return float(a)


def mobil(world, car, keep: Candidate, cand: Candidate, style: Style, bias: float, mandatory: bool) -> dict:
    b_safe = style.b_safe
    ahead_new, behind_new = _neighbors(world, car, cand.lane)
    _, behind_old = _neighbors(world, car, car.lane)
    own = cand.a0 - keep.a0
    front_gap = None if ahead_new is None else ahead_new[0] - car.length / 2 - ahead_new[1].length / 2
    nf = None
    nf_loss = 0.0
    safe = True
    reasons = []
    if behind_new is not None:
        ds, f = behind_new
        gap = ds - car.length / 2 - f.length / 2
        a_new = _follower_accel(world, f, gap, car.speed)
        a_old = _follower_now(world, f)
        nf_loss = a_new - a_old
        nf = {"name": f.name, "gap": round(gap, 2), "speed": round(f.speed, 2), "a_new": round(a_new, 2), "a_old": round(a_old, 2)}
        if a_new < -b_safe:
            safe = False
            reasons.append(f"{f.name} would need {-a_new:.1f} m/s² of braking, over b_safe {b_safe:.1f}")
        if gap < 1.5:
            safe = False
            reasons.append(f"rear gap to {f.name} is {gap:.1f} m, under 1.5 m")
    if front_gap is not None and front_gap < 1.5:
        safe = False
        reasons.append(f"front gap {front_gap:.1f} m, under 1.5 m")
    of = None
    of_gain = 0.0
    if behind_old is not None:
        ds, f = behind_old
        gap_now = ds - car.length / 2 - f.length / 2
        a_old = _follower_accel(world, f, gap_now, car.speed)
        lead_c = keep.binding if keep.binding is not None and keep.binding.kind == "car" else None
        if lead_c is not None:
            a_new = _follower_accel(world, f, gap_now + car.length + lead_c.gap, lead_c.lead_v)
        else:
            st = style_for(f.brain, world.wet)
            a_new = idm_accel(f.speed, st.v0, None, 0.0, st).a
        of_gain = a_new - a_old
        of = {"name": f.name, "a_new": round(a_new, 2), "a_old": round(a_old, 2)}
    incentive = own + style.politeness * (nf_loss + of_gain) + bias
    passes = safe and (mandatory or incentive > MOBIL_THRESHOLD)
    formula = (
        f"Δa = {own:+.2f} + {style.politeness:.2f}×({nf_loss:+.2f} {of_gain:+.2f}) {bias:+.2f} bias = {incentive:+.2f}"
        f" {'>' if incentive > MOBIL_THRESHOLD else '≤'} {MOBIL_THRESHOLD}"
    )
    return {
        "lane": cand.lane,
        "own_gain": round(own, 3),
        "new_follower": nf,
        "old_follower": of,
        "politeness": style.politeness,
        "bias": round(bias, 3),
        "incentive": round(incentive, 3),
        "threshold": MOBIL_THRESHOLD,
        "b_safe": b_safe,
        "safe": safe,
        "mandatory": mandatory,
        "passes": passes,
        "reasons": reasons,
        "formula": formula,
    }


# ---------------------------------------------------------------------------
# Decide


def _lane_change_candidates(car) -> list[tuple[str, str, int]]:
    out = [("keep", "Keep lane", car.target_lane)]
    if car.leg != "link":
        return out
    if car.lane != car.target_lane:
        if car.lane_lock <= 0:
            out.append(("abort", "Abort lane change", car.lane))
        return out
    if car.lane == 0:
        out.append(("left", "Change left", 1))
    elif car.lane == 1:
        out.append(("right", "Change right", 0))
        out.append(("center", "Pass on the center line", -1))
    elif car.lane == -1:
        out.append(("right", "Return to the lane", 1))
    return out


def _queued(world, leader_id: str | None) -> bool:
    if leader_id is None:
        return False
    other = world.car(leader_id)
    if other is None or other.stalled or other.crashed:
        return False
    if other.binding in QUEUE_KINDS:
        return True
    if other.binding == "car" and other.speed < 3.0:
        d = other.decision or {}
        lead = (d.get("idm") or {}).get("leader") or {}
        if lead.get("gap") is not None and lead["gap"] < 15.0:
            nxt = world.car(lead.get("id")) if lead.get("id") else None
            if nxt is not None and (nxt.stalled or nxt.crashed):
                return False
            return True
    # Stopped on green with nothing ahead for more than 4 s: treat as a stall.
    return False


def _oncoming_clear(world, car, pass_len: float) -> tuple[bool, str]:
    link = NETWORK.links[car.link]
    rev = link.reverse
    need = pass_len + 25.0
    for other in world.cars:
        if other.arrived:
            continue
        if other.leg == "link" and other.link == rev:
            s_mine = link.length - other.s
            closing = other.speed * (pass_len / 4.0)
            if car.s - 6.0 < s_mine < car.s + need + closing:
                return False, f"{other.name} is oncoming {s_mine - car.s:.0f} m ahead"
        elif other.leg == "connector" and other.connector and NETWORK.connectors[other.connector].link_out == rev:
            return False, f"{other.name} is turning into the oncoming lane"
    for ped in world.peds:
        if ped.hit:
            continue
        s, lat = link.locate(ped.x, ped.y)
        if -4.0 < lat < 0.5 and car.s - 4 < s < car.s + need:
            return False, f"{ped.name} is near the center line"
    return True, "oncoming lane clear"


def decide(world, car) -> tuple[float, float, dict, Candidate | None]:
    style = style_for(car.brain, world.wet)
    hard = hard_limit(world.wet)
    if car.crashed or car.stalled:
        a = -hard if car.speed > 0.2 else 0.0
        if car.crashed:
            a = 0.0
        text = "Crashed and stopped." if car.crashed else "Stalled in the lane. This car is not choosing a move."
        frame = _base_frame(world, car, style, hard)
        frame.update({"sentence": text, "meta_action": "CRASHED" if car.crashed else "STALLED", "badge": "Crashed" if car.crashed else "Stalled"})
        car.badge = frame["badge"]
        car.binding = None
        car.indicator = "hazard" if car.stalled else None
        return a, 0.0, frame, None

    max_d = max(45.0, car.speed * HORIZON + 30.0)
    keep_trace = car.trace if car.trace is not None else paths.build(car, car.target_lane, max_d)
    verdict = signal_verdict(world, car, keep_trace, style, hard)
    need = required_lane(car.route, car.route_i) if car.leg == "link" else None
    d_line = None if keep_trace.stop_d is None else keep_trace.stop_d - car.length / 2
    in_solid = car.leg != "link" or (d_line is not None and d_line < SOLID_ZONE)
    link = NETWORK.links[car.link] if car.leg == "link" else None
    near_start = link is not None and car.s < link.start_s + 4.0 and link.start_s > 0

    cands: list[Candidate] = []
    for key, label, lane in _lane_change_candidates(car):
        cand = Candidate(key, label, lane)
        cand.trace = keep_trace if key == "keep" else paths.build(car, lane, max_d)
        build_constraints(world, car, cand, verdict, style, hard)
        cands.append(cand)
    keep = cands[0]

    # Rollouts and costs.
    for cand in cands:
        accels, jerks, crossed_red = rollout(world, car, cand, style, hard, verdict)
        _score(world, car, cand, keep, accels, jerks, crossed_red, style, need, d_line, in_solid, near_start, verdict)

    keep_vetoed = keep.ped_hit
    # Feasibility rules that are not costs.
    for cand in cands:
        if cand.key == "keep":
            continue
        _gate(world, car, cand, keep, style, hard, need, d_line, in_solid, near_start, keep_vetoed)

    network_note = _network_term(world, car, cands, verdict, d_line)

    feasible = [c for c in cands if c.feasible and not c.ped_hit]
    if not feasible:
        feasible = [keep]
        keep.reason = keep.reason or "Every option reaches a person; braking as hard as allowed."
    chosen = min(feasible, key=lambda c: c.total)

    # Shield.
    a_cmd = chosen.a0
    shield = _shield(car, chosen, a_cmd, style, hard)
    a_out = shield["a_out"]

    if chosen.key in ("left", "right", "center", "abort") and chosen.lane != car.target_lane:
        if chosen.key != "abort":
            car.lc_start_tick = world.tick
            lead = keep.binding if keep.binding is not None and keep.binding.kind == "car" else None
            if lead is not None and lead.reason in ("stalled", "crashed") or (lead is not None and lead.lead_v < car.speed - 1.0):
                car.overtaking = lead.id
        car.target_lane = chosen.lane

    steer = _pure_pursuit(car, chosen.trace)
    frame = _frame(world, car, style, hard, cands, chosen, verdict, shield, need, d_line, network_note)
    return a_out, steer, frame, chosen


def _score(world, car, cand, keep, accels, jerks, crossed_red, style, need, d_line, in_solid, near_start, verdict):
    terms = []
    ttc = cand.ttc
    risk = 0.0 if ttc is None else W_COLLISION * max(0.0, 1.0 - ttc / 3.0) ** 2
    terms.append(
        {
            "name": "Collision risk",
            "inputs": {"ttc": None if ttc is None else round(ttc, 2), "with": cand.ttc_with},
            "formula": "no overlap within 4 s" if ttc is None else f"{W_COLLISION:.0f} × max(0, 1 − {ttc:.1f}/3)² = {risk:.2f}",
            "value": round(risk, 3),
        }
    )
    lead = next((c for c in cand.constraints if c.kind == "car"), None)
    headway = None
    hw_cost = 0.0
    if lead is not None and car.speed > 1.0:
        headway = max(lead.gap, 0.0) / car.speed
        hw_cost = style.w_headway * max(0.0, style.T - headway) ** 2
    terms.append(
        {
            "name": "Headway",
            "inputs": {"gap": None if lead is None else round(lead.gap, 2), "speed": round(car.speed, 2), "T": style.T},
            "formula": "no car ahead" if headway is None else f"{style.w_headway:.1f} × max(0, {style.T:.1f} − {headway:.2f})² = {hw_cost:.2f}",
            "value": round(hw_cost, 3),
        }
    )
    rules = 0.0
    parts = []
    if crossed_red:
        rules += RULE_RED
        parts.append(f"enters on red +{RULE_RED:.0f}")
    if cand.key in ("left", "right") and in_solid:
        rules += RULE_SOLID
        parts.append(f"crosses the solid line +{RULE_SOLID:.0f}")
    if cand.lane == -1:
        rules += RULE_CENTER
        parts.append(f"center line +{RULE_CENTER:.0f}")
    terms.append({"name": "Rules", "inputs": {"red": crossed_red, "solid": cand.key in ("left", "right") and in_solid, "center": cand.lane == -1}, "formula": ", ".join(parts) or "no rule broken", "value": round(rules, 3)})
    prog = -style.w_progress * cand.progress
    terms.append(
        {
            "name": "Progress to B",
            "inputs": {"meters": round(cand.progress, 2)},
            "formula": f"−{style.w_progress:.2f} × {cand.progress:.1f} m = {prog:.2f}",
            "value": round(prog, 3),
        }
    )
    a2 = sum(a * a for a in accels) / max(len(accels), 1)
    j2 = sum(j * j for j in jerks) / max(len(jerks), 1)
    comfort = style.w_comfort * a2 + style.w_comfort * 0.05 * j2
    terms.append(
        {
            "name": "Comfort",
            "inputs": {"mean_a2": round(a2, 3), "mean_jerk2": round(j2, 3)},
            "formula": f"{style.w_comfort:.2f}×{a2:.2f} + {style.w_comfort * 0.05:.3f}×{j2:.1f} = {comfort:.2f}",
            "value": round(comfort, 3),
        }
    )
    route_cost = 0.0
    route_formula = "no lane needed"
    if need is not None and d_line is not None and d_line < 160:
        lane_at_line = cand.lane
        wrong = 1.0 if lane_at_line != need else 0.0
        route_cost = W_ROUTE * wrong / max(5.0, d_line)
        route_formula = f"{W_ROUTE:.0f} × {wrong:.0f} / max(5, {d_line:.0f}) = {route_cost:.2f}"
    terms.append({"name": "Route lane", "inputs": {"need": need, "lane": cand.lane, "to_line": None if d_line is None else round(d_line, 1)}, "formula": route_formula, "value": round(route_cost, 3)})
    effort = LANE_CHANGE_EFFORT if cand.key in ("left", "right", "center") else 0.0
    terms.append({"name": "Lane change effort", "inputs": {}, "formula": f"{effort:.1f}" if effort else "none", "value": effort})
    cand.terms = terms
    cand.total = sum(t["value"] for t in terms)
    if cand.ped_hit:
        cand.feasible = False
        cand.reason = "Path reaches a person within 4 s (veto)."


def _gate(world, car, cand, keep, style, hard, need, d_line, in_solid, near_start, keep_vetoed):
    lead = keep.binding if keep.binding is not None and keep.binding.kind == "car" else None
    lead_stalled = lead is not None and lead.reason in ("stalled", "crashed")
    evasion = keep_vetoed and car.speed >= 2.0 and not cand.ped_hit
    cand.evasion = evasion
    if cand.key == "abort":
        if not (cand.ttc is not None and (keep.ttc is None or keep.ttc < 1.5)):
            cand.feasible = False
            cand.reason = "Lane change is still safe; finishing it."
        return
    if near_start and not evasion:
        cand.feasible = False
        cand.reason = "Just out of the box; no lane change yet."
        return
    if in_solid and not evasion:
        stopped_long = lead_stalled and car.wait > 4.0 and lead is not None and lead.gap < 10.0
        if not stopped_long or cand.key == "center":
            cand.feasible = False
            cand.reason = f"Inside the {SOLID_ZONE:.0f} m solid-line zone before the stop line." if car.leg == "link" else "Inside the box."
            return
    if not evasion and not in_solid and d_line is not None and d_line - paths.lane_change_distance(car.speed) < SOLID_ZONE - 6.0:
        cand.feasible = False
        cand.reason = f"Not enough room to finish the change before the line ({d_line:.0f} m left)."
        return
    recent = car.lc_start_tick is not None and world.tick - car.lc_start_tick < 30
    if recent and not evasion and car.lane != -1:
        cand.feasible = False
        cand.reason = "Changed lanes less than 3 s ago."
        return
    if cand.key == "center":
        blocked_long = lead_stalled and car.wait >= CENTER_WAIT and lead is not None and lead.gap < 12.0
        ahead, _ = _neighbors(world, car, 0)
        other_blocked = ahead is not None and (ahead[1].stalled or ahead[1].crashed) and ahead[0] < 30.0
        if not (blocked_long and other_blocked):
            cand.feasible = False
            cand.reason = "Center line only after 5 s blocked by stalls in both lanes."
            return
        pass_len = (lead.gap if lead else 0.0) + 2 * car.length + 15.0
        if d_line is not None and d_line < pass_len + SOLID_ZONE:
            cand.feasible = False
            cand.reason = "Not enough road before the stop line to pass and return."
            return
        ok, why = _oncoming_clear(world, car, pass_len)
        if not ok:
            cand.feasible = False
            cand.reason = f"Oncoming lane not clear: {why}."
            return
        cand.mobil = None
        return
    # Discretionary change past a queued leader is pointless.
    mandatory = need is not None and cand.lane == need and d_line is not None and d_line < MANDATORY_WINDOW
    if not mandatory and not evasion and car.lane != -1 and lead is not None and _queued(world, lead.id):
        cand.feasible = False
        cand.reason = f"{lead.name} is queued, not slow; no overtaking a queue."
        return
    bias = 0.0
    if need is not None and d_line is not None and d_line < 160:
        if cand.lane == need:
            bias += min(2.0, 30.0 / max(5.0, d_line))
        elif car.lane == need:
            bias -= min(2.0, 30.0 / max(5.0, d_line)) + 0.3
    if car.lane == -1:
        mandatory = True
    if cand.key == "right" and car.lane == 1 and need is None and not car.overtaking:
        bias += 0.05
    m = mobil(world, car, keep, cand, style, bias, mandatory or evasion)
    if evasion:
        m["b_safe"] = hard
        m["safe"] = all("braking" in r for r in m["reasons"]) or m["safe"]
    cand.mobil = m
    if not m["safe"] and not evasion:
        cand.feasible = False
        cand.reason = "MOBIL safety: " + "; ".join(m["reasons"]) + "."
    elif not m["passes"] and not evasion:
        cand.feasible = False
        cand.reason = f"MOBIL incentive {m['incentive']:+.2f} is not over {MOBIL_THRESHOLD}."
    if in_solid and cand.feasible and not evasion:
        cand.reason = f"Breaks the solid line: {lead.name if lead else 'the car ahead'} has been stopped for {car.wait:.0f} s."


def _network_term(world, car, cands, verdict, d_line) -> dict | None:
    if not car.uses_network or car.model is None:
        return None
    from sim import policies

    color = None if verdict is None else verdict["color"]
    vec = obs_vector(world, car, color, d_line if d_line is not None else 60.0)
    try:
        action, scores, probs, value = policies.network_preference(car.model, vec)
    except Exception as exc:  # noqa: BLE001 — a broken checkpoint must not stop the town
        return {"error": str(exc)}
    mapping = {"keep": "IDLE", "abort": "IDLE", "left": "LANE_LEFT", "right": "LANE_RIGHT", "center": "LANE_LEFT"}
    for cand in cands:
        if cand.lane in (0, 1) and cand.key in ("left", "right"):
            mapping[cand.key] = "LANE_LEFT" if LANE_LAT[cand.lane] < LANE_LAT[car.lane] else "LANE_RIGHT"
        act = mapping[cand.key]
        p = max(float(probs[act]), 1e-4)
        if cand.key == "keep":
            p = max(p, float(probs["FASTER"]), float(probs["SLOWER"]))
        val = -W_NETWORK * math.log(p)
        cand.terms.append({"name": "Learned network", "inputs": {"action": act, "p": round(p, 4)}, "formula": f"−{W_NETWORK} × log({p:.3f}) = {val:.2f}", "value": round(val, 3)})
        cand.total += val
    return {
        "action": action,
        "label": ACTION_LABEL[action],
        "probs": [{"action": a, "label": ACTION_LABEL[a], "p": round(float(probs[a]), 4)} for a in probs],
        "value": round(float(value), 3),
    }


def _shield(car, chosen: Candidate, a_cmd: float, style: Style, hard: float) -> dict:
    a = a_cmd
    acted = False
    text = "IDM braking is within the comfortable limit."
    checks = []
    lead = next((c for c in chosen.constraints if c.kind == "car"), None)
    if lead is not None:
        need = closing_distance(car.speed, lead.lead_v, hard) + 1.0
        checks.append({"name": "Gap to car ahead", "have": round(lead.gap, 2), "need": round(need, 2), "formula": f"({car.speed:.1f}² − {lead.lead_v:.1f}²)/(2×{hard:.0f}) + 1"})
        if lead.gap < need and car.speed > lead.lead_v + 0.2:
            a = -hard
            acted = True
            text = f"Gap {lead.gap:.1f} m is under the {need:.1f} m needed at the hard limit: full braking."
    ped = next((c for c in chosen.constraints if c.kind == "ped"), None)
    if ped is not None:
        need = stopping_distance(car.speed, hard) + 1.0
        checks.append({"name": "Gap to person", "have": round(ped.gap, 2), "need": round(need, 2), "formula": f"{car.speed:.1f}²/(2×{hard:.0f}) + 1"})
        if ped.gap < need and car.speed > 0.2:
            a = -hard
            acted = True
            text = f"Person {ped.gap:.1f} m ahead, stopping takes {need:.1f} m: full braking."
    if a < -style.b and not acted:
        acted = a < -hard
        text = f"IDM asks {a:.1f} m/s², past the comfortable {style.b:.1f}; allowed up to the hard limit {hard:.0f}."
    a_out = max(-hard, min(style.a_max, a))
    if a_cmd < -hard:
        acted = True
        text = f"IDM asks {a_cmd:.1f} m/s²; clipped to the hard limit {-hard:.0f}."
    return {"acted": acted, "a_in": round(a_cmd, 3), "a_out": round(a_out, 3), "comfortable": style.b, "hard": hard, "text": text, "checks": checks}


def _pure_pursuit(car, trace) -> float:
    if trace is None or not trace.xs:
        return 0.0
    ld = max(3.5, min(12.0, 2.5 + 0.6 * car.speed))
    tx, ty, _ = trace.pose_at(ld)
    dx, dy = tx - car.x, ty - car.y
    c, s = math.cos(car.heading), math.sin(car.heading)
    rx, ry = dx * c + dy * s, -dx * s + dy * c
    dist = max(math.hypot(rx, ry), 1.0)
    alpha = math.atan2(ry, rx)
    steer = math.atan(2 * WHEELBASE * math.sin(alpha) / dist)
    return max(-MAX_STEER, min(MAX_STEER, steer))


# ---------------------------------------------------------------------------
# Frame


def _base_frame(world, car, style, hard) -> dict:
    seen, hidden = nearby(world, car)
    return {
        "sentence": "",
        "meta_action": "KEEP",
        "badge": None,
        "brain": car.brain,
        "brain_label": style.label,
        "style": style.to_json(),
        "checkpoint": car.checkpoint,
        "uses_network": bool(car.uses_network and car.model is not None),
        "route": route_frame(car),
        "idm": None,
        "signal": None,
        "candidates": [],
        "mobil": [],
        "shield": None,
        "conflicts": [],
        "seen": seen,
        "hidden_count": hidden,
        "accel": 0.0,
        "steering_deg": 0.0,
        "target_speed": round(style.v0, 2),
        "limits": {"accel_min": -hard, "accel_max": min(style.a_max, hard), "steer_deg": round(math.degrees(MAX_STEER), 1), "wet": world.wet},
        "model": _model(car, None),
        "history": [],
        "trip": trip_frame(world, car),
    }


def route_frame(car) -> dict:
    from sim.routes import maneuvers, route_length, route_points

    mans = maneuvers(car.route)
    i = car.route_i
    next_man = mans[i] if i < len(mans) else None
    start_s = car.s if car.leg == "link" else NETWORK.links[car.route[min(i + 1, len(car.route) - 1)]].start_s
    rest = car.route[i:] if car.leg == "link" else car.route[i + 1 :]
    remaining = route_length(rest, start_s, car.goal_s) if rest else 0.0
    if car.leg == "connector" and car.connector:
        remaining += max(0.0, NETWORK.connectors[car.connector].length - car.t)
    total = route_length(car.route, NETWORK.links[car.route[0]].start_s, car.goal_s)
    need = required_lane(car.route, i) if car.leg == "link" else None
    d_line = None
    if car.leg == "link" and car.trace is not None and car.trace.stop_d is not None:
        d_line = car.trace.stop_d - car.length / 2
    return {
        "from": car.start_label,
        "to": car.dest_label,
        "links": list(car.route),
        "index": i,
        "maneuvers": mans,
        "next": next_man,
        "next_text": None if next_man is None else MANEUVER_TEXT[next_man],
        "next_node": None if next_man is None else NETWORK.nodes[NETWORK.links[car.route[i]].to].name,
        "remaining": round(remaining, 1),
        "length": round(total, 1),
        "progress": round(max(0.0, total - remaining), 1),
        "need_lane": need,
        "lane": car.lane,
        "lane_change_left": None if need is None or need == car.lane or d_line is None else round(max(0.0, d_line - SOLID_ZONE), 1),
        "to_line": None if d_line is None else round(d_line, 1),
        "points": route_points(car.route[i:] if car.leg == "link" else car.route[i + 1 :], start_s, car.goal_s, car.lane if car.lane in (0, 1) else 1, step=8.0),
    }


def trip_frame(world, car) -> dict:
    elapsed = (world.tick - car.start_tick) * 0.1
    return {
        "user": car.user,
        "elapsed": round(elapsed, 1),
        "stops": car.stops,
        "overtakes": car.overtakes,
        "replans": list(car.replans[-8:]),
        "arrived": car.arrived,
    }


def _model(car, net: dict | None) -> dict:
    if car.uses_network and car.model is not None:
        return {
            "loaded": True,
            "mix": car.brain,
            "seed": car.seed,
            "checkpoint": car.checkpoint,
            "text": "PPO network loaded. Its probability for each option is one more cost term: −w·log p.",
            "probs": None if not net or "probs" not in net else net["probs"],
            "value": None if not net else net.get("value"),
        }
    return {"loaded": False, "mix": car.brain, "text": f"No network. {car.name} plans with IDM, MOBIL, and the cost terms only."}


def _frame(world, car, style, hard, cands, chosen, verdict, shield, need, d_line, network_note) -> dict:
    frame = _base_frame(world, car, style, hard)
    binding = chosen.binding
    v = car.speed
    idm_rows = [c.to_json(v, style) for c in chosen.constraints]
    free = chosen.free
    frame["idm"] = {
        "leader": None if binding is None else {"kind": binding.kind, "id": binding.id, "name": binding.name, "reason": binding.reason, "gap": round(binding.gap, 2)},
        "v": round(v, 2),
        "v0": round(chosen.v0_eff, 2),
        "v0_style": style.v0,
        "s": None if binding is None else round(binding.gap, 2),
        "dv": None if binding is None or binding.idm is None else round(binding.idm.dv, 2),
        "s_star": None if binding is None or binding.idm is None or binding.idm.s_star is None else round(binding.idm.s_star, 2),
        "a": round(chosen.a0, 3),
        "free_a": round(free.a, 3) if free else None,
        "formula": idm_formula(binding.idm if binding is not None and binding.idm is not None else free, v, style),
        "constraints": idm_rows,
        "T": style.T,
        "s0": style.s0,
        "a_max": style.a_max,
        "b": style.b,
    }
    frame["signal"] = verdict
    frame["shield"] = shield
    frame["conflicts"] = [y.to_json() for y in chosen.checked]
    frame["mobil"] = [c.mobil for c in cands if c.mobil]
    ranked = sorted([c for c in cands if c.feasible and not c.ped_hit], key=lambda c: c.total)
    runner = next((c for c in ranked if c is not chosen), None)
    frame["candidates"] = [
        {
            "key": c.key,
            "label": c.label,
            "lane": c.lane,
            "feasible": c.feasible and not c.ped_hit,
            "reason": c.reason,
            "chosen": c is chosen,
            "total": round(c.total, 3),
            "terms": c.terms,
            "path": c.path,
            "binding": None if c.binding is None else c.binding.kind,
            "a": round(c.a0, 3),
        }
        for c in cands
    ]
    sentence, badge, meta = _sentence(car, chosen, runner, verdict, shield)
    frame["sentence"] = sentence
    frame["badge"] = badge
    frame["meta_action"] = meta
    frame["compare"] = _compare(chosen, runner)
    frame["model"] = _model(car, network_note)
    frame["target_speed"] = round(chosen.v0_eff, 2)
    frame["stop_point"] = _stop_point(chosen)
    car.badge = badge
    car.binding = None if binding is None else binding.kind
    return frame


def _stop_point(cand: Candidate):
    b = cand.binding
    if b is None or b.kind == "car" or cand.trace is None:
        return None
    x, y, _ = cand.trace.pose_at(b.gap + CAR_LENGTH / 2)
    return {"x": round(x, 2), "y": round(y, 2), "kind": b.kind}


def _compare(chosen: Candidate, runner: Candidate | None) -> dict | None:
    if runner is None:
        return None
    diffs = []
    for t in chosen.terms:
        other = next((r for r in runner.terms if r["name"] == t["name"]), None)
        if other is None:
            continue
        diffs.append({"name": t["name"], "chosen": t["value"], "other": other["value"], "diff": round(other["value"] - t["value"], 3)})
    diffs.sort(key=lambda r: -r["diff"])
    return {"runner": runner.label, "runner_key": runner.key, "margin": round(runner.total - chosen.total, 3), "terms": diffs}


def _sentence(car, chosen: Candidate, runner: Candidate | None, verdict, shield) -> tuple[str, str | None, str]:
    b = chosen.binding
    v = car.speed
    badge = None
    meta = {"keep": "KEEP", "left": "LEFT", "right": "RIGHT", "center": "CENTER", "abort": "ABORT"}[chosen.key]
    lead = next((c for c in chosen.constraints if c.kind == "car"), None)
    if chosen.key in ("left", "right") and chosen.evasion:
        main = f"{chosen.label} to avoid a person on the path"
        badge = "Evading"
    elif chosen.key == "center":
        main = f"Crossing the center line to pass {lead.name if lead else 'the stalled cars'} (stalled)"
        badge = "Passing on center line"
    elif chosen.key in ("left", "right") and car.lane == -1:
        main = "Returning from the center line to the lane"
        badge = "Overtaking"
    elif chosen.key in ("left", "right"):
        keep_lead = None
        if runner is not None and runner.key == "keep":
            keep_lead = next((c for c in runner.constraints if c.kind == "car"), None)
        if chosen.mobil and chosen.mobil.get("mandatory") and chosen.mobil.get("bias", 0) > 0:
            main = f"{chosen.label} for the route: the {MANEUVER_TEXT.get(_next_man(car), 'turn')} needs lane {chosen.lane}"
            badge = "Changing lanes"
        elif keep_lead is not None:
            main = f"{chosen.label} to pass {keep_lead.name} ({keep_lead.reason}, {keep_lead.lead_v:.1f} m/s)"
            badge = "Overtaking"
        else:
            main = f"{chosen.label}"
            badge = "Changing lanes"
    elif b is None:
        main = f"Cruising toward {car.dest_label or 'the exit'} at {v:.1f} m/s; nothing ahead limits speed"
    elif b.kind == "stop_line":
        main = f"Stopping for the {b.reason} at {b.name.replace(' stop line', '')}: {b.gap:.1f} m to the line, IDM {b.idm.a:+.1f} m/s²"
        badge = "Stopping for red" if verdict and verdict["color"] == "red" else ("Stopping for yellow" if verdict and verdict["color"] == "yellow" else "Stopping")
    elif b.kind == "yield":
        main = f"Yielding to {b.name}. {b.reason}"
        badge = "Waiting for gap" if "Permissive" in b.reason else "Yielding"
    elif b.kind == "ped":
        main = f"Stopping for {b.name.lower()} {b.reason}, {b.gap:.1f} m ahead"
        badge = "Pedestrian"
    elif b.kind == "box_exit":
        main = f"Waiting at the line: {b.reason}, so entering would block the box"
        badge = "Box blocked"
    elif b.kind == "goal":
        main = f"Pulling up at the destination, {b.gap:.1f} m to go"
    else:
        s_star = b.idm.s_star if b.idm and b.idm.s_star is not None else 0.0
        main = f"Following {b.name} ({b.reason}) at {b.gap:.1f} m; IDM wants {s_star:.1f} m"
        if b.reason in ("stalled", "crashed") and chosen.key == "keep":
            why = "no lane change is open" if runner is None else "see Options for why no lane change"
            main += f"; waiting ({why})"
            badge = "Blocked"
    if shield and shield.get("acted"):
        main += ". Shield: " + shield["text"]
    tail = ""
    if runner is not None:
        cmp = _compare(chosen, runner)
        if cmp and cmp["terms"]:
            top = cmp["terms"][0]
            if top["diff"] > 0.01:
                tail = f" {runner.label} costs {cmp['margin']:.2f} more, mostly {top['name'].lower()} (+{top['diff']:.2f})."
    return main + "." + tail, badge, meta


def _next_man(car) -> str | None:
    from sim.routes import maneuvers

    mans = maneuvers(car.route)
    return mans[car.route_i] if car.route_i < len(mans) else None
