"""Shared geometry for the one intersection."""

from __future__ import annotations

import math

DT = 0.1
LANE_W = 3.5
CAR_LENGTH = 4.5
CAR_WIDTH = 1.8
HALF_LEN = CAR_LENGTH / 2
HALF_WID = CAR_WIDTH / 2
# Longitudinal coordinate s grows in the direction of travel. s = 0 is the
# middle of the intersection. The stop line sits at s = -11.
STOP_LINE = -11.0
BOX = 7.0
ROAD_EDGE = 7.0
# Crosswalk centerline, just outside the intersection box and in front of the stop line.
CROSSWALK = 8.6
RANGE = 36.0
HALF_ANGLE = math.radians(42)
MAX_STEER = math.radians(45)
DRY_ACCEL = 5.0
WET_ACCEL = 3.0
WHEELBASE = 2.5
MAX_SPEED = 16.0
HISTORY = 50
PED_TTC = 1.6
CAR_TTC = 1.4
PED_STOP_MARGIN = 4.0
CAR_FOLLOW_MARGIN = 4.0
LANE_HALF = 1.8
BOX_CLEAR = 18.0

# Lane index 0 is the right lane, 1 is the left. The value is the fixed
# coordinate: y for east/west traffic, x for north/south.
LATERAL: dict[str, dict[int, float]] = {
    "east": {0: -5.25, 1: -1.75},
    "west": {0: 5.25, 1: 1.75},
    "north": {0: -5.25, 1: -1.75},
    "south": {0: 5.25, 1: 1.75},
}

HEADING: dict[str, float] = {
    "east": 0.0,
    "west": math.pi,
    "north": math.pi / 2,
    "south": -math.pi / 2,
}

# Signal head a driver on this axis is looking at, placed on the stop line.
SIGNAL_POS: dict[str, tuple[float, float]] = {
    "east": (-11.0, -3.5),
    "west": (11.0, 3.5),
    "north": (-3.5, -11.0),
    "south": (3.5, 11.0),
}

ACTIONS = ["LANE_LEFT", "IDLE", "LANE_RIGHT", "FASTER", "SLOWER"]

ACTION_LABEL = {
    "LANE_LEFT": "Lane left",
    "IDLE": "Hold",
    "LANE_RIGHT": "Lane right",
    "FASTER": "Faster",
    "SLOWER": "Slower",
}

APPROACH_OF_AXIS = {"east": "west", "west": "east", "north": "south", "south": "north"}


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def pose(axis: str, lane: int, s: float) -> tuple[float, float, float]:
    lat = LATERAL[axis][lane]
    heading = HEADING[axis]
    if axis == "east":
        return s, lat, heading
    if axis == "west":
        return -s, lat, heading
    if axis == "north":
        return lat, s, heading
    return lat, -s, heading


def measure_s(axis: str, x: float, y: float) -> float:
    if axis == "east":
        return x
    if axis == "west":
        return -x
    if axis == "north":
        return y
    return -y


def lateral_of(axis: str, x: float, y: float) -> float:
    return y if axis in ("east", "west") else x


def left_error(axis: str, x: float, y: float, target_lat: float) -> float:
    """Positive when the car sits to the left of the target line."""
    if axis == "east":
        return y - target_lat
    if axis == "west":
        return target_lat - y
    if axis == "north":
        return target_lat - x
    return x - target_lat


def forward(heading: float) -> tuple[float, float]:
    return math.cos(heading), math.sin(heading)


def left_normal(heading: float) -> tuple[float, float]:
    return -math.sin(heading), math.cos(heading)


def rel_point(x: float, y: float, heading: float, px: float, py: float) -> tuple[float, float]:
    dx, dy = px - x, py - y
    fx, fy = forward(heading)
    lx, ly = left_normal(heading)
    return dx * fx + dy * fy, dx * lx + dy * ly


def in_cone(rx: float, ry: float, reach: float = RANGE, half: float = HALF_ANGLE) -> bool:
    if rx <= 0.2:
        return False
    if math.hypot(rx, ry) > reach:
        return False
    return abs(math.atan2(ry, rx)) <= half


def stopping_distance(speed: float, brake: float) -> float:
    if speed <= 0 or brake <= 0:
        return 0.0
    return (speed * speed) / (2.0 * brake)


def closing_distance(speed: float, lead_speed: float, brake: float) -> float:
    """Meters needed to match a slower lead, not a full stop."""
    if speed <= lead_speed or brake <= 0:
        return 0.0
    return (speed * speed - lead_speed * lead_speed) / (2.0 * brake)


def in_box(s: float) -> bool:
    """True while the car center is between the two stop lines."""
    return STOP_LINE < s < -STOP_LINE


def dist_to_stop(s: float) -> float:
    """Meters from the front bumper to the stop line. Negative once past it."""
    return STOP_LINE - (s + HALF_LEN)
