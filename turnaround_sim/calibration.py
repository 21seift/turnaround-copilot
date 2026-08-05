"""
Delay-code calibration -- typical and bad-day minutes per code.

Source: elicited directly from the TCO\'s operational experience (July 2026),
not from a published table. These are working estimates to drive realistic
scenario generation, and should be refined as more real sheets accrue.

Each entry carries:
  typical      -- the usual delay in minutes when this code bites
  bad          -- a bad-day figure
  mechanic     -- how it acts on the schedule:
                    "spike"   : usually ~0, occasional jump (fuelling)
                    "shift"   : moves the anchor / gates a handover (late inbound, inbound PRM)
                    "stretch" : lengthens a task in place (outbound PRM, EMA, crew)
                    "hold"    : ready but held after closure (slot)
  recoverable  -- does the TCO have a lever? drives the triage the agent must do
  note         -- operational context worth keeping
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CodeCalibration:
    code: str
    label: str
    typical: float
    bad: float
    mechanic: str
    recoverable: bool
    note: str = ""


CALIBRATION = {
    "36": CodeCalibration(
        code="36", label="refuelling", typical=0.0, bad=15.0,
        mechanic="spike", recoverable=True,
        note="Fuellers pre-positioned; normally finishes inside boarding. "
             "Mostly zero delay, rare spike up to ~15 (pink sheet was a bad day)."),
    "93": CodeCalibration(
        code="93", label="late inbound", typical=48.0, bad=120.0,
        mechanic="shift", recoverable=False,
        note="Dominant disruption. Range minutes-to-hours; average ~45-50. "
             "Rebases the whole countdown off actual in-block."),
    "81": CodeCalibration(
        code="81", label="slot", typical=30.0, bad=45.0,
        mechanic="hold", recoverable=False,
        note="Can push up to 20 min before slot; in-season average ~30. "
             "After-closure remainder; office books it, no TCO lever."),
    "41": CodeCalibration(
        code="41", label="engineering on board", typical=30.0, bad=95.0,
        mechanic="stretch", recoverable=False,
        note="Usual 10-60; long tail past that. Not a hard rule, but serious "
             "faults tend to trigger an aircraft swap (~2h region) rather than wait."),
    "67": CodeCalibration(
        code="67", label="late crew", typical=33.0, bad=60.0,
        mechanic="stretch", recoverable=False,
        note="~33 typical for someone called off standby (travel + walk to aircraft)."),
    "04_in": CodeCalibration(
        code="04", label="PRM inbound (off arrival)", typical=20.0, bad=45.0,
        mechanic="shift", recoverable=False,
        note="10-45. GATES the turn: pax off first, then PRMs; prep-to-green-light "
             "clock only starts once PRMs are off. Late PRM pickup holds everything."),
    "04_out": CodeCalibration(
        code="04", label="PRM outbound (boarding)", typical=17.0, bad=25.0,
        mechanic="stretch", recoverable=True,
        note="15-20. Stretches boarding; late in sequence, threatens final KPI."),
    "ema": CodeCalibration(
        code="ema", label="EMA handover", typical=20.0, bad=30.0,
        mechanic="stretch", recoverable=True,
        note="~20. Happens AFTER PRM pax boarded; handover to team leader, out to "
             "hold, strapped down. Late-sequence, only exists if EMA expected."),
}


def summary() -> str:
    rows = []
    for c in CALIBRATION.values():
        rec = "recoverable" if c.recoverable else "not recoverable"
        rows.append(f"  {c.code:<6} {c.label:<26} typ {c.typical:>4.0f}  "
                    f"bad {c.bad:>4.0f}  {c.mechanic:<8} {rec}")
    return "\n".join(rows)
