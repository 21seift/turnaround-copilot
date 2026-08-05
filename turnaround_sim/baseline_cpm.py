"""
Baseline 2: critical-path projection.

Smarter than the threshold monitor: instead of only reacting once a milestone
is already late, it projects the expected door-closure time forward from the
current observed state along the remaining critical chain, and compares that
projection to the -4/-8 target. This is a classical, defensible scheduling
baseline (CPM). It CAN predict a breach before it happens.

What it still CANNOT do -- and this is the thesis gap -- is reason about CAUSE
or RECOVERABILITY. It projects timing; it does not know that a projected breach
driven by fuelling has a TCO lever while one driven by a late inbound (code 93)
or a technical fault (code 41) does not. It treats all slippage as identical.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rebasing import ResolvedSchedule


@dataclass(frozen=True)
class Projection:
    projected_door_closure: float
    door_target: float
    projected_breach: float  # minutes over target (<=0 means on time)

    @property
    def will_breach(self) -> bool:
        return self.projected_breach > 0.0

    def __str__(self) -> str:
        def hm(t): return f"{int(t)//60:02d}:{int(t)%60:02d}"
        verdict = (f"projected breach {self.projected_breach:.0f} min"
                   if self.will_breach else "projected on time")
        return (f"CPM: door closure projected {hm(self.projected_door_closure)} "
                f"vs target {hm(self.door_target)} -> {verdict}")


class CriticalPathProjector:
    """
    Projects door closure from observed progress plus remaining-work estimates.

    ``remaining_minutes`` is the estimated time from *now* to door closure along
    the critical chain, given what has and hasn't completed. In the full sim
    this comes from the task graph; here it is passed in so the baseline is
    testable in isolation and reusable by the agent as a tool.
    """

    def project(self, sched: ResolvedSchedule, *, now: float,
                remaining_minutes: float) -> Projection:
        projected = now + remaining_minutes
        return Projection(
            projected_door_closure=projected,
            door_target=sched.door_target,
            projected_breach=projected - sched.door_target,
        )
