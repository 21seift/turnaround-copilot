"""
Proactive triage layer -- rebuilt on the coordinator's own principles.

Two non-negotiables, stated by the domain expert:

  1. SAFETY IS ALWAYS THE FIRST PRIORITY. A delay is never worse than
     jeopardising safety. Any action that trades safety for time is rejected
     outright, regardless of the delay it would save.

  2. THERE IS ALWAYS A PROACTIVE ACTION. "Unrecoverable" describes the DELAY,
     never the coordinator. When the clock can't be clawed back, the job shifts
     from fixing the turn to managing around it: communicate, protect the
     off-block, free yourself for redeployment. The agent must never say
     "stand down" -- it surfaces the RIGHT proactive action so nothing slips
     when the coordinator is overloaded.

The system is an escape valve for overwhelm: it keeps every available action in
view so pressure never causes one to be forgotten.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ProactiveAction:
    kind: str            # "recover" | "manage_around" | "safety_hold"
    steps: list[str]
    rationale: str
    safety_note: str = ""


# Which delays carry reversible on-stand pressure the coordinator can chase.
DELAY_RECOVERABLE = {
    "36": "fuelling can be expedited / boarding run in parallel",
    "04": "PRM assist can be chased to unblock the prep clock",
    "85": "extra staff to the desk to clear doc/share-code checks",
    "16": "support the medical need, ready the cabin so no further time lost",
    "71": "cabin announcement / crew coax to get pax boarding",
    "89": "confirm tug + headset ready so the wait is minimised",
    # Added after expert appraisal: a GSE fault is outside the coordinator's
    # control, but sourcing replacement equipment is not. Treating it as purely
    # unrecoverable removed the one action a coordinator would actually take.
    "34": ("chase replacement equipment through team leader, ramp allocator "
           "and office before the stand backs up"),
}

# Below this, a delay is too short to justify releasing yourself or chasing a
# new slot; the time is more likely to be found in parallel tasks. Elicited
# from expert appraisal, where redeployment prompts on short delays were
# rejected as premature in fifteen of twenty-seven cases.
REDEPLOY_THRESHOLD = 15

# Every code -- recoverable or not -- has a proactive management action.
MANAGE_AROUND = {
    "default": [
        "Tell tug driver + headset early: departure may slip, stay ready.",
        "Notify office you may be freed up -- offer to be redeployed to a turn that needs you.",
        "Protect the off-block: keep every task that CAN move, moving.",
        "Confirm/expedite new slot as soon as the delay is known.",
    ],
    "93": ["Rebase downstream milestones off the new realistic off-block.",
           "Warn next turn on this aircraft of the knock-on."],
    "96": ["Rebase off the new crew report time.",
           "Flag availability to office -- another TCO may cover the push."],
    "81": ["Push right up to slot limit; keep fuelling + water/waste moving.",
           "Tell office your stand may free late -- offer redeployment."],
    "34": ["Escalate GSE fault to equipment control; source alternative steps/power.",
           "Keep disembark options open so pax flow isn't fully blocked."],
    "41": ["Liaise engineering for realistic fix ETA; brief office early for swap decision."],
    "16": ["Check with gate and cabin crew to establish severity before acting.",
           "If medication is in a hold bag, get the bag code and pull it before "
           "loading completes -- after that it costs far more time."],
}

# Actions that only make sense once a delay is long enough to have released the
# coordinator or put the slot at risk.
LONG_DELAY_ONLY = {
    "Notify office you may be freed up -- offer to be redeployed to a turn that needs you.",
    "Confirm/expedite new slot as soon as the delay is known.",
    "Tell office your stand may free late -- offer redeployment.",
    "Flag availability to office -- another TCO may cover the push.",
}


def triage(code: str, minutes: int, over_target: float,
           safety_flag: bool = False) -> ProactiveAction:
    # 1) SAFETY FIRST -- overrides any time consideration.
    if safety_flag:
        return ProactiveAction(
            kind="safety_hold",
            steps=[
                "STOP -- resolve the safety issue before any recovery action.",
                "A delay is acceptable; compromising safety is not.",
                "Escalate to duty manager / engineering as required.",
                "Only resume turnaround actions once the hazard is cleared.",
            ],
            rationale="Safety is the first priority and overrides the schedule.",
            safety_note="Time saved never justifies a safety compromise.",
        )

    steps: list[str] = []
    # 2a) If reversible pressure exists, chase it FIRST...
    if code in DELAY_RECOVERABLE:
        steps.append(f"RECOVER: {DELAY_RECOVERABLE[code]}.")
        kind = "recover"
        rationale = "Reversible on-stand pressure -- act now, minutes come straight off the breach."
    else:
        kind = "manage_around"
        rationale = ("Delay origin is outside on-stand control -- stay proactive: "
                     "manage around it and protect what follows.")

    # 2b) ...and ALWAYS add the proactive management actions (never 'do nothing').
    steps.extend(MANAGE_AROUND.get(code, []))
    steps.extend(MANAGE_AROUND["default"])

    # Suppress actions that presuppose a long delay. Offering yourself for
    # redeployment three minutes into a turn is not proactive, it is noise, and
    # noise is what stops a coordinator reading the list at all.
    if minutes < REDEPLOY_THRESHOLD:
        steps = [x for x in steps if x not in LONG_DELAY_ONLY]
        if kind == "manage_around":
            steps.insert(0, "Delay is short: look for the time in parallel "
                            "tasks before treating it as lost.")

    return ProactiveAction(kind=kind, steps=steps, rationale=rationale,
                           safety_note="Safety remains the overriding priority throughout.")


if __name__ == "__main__":
    for code, mins, over, safe in [("36",1,5,False), ("96",54,54,False),
                                    ("81",16,16,False), ("41",95,95,True)]:
        a = triage(code, mins, over, safety_flag=safe)
        print(f"\ncode {code} ({mins}m, {'SAFETY' if safe else a.kind}):")
        print(f"  why: {a.rationale}")
        for s in a.steps:
            print(f"    - {s}")
