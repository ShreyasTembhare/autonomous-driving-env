"""The crossing's contract: red lights, cones, replay, and one frame per car."""

from __future__ import annotations

import math

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


class pytest_close:
    """Tiny stand-in so the assertion reads as a comparison."""

    def __init__(self, value: float, tol: float = 1e-4):
        self.value = value
        self.tol = tol

    def __eq__(self, other: object) -> bool:
        return isinstance(other, (int, float)) and abs(float(other) - self.value) <= self.tol
