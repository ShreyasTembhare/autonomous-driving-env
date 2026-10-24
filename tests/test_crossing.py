"""The crossing's contract: red lights, cones, replay, and one frame per car."""

from __future__ import annotations

import math

import pytest

from sim.actors import Pedestrian
from sim.decision import network_preference
from sim.geom import HALF_LEN, STOP_LINE
from sim.perception import sense
from sim.replay import replay
from sim.world import World


def _park_others(world: World, keep: str) -> None:
    for car in world.cars:
        if car.id == keep:
            continue
        car.stalled = True
        car.speed = 0.0
        car.target_speed = 0.0
        x, y, heading = car.x, car.y, car.heading
        # Push them well behind their own stop line, out of the kept car's cone.
        car.s = -70.0
        from sim.geom import pose

        car.x, car.y, car.heading = pose(car.axis, car.lane_index, -70.0)
        _ = (x, y, heading)


def test_red_light_blocks_entry():
    world = World(seed=1, load_policies=False)
    world.apply({"op": "all_red"})
    _park_others(world, "rex")
    rex = world.car("rex")
    assert rex is not None
    from sim.geom import pose

    rex.stalled = False
    rex.x, rex.y, rex.heading = pose("north", rex.lane_index, -32)
    rex.s = -32.0
    rex.speed = 10.0
    rex.target_speed = 12.0
    rex.cruise = 12.0
    max_front = -999.0
    saw_red = False
    for _ in range(80):
        world.step()
        front = rex.s + HALF_LEN
        max_front = max(max_front, front)
        text = " ".join(rex.decision["constraints"]) + " " + rex.decision["sentence"]
        if "red light" in text.lower() or "red" in rex.decision["sentence"].lower():
            saw_red = True
    assert max_front < STOP_LINE + 0.25
    assert saw_red


def test_jaywalker_inside_cone_forces_brake(monkeypatch):
    def always_faster(_model, _vector):
        scores = {"LANE_LEFT": -1.0, "IDLE": -0.4, "LANE_RIGHT": -1.0, "FASTER": 2.4, "SLOWER": -0.3}
        probs = {name: math.exp(value) for name, value in scores.items()}
        total = sum(probs.values())
        probs = {name: value / total for name, value in probs.items()}
        return "FASTER", scores, probs, 0.2

    monkeypatch.setattr("sim.decision.network_preference", always_faster)
    assert network_preference is not None

    world = World(seed=2, load_policies=False)
    world.peds.clear()
    _park_others(world, "rex")
    rex = world.car("rex")
    assert rex is not None
    from sim.geom import pose

    rex.stalled = False
    rex.x, rex.y, rex.heading = pose("north", 1, -20)
    rex.s = -20.0
    rex.lane_index = 1
    rex.target_lane_index = 1
    rex.speed = 10.0
    rex.target_speed = 10.0
    rex.brain = "hurried"
    rex.uses_network = True
    rex.model = object()
    rex.checkpoint = "stub"
    rex.seed = 0
    jay = Pedestrian(
        id="jay-test",
        kind="jaywalker",
        name="Jaywalker",
        x=rex.x,
        y=rex.y + 12.0,
        heading=0.0,
        speed=0.0,
        path=[(rex.x, rex.y + 12.0), (rex.x + 8.0, rex.y + 12.0)],
        moving=False,
    )
    world.peds = [jay]
    world.step()
    frame = rex.decision
    seen_ids = {row["id"] for row in frame["seen"]}
    assert jay.id in seen_ids
    assert frame["filter"]["wanted"] == "FASTER"
    assert frame["filter"]["chose"] == "SLOWER"
    assert "pedestrian time-to-collision" in frame["filter"]["reason"]
    assert "wanted FASTER, filter chose SLOWER" in frame["sentence"]
    assert rex.accel < 0


def test_jaywalker_outside_cone_is_hidden():
    world = World(seed=3, load_policies=False)
    world.peds.clear()
    _park_others(world, "rex")
    rex = world.car("rex")
    assert rex is not None
    from sim.geom import pose

    rex.stalled = False
    rex.x, rex.y, rex.heading = pose("north", 1, -20)
    rex.s = -20.0
    rex.speed = 8.0
    rex.target_speed = 8.0
    # Far to the side: bearing is well outside the forward cone.
    jay = Pedestrian(
        id="jay-hidden",
        kind="jaywalker",
        name="Jaywalker",
        x=rex.x + 18.0,
        y=rex.y + 3.0,
        heading=0.0,
        speed=0.0,
        path=[(rex.x + 18.0, rex.y + 3.0), (rex.x + 18.0, rex.y + 12.0)],
        moving=False,
    )
    world.peds = [jay]
    world.step()
    frame = rex.decision
    seen_ids = {row["id"] for row in frame["seen"]}
    assert jay.id not in seen_ids
    view = sense(world, rex)
    assert jay.id in view.hidden_ids
    assert jay.id not in {row["id"] for row in view.seen}
    assert frame["hidden_count"] == view.hidden_count
    assert frame["hidden_count"] >= 1


def test_replay_matches_positions():
    world = World(seed=7, load_policies=True)
    world.apply({"op": "flip"})
    for i in range(40):
        if i == 12:
            world.apply({"op": "jaywalk", "approach": "west"})
        world.step()
    log = world.export_log()
    again = replay(log)
    assert again.tick == world.tick
    for car, other in zip(world.cars, again.cars, strict=True):
        assert car.id == other.id
        assert car.x == pytest_close(other.x)
        assert car.y == pytest_close(other.y)
        assert car.speed == pytest_close(other.speed)
    assert len(world.peds) == len(again.peds)
    for ped, other in zip(world.peds, again.peds, strict=True):
        assert ped.x == pytest_close(other.x)
        assert ped.y == pytest_close(other.y)


def test_snapshot_has_one_decision_frame_per_car():
    world = World(seed=7, load_policies=False)
    world.step()
    snap = world.snapshot()
    assert len(snap["cars"]) == 6
    frames = [car["decision"] for car in snap["cars"]]
    assert len(frames) == 6
    ids = [car["id"] for car in snap["cars"]]
    assert ids == ["ada", "rex", "mina", "theo", "jules", "nova"]
    for frame in frames:
        assert "sentence" in frame
        assert "seen" in frame
        assert "options" in frame
        assert "meta_action" in frame
        assert len(frame["options"]) == 5


def _solo(seed: int, car_id: str, axis: str, lane: int, s: float, speed: float, wet: bool = False):
    from sim.geom import pose

    world = World(seed=seed, load_policies=False)
    world.peds.clear()
    world.allow_respawn = False
    _park_others(world, car_id)
    car = world.car(car_id)
    car.stalled = False
    car.axis = axis
    car.lane_index = lane
    car.target_lane_index = lane
    car.x, car.y, car.heading = pose(axis, lane, s)
    car.s = s
    car.speed = speed
    car.target_speed = speed
    car.cruise = speed
    world.wet = wet
    world.signal.set_phase("ns_green", 10**6)
    return world, car


def _park(world: World, car, axis: str, lane: int, s: float) -> None:
    from sim.geom import pose

    car.axis = axis
    car.lane_index = lane
    car.target_lane_index = lane
    car.x, car.y, car.heading = pose(axis, lane, s)
    car.s = s
    car.speed = 0.0
    car.target_speed = 0.0


@pytest.mark.parametrize("wet", [False, True])
def test_jaywalk_in_front_of_fast_car_does_not_hit(wet):
    # Wet needs about 24 m to stop from 12 m/s, so it starts where Nova starts.
    world, rex = _solo(11, "rex", "north", 1, -48.0 if wet else -40.0, 12.0, wet=wet)
    rex.brain = "hurried"
    world.apply({"op": "jaywalk", "approach": "south"})
    for _ in range(150):
        world.step()
    assert not rex.hit_ped
    assert not any(p.hit for p in world.peds)


def test_stalled_lead_does_not_cause_crash():
    world, rex = _solo(12, "rex", "north", 1, -45.0, 12.0, wet=True)
    lead = world.car("nova")
    _park(world, lead, "north", 1, -12.0)
    world.apply({"op": "stall", "car": "nova"})
    for _ in range(160):
        world.step()
    assert not rex.crashed
    assert not lead.crashed


def test_cut_in_follower_brakes_before_lane_change_finishes():
    world, rex = _solo(13, "rex", "north", 1, -40.0, 11.0)
    cutter = world.car("nova")
    _park(world, cutter, "north", 0, -20.0)
    cutter.stalled = False
    cutter.speed = 5.0
    cutter.target_speed = 5.0
    world.apply({"op": "cut_in", "car": "nova", "lane": 1})
    first = None
    for _ in range(60):
        world.step()
        if first is None and rex.accel < 0:
            first = world.tick
        if cutter.lane_index == 1:
            break
    assert first is not None
    assert not rex.crashed and not cutter.crashed


def test_flip_cross_traffic_waits_for_box():
    world, ada = _solo(14, "ada", "east", 0, -30.0, 8.0)
    thru = world.car("rex")
    _park(world, thru, "north", 0, -4.0)
    thru.stalled = False
    thru.speed = 5.0
    thru.target_speed = 5.0
    world.signal.set_phase("ew_green", 10**6)
    entered_with_box_busy = False
    for _ in range(120):
        world.step()
        from sim.geom import in_box

        if in_box(thru.s) and in_box(ada.s):
            entered_with_box_busy = True
    assert not entered_with_box_busy
    assert not ada.crashed and not thru.crashed


def test_all_red_car_with_room_stops_before_line():
    from sim.geom import HALF_LEN

    world, rex = _solo(15, "rex", "north", 1, -38.0, 11.0)
    world.apply({"op": "all_red"})
    top = -999.0
    for _ in range(120):
        world.step()
        top = max(top, rex.s + HALF_LEN)
    assert top < STOP_LINE + 0.25


def test_car_already_in_box_clears_on_all_red():
    world, rex = _solo(16, "rex", "north", 1, -3.0, 8.0)
    world.apply({"op": "all_red"})
    for _ in range(80):
        world.step()
    assert rex.s > 8.0
    assert not rex.crashed


def test_pedestrian_inside_stopping_distance_is_not_hit():
    world, rex = _solo(17, "rex", "north", 1, -30.0, 14.0, wet=True)
    jay = Pedestrian(
        id="jay-close",
        kind="jaywalker",
        name="Jaywalker",
        x=rex.x - 6.0,
        y=rex.y + 14.0,
        heading=0.0,
        speed=1.7,
        path=[(rex.x - 6.0, rex.y + 14.0), (rex.x + 6.0, rex.y + 14.0)],
        moving=True,
        cruise=1.7,
    )
    world.peds = [jay]
    for _ in range(100):
        world.step()
    assert not jay.hit


class pytest_close:
    """Tiny stand-in so the assertion reads as a comparison."""

    def __init__(self, value: float, tol: float = 1e-4):
        self.value = value
        self.tol = tol

    def __eq__(self, other: object) -> bool:
        return isinstance(other, (int, float)) and abs(float(other) - self.value) <= self.tol
