"""
Demonstration entry point -- walks one turnaround and shows the agent working.

Intended for the screencast and for viva demonstration. Run:

    python -m turnaround_sim.demo              # a recoverable delay
    python -m turnaround_sim.demo --safety     # a live hazard
    python -m turnaround_sim.demo --compare    # all three approaches, same turn

Nothing here is used by the evaluation; it exists to make the system's behaviour
legible without reading the harness output.
"""

from __future__ import annotations

import sys

from .agent import Observation, TurnaroundAgent
from .baseline_cpm import CriticalPathProjector
from .baseline_rules import ThresholdMonitor
from .rebasing import resolve_from_in_block
from .schedule import Aircraft, TurnType


def _hm(t: float) -> str:
    return f"{int(t) // 60:02d}:{int(t) % 60:02d}"


def _rule(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def scenario(safety: bool = False):
    """One A320 daytime turn, inbound 12 minutes late, boarding under way."""
    sched = resolve_from_in_block(turn=TurnType.DAYTIME_CREW_CHANGE,
                                  actual_in_block=8 * 60 + 12,
                                  scheduled_departure=9 * 60)
    if safety:
        obs = Observation(now=sched.door_target - 25, remaining_minutes=34.0,
                          active_code="41", has_prm=True, has_ema=False,
                          safety_flag=True, delay_minutes=40.0)
    else:
        obs = Observation(now=sched.door_target - 16, remaining_minutes=26.0,
                          active_code="36", has_prm=False, has_ema=False,
                          safety_flag=False, delay_minutes=11.0)
    return sched, obs


def show(safety: bool = False) -> None:
    sched, obs = scenario(safety)

    _rule("TURNAROUND")
    print(f"  aircraft            : A320, daytime turn with crew change")
    print(f"  in-block (actual)   : {_hm(sched.actual_in_block)}")
    print(f"  scheduled departure : {_hm(sched.scheduled_departure)}")
    print(f"  door-closure target : {_hm(sched.door_target)}")
    print(f"  clock now           : {_hm(obs.now)} "
          f"({sched.door_target - obs.now:.0f} min to target)")
    print(f"  live issue          : code {obs.active_code}"
          + ("  [SAFETY HAZARD]" if obs.safety_flag else ""))

    _rule("AGENT")
    rec = TurnaroundAgent().step(sched, obs)
    print(f"  {rec.headline}")
    print(f"  kind        : {rec.kind}")
    print(f"  recoverable : {rec.recoverable}")
    print("  recommends  :")
    for a in rec.actions:
        print(f"    - {a}")
    print("  reasoning   :")
    for r in rec.reasoning:
        print(f"    - {r}")
    print("\n  (decision support -- the coordinator decides; the agent never acts)")


def compare() -> None:
    sched, obs = scenario()
    print(f"\nSame turn, door target {_hm(sched.door_target)}, "
          f"now {_hm(obs.now)} ({sched.door_target - obs.now:.0f} min out)\n")

    # The dashboard can only compare an OBSERVED value against its target. At
    # this moment doors have not yet closed, so it has nothing to observe and
    # stays silent -- which is the behaviour under evaluation, not a limitation
    # imposed on it here.
    mon = ThresholdMonitor()
    fired = mon.check("door_closure", sched.door_target, obs.now, is_kpi=True)
    print("  DASHBOARD      : "
          + (f"breach flagged, {fired.late:.0f} min late" if fired
             else "silent -- target not yet passed"))

    proj = CriticalPathProjector().project(
        sched, now=obs.now, remaining_minutes=obs.remaining_minutes)
    print(f"  CRITICAL PATH  : "
          + (f"breach predicted, doors {_hm(proj.projected_door_closure)}"
             if proj.will_breach else "on track")
          + "  (no cause, no action)")

    rec = TurnaroundAgent().step(sched, obs)
    print(f"  AGENT          : {rec.headline}")
    print(f"                   -> {rec.actions[0]}")


if __name__ == "__main__":
    if "--compare" in sys.argv:
        compare()
    else:
        show(safety="--safety" in sys.argv)
