"""Social scores, learned logits, a narrow safety filter, and the low-level controllers."""

from __future__ import annotations

import math

from sim.actors import Car
from sim.geom import (
    ACTION_LABEL,
    ACTIONS,
    CAR_TTC,
    DRY_ACCEL,
    HEADING,
    LATERAL,
    MAX_SPEED,
    MAX_STEER,
    PED_TTC,
    WET_ACCEL,
    left_error,
    wrap,
)
from sim.kinematics import step_bicycle
from sim.perception import Sense, sense

BRAINS = {
    "cautious": {"desired": 8.0, "gap": 14.0, "patience": 0.15, "label": "Cautious"},
    "impatient": {"desired": 13.5, "gap": 5.5, "patience": 0.9, "label": "Impatient"},
    "careful": {"desired": 8.5, "gap": 12.0, "patience": 0.25, "label": "Careful"},
    "hurried": {"desired": 14.0, "gap": 5.0, "patience": 0.95, "label": "Hurried"},
}


def accel_limit(world) -> float:
    return WET_ACCEL if world.wet else DRY_ACCEL


def controls(car: Car, hazard: bool, limit: float) -> tuple[float, float]:
    h_err = wrap(HEADING[car.axis] - car.heading)
    target_lat = LATERAL[car.axis][car.target_lane_index]
    lat_err = left_error(car.axis, car.x, car.y, target_lat)
    steer = 1.7 * h_err - math.atan2(0.9 * lat_err, car.speed + 2.0)
    steer = max(-MAX_STEER, min(MAX_STEER, steer))
    if hazard or (car.target_speed <= 0.15 and car.speed > 0.3):
        accel = -limit
    else:
        accel = max(-limit, min(limit, 2.0 * (car.target_speed - car.speed)))
    return accel, steer


def commit_action(car: Car, action: str, hazard: bool) -> None:
    style = BRAINS.get(car.brain, BRAINS["cautious"])
    cap = min(MAX_SPEED, style["desired"] + 2.0)
    if action == "FASTER" and not hazard:
        car.target_speed = min(cap, car.target_speed + 2.0)
    elif action == "SLOWER":
        car.target_speed = 0.0 if hazard else max(0.0, car.target_speed - 2.0)
    elif action == "IDLE" and car.target_speed > cap:
        car.target_speed = cap
    elif action == "LANE_LEFT" and car.lane_index < 1:
        car.target_lane_index = car.lane_index + 1
    elif action == "LANE_RIGHT" and car.lane_index > 0:
        car.target_lane_index = car.lane_index - 1


def apply_forced(world, car: Car, action: str) -> tuple[float, float]:
    """Training path: the action is the policy, with no safety filter."""
    commit_action(car, action, hazard=False)
    accel, steer = controls(car, hazard=False, limit=accel_limit(world))
    car.accel = accel
    car.steer = steer
    return accel, steer


def simple_drive(world, car: Car) -> tuple[float, float]:
    """Scripted background car used while a policy is training."""
    color = world.signal.color_for_axis(car.axis)
    dist = world_dist(car)
    limit = accel_limit(world)
    stop_for = color == "red" and dist > 0 and dist < (car.speed ** 2) / (2.0 * max(limit, 0.5)) + 6.0
    if stop_for:
        car.target_speed = 0.0
    elif color == "yellow" and 0 < dist < 16:
        car.target_speed = min(car.target_speed, 4.0)
    else:
        car.target_speed = car.cruise
    accel, steer = controls(car, hazard=stop_for and car.speed > 0.2, limit=limit)
    return accel, steer


def world_dist(car: Car) -> float:
    from sim.geom import dist_to_stop

    return dist_to_stop(car.s)


def decide(world, car: Car, commit: bool = True) -> tuple[float, float, dict]:
    limit = accel_limit(world)
    view = sense(world, car)
    if car.crashed:
        frame = _frame(car, view, "CRASHED", "CRASHED", {}, None, None, [], 0.0, 0.0, limit, None, None)
        frame["sentence"] = "Crashed and stopped."
        frame["meta_action"] = "CRASHED"
        return 0.0, 0.0, frame
    if car.stalled:
        accel = -limit if car.speed > 0.2 else 0.0
        frame = _frame(car, view, "STALLED", "STALLED", {}, None, None, [], accel, 0.0, limit, None, None)
        frame["sentence"] = "Stalled in the lane. This car is not choosing a move."
        frame["meta_action"] = "STALLED"
        return accel, 0.0, frame

    saved_speed = car.target_speed
    saved_lane = car.target_lane_index
    raw, scores, probs, value = preference(car, view)
    wanted, unavailable_note = _best_available(raw, scores, view)
    chose, filter_info, constraints, hazard = _filter(wanted, view, car, world)
    if unavailable_note:
        constraints.append(unavailable_note)
    if world.wet:
        constraints.append("Wet pavement: accel and brake capped at 3 m/s²")
    commit_action(car, chose, hazard)
    accel, steer = controls(car, hazard, limit)
    shown_target = car.target_speed
    if not commit:
        car.target_speed = saved_speed
        car.target_lane_index = saved_lane
    frame = _frame(
        car,
        view,
        wanted,
        chose,
        scores,
        probs,
        value,
        constraints,
        accel,
        steer,
        limit,
        filter_info,
        shown_target,
    )
    return accel, steer, frame


def preference(car: Car, view: Sense):
    if car.uses_network and car.model is not None:
        return network_preference(car.model, view.vector)
    scores = social_scores(car, view)
    available = [action for action in ACTIONS if _available(action, view)]
    wanted = max(available, key=lambda action: scores[action])
    return wanted, scores, None, None


def network_preference(model, vector):
    """Indirection so a test can substitute the network without loading a checkpoint."""
    from sim import policies

    return policies.network_preference(model, vector)


def social_scores(car: Car, view: Sense) -> dict[str, float]:
    style = BRAINS.get(car.brain, BRAINS["cautious"])
    desired = style["desired"]
    gap_pref = style["gap"]
    patience = style["patience"]
    gap = view.gap_here
    speed = car.speed
    color = view.signal_color
    before = view.before_stop
    yellow_left = getattr(getattr(car, "_signal_remaining", None), "real", None)

    s_fast = 0.35 * (desired - speed)
    s_slow = 0.22 * (speed - desired)
    s_idle = 0.45
    if gap < gap_pref:
        pressure = (gap_pref - gap) / gap_pref
        s_fast -= 1.6 * pressure
        s_slow += 1.3 * pressure
        s_idle -= 0.35 * pressure
    if abs(speed - desired) < 1.2 and gap > gap_pref * 0.85 and color == "green":
        s_idle += 0.75
    if color == "green":
        s_fast += 0.25
    if color == "red" and before:
        # Far from the line, keep rolling. Brake once the stopping distance is close.
        from sim.geom import stopping_distance

        window = stopping_distance(speed, 5.0) + 8.0
        if view.dist_stop < window:
            s_fast -= 4.0
            s_idle -= 1.6
            s_slow += 4.0
        else:
            if speed > 9.0:
                s_fast -= 1.0
                s_slow += 0.6
            s_idle += 0.35
    if color == "yellow" and before:
        # Clear the far side of the box, not just the stop line. Patience buys a
        # little extra time; it does not let a driver ignore a yellow they cannot make.
        time_to_clear = (max(view.dist_stop, 0.0) + 18.0) / max(speed, 1.0)
        slack = view.phase_remaining + patience * 1.2
        if time_to_clear > slack:
            # Patience already widened the slack. Missing the yellow means stop.
            s_fast -= 4.2
            s_slow += 4.2
            s_idle -= 1.6
        else:
            s_fast += 1.3 * patience
            s_slow -= 0.5 * patience
    if speed < 0.4 and car.target_speed < 0.4 and color != "red":
        s_slow -= 0.8
        s_fast += 0.4

    scores = {"FASTER": s_fast, "SLOWER": s_slow, "IDLE": s_idle, "LANE_LEFT": -10.0, "LANE_RIGHT": -10.0}
    if view.can_left and view.gap_left is not None:
        scores["LANE_LEFT"] = _lane_score(view.gap_left, gap, gap_pref, patience)
    if view.can_right and view.gap_right is not None:
        scores["LANE_RIGHT"] = _lane_score(view.gap_right, gap, gap_pref, patience)
    _ = yellow_left
    return scores


def _lane_score(target_gap: float, current_gap: float, preferred: float, patience: float) -> float:
    score = -0.15
    if target_gap > current_gap + 4:
        score += 0.9
    if current_gap < preferred and target_gap > preferred:
        score += 1.1
    if target_gap < 6:
        score -= 2.2
    score += (patience - 0.5) * 0.25
    return score


def _available(action: str, view: Sense) -> bool:
    if action == "LANE_LEFT":
        return view.can_left
    if action == "LANE_RIGHT":
        return view.can_right
    return True


def _best_available(raw: str, scores: dict[str, float], view: Sense) -> tuple[str, str | None]:
    if _available(raw, view):
        return raw, None
    reason = view.left_reason if raw == "LANE_LEFT" else view.right_reason
    ranked = sorted(ACTIONS, key=lambda action: scores.get(action, -1e9), reverse=True)
    for action in ranked:
        if _available(action, view):
            note = f"{ACTION_LABEL[raw]} is not available"
            if reason:
                note = f"{note}. {reason}"
            return action, note
    return "IDLE", "No move is available"


def _filter(wanted: str, view: Sense, car: Car, world) -> tuple[str, dict | None, list[str], bool]:
    constraints: list[str] = []
    reason = None
    chose = wanted
    hazard = False
    if view.ped_ttc is not None and view.ped_ttc < PED_TTC:
        text = f"pedestrian time-to-collision {view.ped_ttc:.1f}s"
        constraints.append(f"Pedestrian time-to-collision {view.ped_ttc:.1f}s")
        hazard = True
        if wanted != "SLOWER":
            chose = "SLOWER"
            reason = text
    elif view.car_ttc is not None and view.car_ttc < CAR_TTC:
        text = f"vehicle time-to-collision {view.car_ttc:.1f}s"
        constraints.append(f"Vehicle time-to-collision {view.car_ttc:.1f}s")
        hazard = True
        if wanted != "SLOWER":
            chose = "SLOWER"
            reason = text
    limit = accel_limit(world)
    from sim.geom import STOP_LINE, stopping_distance

    # The center of the car is the point that has "entered". A bumper that has
    # just crossed still has to finish the stop; releasing the brake there is
    # how a car rolls through on red.
    center_before = car.s < STOP_LINE + 0.3
    need = stopping_distance(car.speed, limit) + 6.0
    close = view.dist_stop < 4.0 and car.speed > 0.35
    creeping = view.dist_stop < 1.0 and center_before
    if view.signal_color == "red" and center_before and (view.dist_stop < need or close or creeping):
        constraints.append("Red light before the stop line")
        hazard = True
        if chose != "SLOWER":
            chose = "SLOWER"
            reason = reason or "red light before the stop line"
    info = None
    if reason is not None and chose != wanted:
        info = {"wanted": wanted, "chose": chose, "reason": reason}
    return chose, info, constraints, hazard


def _frame(
    car: Car,
    view: Sense,
    wanted: str,
    chose: str,
    scores: dict,
    probs,
    value,
    constraints: list[str],
    accel: float,
    steer: float,
    limit: float,
    filter_info: dict | None,
    target_speed: float | None,
) -> dict:
    options = []
    for action in ACTIONS:
        available = _available(action, view) if action in ("LANE_LEFT", "LANE_RIGHT") or scores else _available(action, view)
        reason = None
        if action == "LANE_LEFT" and not view.can_left:
            available = False
            reason = view.left_reason
        elif action == "LANE_RIGHT" and not view.can_right:
            available = False
            reason = view.right_reason
        else:
            available = True
        score = scores.get(action) if scores else None
        if score is not None and not available and not car.uses_network:
            score = None
        options.append(
            {
                "action": action,
                "label": ACTION_LABEL[action],
                "available": available,
                "reason": reason,
                "score": None if score is None else round(float(score), 3),
                "chosen": action == chose and chose in ACTION_LABEL,
                "wanted": action == wanted and wanted in ACTION_LABEL,
            }
        )
    sentence = _sentence(car, wanted, chose, filter_info, view)
    model = _model_section(car, view, probs, value)
    return {
        "sentence": sentence,
        "brain": car.brain,
        "brain_label": BRAINS.get(car.brain, {}).get("label", car.brain.title()),
        "checkpoint": car.checkpoint,
        "uses_network": bool(car.uses_network and car.model is not None),
        "meta_action": chose if chose in ACTION_LABEL or chose in ("CRASHED", "STALLED") else "IDLE",
        "wanted": wanted,
        "seen": view.seen,
        "hidden_count": view.hidden_count,
        "constraints": constraints,
        "options": options,
        "filter": filter_info,
        "accel": round(float(accel), 3),
        "steering_deg": round(math.degrees(steer), 2),
        "target_speed": round(float(car.target_speed if target_speed is None else target_speed), 3),
        "limits": {
            "accel_min": -limit,
            "accel_max": limit,
            "steer_deg": round(math.degrees(MAX_STEER), 1),
            "wet": limit < DRY_ACCEL - 0.1,
        },
        "model": model,
        "cone": {"range": 36.0, "half_angle": round(math.radians(42), 4)},
        "history": [],
    }


def _sentence(car: Car, wanted: str, chose: str, filter_info: dict | None, view: Sense) -> str:
    if car.crashed:
        return "Crashed and stopped."
    if car.stalled:
        return "Stalled in the lane. This car is not choosing a move."
    if filter_info is not None:
        return f"wanted {filter_info['wanted']}, filter chose {filter_info['chose']}, {filter_info['reason']}."
    color = view.signal_color
    if chose == "FASTER":
        if color == "yellow":
            return "Speeding up on the yellow. This driver is willing to enter."
        if color == "green":
            return "Speeding up. The light ahead is green."
        return "Speeding up toward the set speed."
    if chose == "SLOWER":
        if color == "red":
            return "Slowing for the red light before the stop line."
        if color == "yellow":
            return "Slowing for the yellow light."
        if view.gap_here < 12:
            return "Slowing for the gap ahead."
        return "Easing off the speed."
    if chose == "LANE_LEFT":
        return "Moving to the left lane. The gap there is longer."
    if chose == "LANE_RIGHT":
        return "Moving to the right lane."
    if color == "green":
        return "Holding pace. The light is green and the lane is clear."
    if color == "red":
        return "Holding. The light ahead is red."
    if color == "yellow":
        return "Holding pace through the yellow."
    return "Holding pace. No signal in view."


def _model_section(car: Car, view: Sense, probs, value) -> dict:
    label = BRAINS.get(car.brain, {}).get("label", car.brain.title())
    seed = "\u2014" if car.seed is None else str(car.seed)
    if car.uses_network and car.model is not None and probs is None:
        return {
            "loaded": True,
            "mix": car.brain,
            "seed": car.seed,
            "checkpoint": car.checkpoint,
            "text": (
                f"{label}, seed {seed}. PPO with two hidden layers of 64. "
                "This car is not scoring a move right now."
            ),
        }
    if not car.uses_network or car.model is None:
        return {
            "loaded": False,
            "mix": car.brain,
            "text": (
                f"No network. {car.name} is driving with {label} rules: "
                "desired speed, following gap, and how readily they enter on yellow."
            ),
        }
    return {
        "loaded": True,
        "mix": car.brain,
        "seed": car.seed,
        "checkpoint": car.checkpoint,
        "text": (
            f"{label}, seed {seed}. PPO with two hidden layers of 64. "
            "The rows below are the observation this car just scored."
        ),
        "groups": view.groups,
        "probs": [
            {"action": action, "label": ACTION_LABEL[action], "p": round(float(probs[action]), 4)}
            for action in ACTIONS
        ],
        "value": round(float(value), 3),
    }


def integrate(car: Car, accel: float, steer: float, limit: float) -> None:
    accel = max(-limit, min(limit, accel))
    if car.crashed:
        car.speed = 0.0
        car.accel = 0.0
        car.steer = 0.0
        return
    car.x, car.y, car.heading, car.speed = step_bicycle(car.x, car.y, car.heading, car.speed, accel, steer)
    car.accel = accel
    car.steer = steer
