"""Live commands: surprises and trips. Each one is stored with resolved values for replay."""

from __future__ import annotations

import math

from sim.actors import Pedestrian
from sim.geom import DT, stopping_distance
from sim.idm import STYLES, hard_limit, style_for
from sim.network import LANE_LAT, NETWORK
from sim.routes import describe, plan, resolve_place, route_length

TRIP_COLORS = ["#ffffff", "#22d3ee", "#f0abfc", "#bef264", "#fde047", "#fca5a5"]


class Rejected(Exception):
    pass


def apply(world, cmd: dict, record: bool = True) -> str:
    op = cmd.get("op")
    stored = dict(cmd)
    handlers = {
        "flip": _signal,
        "all_red": _signal,
        "restore": _signal,
        "jaywalk": _jaywalk,
        "stall": _stall,
        "unstall": _unstall,
        "cut_in": _cut_in,
        "wet": _wet,
        "hot_swap": _hot_swap,
        "spawn_trip": _spawn_trip,
        "set_destination": _set_destination,
        "remove_car": _remove_car,
        "fleet_size": _fleet_size,
    }
    handler = handlers.get(op)
    if handler is None:
        return f"Ignored {op}"
    try:
        label, stored = handler(world, stored)
    except Rejected as exc:
        world.notice(str(exc), "error")
        return f"Rejected: {exc}"
    if record:
        world.log.append({"tick": world.tick, "time": round(world.tick * DT, 2), "label": label, "command": stored})
    return label


# ---------------------------------------------------------------- signals


def _signal(world, cmd: dict):
    op = cmd["op"]
    node = cmd.get("node")
    nodes = [node] if node in world.signals else list(world.signals)
    label = ""
    for nid in nodes:
        sig = world.signals[nid]
        label = sig.flip() if op == "flip" else sig.all_red() if op == "all_red" else sig.restore()
    where = NETWORK.nodes[nodes[0]].name if len(nodes) == 1 else "all intersections"
    return f"{label} at {where}", {"op": op, "node": nodes[0] if len(nodes) == 1 else None}


# ---------------------------------------------------------------- surprises


def _pick_moving(world, cmd: dict, min_line: float = 18.0):
    car = world.car(cmd.get("car"))
    if car is not None and not car.arrived and not car.crashed:
        return car
    best = None
    for c in world.cars:
        if c.arrived or c.crashed or c.stalled or c.leg != "link":
            continue
        link = NETWORK.links[c.link]
        d_line = link.stop_s - c.s - c.length / 2
        if d_line < min_line or c.speed < 3.0:
            continue
        if best is None or c.speed > best.speed:
            best = c
    return best


def _jaywalk(world, cmd: dict):
    if all(k in cmd for k in ("x0", "y0", "x1", "y1")):
        path = [(float(cmd["x0"]), float(cmd["y0"])), (float(cmd["x1"]), float(cmd["y1"]))]
        target = cmd.get("car")
    else:
        car = _pick_moving(world, cmd, 14.0)
        if car is None or car.leg != "link":
            raise Rejected("No car is on a straight road to jaywalk in front of.")
        link = NETWORK.links[car.link]
        brake = hard_limit(world.wet)
        ahead = car.s + car.length / 2 + stopping_distance(car.speed, brake) + 6.0
        far = link.stop_s - 2.5
        near = car.s + car.length / 2 + 8.0
        s = max(min(ahead, far), min(near, far))
        path = [link.point(s, 9.2), link.point(s, -9.2)]
        target = car.id
    world.jay_seq += 1
    (x0, y0), (x1, y1) = path
    world.peds.append(
        Pedestrian(id=f"jay-{world.jay_seq}", kind="jaywalker", name="Jaywalker", x=x0, y=y0, heading=math.atan2(y1 - y0, x1 - x0), speed=1.7, path=path, moving=True, cruise=1.7)
    )
    jay = [p for p in world.peds if p.kind == "jaywalker"]
    if len(jay) > 4:
        world.peds = [p for p in world.peds if p.id != jay[0].id]
    name = world.car(target).name if world.car(target) else "traffic"
    return f"Jaywalker in front of {name}", {"op": "jaywalk", "car": target, "x0": x0, "y0": y0, "x1": x1, "y1": y1}


def _stall(world, cmd: dict):
    car = _pick_moving(world, cmd, 30.0)
    if car is None:
        raise Rejected("No moving car to stall.")
    car.stalled = True
    return f"Stalled {car.name}", {"op": "stall", "car": car.id}


def _unstall(world, cmd: dict):
    car = world.car(cmd.get("car"))
    cars = [car] if car is not None else [c for c in world.cars if c.stalled]
    if not cars:
        raise Rejected("No stalled car to restart.")
    for c in cars:
        c.stalled = False
    names = ", ".join(c.name for c in cars)
    return f"Restarted {names}", {"op": "unstall", "car": None if car is None else car.id}


def _cut_in(world, cmd: dict):
    if cmd.get("car") and cmd.get("lane") is not None:
        car = world.car(cmd["car"])
        lane = int(cmd["lane"])
        if car is None or car.crashed or car.leg != "link" or lane not in (0, 1):
            raise Rejected("That car cannot cut in right now.")
        _force_lane(world, car, lane)
        return f"{car.name} cut into lane {lane}", {"op": "cut_in", "car": car.id, "lane": lane}
    pairs = []
    for cutter in world.cars:
        if cutter.arrived or cutter.crashed or cutter.stalled or cutter.leg != "link" or cutter.lane not in (0, 1):
            continue
        for victim in world.cars:
            if victim is cutter or victim.arrived or victim.crashed or victim.leg != "link" or victim.link != cutter.link:
                continue
            if victim.lane == cutter.lane or victim.lane not in (0, 1):
                continue
            ahead = cutter.s - victim.s
            if 5.0 < ahead < 18.0:
                pairs.append((ahead, cutter, victim))
    sel = world.car(cmd.get("car"))
    if sel is not None:
        pairs = [p for p in pairs if sel in (p[1], p[2])] or pairs
    if not pairs:
        raise Rejected("No two cars are side by side to stage a cut-in.")
    pairs.sort(key=lambda p: (p[0], p[1].id))
    _, cutter, victim = pairs[0]
    _force_lane(world, cutter, victim.lane)
    return f"{cutter.name} cut in front of {victim.name}", {"op": "cut_in", "car": cutter.id, "lane": victim.lane}


def _force_lane(world, car, lane: int) -> None:
    car.target_lane = lane
    car.lane_lock = 30
    car.lc_start_tick = world.tick


def _wet(world, cmd: dict):
    world.wet = bool(cmd["on"]) if "on" in cmd else (not world.wet)
    return ("Wet pavement" if world.wet else "Pavement dried"), {"op": "wet", "on": world.wet}


def _hot_swap(world, cmd: dict):
    from sim.policies import load_checkpoint

    model = load_checkpoint(cmd["checkpoint"], force=True)
    name = cmd.get("name") or str(cmd["checkpoint"]).rsplit("/", 1)[-1].replace(".zip", "")
    for car in world.cars:
        if car.brain == cmd.get("mix"):
            car.model = model
            car.checkpoint = name
            car.uses_network = True
    return f"Driving the new {cmd.get('mix', 'learned')} weights", dict(cmd)


# ---------------------------------------------------------------- trips


def _place_from(world, spec, kind: str):
    if isinstance(spec, dict) and "link" in spec:
        link = str(spec["link"])
        if link not in NETWORK.links:
            raise Rejected("Unknown road.")
        from sim.routes import Place

        return Place(link, float(spec["s"]), spec.get("lane"), spec.get("label") or "")
    place, err = resolve_place(spec, kind, world)
    if place is None:
        raise Rejected(err or "Pick a place on the map.")
    return place


def _spawn_trip(world, cmd: dict):
    from sim.world import MAX_CARS

    if len(world.cars) >= MAX_CARS:
        raise Rejected(f"The town is full ({MAX_CARS} cars). Remove a car or lower the fleet size.")
    start = _place_from(world, cmd.get("start"), "start")
    dest = _place_from(world, cmd.get("dest"), "dest")
    if start.link == dest.link and abs(start.s - dest.s) < 10.0:
        raise Rejected("Start and destination are the same place.")
    if NETWORK.links[start.link].reverse == dest.link and NETWORK.nodes[NETWORK.links[start.link].frm].kind == "stub" and dest.s > NETWORK.links[dest.link].length - 3:
        raise Rejected("Start and destination are the same place.")
    style = cmd.get("style") or "careful"
    if style not in STYLES:
        style = "careful"
    res = plan(start.link, start.s, dest.link, dest.s, world=world)
    if not res.ok:
        raise Rejected(res.error or "No route reaches that destination.")
    need = None
    if len(res.links) > 1:
        from sim.routes import required_lane

        need = required_lane(res.links, 0)
    lane = cmd.get("lane")
    lane = int(lane) if lane in (0, 1) else (start.lane if start.lane in (0, 1) else (need if need is not None else 0))
    link = NETWORK.links[start.link]
    moved = None
    spot = None
    for ln in (lane, 1 - lane):
        for back in range(0, 61, 6):
            s = start.s - back
            if s < link.start_s + 1.0:
                break
            if _spot_clear(world, start.link, s, ln):
                spot = (s, ln)
                break
        if spot:
            break
    if spot is None:
        raise Rejected("No clear spot within 60 m of that start. Try another place.")
    if spot != (start.s, lane):
        moved = f"start moved {start.s - spot[0]:.0f} m upstream to a clear spot" if spot[0] != start.s else "start moved to the other lane"
    if spot[0] != start.s:
        res = plan(start.link, spot[0], dest.link, dest.s, world=world)
        if not res.ok:
            raise Rejected(res.error or "No route reaches that destination.")
    world.trip_seq += 1
    n = world.trip_seq
    car = world._new_car(f"trip-{n}", f"Trip {n}", TRIP_COLORS[(n - 1) % len(TRIP_COLORS)], style)
    car.user = True
    car.tracked = True
    st = style_for(style, world.wet)
    world._place_route(car, start.link, spot[0], spot[1], res, start.label, dest.label, min(5.0, st.v0))
    car.goal_stop = not _is_exit(dest)
    world.cars.append(car)
    world.last_spawned = car.id
    length = route_length(res.links, spot[0], res.goal_s)
    label = f"{car.name}: {start.label} to {dest.label}, {describe(res.links)}, {length:.0f} m"
    if moved:
        world.notice(f"{car.name}: {moved}.", "info", car.id)
    world.notice(f"{car.name} started: {describe(res.links)}, {length:.0f} m", "info", car.id)
    return label, {
        "op": "spawn_trip",
        "id": car.id,
        "start": {"link": start.link, "s": spot[0], "lane": spot[1], "label": start.label},
        "dest": {"link": dest.link, "s": dest.s, "label": dest.label},
        "style": style,
    }


def _is_exit(place) -> bool:
    link = NETWORK.links[place.link]
    return NETWORK.nodes[link.to].kind == "stub" and place.s >= link.length - 3.0


def _spot_clear(world, link_id: str, s: float, lane: int) -> bool:
    x, y = NETWORK.links[link_id].point(s, LANE_LAT[lane])
    for other in world.cars:
        if other.arrived:
            continue
        if math.hypot(other.x - x, other.y - y) < 9.0:
            return False
    return True


def _set_destination(world, cmd: dict):
    car = world.car(cmd.get("car"))
    if car is None or car.arrived:
        raise Rejected("Pick a car on the road first.")
    if car.crashed:
        raise Rejected(f"{car.name} has crashed and cannot drive anywhere.")
    dest = _place_from(world, cmd.get("dest"), "dest")
    if car.leg == "connector":
        conn = NETWORK.connectors[car.connector]
        base, start_s = conn.link_out, NETWORK.links[conn.link_out].start_s
        keep = car.route[: car.route_i + 1]
        note = "finishes the turn first"
    else:
        base, start_s = car.link, car.s
        keep = car.route[: car.route_i]
        note = None
    if base == dest.link and abs(dest.s - start_s) < 6.0:
        raise Rejected(f"{car.name} is already at that place.")
    allowed = None
    if car.leg == "link":
        link = NETWORK.links[base]
        if link.stop_s - start_s - car.length / 2 < 12.0:
            lane = car.target_lane if car.target_lane in (0, 1) else 1
            allowed = {lo for _m, lo in NETWORK.successors(base) if NETWORK.connector_for(base, lo, lane)}
            note = "too close to the line to change lanes, so it keeps a move this lane allows"
    res = plan(base, start_s, dest.link, dest.s, world=world, allowed_first=allowed)
    if not res.ok:
        raise Rejected(res.error or "No route reaches that destination.")
    car.route = keep + res.links
    car.goal_s = res.goal_s
    car.dest_label = dest.label
    car.goal_stop = not _is_exit(dest)
    car.tracked = True
    reason = "Destination changed by user" + (f"; {note}" if note else "")
    world._replanned(car, reason)
    world.notice(f"{car.name} now heads to {dest.label}: {describe(res.links)}", "info", car.id)
    return f"{car.name} re-routed to {dest.label}", {"op": "set_destination", "car": car.id, "dest": {"link": dest.link, "s": dest.s, "label": dest.label}}


def _remove_car(world, cmd: dict):
    car = world.car(cmd.get("car"))
    if car is None:
        raise Rejected("No such car.")
    if not car.user:
        raise Rejected("Only trip cars you added can be removed. Lower the fleet size instead.")
    world.cars = [c for c in world.cars if c is not car]
    return f"Removed {car.name}", {"op": "remove_car", "car": car.id}


def _fleet_size(world, cmd: dict):
    from sim.world import MAX_CARS, MIN_CARS

    n = max(MIN_CARS, min(MAX_CARS, int(cmd.get("value", world.target_size))))
    world.target_size = n
    background = [c for c in world.cars if not c.user]
    extra = len(background) - n
    if extra > 0:
        drop = sorted(background, key=lambda c: (c.named, c.id), reverse=False)
        # Remove unnamed cars first, newest first.
        unnamed = [c for c in drop if not c.named][::-1]
        named = [c for c in drop if c.named][::-1]
        gone = set(c.id for c in (unnamed + named)[:extra])
        world.cars = [c for c in world.cars if c.id not in gone]
    else:
        while len([c for c in world.cars if not c.user]) < n and len(world.cars) < MAX_CARS:
            if not world._add_background():
                break
    return f"Fleet size {n}", {"op": "fleet_size", "value": n}
