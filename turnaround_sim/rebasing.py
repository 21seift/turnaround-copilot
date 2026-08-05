
"""
Rebasing logic: resolving a turnaround schedule from the in-block anchor.

Core operational principle (confirmed against real dispatch records):

  Nothing can be predicted until the aircraft is IN-BLOCK. Before in-block only
  the scheduled times exist. The instant in-block is known, the whole schedule
  crystallises:

      estimated_departure = actual_in_block + spin_minutes
      door_target         = estimated_departure + door_offset   (-4 or -8)
      ... and every milestone resolves off its anchor.

  "spin_minutes" is the turnaround length for the type:
      first wave            -> choreographed from -60 (dead nightstop)
      daytime crew change   -> 35 (hot spin 25 exists but 35 is usual)
      daytime no crew change-> 30

  DELAY DECOMPOSITION (matches how the TCO books codes on the sheet):
      late_inbound (code 93) = estimated_departure - scheduled_departure
      before_closure delay   = actual_door_closure - door_target
                               (apportioned by cause: 36 fuel, 41 eng, 07 crew...)
      after_closure delay    = actual_off_block - (door_target - door_offset)
                               i.e. slippage past the rebased departure after
                               doors (code 81 slot, pushback, etc.)
      total_delay            = actual_off_block - scheduled_departure
"""

from __future__ import annotations

from dataclasses import dataclass

from .schedule import TurnType, Aircraft, door_closure_offset


# Turnaround "spin" length in minutes, by turn type.
def spin_minutes(turn: TurnType) -> float:
    return {
        TurnType.DAYTIME_CREW_CHANGE: 35.0,
        TurnType.DAYTIME_NO_CREW_CHANGE: 30.0,
        TurnType.FIRST_WAVE: 60.0,  # choreographed countdown from -60
    }[turn]


@dataclass
class ResolvedSchedule:
    """A schedule crystallised from a known in-block time."""

    actual_in_block: float
    scheduled_departure: float
    estimated_departure: float
    door_target: float
    door_offset: float

    @property
    def late_inbound(self) -> float:
        """Code 93 portion: how much the inbound pushed the departure."""
        return max(0.0, self.estimated_departure - self.scheduled_departure)


def resolve_from_in_block(
    *,
    turn: TurnType,
    actual_in_block: float,
    scheduled_departure: float,
) -> ResolvedSchedule:
    """
    Crystallise the schedule the moment in-block is known.

    Before this is callable there is no in-block, hence no prediction is
    possible -- the enforced precondition of the whole model.
    """
    est_dep = actual_in_block + spin_minutes(turn)
    offset = door_closure_offset(turn)
    door_target = est_dep + offset
    return ResolvedSchedule(
        actual_in_block=actual_in_block,
        scheduled_departure=scheduled_departure,
        estimated_departure=est_dep,
        door_target=door_target,
        door_offset=offset,
    )


def decompose_delay(
    sched: ResolvedSchedule,
    *,
    actual_door_closure: float,
    actual_off_block: float,
) -> dict[str, float]:
    """
    Break the total delay into the components the TCO books as codes.
    Returns minutes for: late_inbound, before_closure, after_closure, total.
    """
    total = max(0.0, actual_off_block - sched.scheduled_departure)
    before = max(0.0, actual_door_closure - sched.door_target)
    # The codes PARTITION the total delay (they must sum to it, as booked on
    # the sheet). Late-inbound and before-closure are taken first; the
    # after-closure portion (e.g. slot, code 81) is the remainder. This avoids
    # double-counting and matches how the TCO reconciles the sheet.
    after = max(0.0, total - sched.late_inbound - before)
    return {
        "late_inbound": sched.late_inbound,
        "before_closure": before,
        "after_closure": after,
        "total": total,
    }
