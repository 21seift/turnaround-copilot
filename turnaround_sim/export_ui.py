"""Export per-minute engine output for the demonstration interface.

The interface renders this file and computes nothing itself, so what a viewer
sees is the evaluated system's actual output rather than a re-implementation
that could drift from it.

    python -m turnaround_sim.export_ui > ui_data.json
"""

from __future__ import annotations

import json
import sys

from .agent import Observation, TurnaroundAgent
from .baseline_cpm import CriticalPathProjector
from .evaluate_emerging import offsets_for
from .rebasing import resolve_from_in_block
from .schedule import TurnType

HORIZON = 45


def hm(t: float) -> str:
    return f"{int(t) // 60:02d}:{int(t) % 60:02d}"


SCENARIOS = [
    dict(id="fuel", flight="XX 2417", stand="21", aircraft="A320",
         turn=TurnType.DAYTIME_CREW_CHANGE, in_block=8 * 60 + 12,
         sched_dep=9 * 60, code="36", label="refuelling",
         delay=11.0, safety=False, prm=False,
         note="Fuelling started late. The cause is visible well before the "
              "clock can prove the door target is at risk."),
    dict(id="crew", flight="XX 1183", stand="09", aircraft="A319",
         turn=TurnType.DAYTIME_CREW_CHANGE, in_block=13 * 60 + 40,
         sched_dep=14 * 60 + 30, code="64", label="flight crew late",
         delay=14.0, safety=False, prm=False,
         note="The captain is known to be delayed long before that delay "
              "consumes the turnaround's slack. Largest observed advantage."),
    dict(id="inbound", flight="XX 3302", stand="15", aircraft="A321",
         turn=TurnType.FIRST_WAVE, in_block=6 * 60 + 5,
         sched_dep=6 * 60 + 55, code="93", label="late inbound aircraft",
         delay=16.0, safety=False, prm=True,
         note="Known and provable at the same instant. The agent offers no "
              "advantage here, and the interface shows that plainly."),
    dict(id="eng", flight="XX 5540", stand="05", aircraft="A320",
         turn=TurnType.DAYTIME_CREW_CHANGE, in_block=11 * 60 + 20,
         sched_dep=12 * 60 + 10, code="41", label="engineering on board",
         delay=40.0, safety=True, prm=True,
         note="A live hazard. Safety is asserted as a hard constraint, and "
              "manage-around steps stay visible beneath the hold."),
]


def build(sc) -> dict:
    sched = resolve_from_in_block(turn=sc["turn"],
                                  actual_in_block=sc["in_block"],
                                  scheduled_departure=sc["sched_dep"])
    signal_off, proof_off = offsets_for(sc["code"])
    agent = TurnaroundAgent()
    proj = CriticalPathProjector()
    target = int(sched.door_target)

    frames = []
    for t in range(HORIZON, -1, -1):           # minutes before door target
        now = target - t
        # delay emerges linearly between signal and proof
        span = max(1.0, signal_off - proof_off)
        frac = min(1.0, max(0.0, (signal_off - t) / span))
        observed = sc["delay"] * frac

        p = proj.project(sched, now=now,
                         remaining_minutes=max(0.0, t + observed))

        cpm_fired = t <= proof_off and p.will_breach
        dash_fired = t <= 0

        rec = None
        if t <= signal_off:
            obs = Observation(now=now, remaining_minutes=max(0.0, t + sc["delay"]),
                              active_code=sc["code"], has_prm=sc["prm"],
                              has_ema=False, safety_flag=sc["safety"],
                              delay_minutes=sc["delay"])
            r = agent.step(sched, obs)
            rec = dict(headline=r.headline, kind=r.kind,
                       recoverable=r.recoverable, actions=r.actions,
                       reasoning=r.reasoning)

        frames.append(dict(
            t=t, clock=hm(now),
            projected=hm(p.projected_door_closure),
            over=round(max(0.0, p.projected_breach), 1),
            dashboard=dash_fired, cpm=cpm_fired, agent=rec))

    return dict(
        id=sc["id"], flight=sc["flight"], stand=sc["stand"],
        aircraft=sc["aircraft"], turn=sc["turn"].name, code=sc["code"],
        label=sc["label"], safety=sc["safety"], note=sc["note"],
        in_block=hm(sched.actual_in_block),
        sched_dep=hm(sched.scheduled_departure),
        door_target=hm(sched.door_target),
        signal_off=signal_off, proof_off=proof_off,
        frames=frames)


if __name__ == "__main__":
    json.dump([build(s) for s in SCENARIOS], sys.stdout, indent=1)
