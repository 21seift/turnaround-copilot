"""
Event stream primitives.

The simulator's output is a stream of timestamped events. Everything downstream
- the baselines, the agent, the evaluation - consumes this stream rather than
reaching into the simulator's internals. Keeping the event schema small and
explicit is what lets those layers stay decoupled from the simulation engine.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """The kinds of state change the simulator reports."""

    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    MILESTONE = "milestone"          # an A-CDM milestone was reached
    DISRUPTION = "disruption"        # a disruption was injected
    TURNAROUND_STARTED = "turnaround_started"
    TURNAROUND_ENDED = "turnaround_ended"


@dataclass(frozen=True)
class Event:
    """
    A single timestamped occurrence during a turnaround.

    Attributes
    ----------
    time:
        Simulation time in minutes since the turnaround began.
    type:
        The :class:`EventType`.
    stand:
        Identifier of the stand/turnaround this event belongs to. Present from
        the outset so the multi-stand extension needs no schema change.
    task:
        Task key the event concerns, if any.
    detail:
        Free-form structured payload (e.g. milestone label, disruption kind).
    """

    time: float
    type: EventType
    stand: str
    task: str | None = None
    detail: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        return d

    def __str__(self) -> str:
        t = f"[t={self.time:6.2f}] {self.stand:>6} {self.type.value:<18}"
        if self.task:
            t += f" {self.task}"
        if self.detail:
            t += f" {self.detail}"
        return t
