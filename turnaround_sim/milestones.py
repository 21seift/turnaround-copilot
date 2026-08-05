"""
Domain model for the aircraft turnaround.

This module defines the turnaround as a directed acyclic graph (DAG) of tasks
with precedence constraints, grounded in the A-CDM milestone framework. It is
intentionally free of any simulation-engine detail: it describes *what* a
turnaround is, not *how* time advances. That separation keeps the domain model
testable in isolation and reusable by the baselines and the agent.

References for the milestone structure:
    EUROCONTROL Specification for A-CDM (milestones, TOBT logic).
    The task set below is a faithful-but-minimal short-haul turnaround; it can be
    extended without changing the surrounding machinery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class TaskState(str, Enum):
    """Lifecycle of a single turnaround task."""

    PENDING = "pending"      # not yet started; predecessors may be incomplete
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


@dataclass(frozen=True)
class TaskSpec:
    """
    Static specification of one turnaround task.

    Attributes
    ----------
    key:
        Stable machine identifier (e.g. "fuelling").
    name:
        Human-readable label used in event logs and agent prompts.
    nominal_duration:
        Planned duration in minutes under undisrupted conditions.
    predecessors:
        Task keys that must be COMPLETE before this task may start. This encodes
        the precedence structure of the turnaround; tasks with disjoint
        predecessor chains may run concurrently.
    resource:
        Optional key of a shared resource this task requires (e.g. a loading
        team). Used by the multi-stand extension; ``None`` means the task needs
        no contended resource.
    milestone:
        Optional A-CDM milestone label emitted when this task completes. Not all
        tasks map to a formal milestone.
    """

    key: str
    name: str
    nominal_duration: float
    predecessors: tuple[str, ...] = ()
    resource: str | None = None
    milestone: str | None = None


# ---------------------------------------------------------------------------
# The reference short-haul turnaround.
#
# Precedence rationale (defensible in a viva; challenge these with your own
# operational knowledge at the fidelity gate):
#   - Nothing on the aircraft interior starts until the aircraft is on-block and
#     the bridge/steps are connected.
#   - Deboarding must finish before cleaning and (for a single-aisle) before
#     boarding.
#   - Catering and cleaning can proceed in parallel once the cabin is clear.
#   - Fuelling can overlap ground service but, under with-passengers fuelling
#     constraints, boarding completion is gated on fuelling completion here
#     (a deliberately conservative modelling choice).
#   - Loading (holds) runs in parallel with cabin work.
#   - Pushback readiness requires boarding complete, loading complete, and
#     fuelling complete; doors closed follows.
# ---------------------------------------------------------------------------
REFERENCE_TURNAROUND: tuple[TaskSpec, ...] = (
    TaskSpec("on_block", "Aircraft on-block", 0.0, (), None, "AIBT"),
    TaskSpec("bridge", "Bridge/steps connected", 2.0, ("on_block",), "bridge_team"),
    TaskSpec("deboard", "Deboarding", 6.0, ("bridge",), None, "deboarding_complete"),
    TaskSpec("clean", "Cabin cleaning", 8.0, ("deboard",), "cabin_team"),
    TaskSpec("catering", "Catering", 7.0, ("deboard",), "catering_team"),
    TaskSpec("fuelling", "Refuelling", 10.0, ("on_block",), "fuel_team"),
    TaskSpec("unload", "Unload holds", 6.0, ("on_block",), "loading_team"),
    TaskSpec("load", "Load holds", 8.0, ("unload",), "loading_team"),
    TaskSpec("board", "Boarding", 12.0, ("clean", "catering", "fuelling"), "bridge_team", "boarding_complete"),
    TaskSpec("doors", "Doors closed", 1.0, ("board", "load"), None, "doors_closed"),
    TaskSpec("pushback_ready", "Ready for pushback", 0.0, ("doors",), None, "TOBT_met"),
)


class TurnaroundModel:
    """
    A validated turnaround dependency graph.

    Wraps a set of :class:`TaskSpec` objects and provides the queries the
    simulator, baselines and agent all need: predecessor/successor lookups,
    topological ordering, and critical-path duration under nominal timings.
    """

    def __init__(self, tasks: Iterable[TaskSpec] = REFERENCE_TURNAROUND) -> None:
        self._tasks: dict[str, TaskSpec] = {t.key: t for t in tasks}
        self._validate()

    # -- construction-time validation ------------------------------------
    def _validate(self) -> None:
        """Fail fast on malformed graphs: unknown predecessors or cycles."""
        for task in self._tasks.values():
            for pred in task.predecessors:
                if pred not in self._tasks:
                    raise ValueError(
                        f"Task '{task.key}' references unknown predecessor '{pred}'"
                    )
        # Cycle detection via topological sort (raises if impossible).
        self.topological_order()

    # -- basic queries ---------------------------------------------------
    def __contains__(self, key: str) -> bool:
        return key in self._tasks

    def __getitem__(self, key: str) -> TaskSpec:
        return self._tasks[key]

    def __iter__(self):
        return iter(self._tasks.values())

    def __len__(self) -> int:
        return len(self._tasks)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(self._tasks.keys())

    def predecessors(self, key: str) -> tuple[str, ...]:
        return self._tasks[key].predecessors

    def successors(self, key: str) -> tuple[str, ...]:
        return tuple(t.key for t in self._tasks.values() if key in t.predecessors)

    # -- structural algorithms ------------------------------------------
    def topological_order(self) -> list[str]:
        """
        Return task keys in a valid dependency order (Kahn's algorithm).

        Raises
        ------
        ValueError
            If the graph contains a cycle (which would make the turnaround
            physically impossible).
        """
        indegree = {k: len(self._tasks[k].predecessors) for k in self._tasks}
        ready = [k for k, d in indegree.items() if d == 0]
        order: list[str] = []
        while ready:
            node = ready.pop()
            order.append(node)
            for succ in self.successors(node):
                indegree[succ] -= 1
                if indegree[succ] == 0:
                    ready.append(succ)
        if len(order) != len(self._tasks):
            raise ValueError("Turnaround graph contains a cycle")
        return order

    def critical_path_duration(self) -> float:
        """
        Longest-path duration through the graph under nominal timings.

        This is the theoretical minimum turnaround time when no disruption
        occurs and resources are unconstrained. It is the natural reference
        point for both the critical-path baseline and for judging breaches.
        """
        earliest_finish: dict[str, float] = {}
        for key in self.topological_order():
            task = self._tasks[key]
            start = max(
                (earliest_finish[p] for p in task.predecessors),
                default=0.0,
            )
            earliest_finish[key] = start + task.nominal_duration
        return max(earliest_finish.values(), default=0.0)

    def critical_path(self) -> list[str]:
        """Return the sequence of task keys lying on the critical path."""
        earliest_finish: dict[str, float] = {}
        chosen_pred: dict[str, str | None] = {}
        for key in self.topological_order():
            task = self._tasks[key]
            best_pred, best_finish = None, 0.0
            for p in task.predecessors:
                if earliest_finish[p] >= best_finish:
                    best_pred, best_finish = p, earliest_finish[p]
            earliest_finish[key] = best_finish + task.nominal_duration
            chosen_pred[key] = best_pred
        # Walk back from the latest-finishing task.
        end = max(earliest_finish, key=earliest_finish.get)
        path = [end]
        while chosen_pred[path[-1]] is not None:
            path.append(chosen_pred[path[-1]])
        return list(reversed(path))
