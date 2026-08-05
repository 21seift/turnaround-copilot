"""
Swappable reasoning layer for the turnaround agent.

The agent's loop (perceive -> predict -> plan -> act -> reflect) is unchanged.
Only the PLAN/ACT step is delegated here, behind a single interface, so that a
rule-driven reasoner and an LLM reasoner are interchangeable and can be run
against the identical evaluation harness.

    ReasonerInput  -> Reasoner.reason() -> ReasonerOutput

DESIGN NOTE (this is a contribution, not plumbing):
The LLM is NOT trusted to honour the operating hierarchy elicited from the
domain expert. It is CONSTRAINED by it. Every LLM output passes through
`enforce_hierarchy()`, which is the same constraint the rule reasoner satisfies
by construction:

    1. SAFETY   -- a hard constraint. If a hazard is live, a safety hold is
                   asserted regardless of what the model proposed.
                   Safety takes priority in ACTION, not in ATTENTION: the
                   manage-around steps REMAIN VISIBLE beneath the hold
                   (confirmed by the practitioner -- going silent would abandon
                   the coordinator at the moment of highest load).
    2. PROACTIVE ASSERTION -- an empty recommendation is invalid output. If the
                   model returns no action, management steps are injected.
                   "Unrecoverable" classifies the DELAY, never the coordinator.
    3. MINUTE RECOVERY -- lowest priority; only optimised once 1 and 2 hold.

This makes the safety property a property of the SYSTEM, not of the model --
which is what lets an LLM be used at all in a safety-critical advisory role.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from .proactive_triage import MANAGE_AROUND, triage


# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------
@dataclass
class ReasonerInput:
    """Everything the reasoner is allowed to see. Identical for both backends."""
    code: str | None            # attributed delay code, if known
    code_label: str             # human label for the code
    minutes: float              # magnitude of the delay, minutes
    over_target: float          # projected minutes past the door target
    will_breach: bool
    projected_door: str         # HH:MM
    door_target: str            # HH:MM
    turn_type: str
    aircraft: str
    has_prm: bool = False
    has_ema: bool = False
    safety_flag: bool = False
    lead_time: float = 0.0      # minutes ahead of the timing-only baseline


@dataclass
class ReasonerOutput:
    headline: str
    recoverable: bool
    kind: str                   # "recover" | "manage_around" | "safety_hold"
    actions: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)
    backend: str = "unknown"

    def __str__(self) -> str:
        lines = [f"[{self.backend}] {self.headline}",
                 f"  kind       : {self.kind}",
                 f"  recoverable: {self.recoverable}",
                 "  actions    :"]
        lines += [f"    - {a}" for a in self.actions]
        if self.reasoning:
            lines.append("  reasoning  :")
            lines += [f"    - {r}" for r in self.reasoning]
        return "\n".join(lines)


class Reasoner(Protocol):
    name: str
    def reason(self, inp: ReasonerInput) -> ReasonerOutput: ...


# --------------------------------------------------------------------------
# The hierarchy constraint -- applied to EVERY backend's output
# --------------------------------------------------------------------------
def enforce_hierarchy(out: ReasonerOutput, inp: ReasonerInput) -> ReasonerOutput:
    """Coerce any reasoner's output into the elicited operating hierarchy."""
    violations: list[str] = []

    # 1. SAFETY -- hard constraint, asserted regardless of model output.
    if inp.safety_flag:
        hold = [
            "STOP -- resolve the safety issue before any recovery action.",
            "A delay is acceptable; compromising safety is not.",
            "Escalate to duty manager / engineering as required.",
        ]
        # Safety governs ACTION, not ATTENTION: manage-around stays visible.
        beneath = MANAGE_AROUND.get(inp.code or "", []) + MANAGE_AROUND["default"]
        if out.kind != "safety_hold":
            violations.append("model did not assert a safety hold on a live hazard "
                              "-- hold asserted by constraint layer")
        out.kind = "safety_hold"
        out.recoverable = False
        out.actions = hold + [f"(still live) {s}" for s in beneath]
        out.headline = (f"SAFETY HOLD -- {inp.code_label}. Resolve before any "
                        f"recovery action; doors are secondary.")

    # 2. PROACTIVE ASSERTION -- an empty recommendation is invalid.
    if not out.actions:
        violations.append("model returned no action -- proactive steps injected")
        out.actions = (MANAGE_AROUND.get(inp.code or "", [])
                       + MANAGE_AROUND["default"])
        out.kind = out.kind or "manage_around"

    # Reject stand-down language outright: unrecoverable describes the DELAY.
    banned = ("stand down", "nothing to do", "no action needed", "do nothing")
    if inp.will_breach:
        kept = [a for a in out.actions
                if not any(b in a.lower() for b in banned)]
        if len(kept) != len(out.actions):
            violations.append("stand-down advice stripped -- 'unrecoverable' "
                              "describes the delay, never the coordinator")
            out.actions = kept or (MANAGE_AROUND.get(inp.code or "", [])
                                   + MANAGE_AROUND["default"])

    if violations:
        out.reasoning.append("CONSTRAINT LAYER: " + "; ".join(violations))
    return out


# --------------------------------------------------------------------------
# Backend A -- rule reasoner (the v1 system, now behind the interface)
# --------------------------------------------------------------------------
class RuleReasoner:
    name = "rules"

    def reason(self, inp: ReasonerInput) -> ReasonerOutput:
        action = triage(inp.code or "", int(inp.minutes), inp.over_target,
                        safety_flag=inp.safety_flag)
        # Single source of truth. Recoverability and the chosen action kind are
        # the same judgement and must never contradict each other: triage()
        # already decides it from the elicited recoverable-cause set, so the
        # flag is read back from that decision rather than from the calibration
        # table, which covers only a subset of codes and previously produced
        # cases reporting kind="recover" alongside recoverable=False.
        recoverable = (action.kind == "recover")
        head = (f"{'Recoverable' if recoverable else 'Unrecoverable'} breach "
                f"{inp.over_target:.0f} min from {inp.code_label}.")
        out = ReasonerOutput(
            headline=head, recoverable=recoverable, kind=action.kind,
            actions=list(action.steps),
            reasoning=[action.rationale, action.safety_note],
            backend=self.name)
        return enforce_hierarchy(out, inp)


# --------------------------------------------------------------------------
# Backend B -- LLM reasoner (identical interface)
# --------------------------------------------------------------------------
SYSTEM_PROMPT = """You advise an aircraft turnaround coordinator (TCO) at a UK \
regional airport, working a low-cost carrier's ground handling. You are DECISION \
SUPPORT: you recommend, the coordinator decides. You never act.

You must follow this strict priority order:
1. SAFETY is a hard constraint, never traded against minutes. A delay is never \
worse than jeopardising safety.
2. PROACTIVE ASSERTION: every situation yields an action. "Unrecoverable" \
describes the DELAY, never the coordinator. Never advise standing down or doing \
nothing. When the clock cannot be clawed back, the job shifts to managing around \
it: communicate with tug and headset, protect the off-block, confirm the slot, \
notify the office you may be freed for redeployment.
3. MINUTE RECOVERY is the lowest priority, pursued only once 1 and 2 hold.

DEFINITION -- "recoverable" refers to the CAUSE, not to the clock. Set
recoverable=true when the cause of this delay admits direct operational
intervention by the coordinator or the ground team: fuelling, passenger
boarding, document and travel-permission checks, inbound PRM pickup, the
handling of a passenger issue at the gate, or pushback coordination. Set
recoverable=false when the cause sits outside the coordinator's control however
early it is known: an ATC slot restriction, a late inbound aircraft, a crew
report-time or rostering change, an engineering or airport-facilities issue.

Do NOT base this on whether the minutes can still be made up, and do NOT base it
on how much time remains. A cause may be recoverable even when the delay is now
too large to absorb, and unrecoverable even when the delay is small. The
question is solely whether the cause is one you can act on.

The coordinator may be handling several things at once. Your value is ensuring \
no available action is forgotten under load.

Reply with ONLY a JSON object, no prose and no markdown fences:
{"headline": str, "recoverable": bool, "kind": "recover"|"manage_around"|"safety_hold",
 "actions": [str, ...], "reasoning": [str, ...]}"""


def _build_user_prompt(inp: ReasonerInput) -> str:
    return (
        f"Turn: {inp.aircraft}, {inp.turn_type}.\n"
        f"Delay code {inp.code} ({inp.code_label}), {inp.minutes:.0f} min.\n"
        f"Door target {inp.door_target}; projected {inp.projected_door} "
        f"({inp.over_target:+.0f} min vs target).\n"
        f"PRM booked: {inp.has_prm}. EMA expected: {inp.has_ema}.\n"
        f"Live safety hazard: {inp.safety_flag}.\n"
        f"Flagged {inp.lead_time:.0f} min before a timing-only monitor could "
        f"prove the breach.\n"
        "Give the coordinator their next actions."
    )


class LLMReasoner:
    """Calls the Anthropic Messages API. Requires ANTHROPIC_API_KEY in env.

    Replies are cached on disk, keyed by the exact prompt and model. A run that
    changes only the rule side therefore costs nothing and returns instantly,
    and the cache doubles as an audit trail: the model outputs behind a reported
    result stay on disk and can be re-examined without another API call. Delete
    the cache directory, or pass use_cache=False, to force fresh calls.
    """
    name = "llm"

    def __init__(self, model: str = "claude-sonnet-4-6", max_tokens: int = 1000,
                 use_cache: bool = True):
        self.model = model
        self.max_tokens = max_tokens
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.use_cache = use_cache
        self.cache_dir = pathlib.Path(__file__).parent / "data" / "llm_cache"
        self.hits = 0
        self.misses = 0

    def _cache_path(self, prompt: str) -> pathlib.Path:
        key = hashlib.sha256(
            f"{self.model}\x00{SYSTEM_PROMPT}\x00{prompt}".encode()).hexdigest()
        return self.cache_dir / f"{key}.json"

    def _call(self, inp: ReasonerInput) -> str:
        prompt = _build_user_prompt(inp)

        if self.use_cache:
            p = self._cache_path(prompt)
            if p.exists():
                try:
                    self.hits += 1
                    return json.loads(p.read_text())["text"]
                except Exception:
                    pass

        body = json.dumps({
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"content-type": "application/json",
                     "x-api-key": self.api_key,
                     "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        text = "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text")

        self.misses += 1
        if self.use_cache:
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                self._cache_path(prompt).write_text(json.dumps(
                    {"model": self.model, "code": inp.code,
                     "prompt": prompt, "text": text}, indent=2))
            except Exception:
                pass
        return text

    def reason(self, inp: ReasonerInput) -> ReasonerOutput:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set -- export it to run "
                               "the LLM backend, or use MockLLMReasoner.")
        raw = self._call(inp).strip()
        return enforce_hierarchy(_parse(raw, self.name), inp)


def _parse(raw: str, backend: str) -> ReasonerOutput:
    """Parse model JSON defensively; a malformed reply must not crash the loop."""
    txt = raw.replace("```json", "").replace("```", "").strip()
    try:
        d = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
    except Exception:
        # Degrade safely -- the constraint layer will inject proactive steps.
        return ReasonerOutput(headline="Model reply unparsable.",
                              recoverable=False, kind="manage_around",
                              actions=[], reasoning=["parse failure"],
                              backend=backend)
    return ReasonerOutput(
        headline=str(d.get("headline", "")),
        recoverable=bool(d.get("recoverable", False)),
        kind=str(d.get("kind", "manage_around")),
        actions=[str(a) for a in d.get("actions", [])],
        reasoning=[str(r) for r in d.get("reasoning", [])],
        backend=backend)


class MockLLMReasoner(LLMReasoner):
    """Offline stand-in: exercises the parse + constraint path with no API key.

    Deliberately IMPERFECT -- it omits a safety hold and can return no action,
    so the constraint layer is demonstrably doing work rather than sitting idle.
    """
    name = "llm-mock"

    def reason(self, inp: ReasonerInput) -> ReasonerOutput:
        if inp.over_target > 40:
            raw = json.dumps({"headline": f"Large {inp.code_label} delay.",
                              "recoverable": False, "kind": "manage_around",
                              "actions": ["Nothing to do -- stand down and wait."],
                              "reasoning": ["Delay is outside TCO control."]})
        elif inp.code in ("36", "04", "85"):
            raw = json.dumps({"headline": f"Recoverable {inp.code_label} pressure.",
                              "recoverable": True, "kind": "recover",
                              "actions": [f"Chase the {inp.code_label} directly.",
                                          "Tell tug and headset departure may slip."],
                              "reasoning": ["Reversible on-stand pressure."]})
        else:
            raw = "not json at all"
        return enforce_hierarchy(_parse(raw, self.name), inp)


REASONERS = {"rules": RuleReasoner, "llm": LLMReasoner, "llm-mock": MockLLMReasoner}
