"""
Local server for the demonstration interface.

    python -m turnaround_sim.serve      then open http://localhost:8000

Standard library only -- no framework, no build step, nothing to install
beyond the project's own requirements. The browser holds no domain logic: it
posts timestamps and renders what comes back, so the interface cannot drift
from the engine evaluated in Chapter 4.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
from http.server import BaseHTTPRequestHandler, HTTPServer

from .attribution import assess

UI = pathlib.Path(__file__).parent / "ui" / "index.html"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:                                   # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, UI.read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:                                  # noqa: N802
        if self.path not in ("/api/assess", "/api/timeline"):
            self._send(404, b"not found", "text/plain")
            return
        n = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
            kw = dict(
                turn=payload.get("turn", "DAYTIME_CREW_CHANGE"),
                aircraft=payload.get("aircraft", "A320"),
                scheduled_departure=float(payload["scheduled_departure"]),
                actual_in_block=float(payload["actual_in_block"]),
                has_prm=bool(payload.get("has_prm")),
                has_ema=bool(payload.get("has_ema")),
                safety_flag=bool(payload.get("safety_flag")),
                reported_code=(payload.get("reported_code") or None),
                reported_at=(float(payload["reported_at"])
                             if payload.get("reported_at") not in (None, "")
                             else None))
            actuals = {k: float(v) for k, v in
                       (payload.get("actuals") or {}).items()
                       if v is not None and v != ""}

            if self.path == "/api/assess":
                body = json.dumps(dataclasses.asdict(
                    assess(actuals=actuals, **kw))).encode()
            else:
                body = json.dumps(self._timeline(actuals, kw)).encode()
            self._send(200, body, "application/json")
        except Exception as e:                                  # noqa: BLE001
            self._send(400, json.dumps({"error": f"{type(e).__name__}: {e}"})
                       .encode(), "application/json")

    @staticmethod
    def _timeline(actuals: dict, kw: dict) -> dict:
        """
        Replay the turn a minute at a time, showing each approach only what
        had actually happened by that minute.

        This is what makes the comparison honest: the agent is not given the
        finished record and asked to explain it after the fact. At every step
        it sees the same partial event stream a coordinator would have, and
        the moment a cause becomes knowable is exactly the moment it speaks.
        """
        start = int(kw["actual_in_block"])
        end = int(max(list(actuals.values()) or [start]) + 5)
        base = assess(actuals=actuals, **kw)          # full-record reference
        door_target = base.schedule["door_target"]
        end = int(max(end, door_target + 10))

        frames = []
        for t in range(start, end + 1):
            known = {k: v for k, v in actuals.items() if v <= t}
            a = assess(actuals=known, now=float(t), **kw)
            landed = sorted(known.items(), key=lambda kv: kv[1])
            # A threshold dashboard cannot say anything until a target is
            # actually passed -- that is the whole of its logic.
            closure = actuals.get("door_closure")
            dashboard = (t >= door_target and
                         (closure is None or closure > door_target))
            frames.append({
                "t": t,
                "assessment": dataclasses.asdict(a),
                "dashboard": bool(dashboard),
                "landed": [k for k, _ in landed],
            })
        return {"frames": frames, "start": start, "end": end,
                "door_target": door_target,
                "schedule": base.schedule}

    def log_message(self, *a) -> None:                          # quiet
        pass


def main(port: int = 8000) -> None:
    try:
        srv = HTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        raise SystemExit(f"Port {port} is not available ({e}). "
                         f"Try another, e.g. python -m turnaround_sim.serve 8765")
    print(f"Turnaround copilot -- open http://localhost:{port}")
    print("Ctrl-C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    import sys
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
