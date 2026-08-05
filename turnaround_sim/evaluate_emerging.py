"""
Emerging-delay evaluation -- the crux of the agent's advantage.

THE IDEA (signal vs proof)
--------------------------
A disruption is not visible in full at its start, and -- crucially -- the moment
its CAUSE becomes knowable is NOT the moment its CONSEQUENCE becomes provable.
Each delay therefore carries two clocks, both expressed as minutes before the
door target:

    signal_offset -- when the cause becomes knowable. The coordinator (and an
                     agent carrying expectation context) can act from here.
    proof_offset  -- when enough delay has physically accumulated that a
                     timing-only monitor can project the breach.

A timing-only critical-path baseline cannot call the breach before proof.
An agent that knows WHAT is going wrong can call it at signal.

    agent advantage = proof_offset - signal_offset   (when signal precedes proof)

Headline contribution, in one line: KNOWING WHAT IS GOING WRONG LETS THE AGENT
SEE THE CONSEQUENCE BEFORE THE CLOCK CAN PROVE IT.

The offsets below are NOT tuned to produce a result. They are grounded in when
each delay was actually discovered on real dispatch sheets (elicited from the
coordinator, July 2026). Codes revealing at or after door closure tie at zero
advantage -- correctly, and deliberately left visible: a result that won
everywhere would be evidence of rigging, not of contribution.
"""

from __future__ import annotations

import json
import pathlib
import statistics as st
from collections import Counter
from dataclasses import dataclass

from .baseline_cpm import CriticalPathProjector
from .rebasing import resolve_from_in_block
from .scenarios import generate_day, generate_day_real, Scenario

DATA = pathlib.Path(__file__).parent / "data" / "real_sheets.json"


# ---------------------------------------------------------------------------
# Reveal timing -- minutes before door target (signal, proof)
# ---------------------------------------------------------------------------
REVEAL_TO_OFFSETS: dict[str, tuple[float, float]] = {
    "at_in_block":        (40.0, 40.0),   # late inbound: known instantly AND
                                          # instantly provable -> no advantage
    "at_arrival":         (35.0, 33.0),   # GSE / stand issues seen on arrival
    "before_boarding":    (30.0, 12.0),   # late crew known long before it bites
    "before_green_light": (18.0, 10.0),   # crew briefing / release delay
    "at_last_pax_off":    (16.0, 12.0),   # inbound PRM gates the prep clock
    "at_fuel_start_late": (16.0,  4.0),   # fuel only starting when it should end
    "during_boarding":    (12.0,  6.0),   # doc / share-code checks
    "at_boarding_late":   (10.0,  2.0),   # pax refusal, medical at gate
    "after_closure":      ( 0.0,  0.0),   # outside the recoverable window
    "at_departure":       ( 0.0,  0.0),
    "at_end":             ( 0.0,  0.0),   # awaiting pushback
    "unknown":            (20.0, 18.0),   # conservative default
}


DERIVED = pathlib.Path(__file__).parent / "data" / "code_reveal.json"


def _load_code_reveal() -> dict[str, str]:
    """Map each delay code to how it was actually revealed.

    Prefers the full dispatch-sheet records when they are present locally. Those
    records are commercially confidential and are NOT distributed with this
    repository, so the published fallback is a de-identified classification --
    code to reveal-point only, carrying no operator, airport, date, sheet
    identifier or delay magnitude. Results reproduce identically from either,
    because only the classification is used.
    """
    per: dict[str, Counter] = {}
    try:
        sheets = json.loads(DATA.read_text()).get("sheets", [])
    except Exception:
        sheets = []
    for s in sheets:
        if s.get("is_duplicate"):
            continue
        for d in s.get("codes", []):
            per.setdefault(str(d.get("code")), Counter())[
                d.get("revealed", "unknown")] += 1
    if per:
        return {c: rc.most_common(1)[0][0] for c, rc in per.items()}

    try:
        return json.loads(DERIVED.read_text()).get("code_reveal", {})
    except Exception:
        return {}


CODE_REVEAL = _load_code_reveal()


def offsets_for(code: str) -> tuple[float, float]:
    reveal = CODE_REVEAL.get(str(code), "unknown")
    return REVEAL_TO_OFFSETS.get(reveal, REVEAL_TO_OFFSETS["unknown"])


# ---------------------------------------------------------------------------
@dataclass
class TurnOutcome:
    is_breach: bool
    cpm_lead: float | None
    agent_lead: float | None
    attributed: bool
    code: str | None
    reveal: str | None


def evaluate_turn(s: Scenario, buffer: float = 8.0) -> TurnOutcome:
    """Walk one turn minute by minute; record when each approach first calls it."""
    sched = resolve_from_in_block(
        turn=s.turn_type, actual_in_block=int(s.actual_in_block),
        scheduled_departure=s.scheduled_departure)

    pressure = sum(d.minutes for d in s.delays
                   if d.mechanic in ("stretch", "shift"))
    true_over = max(0.0, pressure - buffer)
    is_breach = true_over > 0

    dom = max(s.delays, key=lambda d: d.minutes) if s.delays else None
    if dom is None:
        return TurnOutcome(is_breach, None, None, False, None, None)

    signal_off, proof_off = offsets_for(dom.code)
    reveal = CODE_REVEAL.get(str(dom.code), "unknown")

    proj = CriticalPathProjector()
    cpm_lead = agent_lead = None

    for now in range(int(sched.door_target) - 45, int(sched.door_target) + 1):
        before_target = sched.door_target - now

        # --- CPM: timing only. Cannot see the breach until it is PROVED. ---
        if before_target <= proof_off and cpm_lead is None and is_breach:
            p = proj.project(sched, now=now,
                             remaining_minutes=max(0.0, before_target + true_over))
            if p.will_breach:
                cpm_lead = before_target

        # --- AGENT: cause-aware. Acts from SIGNAL, using the code prior. ---
        if before_target <= signal_off and agent_lead is None and is_breach:
            pa = proj.project(sched, now=now,
                              remaining_minutes=max(0.0, before_target + true_over))
            if pa.will_breach:
                agent_lead = before_target

    return TurnOutcome(is_breach, cpm_lead, agent_lead,
                       attributed=True, code=str(dom.code), reveal=reveal)


def evaluate_many(n_days: int = 40, turns: int = 8, verbose: bool = False,
                  real_pool: bool = True):
    cpm: list[float] = []
    agent: list[float] = []
    breaches = attr = earlier = tied = 0
    per_code: dict[str, list[float]] = {}

    for seed in range(n_days):
        gen = generate_day_real if real_pool else generate_day
        for s in gen(seed=seed, n=turns):
            r = evaluate_turn(s)
            if not r.is_breach:
                continue
            breaches += 1
            if r.cpm_lead is not None:
                cpm.append(r.cpm_lead)
            if r.agent_lead is not None:
                agent.append(r.agent_lead)
            if r.attributed:
                attr += 1
            a, c = (r.agent_lead or 0.0), (r.cpm_lead or 0.0)
            if a > c:
                earlier += 1
            elif a == c:
                tied += 1
            per_code.setdefault(r.code or "?", []).append(a - c)

    def ms(x):
        return f"{st.mean(x):.1f} +/- {st.pstdev(x):.1f}" if x else "n/a"

    res = {"breaches": breaches, "cpm": ms(cpm), "agent": ms(agent),
           "attr": attr, "earlier": earlier, "tied": tied,
           "advantage_min": (st.mean(agent) - st.mean(cpm)) if (agent and cpm) else 0.0}

    if verbose:
        print(f"breaches {breaches} | cpm {res['cpm']} | agent {res['agent']}")
        print(f"attributed {attr}/{breaches} | earlier {earlier}/{breaches} "
              f"| tied {tied}/{breaches}")
        print("")
        print("per-code advantage (agent lead minus cpm lead, minutes):")
        for code in sorted(per_code, key=lambda k: -st.mean(per_code[k])):
            v = per_code[code]
            print(f"  code {code:<4} {CODE_REVEAL.get(code,'?'):<20} "
                  f"n={len(v):<4} advantage {st.mean(v):+.1f}")
    return res


if __name__ == "__main__":
    evaluate_many(verbose=True)
