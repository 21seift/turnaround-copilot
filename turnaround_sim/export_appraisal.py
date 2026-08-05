"""
Build the expert appraisal instrument.

Chapter 4 establishes that the agent is earlier than the baselines and that it
attributes a cause to every breach. Neither of those says the advice is any
good -- a system can be reliably early and reliably wrong. Only a practising
coordinator can judge that, so this generates a rating instrument over the same
27 cases the reasoner comparison uses.

Cases are rendered with calibrated code labels rather than the wording recorded
on the source sheets, so the instrument carries no operator-identifying text and
can be reproduced in an appendix.

    python -m turnaround_sim.export_appraisal
"""

from __future__ import annotations

import json
import pathlib

from .calibration import CALIBRATION
from .compare_reasoners import load_cases
from .reasoner import RuleReasoner, enforce_hierarchy

OUT = pathlib.Path("/mnt/user-data/outputs")

CONSENT = """This survey supports a postgraduate research project on decision
support for aircraft turnaround coordination. It asks for your professional
judgement of recommendations produced by a prototype system.

Taking part is voluntary and you may stop at any time. No name, staff number,
employer or any other identifying detail is collected, and responses cannot be
traced back to you. Results are reported only as aggregate counts and anonymous
comments. Nothing you enter is sent anywhere automatically -- your answers stay
in this browser until you export them and hand them back.

There are no right answers. Where you disagree with the system, that
disagreement is the most useful thing you can give."""


def build_cases() -> list[dict]:
    reasoner = RuleReasoner()
    out = []
    for i, c in enumerate(load_cases(), start=1):
        cal = CALIBRATION.get(c.code)
        label = cal.label if cal else c.code_label
        rec = enforce_hierarchy(reasoner.reason(c), c)
        out.append({
            "n": i,
            "code": c.code,
            "label": label,
            "minutes": c.minutes,
            "turn": c.turn_type.replace("_", " ").lower(),
            "aircraft": c.aircraft,
            "prm": bool(c.has_prm),
            "safety": bool(c.safety_flag),
            "headline": rec.headline,
            "kind": rec.kind,
            "recoverable": bool(rec.recoverable),
            "actions": list(rec.actions),
        })
    return out


HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Turnaround recommendations — professional appraisal</title>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700&family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#0B1015;--panel:#141C24;--panel2:#1B2732;--line:#2A3A47;--text:#DCE6ED;
--dim:#7E93A3;--cyan:#55C7DE;--green:#35D08A;--amber:#FFB020;--red:#FF4D4F;
--sans:"Barlow Condensed",Arial Narrow,sans-serif;--mono:"IBM Plex Mono",monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:var(--sans);
font-size:18px;line-height:1.45}
.wrap{max-width:660px;margin:0 auto;padding:18px 16px 70px}
h1{font-size:25px;margin:0 0 4px}
.sub{font-family:var(--mono);font-size:11px;color:var(--dim);letter-spacing:.12em;
text-transform:uppercase}
.card{background:var(--panel);border:1px solid var(--line);margin:14px 0}
.card-b{padding:16px}
.consent{white-space:pre-line;color:var(--dim);font-size:16px}
button{background:var(--cyan);color:#04161C;border:none;font-family:var(--mono);
font-size:13px;letter-spacing:.12em;text-transform:uppercase;font-weight:600;
padding:14px 18px;cursor:pointer;width:100%;margin-top:10px}
button.ghost{background:transparent;color:var(--dim);border:1px solid var(--line)}
button:focus-visible{outline:2px solid var(--text);outline-offset:2px}
.prog{font-family:var(--mono);font-size:11px;color:var(--dim);letter-spacing:.1em;
display:flex;justify-content:space-between;margin-bottom:8px}
.pbar{height:3px;background:var(--line);margin-bottom:16px}
.pbar div{height:3px;background:var(--cyan)}
.sit{font-family:var(--mono);font-size:12px;color:var(--dim);letter-spacing:.06em;
margin-bottom:10px}
.chip{display:inline-block;border:1px solid var(--line);padding:2px 8px;margin-right:6px}
.chip.sf{border-color:var(--red);color:var(--red)}
.badge{display:inline-block;font-family:var(--mono);font-size:10px;letter-spacing:.14em;
text-transform:uppercase;padding:4px 9px;margin-bottom:10px}
.b-safety{background:var(--red);color:#160406;font-weight:600}
.b-recover{background:var(--green);color:#04160E;font-weight:600}
.b-manage{background:var(--amber);color:#1A1000;font-weight:600}
h2{font-size:21px;margin:0 0 12px;line-height:1.25}
ul.acts{list-style:none;margin:0;padding:0}
ul.acts li{padding:7px 0;border-top:1px solid var(--line);font-size:17px}
.q{margin-top:18px;border-top:1px solid var(--line);padding-top:14px}
.q p{font-size:17px;margin:0 0 9px}
.opts{display:grid;gap:7px}
.opt{display:block;border:1px solid var(--line);padding:11px 13px;cursor:pointer;
font-size:16px;background:var(--panel2)}
.opt:hover{border-color:var(--dim)}
.opt input{margin-right:9px;accent-color:var(--cyan)}
.opt.sel{border-color:var(--cyan);background:rgba(85,199,222,.10)}
textarea{width:100%;background:var(--panel2);border:1px solid var(--line);
color:var(--text);font-family:var(--sans);font-size:16px;padding:10px;min-height:64px}
textarea:focus{outline:2px solid var(--cyan);outline-offset:-1px}
.nav{display:flex;gap:9px;margin-top:14px}
.nav button{margin:0}
.done{text-align:center;padding:26px 0}
.done .big{font-size:30px;font-weight:700;margin-bottom:8px}
label.scale{display:flex;justify-content:space-between;font-family:var(--mono);
font-size:11px;color:var(--dim);margin-top:4px}
@media print{body{background:#fff;color:#000}.nav,button{display:none}
.card{border-color:#999;page-break-inside:avoid}}
</style></head><body><div class="wrap" id="app"></div>
<script>
const CASES = __CASES__;
const CONSENT = __CONSENT__;
let step = -1;                       // -1 consent, 0..n-1 cases, n final, n+1 done
const R = {};                        // responses
const FINAL = {};

const $ = () => document.getElementById("app");
const esc = s => String(s).replace(/[<>&]/g, c => ({"<":"&lt;",">":"&gt;","&":"&amp;"}[c]));

function render(){
  if(step === -1) return consent();
  if(step < CASES.length) return caseView(CASES[step]);
  if(step === CASES.length) return finalView();
  return doneView();
}

function consent(){
  $().innerHTML = `<h1>Turnaround recommendations</h1>
    <div class="sub">professional appraisal — about 15 minutes</div>
    <div class="card"><div class="card-b">
      <div class="consent">${esc(CONSENT)}</div>
      <button onclick="start()">I understand — begin</button>
    </div></div>`;
}
function start(){ step = 0; render(); }

function caseView(c){
  const bm = c.kind==="safety_hold" ? ["b-safety","safety hold"]
           : c.kind==="recover" ? ["b-recover","recoverable"]
           : ["b-manage","manage around"];
  const r = R[c.n] || {};
  const opt = (name,val,txt) => `<label class="opt ${r[name]===val?"sel":""}">
     <input type="radio" name="${name}" ${r[name]===val?"checked":""}
      onchange="set(${c.n},'${name}','${val}',this)">${txt}</label>`;
  $().innerHTML = `
    <div class="prog"><span>case ${c.n} of ${CASES.length}</span>
      <span>code ${c.code}</span></div>
    <div class="pbar"><div style="width:${(c.n/CASES.length)*100}%"></div></div>
    <div class="card"><div class="card-b">
      <div class="sit">
        <span class="chip">${esc(c.turn)}</span><span class="chip">${c.aircraft}</span>
        ${c.prm?'<span class="chip">PRM</span>':""}
        ${c.safety?'<span class="chip sf">hazard</span>':""}
      </div>
      <div class="sit">Code ${c.code} — ${esc(c.label)} · ${c.minutes} min</div>
      <span class="badge ${bm[0]}">${bm[1]}</span>
      <h2>${esc(c.headline)}</h2>
      <ul class="acts">${c.actions.map(a=>`<li>${esc(a)}</li>`).join("")}</ul>

      <div class="q"><p>Would you action this recommendation?</p>
        <div class="opts">
          ${opt("action","as_written","Yes — as written")}
          ${opt("action","with_changes","Yes — but I would change something")}
          ${opt("action","no","No")}
        </div></div>

      <div class="q"><p>Is the system right that this is
        <strong>${c.recoverable?"recoverable":"not recoverable"}</strong>?</p>
        <div class="opts">
          ${opt("recov","agree","Agree")}
          ${opt("recov","disagree","Disagree")}
          ${opt("recov","unsure","Not sure")}
        </div></div>

      <div class="q"><p>Anything you would change or add? (optional)</p>
        <textarea onchange="set(${c.n},'comment',this.value)">${esc(r.comment||"")}</textarea>
      </div>

      <div class="nav">
        <button class="ghost" onclick="back()">Back</button>
        <button onclick="next()">${step===CASES.length-1?"Last questions":"Next"}</button>
      </div>
    </div></div>`;
}

// Update the selection in place. A full re-render on every tap would throw the
// reader back to the top of the page, which on a phone in a crew room is the
// difference between finishing the survey and abandoning it.
function set(n,k,v,el){
  (R[n] = R[n]||{})[k]=v;
  if(k==="comment" || !el) return;
  document.querySelectorAll(`input[name="${k}"]`).forEach(i=>
    i.closest(".opt").classList.toggle("sel", i===el));
}
function next(){ step++; window.scrollTo(0,0); render(); }
function back(){ if(step>0){ step--; window.scrollTo(0,0); render(); } }

function finalView(){
  const sc = (name,q) => `<div class="q"><p>${q}</p><div class="opts">
    ${[1,2,3,4,5].map(v=>`<label class="opt ${FINAL[name]==v?"sel":""}">
      <input type="radio" name="${name}" ${FINAL[name]==v?"checked":""}
       onchange="setF('${name}',${v},this)">${v} — ${["not at all","a little","somewhat","quite","very"][v-1]}
    </label>`).join("")}</div></div>`;
  $().innerHTML = `<h1>Last few questions</h1>
    <div class="card"><div class="card-b">
      ${sc("useful","Overall, would this be useful to you on shift?")}
      ${sc("trust","Would you trust its cause attribution?")}
      ${sc("clear","Were the recommendations clear enough to act on?")}
      <div class="q"><p>How long have you worked in ground operations?</p>
        <div class="opts">
          ${["under 1 year","1–3 years","3–10 years","over 10 years"].map(v=>
            `<label class="opt ${FINAL.exp===v?"sel":""}">
             <input type="radio" name="exp" ${FINAL.exp===v?"checked":""}
              onchange="setF('exp','${v}',this)">${v}</label>`).join("")}
        </div></div>
      <div class="q"><p>Anything else? (optional)</p>
        <textarea onchange="setF('notes',this.value)">${esc(FINAL.notes||"")}</textarea></div>
      <div class="nav"><button class="ghost" onclick="back()">Back</button>
        <button onclick="finish()">Finish and export</button></div>
    </div></div>`;
}
function setF(k,v,el){
  FINAL[k]=v;
  if(k==="notes" || !el) return;
  document.querySelectorAll(`input[name="${k}"]`).forEach(i=>
    i.closest(".opt").classList.toggle("sel", i===el));
}

function finish(){ step = CASES.length+1; render(); download(); }

function csv(){
  const rows=[["case","code","label","minutes","kind","recoverable",
               "would_action","recoverability_view","comment"]];
  CASES.forEach(c=>{ const r=R[c.n]||{};
    rows.push([c.n,c.code,c.label,c.minutes,c.kind,c.recoverable,
      r.action||"",r.recov||"",(r.comment||"").replace(/[\n\r"]/g," ")]); });
  rows.push([]); rows.push(["overall_useful",FINAL.useful||""]);
  rows.push(["overall_trust",FINAL.trust||""]);
  rows.push(["overall_clear",FINAL.clear||""]);
  rows.push(["experience",FINAL.exp||""]);
  rows.push(["notes",(FINAL.notes||"").replace(/[\n\r"]/g," ")]);
  return rows.map(r=>r.map(v=>`"${String(v)}"`).join(",")).join("\n");
}
function download(){
  const blob=new Blob([csv()],{type:"text/csv"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);
  a.download=`appraisal_${Date.now()}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
}
function doneView(){
  const n=Object.keys(R).length;
  $().innerHTML=`<div class="card"><div class="card-b done">
    <div class="big">Thank you</div>
    <p style="color:var(--dim)">${n} of ${CASES.length} cases rated. A file has
    been saved to your downloads — please hand that back.</p>
    <button onclick="download()">Save the file again</button>
  </div></div>`;
}
render();
</script></body></html>"""


def main() -> None:
    cases = build_cases()
    html = (HTML.replace("__CASES__", json.dumps(cases))
                .replace("__CONSENT__", json.dumps(CONSENT)))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "Expert_Appraisal_Survey.html").write_text(html)
    (OUT / "appraisal_cases.json").write_text(json.dumps(cases, indent=1))
    print(f"{len(cases)} cases -> Expert_Appraisal_Survey.html")
    kinds: dict[str, int] = {}
    for c in cases:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    print("  kinds:", kinds)


if __name__ == "__main__":
    main()
