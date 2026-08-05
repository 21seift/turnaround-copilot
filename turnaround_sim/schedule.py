"""
Turnaround schedule model: the countdown structure.

This module replaces the earlier forward-counting task graph with a model that
reflects how a turnaround coordinator (TCO) actually works: BACKWARDS from a
fixed off-block time. Every milestone is a target pegged as an offset from
off-block (negative = before off-block; positive offsets exist only in the
inbound phase, measured from last-passenger-off the inbound).

Two linked phases:

  1. INBOUND ARRIVAL - the aircraft we meet, with its own schedule:
        in-block (t=0 for this phase), door 1 open +1.5, door 2 open +2.0,
        disembark complete +6.0. Delays here are diagnosed and coded against
        the inbound (late in-block -> code 93; slow disembark -> crew code).
        Last-passenger-off hands over to the outbound turnaround.

  2. OUTBOUND TURNAROUND - a backward countdown to a fixed off-block:
        the pivotal line is DOOR CLOSURE (-8 for a dead nightstop first wave,
        -4 for a daytime turn). Before closure the TCO owns the delay and may
        recover it; after closure it is largely out of their hands.

Turn types differ structurally, so the schedule is generated per type rather
than hard-coded once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TurnType(str, Enum):
    """The structurally distinct turnaround types."""

    FIRST_WAVE = "first_wave"                 # nightstop on stand, dead aircraft
    DAYTIME_CREW_CHANGE = "daytime_crew_change"
    DAYTIME_NO_CREW_CHANGE = "daytime_no_crew_change"


class Aircraft(str, Enum):
    """Airbus single-aisle types worked on the contract."""

    A319 = "319"
    A320 = "320"
    A321 = "321"


# Crew prep window (minutes from last-passenger-off inbound to green-light).
#   - Crew change: always 10 minutes, regardless of type.
#   - No crew change: driven by aircraft type (319 -> 7, 320/321 -> 8).
def prep_minutes(turn: TurnType, aircraft: Aircraft) -> float:
    if turn is TurnType.DAYTIME_CREW_CHANGE:
        return 10.0
    if turn is TurnType.FIRST_WAVE:
        # First wave has its own choreography from -60; prep does not apply
        # in the last-passenger-off sense (aircraft nightstopped, no inbound).
        return 0.0
    # No crew change: aircraft-type dependent.
    return 7.0 if aircraft is Aircraft.A319 else 8.0


# Door-closure target as an offset from off-block (minutes, negative).
def door_closure_offset(turn: TurnType) -> float:
    return -8.0 if turn is TurnType.FIRST_WAVE else -4.0
