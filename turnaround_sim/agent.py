"""
The turnaround agent -- perceive / predict / plan / act / reflect.

The project's core contribution: an orchestrator that does what the two
baselines cannot. It PREDICTS door-closure breach (calling the critical-path
projector AS A TOOL), ATTRIBUTES the breach to a cause/code, TRIAGES it, and
RECOMMENDS proactive action -- always as decision support, never acting
autonomously. The TCO decides.

As of WP6 the PLAN/ACT step is delegated to a swappable `Reasoner`
(see reasoner.py), so the rule-driven reasoner and an LLM reasoner run through
the identical loop and the identical evaluation harness. The agent below does
not know or care which backend it holds.

Whichever backend is used, its output passes through the elicited operating
hierarchy -- safety first, proactive assertion always, minute recovery last --
enforced in reasoner.enforce_hierarchy(). The safety guarantee is therefore a
property of the system, not of the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .baseline_cpm import CriticalPathProjector, Projection
from .calibration import CALIBRATION
from .reasoner import Reasoner, ReasonerInput, RuleReasoner
from .rebasing import ResolvedSchedule


@dataclass
class Observation:
    """What the agent perceives at a decision point."""
    now: float
    remaining_minutes: float
    active_code: str | None = None      # dominant live disruption, if known
    has_prm: bool = False
    has_ema: bool = False
    safety_flag: bool = False           # live hazard -> hard constraint
    delay_minutes: float = 0.0          # magnitude of the attributed delay
    code_label: str = ""                # human label when calibration lacks it


@dataclass
class Recommendation:
    headline: str
    recoverable: bool
    action: str                          # primary action (back-compat)
    reasoning: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)   # full proactive set
    kind: str = "manage_around"
    backend: str = "rules"

    def __str__(self) -> str:
        lines = [self.headline,
                 f"  backend    : {self.backend}",
                 f"  kind       : {self.kind}",
                 f"  recoverable: {self.recoverable}",
                 "  recommend  :"]
        lines += [f"    - {a}" for a in (self.actions or [self.action])]
        lines.append("  reasoning  :")
        lines += [f"    - {r}" for r in self.reasoning]
        return "\n".join(lines)


class TurnaroundAgent:
    def __init__(self, reasoner: Reasoner | None = None) -> None:
        self.projector = CriticalPathProjector()      # the solver, used as a TOOL
        self.reasoner: Reasoner = reasoner or RuleReasoner()

    # -- PREDICT: call the critical-path tool -------------------------------
    def _predict(self, sched: ResolvedSchedule, obs: Observation) -> Projection:
        return self.projector.project(sched, now=obs.now,
                                      remaining_minutes=obs.remaining_minutes)

    # -- full loop ----------------------------------------------------------
    def step(self, sched: ResolvedSchedule, obs: Observation) -> Recommendation:
        trace: list[str] = []
        backend = getattr(self.reasoner, "name", "?")

        # PERCEIVE
        trace.append(f"Perceived state at {_hm(obs.now)}; "
                     f"{obs.remaining_minutes:.0f} min work remaining to doors.")
        cal = CALIBRATION.get(obs.active_code or "")
        if cal:
            trace.append(f"Active disruption: code {cal.code} ({cal.label}), "
                         f"mechanic '{cal.mechanic}'.")

        # PREDICT (tool call)
        proj = self._predict(sched, obs)
        trace.append(f"Critical-path tool projects doors "
                     f"{_hm(proj.projected_door_closure)} "
                     f"vs target {_hm(proj.door_target)}.")

        # SAFETY is a hard constraint -- evaluated before any timing question.
        if obs.safety_flag:
            trace.append("SAFETY: live hazard flagged -- hard constraint, "
                         "overrides all timing considerations.")
        elif not proj.will_breach:
            return Recommendation(
                headline=f"On track: doors projected on time "
                         f"({_hm(proj.projected_door_closure)}).",
                recoverable=True, kind="monitor",
                action="No action needed; continue monitoring.",
                actions=["Continue monitoring; nothing outstanding."],
                reasoning=trace, backend=backend)

        # Expectation-context guard: a milestone never expected is not a delay.
        # Suppressing this is a capability neither baseline has.
        if obs.active_code == "04" and not obs.has_prm and not obs.safety_flag:
            trace.append("Expectation check: no PRM booked -> non-event, "
                         "not a delay.")
            return Recommendation(
                headline="Apparent PRM slippage on a flight with no PRMs "
                         "booked -- disregard.",
                recoverable=True, kind="monitor",
                action="No action; missing PRM milestone is expected here.",
                actions=["No action; missing PRM milestone is expected here."],
                reasoning=trace, backend=backend)

        # ATTRIBUTE
        if cal is None and not obs.safety_flag:
            trace.append("No attributed cause; triage on timing evidence alone.")

        # PLAN + ACT -- delegated to the swappable reasoner
        inp = ReasonerInput(
            code=obs.active_code,
            code_label=(cal.label if cal else
                        (obs.code_label or f"code {obs.active_code or '?'}")),
            minutes=obs.delay_minutes or max(0.0, proj.projected_breach),
            over_target=max(0.0, proj.projected_breach),
            will_breach=bool(proj.will_breach) or obs.safety_flag,
            projected_door=_hm(proj.projected_door_closure),
            door_target=_hm(proj.door_target),
            turn_type=str(getattr(sched, "turn_type", "unknown")),
            aircraft=str(getattr(sched, "aircraft", "unknown")),
            has_prm=obs.has_prm, has_ema=obs.has_ema,
            safety_flag=obs.safety_flag,
            lead_time=max(0.0, sched.door_target - obs.now))

        out = self.reasoner.reason(inp)
        trace.extend(out.reasoning)
        trace.append("Recommendation formed as decision support; TCO decides.")

        return Recommendation(
            headline=out.headline, recoverable=out.recoverable, kind=out.kind,
            action=(out.actions[0] if out.actions
                    else "Escalate and protect downstream milestones."),
            actions=out.actions, reasoning=trace, backend=out.backend)


def _hm(t: float) -> str:
    return f"{int(t)//60:02d}:{int(t)%60:02d}"
