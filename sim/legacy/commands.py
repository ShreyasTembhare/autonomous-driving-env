"""Live surprises. A command changes the running town and is stored for replay."""

from __future__ import annotations

import math

from sim.legacy.actors import Pedestrian
from sim.geom import APPROACH_OF_AXIS, DRY_ACCEL, DT, HALF_LEN, STOP_LINE, WET_ACCEL, pose, stopping_distance


def apply(world, cmd: dict, record: bool = True) -> str:
    op = cmd.get("op")
    stored = dict(cmd)
    if op == "flip":
        label = world.signal.flip()
    elif op == "all_red":
        label = world.signal.all_red()
    elif op == "restore":
        label = world.signal.restore()
    elif op == "jaywalk":
        label, stored = _jaywalk(world, stored)
    elif op == "stall":
        label, stored = _stall(world, stored)
    elif op == "cut_in":
        label, stored = _cut_in(world, stored)
    elif op == "wet":
        label, stored = _wet(world, stored)
    elif op == "hot_swap":
        label = _hot_swap(world, stored)
    else:
        label = f"Ignored {op}"
        record = False
    if record:
        world.log.append(
            {
                "tick": world.tick,
                "time": round(world.tick * DT, 2),
                "label": label,
                "command": stored,
            }
        )
    return label


def _jaywalk(world, cmd: dict) -> tuple[str, dict]:
    if "x0" in cmd and "y0" in cmd and "x1" in cmd and "y1" in cmd:
        path = [(float(cmd["x0"]), float(cmd["y0"])), (float(cmd["x1"]), float(cmd["y1"]))]
        approach = cmd.get("approach") or "west"
    else:
        approach, path = _plan_jaywalk(world, cmd.get("approach"))
    world.jay_seq += 1
    dx, dy = path[1][0] - path[0][0], path[1][1] - path[0][1]
    ped = Pedestrian(
        id=f"jay-{world.jay_seq}",
        kind="jaywalker",
        name="Jaywalker",
        x=path[0][0],
        y=path[0][1],
        heading=math.atan2(dy, dx),
        speed=1.7,
        path=path,
        moving=True,
        cruise=1.7,
    )
    world.peds.append(ped)
    # Keep the street readable if someone spams the button.
    jaywalkers = [p for p in world.peds if p.kind == "jaywalker"]
    if len(jaywalkers) > 4:
        drop = jaywalkers[0]
        world.peds = [p for p in world.peds if p.id != drop.id]
    stored = {
        "op": "jaywalk",
        "approach": approach,
        "x0": path[0][0],
        "y0": path[0][1],
        "x1": path[1][0],
        "y1": path[1][1],
    }
    return f"Jaywalk across the {approach} approach", stored


def _plan_jaywalk(world, approach: str | None) -> tuple[str, list[tuple[float, float]]]:
    best = None
    for car in world.cars:
        if car.crashed or car.stalled or car.simple:
            continue
        if not (-48 < car.s < -12):
            continue
        if best is None or car.s > best[0]:
            best = (car.s, car, APPROACH_OF_AXIS[car.axis])
    car = None
    if best is not None and approach is None:
        approach = best[2]
        car = best[1]
    elif best is not None and approach == best[2]:
        car = best[1]
    approach = approach or "west"
    brake = WET_ACCEL if world.wet else DRY_ACCEL
    return approach, _path_for(approach, car, brake)


def _crossing_s(car, brake: float) -> float:
    """Longitudinal s of the jaywalk, far enough to stop, still on the approach."""
    need = stopping_distance(car.speed, max(brake, 0.5)) + 6.0
    ahead = car.s + HALF_LEN + need
    far = STOP_LINE - 2.5
    near = car.s + HALF_LEN + 8.0
    return max(min(ahead, far), min(near, far))


def _path_for(approach: str, car, brake: float = DRY_ACCEL) -> list[tuple[float, float]]:
    if approach == "west":
        x = -18.0 if car is None or car.axis != "east" else _crossing_s(car, brake)
        return [(x, -9.2), (x, 9.2)]
    if approach == "east":
        x = 18.0 if car is None or car.axis != "west" else -_crossing_s(car, brake)
        return [(x, 9.2), (x, -9.2)]
    if approach == "south":
        y = -18.0 if car is None or car.axis != "north" else _crossing_s(car, brake)
        return [(-9.2, y), (9.2, y)]
    y = 18.0 if car is None or car.axis != "south" else -_crossing_s(car, brake)
    return [(9.2, y), (-9.2, y)]


def _stall(world, cmd: dict) -> tuple[str, dict]:
    car = world.car(cmd["car"]) if cmd.get("car") else None
    if car is None or car.crashed:
        approaching = [c for c in world.cars if not c.crashed and not c.stalled and c.s < -11]
        approaching.sort(key=lambda item: -item.s)
        car = approaching[0] if approaching else world.cars[0]
    car.stalled = True
    car.target_speed = 0.0
    return f"Stalled {car.name}", {"op": "stall", "car": car.id}


def _cut_in(world, cmd: dict) -> tuple[str, dict]:
    if cmd.get("car") and cmd.get("lane") is not None:
        car = world.car(cmd["car"])
        if car and not car.crashed:
            car.target_lane_index = int(cmd["lane"])
            return f"{car.name} cut into lane {int(cmd['lane'])}", {
                "op": "cut_in",
                "car": car.id,
                "lane": int(cmd["lane"]),
            }
        return "Cut-in had no car to move", {"op": "cut_in", "car": None, "lane": None}

    jules = world.car("jules")
    ada = world.car("ada")
    if (
        jules
        and ada
        and not jules.crashed
        and jules.axis == ada.axis
        and jules.lane_index != ada.lane_index
    ):
        jules.target_lane_index = ada.lane_index
        return "Jules cut into Ada's lane", {"op": "cut_in", "car": "jules", "lane": ada.lane_index}

    pairs = []
    for car in world.cars:
        if car.crashed:
            continue
        for other in world.cars:
            if other.id == car.id or other.crashed or other.axis != car.axis:
                continue
            if car.lane_index == other.lane_index:
                continue
            if car.s < other.s:
                pairs.append((other.s - car.s, car, other))
    pairs.sort(key=lambda item: item[0])
    if not pairs:
        return "No car had a gap to cut into", {"op": "cut_in", "car": None, "lane": None}
    _, cutter, target = pairs[0]
    cutter.target_lane_index = target.lane_index
    return f"{cutter.name} cut into {target.name}'s lane", {
        "op": "cut_in",
        "car": cutter.id,
        "lane": target.lane_index,
    }


def _wet(world, cmd: dict) -> tuple[str, dict]:
    world.wet = bool(cmd["on"]) if "on" in cmd else (not world.wet)
    label = "Wet pavement" if world.wet else "Pavement dried"
    return label, {"op": "wet", "on": world.wet}


def _hot_swap(world, cmd: dict) -> str:
    from sim.policies import load_checkpoint

    model = load_checkpoint(cmd["checkpoint"], force=True)
    name = cmd.get("name") or str(cmd["checkpoint"]).rsplit("/", 1)[-1].replace(".zip", "")
    for car in world.cars:
        if car.brain == cmd.get("mix"):
            car.model = model
            car.checkpoint = name
            car.uses_network = True
    mix = cmd.get("mix", "learned")
    return f"Driving the new {mix} weights"


def place(axis: str, lane: int, s: float):
    return pose(axis, lane, s)
