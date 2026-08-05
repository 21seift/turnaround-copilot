# An Agentic LLM Copilot for Aircraft Turnaround Delay Recovery

MSc Artificial Intelligence capstone project.

Decision-support agent for aircraft turnaround coordination. It ingests a live
milestone event stream, predicts door-closure breaches, attributes them to a
cause, triages recoverability, and recommends proactive action. It recommends;
the coordinator decides. It never acts autonomously.

## The contribution: signal versus proof

A delay carries two distinct clocks, and conflating them is why timing-only
monitoring is structurally late:

- **Signal time** — the moment the *cause* becomes knowable. The captain is not
  at the aircraft; fuelling has not started; a passenger has refused to board.
  Nothing is lost yet, but the cause is legible to anyone who knows what it
  implies.
- **Proof time** — the moment enough delay has physically accumulated that a
  projector reasoning from timing alone can show the target will be missed.

Signal precedes proof for any delay whose cause is observable before its
consequence. The agent's advantage is exactly that interval.

> Knowing *what* is going wrong lets the agent see the consequence before the
> clock can prove it.

## Results

Evaluated over 40 simulated days x 8 turns, delays sampled from the observed
occurrence distribution. Lead time is minutes before the door-closure target at
which each approach first calls the breach.

| approach | mean lead (min) | notes |
|---|---|---|
| Threshold dashboard (baseline 1) | 0.0 | reactive; flags only after the target is passed |
| Critical-path projector (baseline 2) | 19.8 ± 12.3 | predicts breach, but no cause, triage or action |
| **Agent** | **23.8 ± 10.2** | earlier on 85/86 breaches; attribution and triage 86/86 |

Per-code advantage, which matters more than the headline:

| code | discovery point | n | advantage |
|---|---|---|---|
| 64 flight crew late | before boarding | 3 | **+18.0** |
| 71 passenger refused boarding | at boarding | 17 | +8.0 |
| 04 inbound PRM pickup | at last passenger off | 5 | +4.0 |
| 87 / 34 stand and ground equipment | at arrival | 33 | +2.0 |
| **93 late inbound** | **at in-block** | **1** | **+0.0** |

Code 93 ties at zero, correctly and deliberately. A late inbound is knowable and
provable at the same instant, so there is no interval to exploit. A method that
won everywhere would be evidence of tuning, not of contribution.

On the subset of breaches whose causes admit intervention (35 of 86), the
recovery model estimates 2.7 minutes recovered per case against 14.2 minutes
of delay — a 19.1% reduction, robust across the plausible range of the
recovery-rate assumption. On the remaining 51 the agent recovers nothing by
definition, but produces directed action in every case where the baselines
produce none.

## Operating hierarchy

Elicited from a practising turnaround coordinator and enforced in code as a
strict ordering, not a preference:

1. **Safety** — a hard constraint, never traded against minutes.
2. **Proactive assertion** — every situation yields an action. "Unrecoverable"
   classifies the *delay*, never the coordinator. The system never stands down.
3. **Minute recovery** — optimised only once (1) and (2) are satisfied.

`reasoner.enforce_hierarchy()` applies this to the output of *every* reasoning
backend: it asserts safety holds rather than requesting them from the model,
keeps manage-around steps visible beneath an active hold, rejects empty
recommendations, and strips stand-down language. Safety is therefore a property
of the **system**, not of the model — which is what licenses using a language
model in an advisory safety-critical role at all.

## Layout

```
turnaround_sim/
  agent.py              perceive / predict / plan / act / reflect
  reasoner.py           swappable reasoning layer + hierarchy enforcement
  baseline_rules.py     baseline 1: threshold dashboard
  baseline_cpm.py       baseline 2: critical-path projector (also an agent tool)
  rebasing.py           in-block anchoring and delay decomposition
  schedule.py           turn types, prep windows, door-closure offsets
  calibration.py        per-code duration and mechanic calibration
  scenarios.py          seeded scenario generation
  evaluate.py           attribution / triage / action scoring
  evaluate_emerging.py  signal-vs-proof lead-time evaluation
  evaluate_outcomes.py  recovered delay, split by recoverability
  compare_reasoners.py  rule reasoner vs language reasoner
  attribution.py        timestamp intake -> cause, breakdown, projection
                        (a reported issue is the only input the agent gets
                         that the critical-path projector does not)
  export_appraisal.py   generates the expert appraisal instrument
  tally_appraisal.py    aggregates returned appraisal responses
  serve.py              local server backing the interface
  ui/index.html         timestamp intake and assessment interface
  demo.py               command-line demonstration entry point
tests/
  test_rebasing.py      countdown regression against real records
  test_hierarchy.py     constraint-layer invariants (11 tests)
```

## Running

```bash
pip install -r requirements.txt

python -m turnaround_sim.serve                 # interface at localhost:8000
python -m turnaround_sim.demo                  # one turn, agent working
python -m turnaround_sim.demo --safety         # hierarchy under a live hazard
python -m turnaround_sim.demo --compare        # all three approaches, same turn

python -m tests.test_hierarchy                 # constraint-layer invariants
python -m turnaround_sim.evaluate_emerging     # headline result
python -m turnaround_sim.evaluate              # attribution / triage / action
python -m turnaround_sim.compare_reasoners     # offline mock backend
```

With a language backend:

```bash
export ANTHROPIC_API_KEY=...
python -m turnaround_sim.compare_reasoners --llm
```

## Data statement

The model was calibrated against real dispatch records from an operational
ground-handling environment. **Those records are commercially confidential and
are not distributed with this repository.** Committed in their place are two
de-identified derivatives carrying the empirical distribution but no operator,
airport, date, flight, stand, sheet identifier or verbatim delay-code label:

- `data/code_reveal.json` — discovery-point classification per delay code
- `data/delay_pool.json` — observed occurrence durations per code

All published results reproduce identically from these derivatives; the
evaluation was verified to give the same figures with the confidential source
files absent.

## Appraisal instrument

The instrument used for the expert appraisal is hosted at
https://tranquil-cheesecake-d01e34.netlify.app/ and generated by
`turnaround_sim/export_appraisal.py`.

## Status

Research prototype supporting an MSc dissertation. Not operational software and
not certified for use in live ground handling. Full dissertation available from
the author.
