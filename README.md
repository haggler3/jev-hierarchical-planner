# Jev hierarchical planner

A drone that is flown by **three layers**, with [Jev](https://typesafe.ai) (TypeSafe AI's typed-decision model, reached through
OpenRouter's alpha `/decisions` endpoint) as the *strategic* layer on top of a classical planner and a physics-based flight
controller. Includes a Monte-Carlo evaluation harness with an exhaustive-search oracle, ablations and a calibration analysis.

**demo video: [`docs/demo.mp4`](docs/demo.mp4)** &nbsp;|&nbsp; **analysis: [`docs/analysis.png`](docs/analysis.png)**

![architecture](docs/architecture.png)

## What each layer does

| layer | rate | what it decides | implementation |
|---|---|---|---|
| **L3 Jev** | ~0.4 Hz, ~0.35 s/call | *which job next*, speed mode, mission risk | `jevplanner/strategist.py` |
| **L2 planner** | on demand, ~60 ms | the 3D route (towers, street canyons, ceiling, no-fly zones) | `jevplanner/planner.py` (weighted A\*) |
| **L1 control** | 100 Hz ctrl / 500 Hz physics | rotor thrusts that follow the route | `jevplanner/physics.py` (MuJoCo + geometric SO(3) controller) |
| **L0 safety** | every tick | battery < 8% -> latch "return to depot" | `jevplanner/mission.py` |

Jev never writes prose. Every ~2.5 s it is handed a text description of the world and **three typed questions**:

```
next_job : choice  - options built fresh each call from the planner's live numbers, e.g.
                     "Deliver URGENT medical supplies to the Clinic. Planned route 141 m, ETA 27 s, uses ~47% battery,
                      leaving ~32%; a further ~38% is then needed to fly home. HARD DEADLINE in 31 s."
speed    : choice  - eco | normal | urgent
risk     : score   - low | moderate | high | critical
```

and answers with a probability for every option. The planner prices every candidate goal and feeds route length / ETA / battery
cost back up into Jev's prompt, so the two layers form a closed loop: **Jev picks goals, the planner prices them.**

## Results

Randomised city missions (storm and no-fly timing/size/position, medical deadline, start battery 72-100%, wind). Every
configuration flies the *same* scenario for a given seed. **Seeds 25-48 are held out** - they were not looked at while the
prompt was being fixed (see "What the analytics found").

| configuration | success | clean success* | deadline met | time (s) | oracle agreement | mean regret | cost / mission |
|---|---|---|---|---|---|---|---|
| **Jev hierarchy (L0-L3)** | 23/24 (96%) | 19/24 | 22/24 | 139 | 86% | 8.2 s | $0.0016 |
| Rule-based dispatcher | 24/24 (100%) | 20/24 | 22/24 | 129 | 89% | 1.9 s | - |
| Greedy dispatcher | **0/24** | 0/24 | 24/24 | - | 62% | 36.3 s | - |
| Jev, **no A\* planner** | 24/24 | **0/24** | 24/24 | 106 | - | - | $0.0012 |
| Jev, no L0 safety | 23/24 | 19/24 | 22/24 | 138 | 85% | 8.5 s | $0.0016 |

\*clean = all delivered, landed, never inside a building, < 2 s inside a no-fly zone. Full table with confidence intervals and
paired tests: [`docs/RESULTS.md`](docs/RESULTS.md). The "oracle" enumerates every ordering of the remaining jobs (with recharge
stops) using the same cost model Jev is shown, so agreement/regret measure *judgment given the same information*.

![analysis](docs/analysis.png)

### What the numbers say (and don't)

- **The hierarchy works; the layers earn their keep.** A greedy dispatcher with no battery look-ahead crashes in every scenario.
  Removing the planner makes missions look faster and "successful" - but only because the drone flies *through the buildings*
  for 27.5 s per mission on average (0/24 clean). Paired against Jev-with-planner it is 32 s faster, which is exactly the
  shortcut through the towers.
- **Jev is not better than a competent hand-written dispatcher here.** On these scenarios it ties on success
  (23/24 vs 24/24, not significantly different), agrees with the oracle slightly less often (86% vs 89%) and is on average
  8.5 s slower (95% CI 1.8-15.8 s, 20 of 23 paired seeds). The rules baseline is given the *same* structured numbers as Jev, so
  this is a fair "same information" comparison. What Jev offers is not a better policy on a fixed task - it is that the
  policy is specified in a sentence of language instead of code.
- **Jev's confidence is meaningfully calibrated.** ECE 0.061 / Brier 0.114 against the oracle's choice (reliability diagram in
  the figure): when Jev says 0.9 it agrees with the oracle about 90% of the time. A typed probability you can threshold is the
  useful property of this model class.
- **It never uses the `urgent` speed mode**, even on the two seeds that missed the deadline (seed 30 was missed by both Jev and
  the rules dispatcher; on seed 31 only Jev was late, by 2.2 s). A real gap in how it trades battery against time.
- **L0 is a null result.** The supervisor never triggered in Jev's runs, and the single Jev crash (seed 35) happened with L0 on:
  an 8% trip level is too late when the drone is far from the depot. A distance-aware trip level would be the fix.

### What the analytics found (v1 -> v2)

The first full run (seeds 1-24, archived in [`docs/v1/`](docs/v1/)) gave Jev **21/24 (88%)** vs the rules dispatcher's 23/24. All
three Jev failures had the same shape: low start battery (~79%), Jev flew the urgent medical run to the far corner, and died
before it could get home. Cause: my prompt listed "hard-deadline delivery" as priority 1 and "battery" as priority 2, and Jev
followed it. I made battery safety a hard constraint above the deadline, then re-evaluated on **fresh held-out seeds** rather than
re-running the same ones: 96%. Jev's calibration also improved (ECE 0.128 -> 0.061). Same model, better specification.

## Run it

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt      # Windows; use .venv/bin/ on Linux
echo OPENROUTER_API_KEY=sk-or-... > .env

python run_demo.py                  # live Jev, seed 0 -> out/demo.mp4 + out/summary.png + out/decision_log.json
python run_demo.py --policy rules   # offline hand-written dispatcher
python rollout.py --seeds 1-24 --workers 6     # Monte-Carlo (resumable, one JSON per rollout)
python analyze.py                   # -> docs/analysis.png, docs/RESULTS.md
```

One Jev call (3 typed questions) is about **$0.000035** and ~0.35 s; a mission is ~45 calls = **$0.0016**. Each 120-rollout
campaign (72 Jev missions) cost about $0.10. Rollouts are CPU/API bound - **a GPU is not used**. On a Linux VM:
`bash scripts/vm_rollout.sh 1-96 8` (finished rollouts are skipped, so spot pre-emption is harmless).

## Layout

```
jevplanner/  world.py (city, jobs, zones)  planner.py (A*)  physics.py (MuJoCo + controller)
             strategist.py (Jev + baselines)  oracle.py (exhaustive search)  scenario.py  mission.py  hud.py
run_demo.py  rollout.py  analyze.py  scripts/
```

## Caveats

Simulation only. Buildings are visual - physics has no collisions, so building clearance is *measured*, not enforced. The battery
model is a simple thrust-proportional drain. Jev is reached through an alpha endpoint (`typesafe/jev-1.13`) that may change.
The oracle uses Jev's own cost model, so it scores judgment, not the accuracy of the model itself. 24 scenarios give wide
confidence intervals (see Wilson CIs in `docs/RESULTS.md`); differences of a task or two are noise.
