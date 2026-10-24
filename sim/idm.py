"""Intelligent Driver Model and the driver styles that parameterize it.

a = a_max * [1 - (v / v0)^4 - (s* / s)^2]
s* = s0 + v*T + v*dv / (2*sqrt(a_max*b))
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace

DELTA = 4.0


@dataclass(frozen=True)
class Style:
    label: str
    v0: float
    T: float
    s0: float
    a_max: float
    b: float
    politeness: float
    b_safe: float
    gap_accept: float
    w_progress: float
    w_headway: float
    w_comfort: float

    def to_json(self) -> dict:
        return asdict(self)


STYLES: dict[str, Style] = {
    "cautious": Style("Cautious", 9.0, 1.8, 2.0, 1.6, 2.2, 0.5, 3.0, 5.0, 0.20, 3.0, 0.08),
    "careful": Style("Careful", 10.0, 1.5, 2.0, 1.8, 2.5, 0.4, 3.5, 4.5, 0.25, 2.5, 0.06),
    "impatient": Style("Impatient", 13.5, 1.0, 2.0, 2.4, 3.0, 0.1, 4.0, 3.5, 0.45, 1.0, 0.03),
    "hurried": Style("Hurried", 14.0, 0.9, 2.0, 2.6, 3.2, 0.05, 4.0, 3.5, 0.50, 0.8, 0.03),
}

DRY_HARD = 5.0
WET_HARD = 3.0


def style_for(brain: str, wet: bool) -> Style:
    base = STYLES.get(brain, STYLES["careful"])
    if not wet:
        return base
    return replace(
        base,
        a_max=round(base.a_max * 0.75, 3),
        b=round(min(base.b * 0.7, 2.2), 3),
        T=round(base.T * 1.3, 3),
        b_safe=round(min(base.b_safe, 2.5), 3),
        v0=round(base.v0 * 0.85, 3),
    )


def hard_limit(wet: bool) -> float:
    return WET_HARD if wet else DRY_HARD


@dataclass
class IdmResult:
    a: float
    free: float
    interaction: float
    s_star: float | None
    gap: float | None
    dv: float
    v0: float
    s0: float

    def to_json(self) -> dict:
        return {
            "a": round(self.a, 3),
            "free": round(self.free, 3),
            "interaction": round(self.interaction, 3),
            "s_star": None if self.s_star is None else round(self.s_star, 2),
            "gap": None if self.gap is None else round(self.gap, 2),
            "dv": round(self.dv, 2),
            "v0": round(self.v0, 2),
            "s0": round(self.s0, 2),
        }


def accel(v: float, v0: float, gap: float | None, lead_v: float, style: Style, s0: float | None = None) -> IdmResult:
    v0 = max(v0, 0.1)
    s0 = style.s0 if s0 is None else s0
    free = 1.0 - (max(v, 0.0) / v0) ** DELTA
    if gap is None:
        return IdmResult(style.a_max * free, style.a_max * free, 0.0, None, None, 0.0, v0, s0)
    dv = v - lead_v
    s_star = s0 + max(0.0, v * style.T + v * dv / (2.0 * math.sqrt(style.a_max * style.b)))
    s = max(gap, 0.05)
    inter = (s_star / s) ** 2
    a = style.a_max * (free - inter)
    return IdmResult(a, style.a_max * free, -style.a_max * inter, s_star, gap, dv, v0, s0)


def formula(res: IdmResult, v: float, style: Style) -> str:
    if res.gap is None:
        return (
            f"a = {style.a_max:.2f} × [1 − ({v:.1f}/{res.v0:.1f})⁴] = {res.a:.2f} m/s²  (free road)"
        )
    return (
        f"s* = {res.s0:.1f} + {v:.1f}×{style.T:.1f} + {v:.1f}×{res.dv:.1f}/(2√({style.a_max:.1f}×{style.b:.1f}))"
        f" = {res.s_star:.1f} m;  a = {style.a_max:.2f} × [1 − ({v:.1f}/{res.v0:.1f})⁴ − ({res.s_star:.1f}/{max(res.gap, 0.05):.1f})²]"
        f" = {res.a:.2f} m/s²"
    )
