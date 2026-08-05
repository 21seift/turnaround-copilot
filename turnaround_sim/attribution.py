"""
Timestamp intake and attribution.

Takes the raw milestone timestamps a coordinator actually records and derives
everything downstream from them: which milestones slipped and by how much,
which delay code that pattern implies, how the total delay partitions across
the codes as they would be booked on the sheet, whether the door target is
projected to be missed, and what should be done about it.

This is the layer that turns an event stream into a decision. It performs no
reasoning of its own -- attribution feeds the existing agent, which calls the
critical-path projector as a tool and delegates planning to the reasoner -- so
the behaviour exposed here is the same behaviour evaluated in Chapter 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .agent import Observation, TurnaroundAgent
from .baseline_cpm import CriticalPathProjector
from .calibration import CALIBRATION
from .milestones_v2 import (INBOUND_MILESTONES, Anchor,
                            build_outbound_milestones)
from .rebasing import decompose_delay, resolve_from_in_block, spin_minutes
from .schedule import Aircraft, TurnType, door_closure_offset, prep_minutes

# Which delay code a slipped milestone implies. Grounded in the codes observed
# on the real dispatch records; where one milestone admits two readings the
# expectation context decides (an inbound PRM pickup is only code 04 if PRMs
# were actually booked).
MILESTONE_CODE: dict[str, tuple[str, str]] = {
    "in_block":               ("93", "late inbound aircraft"),
    "door1_open":             ("34", "ground equipment / steps"),
    "door2_open":             ("34", "ground equipment / steps"),
    "last_pax_off":           ("05", "disembarkation slow"),
    "fuelling_start":         ("36", "refuelling"),
    "fuelling_end":           ("36", "refuelling"),
    "green_light":            ("65", "crew briefing / release late"),
    "first_prm_on":           ("04", "PRM boarding"),
    "last_prm_on":            ("04", "PRM boarding"),
    "ema_handover":           ("ema", "EMA handover"),
    "last_pax_on":            ("71", "passenger boarding"),
    "gate_close":             ("85", "document / travel-permission checks"),
    "loadsheet_to_captain":   ("64", "flight crew"),
    "loadsheet_from_captain": ("64", "flight crew"),
    "door_closure":           ("", ""),      # an outcome, never a cause
    "off_block":              ("89", "awaiting pushback"),
}

SAFETY_CODES = {"41"}

# Minutes of drift below which a variance is recording noise, not a delay.
MATERIAL = 0.5


def now_hint(actuals: dict, now: float | None) -> float:
    """The clock, whether pinned by a replay or taken from the last event."""
    if now is not None:
        return now
    known = [a for a in actuals.values() if a is not None]
    return max(known) if known else 0.0


@dataclass
class MilestoneRow:
    key: str
    name: str
    target: float | None
    actual: float | None
    variance: float | None          # +late / -early, minutes
    expected: bool
    is_kpi: bool
    code: str = ""
    code_label: str = ""

    @property
    def late(self) -> bool:
        return self.variance is not None and self.variance > 0.5


@dataclass
class Assessment:
    schedule: dict
    milestones: list[MilestoneRow] = field(default_factory=list)
    attribution: dict = field(default_factory=dict)
    decomposition: dict = field(default_factory=dict)
    projection: dict = field(default_factory=dict)
    recommendation: dict = field(default_factory=dict)


def assess(*, turn: str, aircraft: str, scheduled_departure: float,
           actual_in_block: float, actuals: dict[str, float],
           has_prm: bool = False, has_ema: bool = False,
           safety_flag: bool = False, now: float | None = None,
           reported_code: str | None = None,
           reported_at: float | None = None) -> Assessment:
    tt = TurnType[turn]
    ac = Aircraft[aircraft]

    sched = resolve_from_in_block(turn=tt, actual_in_block=actual_in_block,
                                  scheduled_departure=scheduled_departure)
    prep = prep_minutes(tt, ac)
    door_off = door_closure_offset(tt)

    # ---- resolve every milestone target from its anchor -------------------
    rows: list[MilestoneRow] = []
    lpo_target = actual_in_block + 6.0
    lpo_actual = actuals.get("last_pax_off")
    lpo_ref = lpo_actual if lpo_actual is not None else lpo_target

    for m in list(INBOUND_MILESTONES) + list(build_outbound_milestones(door_off)):
        if m.anchor == Anchor.IN_BLOCK:
            target = actual_in_block + m.target_offset
        elif m.anchor == Anchor.OFF_BLOCK:
            target = sched.estimated_departure + m.target_offset
        else:                                   # LAST_PAX_OFF (+ prep window)
            target = lpo_ref + m.target_offset + prep

        expected = True
        if m.requires == "prm" and not has_prm:
            expected = False
        if m.requires == "ema" and not has_ema:
            expected = False

        actual = actuals.get(m.key)
        var = None if actual is None else round(actual - target, 1)
        code, label = MILESTONE_CODE.get(m.key, ("", ""))
        if m.key == "last_pax_off" and has_prm:
            code, label = "04", "inbound PRM pickup"

        rows.append(MilestoneRow(m.key, m.name, round(target, 1), actual, var,
                                 expected, m.is_kpi, code, label))

    # ---- attribution -------------------------------------------------------
    contributors = [
        {"code": r.code, "label": r.code_label, "milestone": r.name,
         "minutes": r.variance}
        for r in rows
        if r.late and r.expected and r.code and r.key != "in_block"
    ]
    if sched.late_inbound > 0.5:
        contributors.insert(0, {"code": "93", "label": "late inbound aircraft",
                                "milestone": "Aircraft in-block",
                                "minutes": round(sched.late_inbound, 1)})

    dominant = max(contributors, key=lambda c: c["minutes"], default=None)

    # A coordinator hears about a problem before it shows up in a timestamp.
    # Once reported, the cause is known and its likely exposure comes from the
    # calibrated history of that code -- this is the agent's whole advantage,
    # and the projector below is deliberately given none of it.
    reported = None
    if reported_code and (reported_at is None or now_hint(actuals, now) >= reported_at):
        cal = CALIBRATION.get(reported_code)
        exposure = (cal.bad if cal and cal.typical == 0 else
                    cal.typical if cal else 10.0)
        reported = {"code": reported_code,
                    "label": cal.label if cal else f"code {reported_code}",
                    "milestone": "reported by the coordinator",
                    "minutes": round(float(exposure), 1), "reported": True}
        if reported not in contributors:
            contributors.insert(0, reported)
        dominant = reported
    if (dominant and not dominant.get("reported")
            and dominant["code"] == "93" and len(contributors) == 1):
        # Rebasing has already absorbed it; the door target is not threatened.
        dominant = None

    if safety_flag:
        dominant = {"code": "41", "label": "engineering / live hazard",
                    "milestone": "reported by coordinator",
                    "minutes": dominant["minutes"] if dominant else 0.0}

    # ---- projection --------------------------------------------------------
    if now is None:
        known = [a for a in actuals.values() if a is not None]
        now = max(known) if known else actual_in_block
    # Only material drift counts. Half a minute on a door-open is recording
    # granularity, not a delay, and treating it as one makes the projector
    # cry breach on every turn -- the false-alarm failure mode the threshold
    # dashboard is criticised for in Chapter 4.
    slip = max([r.variance for r in rows
                if r.variance is not None and r.expected
                and r.variance > MATERIAL] or [0.0])

    # The projector is given only what the clock has already proved: drift that
    # has actually materialised in a recorded milestone. It is never told the
    # cause, because a critical-path method has no way to represent one.
    cpm_remaining = max(0.0, (sched.door_target - now)) + slip
    proj = CriticalPathProjector().project(sched, now=now,
                                           remaining_minutes=cpm_remaining)

    # The agent additionally carries the exposure implied by a known cause,
    # which is what lets it act before the drift shows up in a timestamp.
    exposure = float((dominant or {}).get("minutes", 0.0) or 0.0)
    agent_remaining = max(0.0, (sched.door_target - now)) + max(slip, exposure)

    # ---- recommendation (the evaluated agent, unchanged) -------------------
    obs = Observation(now=now, remaining_minutes=agent_remaining,
                      active_code=(dominant or {}).get("code"),
                      has_prm=has_prm, has_ema=has_ema,
                      safety_flag=safety_flag or
                      bool(dominant and dominant["code"] in SAFETY_CODES
                           and dominant["code"] == "41"),
                      delay_minutes=(dominant or {}).get("minutes", 0.0) or 0.0,
                      code_label=(dominant or {}).get("label", ""))
    rec = TurnaroundAgent().step(sched, obs)

    # ---- decomposition (only once doors and off-block are known) -----------
    decomp = {}
    if actuals.get("door_closure") is not None and actuals.get("off_block") is not None:
        d = decompose_delay(sched,
                            actual_door_closure=actuals["door_closure"],
                            actual_off_block=actuals["off_block"])
        decomp = {k: round(v, 1) for k, v in d.items()}

    return Assessment(
        schedule={
            "turn": tt.name, "aircraft": ac.name,
            "spin": spin_minutes(tt), "prep": prep,
            "door_offset": door_off,
            "scheduled_departure": scheduled_departure,
            "actual_in_block": actual_in_block,
            "estimated_departure": sched.estimated_departure,
            "door_target": sched.door_target,
            "late_inbound": round(sched.late_inbound, 1),
            "now": now,
        },
        milestones=rows,
        attribution={"dominant": dominant, "contributors": contributors},
        decomposition=decomp,
        projection={
            "will_breach": bool(proj.will_breach),
            "projected_door_closure": proj.projected_door_closure,
            "door_target": proj.door_target,
            "over": round(max(0.0, proj.projected_breach), 1),
            "lead": round(max(0.0, sched.door_target - now), 1),
        },
        recommendation={
            "headline": rec.headline, "kind": rec.kind,
            "recoverable": rec.recoverable, "actions": rec.actions,
            "reasoning": rec.reasoning, "backend": rec.backend,
        })
