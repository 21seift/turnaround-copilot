"""
Baseline 1: rule-based A-CDM threshold monitor.

This is the "dashboard" baseline -- what current tooling effectively does. It
watches milestones against their resolved targets and raises an alert when a
milestone breaches a fixed threshold. It has NO reasoning: it cannot explain
*why* a breach happened, cannot triage recoverable vs unrecoverable, and cannot
recommend an action. It only says "this milestone is late by N minutes".

The agent must beat this on: attribution (which code), triage (recoverable?),
and recommendation (what to do). Establishing what the dashboard CAN'T do is
half the contribution -- so this baseline is deliberately faithful and honest,
not a straw man.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rebasing import ResolvedSchedule


@dataclass(frozen=True)
class Alert:
    """A threshold breach detected by the rule-based monitor."""

    milestone: str
    target: float
    actual: float
    minutes_late: float
    is_kpi: bool

    def __str__(self) -> str:
        def hm(t): return f"{int(t)//60:02d}:{int(t)%60:02d}"
        kpi = " [KPI]" if self.is_kpi else ""
        return (f"BREACH {self.milestone}{kpi}: target {hm(self.target)}, "
                f"actual {hm(self.actual)}, {self.minutes_late:.0f} min late")


class ThresholdMonitor:
    """
    Raises an alert whenever an observed milestone exceeds its target by more
    than ``tolerance`` minutes. This is the extent of a dashboard's "reasoning".
    """

    def __init__(self, tolerance: float = 0.0) -> None:
        self.tolerance = tolerance

    def check(self, milestone: str, target: float, actual: float,
              is_kpi: bool = False) -> Alert | None:
        late = actual - target
        if late > self.tolerance:
            return Alert(milestone, target, actual, late, is_kpi)
        return None

    def predict_door_breach(self, sched: ResolvedSchedule,
                            projected_door_closure: float) -> Alert | None:
        """Will the pivotal door-closure KPI be missed against -4/-8?"""
        return self.check("door_closure", sched.door_target,
                          projected_door_closure, is_kpi=True)
