"""
Milestone definitions for the countdown turnaround model.

A Milestone is a named point in the turnaround with a TARGET time expressed as
an offset from a reference anchor. Two anchors are used:

  - OFF_BLOCK: the fixed departure anchor for the outbound turnaround. Offsets
    are negative (before departure). Door closure, gate close, green-light etc.
  - LAST_PAX_OFF: the handover point from inbound to outbound. The crew prep
    window and green-light are measured forwards from here.
  - IN_BLOCK: the anchor for the inbound arrival phase.

A "delay" is defined as a milestone's ACTUAL time slipping past its TARGET.
This is the operational definition the TCO uses, and the prediction target for
the agent: will door closure (the KPI) be met against -4 or -8?
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Anchor(str, Enum):
    IN_BLOCK = "in_block"
    LAST_PAX_OFF = "last_pax_off"
    OFF_BLOCK = "off_block"


class Phase(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


@dataclass(frozen=True)
class Milestone:
    """
    A target point in the turnaround.

    Attributes
    ----------
    key: stable identifier, e.g. "door_closure".
    name: human-readable label for logs and agent prompts.
    anchor: which reference time the target offset is measured from.
    target_offset: minutes from the anchor (negative = before OFF_BLOCK).
    phase: inbound arrival vs outbound turnaround.
    is_kpi: whether the airline judges the TCO against this milestone.
    requires: optional expectation-context flag that must be true for this
              milestone to be expected at all (e.g. "prm" -> only expected if
              PRMs are booked; a missing PRM timestamp only matters then).
    """

    key: str
    name: str
    anchor: Anchor
    target_offset: float
    phase: Phase
    is_kpi: bool = False
    requires: str | None = None


# ---------------------------------------------------------------------------
# INBOUND ARRIVAL SCHEDULE (anchor = IN_BLOCK, offsets forward/positive).
# ---------------------------------------------------------------------------
INBOUND_MILESTONES: tuple[Milestone, ...] = (
    Milestone("in_block", "Aircraft in-block", Anchor.IN_BLOCK, 0.0,
              Phase.INBOUND, is_kpi=True),
    Milestone("door1_open", "Door 1 (front) open", Anchor.IN_BLOCK, 1.5,
              Phase.INBOUND),
    Milestone("door2_open", "Door 2 open", Anchor.IN_BLOCK, 2.0,
              Phase.INBOUND),
    Milestone("last_pax_off", "Last passenger off (disembark complete)",
              Anchor.IN_BLOCK, 6.0, Phase.INBOUND, is_kpi=True),
)


# ---------------------------------------------------------------------------
# OUTBOUND MILESTONES.
#
# Green-light and the boarding sequence are measured from LAST_PAX_OFF (the
# handover). Door closure, gate close and off-block are pegged to OFF_BLOCK.
# The prep window length (7/8/10 min) is turn/aircraft dependent and supplied
# at profile-build time, so green_light's offset from LAST_PAX_OFF is set then.
# ---------------------------------------------------------------------------


def build_outbound_milestones(door_offset: float) -> tuple[Milestone, ...]:
    """
    Outbound milestones for a given turn type.

    ``door_offset`` is -8.0 for a first-wave dead nightstop, -4.0 for daytime.
    Green-light's offset from LAST_PAX_OFF is the crew prep window; it is set
    on the profile (see TurnaroundProfile) rather than baked in here, because
    it varies by turn type and aircraft.
    """
    return (
        # Fuelling / services run in parallel; timestamps captured for
        # diagnosis. Targets here are guidance points before door closure.
        Milestone("fuelling_start", "Fuelling start", Anchor.OFF_BLOCK,
                  door_offset - 12.0, Phase.OUTBOUND),
        Milestone("fuelling_end", "Fuelling complete", Anchor.OFF_BLOCK,
                  door_offset - 4.0, Phase.OUTBOUND),
        Milestone("green_light", "Green-light boarding (boarding KPI)",
                  Anchor.LAST_PAX_OFF, 0.0, Phase.OUTBOUND, is_kpi=True),
        Milestone("first_prm_on", "First PRM boarded", Anchor.OFF_BLOCK,
                  door_offset - 6.0, Phase.OUTBOUND, requires="prm"),
        Milestone("last_prm_on", "Last PRM boarded", Anchor.OFF_BLOCK,
                  door_offset - 4.0, Phase.OUTBOUND, requires="prm"),
        Milestone("gate_close", "Gate closed", Anchor.OFF_BLOCK,
                  door_offset - 1.0, Phase.OUTBOUND, is_kpi=True),
        Milestone("last_pax_on", "Last passenger boarded", Anchor.OFF_BLOCK,
                  door_offset - 1.0, Phase.OUTBOUND),
        Milestone("ema_handover", "EMA handover complete", Anchor.OFF_BLOCK,
                  door_offset - 2.0, Phase.OUTBOUND, requires="ema"),
        Milestone("loadsheet_to_captain", "Final figures to captain",
                  Anchor.OFF_BLOCK, door_offset - 1.0, Phase.OUTBOUND),
        Milestone("loadsheet_from_captain", "Loadsheet returned by captain",
                  Anchor.OFF_BLOCK, door_offset - 0.5, Phase.OUTBOUND),
        Milestone("door_closure", "Doors closed (pivotal KPI)",
                  Anchor.OFF_BLOCK, door_offset, Phase.OUTBOUND, is_kpi=True),
        Milestone("off_block", "Off-block (departure)", Anchor.OFF_BLOCK, 0.0,
                  Phase.OUTBOUND, is_kpi=True),
    )
