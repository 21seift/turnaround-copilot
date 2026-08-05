
"""
TurnaroundProfile: a concrete, resolved turnaround.

Combines a turn type, aircraft type and the expectation context (are there
PRMs? an EMA? how many bags expected?) into a fully-resolved set of milestones
with concrete target times, once a fixed off-block time is chosen.

The expectation context is what lets the agent reason correctly about missing
timestamps: a missing PRM-boarded milestone only signals a problem if PRMs were
expected. This is the "expectation vs reality" reasoning at the core of the
agentic contribution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .schedule import TurnType, Aircraft, prep_minutes, door_closure_offset
from .milestones_v2 import (
    Anchor, Phase, Milestone, INBOUND_MILESTONES, build_outbound_milestones,
)


@dataclass
class ExpectationContext:
    """
    What the TCO expects for this specific turnaround.

    Only fields that change what the agent should EXPECT or RECOMMEND are kept;
    pure compliance detail (base splits, bag weights, signatures) is out of
    scope by design.
    """

    has_prm: bool = False
    has_ema: bool = False
    bags_expected: int = 0  # how many bags SHOULD be loaded (0 = none expected)

    def flag(self, name: str) -> bool:
        return {"prm": self.has_prm, "ema": self.has_ema}.get(name, True)


@dataclass
class TurnaroundProfile:
    """A fully-resolved turnaround ready to schedule against a fixed off-block."""

    turn_type: TurnType
    aircraft: Aircraft
    context: ExpectationContext = field(default_factory=ExpectationContext)

    @property
    def prep_window(self) -> float:
        return prep_minutes(self.turn_type, self.aircraft)

    @property
    def door_offset(self) -> float:
        return door_closure_offset(self.turn_type)

    def milestones(self) -> tuple[Milestone, ...]:
        """
        Expected milestones for this turn, filtered by expectation context.

        A milestone with a ``requires`` flag is only included if the context
        says it is expected (e.g. PRM milestones only when has_prm is True).
        Green-light's LAST_PAX_OFF offset is set to the prep window here.
        """
        outbound = build_outbound_milestones(self.door_offset)
        resolved = []
        for m in INBOUND_MILESTONES + outbound:
            if m.requires and not self.context.flag(m.requires):
                continue  # not expected -> a missing timestamp is a non-event
            if m.key == "green_light":
                m = Milestone(m.key, m.name, m.anchor, self.prep_window,
                              m.phase, m.is_kpi, m.requires)
            resolved.append(m)
        return tuple(resolved)

    def target_time(self, milestone: Milestone, *, off_block: float,
                    in_block: float, last_pax_off: float) -> float:
        """Resolve a milestone's target to an absolute clock time (minutes)."""
        if milestone.anchor is Anchor.OFF_BLOCK:
            return off_block + milestone.target_offset
        if milestone.anchor is Anchor.IN_BLOCK:
            return in_block + milestone.target_offset
        return last_pax_off + milestone.target_offset
