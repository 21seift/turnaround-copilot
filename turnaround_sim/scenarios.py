"""
Scenario generator -- rolls realistic turnarounds from the calibration table.

Draws delays per code using the elicited typical/bad figures, respecting each
code\'s mechanic (spike codes are usually zero; shift codes rebase the anchor;
etc.). Seeded for reproducibility so every generated day can be replayed -- a
requirement for fair baseline-vs-agent comparison.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .calibration import CALIBRATION, CodeCalibration
from .schedule import TurnType, Aircraft


@dataclass(frozen=True)
class InjectedDelay:
    code: str
    label: str
    minutes: float
    mechanic: str
    recoverable: bool


@dataclass
class Scenario:
    turn_type: TurnType
    aircraft: Aircraft
    scheduled_departure: int          # minutes past midnight
    late_inbound: float               # code 93, drives actual in-block
    delays: list[InjectedDelay] = field(default_factory=list)
    has_prm: bool = False
    has_ema: bool = False

    @property
    def actual_in_block(self) -> float:
        # late inbound shifts arrival; spin is applied downstream by rebasing.
        return self.scheduled_departure - _spin(self.turn_type) + self.late_inbound


def _spin(turn: TurnType) -> int:
    return {TurnType.FIRST_WAVE: 60,
            TurnType.DAYTIME_CREW_CHANGE: 35,
            TurnType.DAYTIME_NO_CREW_CHANGE: 30}[turn]


def _draw(cal: CodeCalibration, rng: random.Random) -> float:
    """
    Draw a delay in minutes for one code, honouring its shape.
      spike : usually 0, occasionally jumps toward bad
      others: triangular-ish around typical, capped near bad
    """
    if cal.mechanic == "spike":
        # ~75% of the time it does not bite at all
        if rng.random() < 0.75:
            return 0.0
        return round(rng.uniform(cal.typical + 5, cal.bad), 0)
    # centre on typical, allow spread toward bad (and a little below)
    low = max(0.0, cal.typical * 0.5)
    return round(rng.triangular(low, cal.bad, cal.typical), 0)


def generate_scenario(rng: random.Random, *, turn_type: TurnType | None = None,
                      aircraft: Aircraft | None = None,
                      base_departure: int = 6 * 60) -> Scenario:
    turn_type = turn_type or rng.choice(list(TurnType))
    aircraft = aircraft or rng.choice(list(Aircraft))

    has_prm = rng.random() < 0.45
    has_ema = rng.random() < 0.30

    # late inbound (code 93) almost always present to some degree
    late_inbound = _draw(CALIBRATION["93"], rng)

    delays: list[InjectedDelay] = []

    def maybe(key: str, prob: float, gate: bool = True):
        if gate and rng.random() < prob:
            cal = CALIBRATION[key]
            m = _draw(cal, rng)
            if m > 0:
                delays.append(InjectedDelay(cal.code, cal.label, m,
                                            cal.mechanic, cal.recoverable))

    maybe("36", 0.25)                              # refuelling spike
    maybe("41", 0.06)                              # engineering (rare, heavy)
    if turn_type == TurnType.DAYTIME_CREW_CHANGE:
        maybe("67", 0.20)                          # late crew only on changes
    maybe("04_in", 0.35, gate=has_prm)             # inbound PRM if expected
    maybe("04_out", 0.30, gate=has_prm)            # outbound PRM if expected
    maybe("ema", 0.40, gate=has_ema)               # EMA handover if expected
    maybe("81", 0.55)                              # slot -- common in season

    return Scenario(turn_type, aircraft, base_departure, late_inbound,
                    delays, has_prm, has_ema)


def generate_day(seed: int = 0, n: int = 8, start_hour: int = 6) -> list[Scenario]:
    rng = random.Random(seed)
    out = []
    dep = start_hour * 60
    for _ in range(n):
        out.append(generate_scenario(rng, base_departure=dep))
        dep += rng.choice([75, 90, 105, 120])      # spacing between departures
    return out


# ---------------------------------------------------------------------------
# Real-pool generator -- delays sampled from the actual dispatch sheets.
#
# The calibration-driven generator above uses the initial five-code elicitation.
# This one draws from the 15 distinct IATA codes recorded on real front sheets,
# so the evaluation runs on the operation's true delay mix rather than on an
# assumed one. This is the generator used for the headline emerging-delay result.
# ---------------------------------------------------------------------------
import json as _json
import pathlib as _pathlib

_REAL = _pathlib.Path(__file__).parent / "data" / "real_sheets.json"

# How each reveal point behaves against the door target.
#   hold    -- lands at/after door closure: no pre-closure pressure
#   shift   -- rebases the anchor (late inbound)
#   stretch -- lengthens work in place, pushing the door target
_REVEAL_MECHANIC = {
    "at_end": "hold", "at_departure": "hold", "after_closure": "hold",
    "at_in_block": "shift",
}

_RECOVERABLE_CODES = {"36", "04", "85", "16", "71", "89"}


_POOL_FALLBACK = _REAL.parent / "delay_pool.json"


def _fallback_pool() -> list[InjectedDelay]:
    """De-identified occurrence pool distributed with the repository.

    The full dispatch records are commercially confidential and withheld; this
    carries the same empirical distribution (code, duration, reveal point) with
    every identifier and verbatim label removed.
    """
    try:
        occ = _json.loads(_POOL_FALLBACK.read_text()).get("occurrences", [])
    except Exception:
        return []
    pool: list[InjectedDelay] = []
    for d in occ:
        code = str(d.get("code"))
        mech = d.get("mechanic") or _REVEAL_MECHANIC.get(
            d.get("revealed", "unknown"), "stretch")
        pool.append(InjectedDelay(code, f"code {code}",
                                  float(d.get("minutes", 0)), mech,
                                  code in _RECOVERABLE_CODES))
    return pool or _fallback_pool()


def _real_pool() -> list[InjectedDelay]:
    try:
        sheets = _json.loads(_REAL.read_text()).get("sheets", [])
    except Exception:
        return _fallback_pool()
    pool: list[InjectedDelay] = []
    for s in sheets:
        if s.get("is_duplicate"):
            continue
        for d in s.get("codes", []):
            code = str(d.get("code"))
            mins = float(d.get("minutes", 0) or 0)
            if mins <= 0:
                continue
            mech = d.get("mechanic") or _REVEAL_MECHANIC.get(
                d.get("revealed", "unknown"), "stretch")
            pool.append(InjectedDelay(code, d.get("label", f"code {code}"),
                                      mins, mech, code in _RECOVERABLE_CODES))
    return pool or _fallback_pool()


REAL_POOL = _real_pool()


def generate_scenario_real(rng: random.Random, *,
                           base_departure: int = 6 * 60) -> Scenario:
    """One turn whose delays are sampled from real recorded occurrences."""
    turn_type = rng.choice(list(TurnType))
    aircraft = rng.choice(list(Aircraft))
    has_prm = rng.random() < 0.45
    has_ema = rng.random() < 0.30

    delays: list[InjectedDelay] = []
    late_inbound = 0.0
    if REAL_POOL:
        # Real sheets average ~1.8 coded delays per turn.
        for _ in range(rng.choice([1, 1, 2, 2, 3])):
            d = rng.choice(REAL_POOL)
            if d.code == "93":
                late_inbound = max(late_inbound, d.minutes)
            delays.append(d)
    return Scenario(turn_type, aircraft, base_departure, late_inbound,
                    delays, has_prm, has_ema)


def generate_day_real(seed: int = 0, n: int = 8,
                      start_hour: int = 6) -> list[Scenario]:
    rng = random.Random(seed)
    out, dep = [], start_hour * 60
    for _ in range(n):
        out.append(generate_scenario_real(rng, base_departure=dep))
        dep += rng.choice([75, 90, 105, 120])
    return out
