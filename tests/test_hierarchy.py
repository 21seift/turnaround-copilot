"""
Invariant tests for the operating hierarchy.

Chapter 4 claims the constraint layer makes hierarchy compliance a property of
the SYSTEM rather than of the model behind it. That claim is only worth making
if it holds against a reasoner actively trying to violate it, so these tests
drive enforce_hierarchy() with deliberately non-compliant output: a reasoner
that ignores hazards, one that returns nothing, and one that advises standing
down. Each invariant below corresponds to a specific claim in the report.

Runnable without pytest (which is not installed in the evaluation container):

    python -m tests.test_hierarchy
"""

from __future__ import annotations

import sys

from turnaround_sim.compare_reasoners import load_cases
from turnaround_sim.proactive_triage import DELAY_RECOVERABLE
from turnaround_sim.reasoner import (REASONERS, ReasonerInput, ReasonerOutput,
                                     RuleReasoner, _parse, enforce_hierarchy)


def _inp(**kw) -> ReasonerInput:
    base = dict(code="36", code_label="fuelling", minutes=10.0, over_target=10.0,
                will_breach=True, projected_door="10:00", door_target="09:50",
                turn_type="DAYTIME_CREW_CHANGE", aircraft="A320",
                has_prm=False, has_ema=False, safety_flag=False, lead_time=10.0)
    base.update(kw)
    return ReasonerInput(**base)


def _out(**kw) -> ReasonerOutput:
    base = dict(headline="x", recoverable=True, kind="recover",
                actions=["chase the bowser"], reasoning=[], backend="test")
    base.update(kw)
    return ReasonerOutput(**base)


# -- 1. SAFETY -------------------------------------------------------------

def test_safety_hold_asserted_when_model_omits_it():
    """A reasoner ignoring a live hazard must not be able to suppress the hold."""
    out = enforce_hierarchy(_out(kind="recover", recoverable=True),
                            _inp(safety_flag=True))
    assert out.kind == "safety_hold", out.kind
    assert out.recoverable is False
    assert "SAFETY HOLD" in out.headline


def test_safety_hold_retains_manage_around_beneath():
    """Safety governs ACTION, not ATTENTION -- steps stay visible under the hold."""
    out = enforce_hierarchy(_out(), _inp(safety_flag=True))
    assert any(a.startswith("(still live)") for a in out.actions), out.actions
    assert len(out.actions) > 3


def test_safety_overrides_even_under_extreme_time_pressure():
    """Minutes must never buy their way past the hard constraint."""
    out = enforce_hierarchy(_out(kind="recover"),
                            _inp(safety_flag=True, over_target=95.0,
                                 lead_time=0.0))
    assert out.kind == "safety_hold"


# -- 2. PROACTIVE ASSERTION ------------------------------------------------

def test_empty_recommendation_is_invalid():
    out = enforce_hierarchy(_out(actions=[]), _inp())
    assert out.actions, "empty action list must be repaired"


def test_stand_down_language_is_stripped():
    for phrase in ("stand down", "nothing to do", "no action needed",
                   "do nothing"):
        out = enforce_hierarchy(_out(actions=[f"Just {phrase} and wait."]),
                                _inp())
        joined = " ".join(out.actions).lower()
        assert phrase not in joined, f"{phrase!r} survived: {out.actions}"


def test_stripping_never_leaves_an_empty_list():
    out = enforce_hierarchy(_out(actions=["stand down", "do nothing"]), _inp())
    assert out.actions, "stripping must inject replacements, not empty the list"


def test_every_case_every_backend_yields_an_action():
    """The proactive-assertion guarantee, over all real cases and backends."""
    for name, factory in REASONERS.items():
        if name == "llm":
            continue                      # requires network and a key
        r = factory()
        for c in load_cases():
            out = r.reason(c)
            assert out.actions, f"{name} produced no action for code {c.code}"


# -- 3. INTERNAL CONSISTENCY ----------------------------------------------

def test_rule_reasoner_kind_and_flag_never_contradict():
    """Regression: recoverable was read from a table covering only some codes."""
    r = RuleReasoner()
    for c in load_cases():
        out = r.reason(c)
        if out.kind == "safety_hold":
            continue
        assert (out.kind == "recover") == out.recoverable, (
            f"code {c.code}: kind={out.kind} recoverable={out.recoverable}")


def test_recoverable_codes_are_triaged_recoverable():
    r = RuleReasoner()
    for c in load_cases():
        if c.safety_flag or c.code not in DELAY_RECOVERABLE:
            continue
        assert r.reason(c).recoverable, f"code {c.code} should be recoverable"


# -- 4. DEFENSIVE PARSING --------------------------------------------------

def test_malformed_model_output_degrades_safely():
    for raw in ("not json at all", "", "{broken", "```json\n{}\n```", "[]"):
        out = _parse(raw, "test")
        assert isinstance(out, ReasonerOutput)
        assert isinstance(out.actions, list)


def test_malformed_output_still_passes_the_hierarchy():
    out = enforce_hierarchy(_parse("garbage", "test"), _inp(safety_flag=True))
    assert out.kind == "safety_hold"
    assert out.actions


# -- runner ----------------------------------------------------------------

def main() -> int:
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
        except Exception as e:                        # noqa: BLE001
            failed += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
