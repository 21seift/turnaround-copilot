"""
Aggregate returned expert appraisals.

Put the returned CSV files in one folder and point this at it:

    python -m turnaround_sim.tally_appraisal /mnt/user-data/uploads

Reports agreement rates overall and per delay code, and lists every case where
a respondent dissented. The dissents matter more than the totals: an agreement
percentage says the system is plausible, whereas a coordinator explaining why
they would not action a recommendation says exactly where it is wrong.
"""

from __future__ import annotations

import csv
import pathlib
import sys
from collections import defaultdict

ACTION = {"as_written": "would action as written",
          "with_changes": "would action with changes",
          "no": "would not action"}


def read(folder: pathlib.Path) -> list[dict]:
    responses = []
    for f in sorted(folder.glob("*.csv")):
        rows, overall = [], {}
        with f.open() as fh:
            for r in csv.reader(fh):
                if not r or not r[0]:
                    continue
                if r[0] in ("overall_useful", "overall_trust", "overall_clear",
                            "experience", "notes"):
                    overall[r[0]] = r[1] if len(r) > 1 else ""
                elif r[0] != "case":
                    rows.append(dict(zip(
                        ["case", "code", "label", "minutes", "kind",
                         "recoverable", "would_action", "recoverability_view",
                         "comment"], r)))
        if rows:
            responses.append({"file": f.name, "rows": rows, "overall": overall})
    return responses


def main(folder: str = "/mnt/user-data/uploads") -> None:
    responses = read(pathlib.Path(folder))
    if not responses:
        raise SystemExit(f"No appraisal CSV files found in {folder}")

    n = len(responses)
    print(f"\n{n} respondent{'s' if n != 1 else ''}\n" + "=" * 58)

    act: dict[str, int] = defaultdict(int)
    rec: dict[str, int] = defaultdict(int)
    by_code: dict[str, list[str]] = defaultdict(list)
    dissent = []

    for r in responses:
        for row in r["rows"]:
            a, v = row["would_action"], row["recoverability_view"]
            if a:
                act[a] += 1
                by_code[row["code"]].append(a)
            if v:
                rec[v] += 1
            if a in ("no", "with_changes") or v == "disagree":
                dissent.append((row["code"], row["label"], a, v,
                                row["comment"].strip()))

    total = sum(act.values())
    print("\nWould you action this recommendation?")
    for k, lab in ACTION.items():
        c = act.get(k, 0)
        print(f"  {lab:<28} {c:>4}  ({c/total*100:.0f}%)" if total else "")
    accept = act.get("as_written", 0) + act.get("with_changes", 0)
    if total:
        print(f"  -> actionable in some form      {accept:>4}  "
              f"({accept/total*100:.0f}%)")

    rtot = sum(rec.values())
    if rtot:
        print("\nRecoverability classification")
        for k in ("agree", "disagree", "unsure"):
            c = rec.get(k, 0)
            print(f"  {k:<28} {c:>4}  ({c/rtot*100:.0f}%)")

    print("\nBy delay code (share actionable in some form)")
    for code in sorted(by_code):
        v = by_code[code]
        ok = sum(1 for x in v if x != "no")
        print(f"  code {code:<4} n={len(v):<3} {ok/len(v)*100:>5.0f}%")

    print(f"\nDissents ({len(dissent)}) -- the useful part")
    for code, label, a, v, comment in dissent:
        note = f' "{comment}"' if comment else ""
        print(f"  code {code} {label[:26]:<26} {a or '-'}/{v or '-'}{note}")

    print("\nOverall ratings (1 low - 5 high)")
    for key in ("overall_useful", "overall_trust", "overall_clear"):
        vals = [int(r["overall"][key]) for r in responses
                if r["overall"].get(key, "").isdigit()]
        if vals:
            print(f"  {key.replace('overall_',''):<10} "
                  f"mean {sum(vals)/len(vals):.1f}  n={len(vals)}")
    exp = [r["overall"].get("experience", "") for r in responses]
    print("  experience:", ", ".join(x for x in exp if x) or "not given")
    print()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads")
