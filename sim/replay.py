"""Replay stores the seed, the policy ids, and {tick, command}."""

from __future__ import annotations

from collections import defaultdict


def replay(log: dict, steps: int | None = None):
    """Rebuild the town and reapply commands at the same ticks. Positions match."""
    from sim.world import World

    world = World(seed=int(log["seed"]), fleet="town", load_policies=True)
    by_tick: dict[int, list] = defaultdict(list)
    for entry in log["commands"]:
        by_tick[int(entry["tick"])].append(entry["command"])
    total = int(log["steps"] if steps is None else steps)
    for n in range(total):
        for command in by_tick.get(n, []):
            world.apply(command, record=False)
        world.step()
    return world


def seek(log: dict, index: int):
    """Reset and reapply the log through one surprise, then stop on that tick."""
    from sim.world import World

    commands = list(log["commands"])
    if index < 0 or index >= len(commands):
        return World(seed=int(log["seed"]), fleet="town", load_policies=True)
    target = int(commands[index]["tick"])
    world = World(seed=int(log["seed"]), fleet="town", load_policies=True)
    by_tick: dict[int, list] = defaultdict(list)
    for i, entry in enumerate(commands):
        if i > index:
            break
        by_tick[int(entry["tick"])].append(entry["command"])
    for n in range(target):
        for command in by_tick.get(n, []):
            world.apply(command, record=True)
        world.step()
    for command in by_tick.get(target, []):
        world.apply(command, record=True)
    return world
