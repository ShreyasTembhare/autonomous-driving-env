"""Phase cycle for the crossing. North–south, then east–west, with a yellow between."""

from __future__ import annotations

GREEN_TICKS = 120
YELLOW_TICKS = 30
SHORT_YELLOW = 10

PHASE_LABEL = {
    "ns_green": "North–south green",
    "ns_yellow": "North–south yellow",
    "ew_green": "East–west green",
    "ew_yellow": "East–west yellow",
    "all_red": "All red",
}

_ORDER = ["ns_green", "ns_yellow", "ew_green", "ew_yellow"]


class Signal:
    def __init__(self) -> None:
        self.phase = "ns_green"
        self.remaining = GREEN_TICKS
        self.queue: str | None = None
        self.held = "ns_green"
        self.held_remaining = GREEN_TICKS
        self.axis = "ns"
        self.green_gen = 1

    def color_for_axis(self, axis: str) -> str:
        north_south = axis in ("north", "south")
        if self.phase == "all_red":
            return "red"
        if self.phase == "ns_green":
            return "green" if north_south else "red"
        if self.phase == "ns_yellow":
            return "yellow" if north_south else "red"
        if self.phase == "ew_green":
            return "green" if not north_south else "red"
        if self.phase == "ew_yellow":
            return "yellow" if not north_south else "red"
        return "red"

    def approach_colors(self) -> dict[str, str]:
        # The lamp on an approach faces the traffic coming from that side.
        return {
            "north": self.color_for_axis("south"),
            "south": self.color_for_axis("north"),
            "east": self.color_for_axis("west"),
            "west": self.color_for_axis("east"),
        }

    def advance(self) -> None:
        if self.phase == "all_red" and self.queue is None:
            return
        self.remaining -= 1
        if self.remaining > 0:
            return
        if self.queue:
            nxt = self.queue
            self.queue = None
            self._enter(nxt)
            return
        if self.phase in _ORDER:
            self._enter(_ORDER[(_ORDER.index(self.phase) + 1) % 4])
        else:
            self._enter(self.held or "ns_green")

    def _enter(self, phase: str) -> None:
        self.phase = phase
        if phase.endswith("green"):
            self.remaining = GREEN_TICKS
            self.green_gen += 1
            self.axis = "ns" if phase.startswith("ns") else "ew"
        elif phase.endswith("yellow"):
            self.remaining = YELLOW_TICKS
            self.axis = "ns" if phase.startswith("ns") else "ew"
        else:
            self.remaining = 10**9

    def flip(self) -> str:
        """Short yellow, then the other axis. Does not reset the town."""
        if self.phase == "all_red":
            other = "ew" if self.axis == "ns" else "ns"
            self.remaining = SHORT_YELLOW
            self.queue = f"{other}_green"
            return "Flipped toward the other axis"
        axis = "ns" if self.phase.startswith("ns") else "ew"
        other = "ew" if axis == "ns" else "ns"
        self.phase = f"{axis}_yellow"
        self.remaining = SHORT_YELLOW
        self.queue = f"{other}_green"
        self.axis = axis
        return "Flipped the green"

    def all_red(self) -> str:
        if self.phase != "all_red":
            self.held = self.phase
            self.held_remaining = self.remaining
        self.queue = None
        self.phase = "all_red"
        self.remaining = 10**9
        return "All red"

    def restore(self) -> str:
        self.queue = None
        if self.phase == "all_red":
            phase = self.held or "ns_green"
            self.phase = phase
            self.remaining = max(10, self.held_remaining or GREEN_TICKS)
            if phase.startswith("ns"):
                self.axis = "ns"
            elif phase.startswith("ew"):
                self.axis = "ew"
        return "Restored the cycle"

    def set_phase(self, phase: str, remaining: int) -> None:
        self.queue = None
        self.phase = phase
        self.remaining = remaining
        if phase.startswith("ns"):
            self.axis = "ns"
        elif phase.startswith("ew"):
            self.axis = "ew"
        else:
            self.held = "ns_green"
