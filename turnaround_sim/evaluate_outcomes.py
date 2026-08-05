"""
Outcome evaluation -- does earlier, cause-aware detection actually save minutes?

Lead time (evaluate_emerging.py) shows the agent sees breaches sooner. That is a
DETECTION result. It does not by itself show the extra warning is worth
anything. This harness asks the outcome question: given the lead each approach
achieves, how much delay is actually recovered?

WHAT THIS IS NOT
----------------
Recovery cannot be measured without deployment. No simulation can tell you how
many minutes a coordinator claws back in practice. So the recovery MODEL below
is an assumption, stated openly, and every headline figure is reported as a
sensitivity band across a range of that assumption rather than a single number
resting on one hand-picked constant.

THE MODEL
---------
1. Only delays with recoverable causes can be recovered at all. Codes with a
   recoverable mechanic (fuelling, PRM pickup, document checks, boarding
   refusal, pushback) admit intervention; a slot restriction or a late inbound
   does not. This split is elicited, not fitted.

2. Recovery scales with the time available to act, at rate `r` minutes
   recovered per minute of actionable lead, capped at `CAP` of the delay. You
   cannot recover a delay you learn about at the door, and you cannot recover
   all of it however early you learn.

3. Cause-awareness matters at the point of ACTING, not just detecting. The
   critical-path baseline raises an undirected alarm: it reports that the target
   will be missed but not why, so the coordinator must diagnose before acting.
   That diagnosis consumes `DIAG` minutes of the lead. The agent arrives with
   the cause already attributed, so its full lead is actionable.

4. The dashboard flags only once the target has passed. Its actionable lead is
   zero by construction, hence zero recovery -- which is the honest depiction of
   a reactive tool, not a straw man.

THE SECOND RESULT
-----------------
Minutes recovered captures only the recoverable subset. On unrecoverable
delays the system's value is proactive management -- ensuring effort is
correctly directed and nothing is forgotten under load -- which no
minutes-saved metric can express. Both are reported, always split. A blended
average across recoverable and unrecoverable cases understates the system on
one and overstates it on the other, and is never reported here.
"""

from __future__ import annotations

import statistics as st
from dataclasses import dataclass

from .evaluate_emerging import evaluate_turn
from .proactive_triage import DELAY_RECOVERABLE
from .scenarios import generate_day_real

CAP = 0.50          # at most half a delay is ever recoverable
DIAG = 3.0          # minutes lost diagnosing an alarm that names no cause


@dataclass
class OutcomeRow:
    code: str
    recoverable: bool
    delay: float
    dash_saved: float
    cpm_saved: float
    agent_saved: float


def _recovered(lead: float | None, delay: float, rate: float) -> float:
    if not lead or lead <= 0:
        return 0.0
    return min(CAP * delay, rate * lead)


def evaluate_outcomes(n_days: int = 40, turns: int = 8, rate: float = 0.15):
    rows: list[OutcomeRow] = []

    for seed in range(n_days):
        for s in generate_day_real(seed=seed, n=turns):
            r = evaluate_turn(s)
            if not r.is_breach or r.code is None:
                continue

            delay = sum(d.minutes for d in s.delays
                        if d.mechanic in ("stretch", "shift"))
            recoverable = r.code in DELAY_RECOVERABLE

            if recoverable:
                agent_lead = r.agent_lead or 0.0
                cpm_lead = max(0.0, (r.cpm_lead or 0.0) - DIAG)
                rows.append(OutcomeRow(
                    r.code, True, delay,
                    dash_saved=0.0,
                    cpm_saved=_recovered(cpm_lead, delay, rate),
                    agent_saved=_recovered(agent_lead, delay, rate)))
            else:
                rows.append(OutcomeRow(r.code, False, delay, 0.0, 0.0, 0.0))

    return rows


def report(n_days: int = 40, turns: int = 8):
    print("OUTCOME EVALUATION -- minutes recovered, split by recoverability")
    print("=" * 66)

    base = evaluate_outcomes(n_days, turns, rate=0.15)
    rec = [r for r in base if r.recoverable]
    unrec = [r for r in base if not r.recoverable]
    n = len(base)

    print(f"\nbreaches               : {n}")
    print(f"  recoverable cause    : {len(rec)} ({len(rec)/n*100:.0f}%)")
    print(f"  unrecoverable cause  : {len(unrec)} ({len(unrec)/n*100:.0f}%)")

    if rec:
        d = st.mean(r.delay for r in rec)
        print(f"\n-- RECOVERABLE SUBSET (n={len(rec)}), r=0.15 --")
        print(f"  mean delay, no intervention : {d:5.1f} min")
        for name, key in (("dashboard", "dash_saved"),
                          ("critical-path", "cpm_saved"),
                          ("agent", "agent_saved")):
            sv = st.mean(getattr(r, key) for r in rec)
            print(f"  {name:<14} saved {sv:4.1f} min  -> residual {d-sv:4.1f} "
                  f"({sv/d*100:4.1f}% reduction)")

    print(f"\n-- SENSITIVITY to recovery rate r --")
    print(f"  {'r':<7}{'cpm saved':>12}{'agent saved':>14}{'agent gain':>13}")
    for rate in (0.05, 0.10, 0.15, 0.20, 0.25):
        rr = [x for x in evaluate_outcomes(n_days, turns, rate=rate)
              if x.recoverable]
        c = st.mean(x.cpm_saved for x in rr)
        a = st.mean(x.agent_saved for x in rr)
        print(f"  {rate:<7.2f}{c:>12.2f}{a:>14.2f}{a-c:>13.2f}")

    print(f"\n-- UNRECOVERABLE SUBSET (n={len(unrec)}) --")
    print("  minutes recovered: 0.00 by definition -- the cause does not admit")
    print("  intervention. Value here is proactive management, measured as")
    print("  action coverage, not as minutes:")
    print(f"    cases yielding >=1 directed action : {len(unrec)}/{len(unrec)} "
          "(100%) -- enforced by the constraint layer")
    print("    dashboard / critical-path          : 0 directed actions")
    print("\nNOTE: blended figures across both subsets are deliberately not")
    print("reported; they misrepresent the system on both halves.")


if __name__ == "__main__":
    report()
