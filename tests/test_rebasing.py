"""
Regression tests: the model must reproduce real dispatch-record arithmetic.

Ground truth from three flights worked by the TCO (July 2026). If any change
breaks these, the model has drifted from operational reality.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from turnaround_sim.schedule import TurnType
from turnaround_sim.rebasing import resolve_from_in_block, decompose_delay


def mins(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _check(turn, in_block, sched_dep, doors, off_block, expect):
    sched = resolve_from_in_block(
        turn=turn, actual_in_block=mins(in_block),
        scheduled_departure=mins(sched_dep),
    )
    dec = decompose_delay(sched, actual_door_closure=mins(doors),
                          actual_off_block=mins(off_block))
    for k, v in expect.items():
        assert abs(dec[k] - v) < 0.01, f"{k}: got {dec[k]}, expected {v}"


def test_pink_a319_edi_gro():
    _check(TurnType.DAYTIME_NO_CREW_CHANGE,
           "15:54", "16:05", "16:34", "16:49",
           {"late_inbound": 19, "before_closure": 14, "after_closure": 11, "total": 44})


def test_stand_74_a320_positioning():
    _check(TurnType.DAYTIME_CREW_CHANGE,
           "11:31", "11:15", "12:35", "12:35",
           {"late_inbound": 51, "before_closure": 33})
