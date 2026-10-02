<div align="center">

# Jev Hierarchical Planner

**A typed-decision model flies a drone: Jev decides *what to do*, an A\* planner decides *where to fly*, and a physics-based controller decides *how to fly it*.**

![python](https://img.shields.io/badge/python-3.9%2B-3776ab?style=flat-square)
![physics](https://img.shields.io/badge/physics-MuJoCo-5b8def?style=flat-square)
![planner](https://img.shields.io/badge/planner-3D%20A*-ffb74d?style=flat-square)
![strategist](https://img.shields.io/badge/strategist-Jev%20(typed%20decisions)-b388ff?style=flat-square)
![eval](https://img.shields.io/badge/eval-120%20rollouts%20%C3%97%202%20campaigns-69f0ae?style=flat-square)
![cost](https://img.shields.io/badge/API%20cost-%240.0016%20%2F%20mission-4dd0e1?style=flat-square)

<img src="docs/demo_preview.gif" width="900" alt="Annotated demo: Jev flying a delivery mission through a city">

*Annotated live run, seed 0 (first 24 s shown). Full 104 s video: [`docs/demo.mp4`](docs/demo.mp4). Every overlay is explained in [What the video shows](#what-the-video-shows).*

</div>

---

## Contents
[Why Jev?](#why-jev-high-level) · [What the video shows](#what-the-video-shows) · [Architecture](#architecture) · [The math](#the-math) · [Results](#results) · [What the analytics found](#what-the-analytics-found-v1--v2) · [Run it](#run-it) · [Caveats](#caveats) · [References](#references)

---

## Why Jev? (high level)

Planners and flight controllers are good at geometry and dynamics. What they handle badly is the **judgment layer**: choosing between competing goals under constraints that are stated in words (a medical deadline, a battery reserve, a hazard). Jev is a hosted "System One" model built for exactly that slot: you give it a block of text state and a set of typed questions, and it returns typed answers (`choice`, `score` or yes/no `noul`) with a probability for every option, and no generated prose [[1]](#references) [[2]](#references).

**What it provided in this project, with the evidence:**

| what Jev provides | evidence in this repo | caveat |
|---|---|---|
| **Machine-checkable outputs.** The answer is always one of the options you supplied, so nothing has to be parsed or validated. | 0 API failures or fallbacks across 5,727 calls in 144 Jev-driven missions. Answers are constrained to the supplied options by design. | My client would silently repair an out-of-set choice (taking the highest-probability option) and I did not log whether that ever fired. Also, a valid answer is not a correct one: 86% oracle agreement, and one held-out mission ended in a crash. |
| **Probabilities you can act on.** Each option carries a probability, which the mission loop uses directly (it only switches jobs when a challenger beats the current job by 0.15). | Confidence is roughly calibrated against an exhaustive-search oracle: ECE 0.061, Brier 0.114. | Overconfident in the 0.95-0.99 bin (about 80% agreement). The oracle is a proxy for ground truth, not ground truth. |
| **Latency and cost that fit inside a control loop.** | Median 320 ms, p95 500 ms (held-out missions), about \$0.000035 per call, \$0.0016 per mission (45 calls). | Cost and speed against LLMs are worked out in [Cost and speed versus a general-purpose LLM](#cost-and-speed-versus-a-general-purpose-llm): the cost side uses published prices, the latency side uses vendor-reported figures. **No LLM was benchmarked here.** |
| **A policy written in language.** The dispatch rules are a paragraph of English, not code. | Fixing the v1 failures meant reordering one sentence in the prompt (see [v1 &rarr; v2](#what-the-analytics-found-v1--v2)). | The flip side: behaviour is sensitive to wording, and that sensitivity caused the v1 failures. |
| **Grounded by tools instead of replacing them.** The planner prices every option and the prices go into Jev's prompt. | Without the A\* planner the drone spent 27.5 s per mission inside buildings (0/24 clean). | Jev does not plan routes and was never asked to. |

Related work and what is different about this project are laid out in [Related work](#related-work-and-what-is-different) below.

**Where it sits next to the alternatives (for this task):**

| approach | what it is good at | what it costs you here |
|---|---|---|
| Hand-written rules | **Best results here** (24/24 missions), free, deterministic | every new constraint is a code change; no uncertainty output |
| Exhaustive search (the oracle) | optimal for a fully specified model | needs the whole problem formalised; factorial in the number of jobs; used here only offline for scoring |
| General LLM agent (free text) | flexible, can explain itself | costlier per decision at published prices, latency not measured here, output must be parsed unless structured outputs are used; **not tested here** |
| **Jev** | typed, probability-scored, fast, specified in language | no rationale text (a gap for audit) [[1]](#references); alpha hosted endpoint; vendor claims unverified independently |

### Related work and what is different

None of the systems below were re-run here; the comparison is about design, not benchmark numbers, and the tasks differ.

| work | what it does | how this project relates |
|---|---|---|
| **SayCan** (Ahn et al. 2022) [[3]](#references) | A language model proposes natural-language skills and learned value functions of pretrained skills constrain the choice to what is feasible. | Same idea of grounding a language-side choice in feasibility. Here the grounding is a classical planner's route cost, written into the prompt as numbers, and the selector returns per-option probabilities directly. |
| **Code as Policies** (Liang et al. 2022) [[12]](#references) | A code-writing language model synthesises executable Python that calls robot control APIs. | No code is generated or executed at run time. The strategic model can only pick among enumerated options, which limits what it can do and what it can break. |
| **TypeFly** (Chen et al. 2023) [[13]](#references) | An LLM writes drone control plans in a small custom language (MiniSpec), designed because generation latency grows with the length of the output plan. | Also a drone, but the model emits a plan program from an English command. Here the model emits a fixed-size typed answer, so its latency does not grow with plan length. The flexibility is correspondingly lower: the options are fixed in advance. |
| **LLM+P** (Liu et al. 2023) [[14]](#references) | The LLM translates a problem into PDDL and a classical planner solves it optimally. | For a fully formalised problem like this one, formalise-and-solve is the stronger approach: the exhaustive-search oracle here is exactly that, and it is optimal by construction. A model like Jev only makes sense in this slot when constraints cannot be fully formalised, which this project does not test. |
| **PlanBench** (Valmeekam et al. 2022) [[4]](#references) | A benchmark showing that LLMs struggle to plan about actions and change. | Motivation for keeping route geometry in A\* rather than asking the strategic model to plan. |
| **KnowNo** (Ren et al. 2023) [[15]](#references) | Conformal prediction over an LLM's option-confidence scores yields a prediction set, and the robot asks for help when the set has more than one option. | The same use case for option probabilities. This project uses them only for switching hysteresis and measures calibration (ECE), but gives no coverage guarantee. A KnowNo-style conformal wrapper around Jev's probabilities is an obvious next step and is **not done here**. |
| **Calibration of language models** (Kadavath et al. 2022 [[5]](#references); Tian et al. 2023 [[16]](#references)) | Large models can be well calibrated on multiple-choice questions posed in the right format; for RLHF models, verbalised confidence is often better calibrated than raw token probabilities. | Here confidence is a first-class typed output of the model rather than something elicited by prompting, and it is scored against an oracle on the actual decision problem. |
| **Three-layer architectures** (Gat 1998) [[11]](#references) | The classical split of an autonomous robot into deliberation, sequencing and reactive control. | The L3 / L2 / L1 split follows this pattern. **The architecture is not new**; what is new is the kind of model in the deliberative slot. |

**What this project adds, and what it does not.**

- **A typed, probability-returning model in the strategic slot**, rather than generated text, code or a plan program, with its decisions scored one by one.
- **A closed loop with the planner.** The classical planner prices every option and those prices are rendered into the model's prompt, so the model's goal choices are informed by up-to-date route length, ETA and battery cost.
- **An evaluation harness aimed at the strategic layer itself.** An exhaustive-search oracle gives every decision a regret and an agreement label; scenarios are randomised and paired across configurations with held-out seeds; and ablations use a "clean success" metric that exposes shortcuts (such as flying through buildings) which plain success hides. I did not survey how the papers above evaluate, so I make no claim that this is unusual.
- **An unflattering result, reported as such:** no better than a hand-written dispatcher on this task, plus a failure traced to prompt wording.
- **No claim of novelty beyond that.** The hierarchy, the grounding idea and the use of calibrated option probabilities all have clear precedents above.

### Cost and speed versus a general-purpose LLM

**This is a calculation, not a benchmark.** I chose not to spend API money on an LLM head-to-head, so the LLM side uses published prices and vendor-reported latency. Reproduce every number with [`scripts/cost_compare.py`](scripts/cost_compare.py).

| | basis |
|---|---|
| **Measured here (Jev)** | 44.8 calls per mission, \$0.000035 per call, \$0.0016 per mission, median 0.32 s and p95 0.50 s, over the 24 held-out missions. About 840 input tokens per call, inferred from the billed cost and the published \$0.042 per million input tokens (output is free) [[1]](#references). |
| **Assumed (LLM)** | The same ~840-token prompt, and either 100 output tokens (a short JSON answer) or 1,000 (modest reasoning). OpenRouter list prices retrieved 2026-10-02 [[17]](#references); providers and tiers vary by roughly 2x. |
| **"Frontier average"** | The mean price of four flagships I picked (Claude Opus 5.5, Claude Sonnet 5.5, GPT-6.1 Sol, Grok 4.7): \$2.50 in / \$11.50 out per million tokens. "Frontier" is my judgment. |
| **Not measured** | LLM latency and LLM decision quality. |

**Cost per decision call and per mission**

| model (OpenRouter list price, in / out per M tokens) | cost per call | cost per mission | vs Jev |
|---|---|---|---|
| **Jev (measured)** | \$0.000035 | \$0.0016 | 1x |
| *short JSON answer (no hidden reasoning): 100 output tokens* | | | |
| Frontier average of 4 flagships (\$2.50 / \$11.50) | \$0.00325 | \$0.1453 | 92x |
| claude-opus-5.5 (\$4 / \$20) | \$0.00535 | \$0.2396 | 152x |
| claude-sonnet-5.5 (\$2 / \$10) | \$0.00268 | \$0.1198 | 76x |
| gpt-6.1-sol (\$2 / \$10) | \$0.00268 | \$0.1198 | 76x |
| grok-4.7 (\$2 / \$6) | \$0.00228 | \$0.1019 | 65x |
| gemini-3.8-flash (\$0.75 / \$3.75) | \$0.00100 | \$0.0449 | 29x |
| gpt-6-luna (\$0.1 / \$0.5) | \$0.00013 | \$0.0060 | 4x |
| deepseek-v4-flash (\$0.028 / \$0.056) | \$0.00003 | \$0.0013 | 1x |
| *modest reasoning + answer: 1000 output tokens* | | | |
| Frontier average of 4 flagships (\$2.50 / \$11.50) | \$0.01360 | \$0.6084 | 386x |
| claude-opus-5.5 (\$4 / \$20) | \$0.02335 | \$1.0451 | 663x |
| claude-sonnet-5.5 (\$2 / \$10) | \$0.01168 | \$0.5225 | 332x |
| gpt-6.1-sol (\$2 / \$10) | \$0.01168 | \$0.5225 | 332x |
| grok-4.7 (\$2 / \$6) | \$0.00768 | \$0.3435 | 218x |
| gemini-3.8-flash (\$0.75 / \$3.75) | \$0.00438 | \$0.1960 | 124x |
| gpt-6-luna (\$0.1 / \$0.5) | \$0.00058 | \$0.0261 | 17x |
| deepseek-v4-flash (\$0.028 / \$0.056) | \$0.00008 | \$0.0036 | 2x |

- Against the frontier average, the same decisions cost roughly **90x** more per call with a short JSON answer, and roughly **390x** more once the model spends 1,000 tokens reasoning.
- **Price alone is not Jev's edge against cheap models.** A small model (Gemini 3.8 Flash) is about 29x Jev's cost, GPT-6 Luna about 4x, and DeepSeek V4 Flash at its cheapest listed tier is about the same as Jev for a short answer. Whether those cheap models decide as well as Jev here is untested.

**Latency**

| decision latency | per call | decision time per mission | distance flown at 7 m/s waiting for ONE decision | speed-up vs Jev |
|---|---|---|---|---|
| **Jev, measured median** | 0.32 s | 14 s | 2.2 m | 1x |
| Jev, measured p95 | 0.50 s | 22 s | 3.5 m | - |
| LLM, vendor-reported low end | 3 s | 134 s | 21 m | 9x |
| LLM, vendor-reported high end | 30 s | 1342 s | 210 m | 94x |

- **Speed-up: about 9x to 94x**, but only because the LLM figures (3 to 30 s) are the vendor's own, as summarised in [[1]](#references). They are not measured here, and the vendor's headline claim of 40x to 200x is not reproduced. A small fast model on a short JSON answer can plausibly respond in well under 3 s, in which case the real speed-up would be smaller than 9x.
- **Why latency matters in this loop.** The mission asks for a decision every 2.5 s. With a 3 s LLM the decisions alone would take about 134 s, longer than the whole 104 s mission, so the loop would have to run asynchronously on stale decisions. Each decision would then be 3 to 30 s old: **21 to 210 m of flight at 7 m/s**, compared with 2.2 m for Jev. The tabulated "decision time per mission" is the sum of waiting, not extra mission time.

**What this comparison leaves out**

- **Quality.** The vendor's own benchmark has Jev a few points behind the top LLMs (67.8 % against 73-74 %, as summarised in [[1]](#references)), and a general LLM can explain its choice, which Jev cannot. This repo measures Jev's decision quality against an oracle but does not measure any LLM's.
- **Typed output is not unique to Jev.** Many of these models advertise structured-output support on OpenRouter, so a valid-option guarantee is available to LLMs too. What differs is that Jev's per-option probabilities are a native output, whereas an LLM's would be token log-probabilities or self-reported confidence [[16]](#references).
- **Prompt caching.** Most of this prompt is a stable question block, so LLM input cost with caching could be well below the figures above. I did not model it.
- **Prices drift.** Treat the multiples as a snapshot.

To turn the calculation into a measurement, the captured decision prompts would be sent to the same models and timed; that is the natural next step and was not done.

**What this project did *not* show.** Jev did not beat the hand-written dispatcher (23/24 vs 24/24, about 8.5 s slower per mission), and it never chose the `urgent` speed mode when a deadline was tight. The case where Jev should have a real edge, constraints that arrive as free-form text a rule author could not have anticipated, is **a hypothesis this repo does not test**: every option here was described by numbers a rules baseline could read directly.

---

## What the video shows

The video is one live run (seed 0): Jev makes 35 decisions, the planner builds 8 routes, and the drone delivers four packages and lands. **Video time equals simulation time.** Overlays burned into the video (made by [`scripts/annotate_video.py`](scripts/annotate_video.py) from the recorded run, no re-simulation):

<div align="center">
<img src="docs/video_annotated_frame.png" width="900" alt="Annotated frame at t=14.5 s: storm cell appears">
</div>

| overlay | what it tells you |
|---|---|
| **Clock + timeline bar** (top-left, bottom) | Current time. Coloured ticks mark events: purple = a Jev decision, red = a no-fly zone appears, green = package delivered. |
| **"How to read the right-hand panel"** (top-left) | Key to the three HUD cards: purple L3 = Jev's probabilities, amber L2 = planner map, green L1 = flight telemetry. |
| **"3D view key"** (bottom-left) | Cyan line = A\* route, yellow dots = trail flown, purple pillar = current goal, red cylinders = no-fly zones, orange/green discs = delivery pads pending/done, blue disc = depot, glowing sphere = the drone. |
| **Caption banner** (bottom) | What is happening right now, tagged by layer (L3 Jev, L2 planner, L1 control, or an EVENT). |
| **HUD line "oracle: X MATCH"** | The exhaustive-search best first job; MATCH means Jev's choice agrees with it. |

**Timeline of this run** (all values are from the run's own log):

| time (s) | layer | what happens |
|---|---|---|
| 0.0 | L3 | Jev picks **Clinic** first (p = 0.94); L2 prices the route at 93 m |
| 3-14 | L2/L1 | Drone follows the A\* route through the street canyons at 7 m/s |
| 14.0 | event | **Storm cell** appears (red cylinder); A\* re-plans. The drone is already ~3 m from the clinic, so little changes |
| 16.5-19.0 | L1 | Hovers over the Clinic pad, drops the package (deadline was 60 s) |
| 19.0 | L3 | Jev picks **Bakery** with **low confidence (p = 0.30)**; 48 m route |
| 30.4 | L3 | Jev picks **Cafe** (p = 0.56) and speed mode **ECO** (4.5 m/s) |
| 36.0 | event | **Helicopter no-fly zone** appears; A\* re-plans a 21 m route to the Cafe |
| 42.3 | L3 | Jev sends the drone home to **recharge** (Depot, p = 0.97) |
| 57.6 | L1 | Lands with **7 % battery**; L0's trip level is 8 %, but the drone was already returning so L0 never fired. A thin margin |
| 57.6-63.6 | L1 | Recharging (motors off); pad restores 100 % |
| 63.6 | L3 | Jev picks **Apartment** (p = 0.73), speed NORMAL; 100 m route |
| 83.3 | L3 | All four delivered: Jev sends the drone home (p = 1.00) |
| 104.0 | L1 | **Mission complete**: 4/4 delivered, 0 s inside a building, 1.1 s inside a no-fly zone (the same 1.1 s shows up for every policy on this seed in my runs, which points at a zone appearing on top of the drone rather than a routing error, but I did not trace it) |

Captions describe only what is observable. Jev returns probabilities, not reasons, so the video never claims *why* it chose something. Oracle agreement for this particular run was 86 %.

---

## Architecture

```mermaid
flowchart TB
    subgraph L3["L3 · JEV · strategic · ~0.4 Hz"]
        J["reads a live text description of every option<br/>returns typed answers + probabilities:<br/><b>next_job</b> (choice) · <b>speed</b> (choice) · <b>risk</b> (score)"]
    end
    subgraph L2["L2 · PLANNER · tactical · on demand"]
        P["3D weighted A* over a voxel city<br/>string-pulling smoothing · lookahead carrot"]
    end
    subgraph L1["L1 · CONTROL · 100 Hz / 500 Hz physics"]
        C["geometric SO(3) controller → 4-rotor mixer<br/>MuJoCo rigid body + motor lag + wind"]
    end
    L0["L0 · SAFETY<br/>battery &lt; 8% → latch return-to-depot"]
    O["ORACLE (analysis only)<br/>exhaustive search · regret · calibration"]
    J -- "goal job + speed mode" --> P
    P -- "route length · ETA · feasibility" --> J
    P -- "path + carrot" --> C
    C -- "pose · speed · battery" --> P
    L0 -. override .-> J
    O -. "scores every decision" .-> J
    style L3 fill:#1b1530,stroke:#b388ff,color:#e8eefc
    style L2 fill:#2a2113,stroke:#ffb74d,color:#e8eefc
    style L1 fill:#10261d,stroke:#69f0ae,color:#e8eefc
    style L0 fill:#2a1313,stroke:#ff5252,color:#e8eefc
    style O fill:#0f2328,stroke:#4dd0e1,color:#e8eefc
```

| layer | rate | decides | code |
|---|---|---|---|
| **L3 Jev** | ~0.4 Hz, ~0.35 s/call | *which job next*, speed mode, mission risk | [`strategist.py`](jevplanner/strategist.py) |
| **L2 planner** | on demand, ~60 ms | the 3D route through towers, canyons, ceiling, no-fly zones | [`planner.py`](jevplanner/planner.py) |
| **L1 control** | 100 Hz ctrl / 500 Hz physics | rotor thrusts that track the route | [`physics.py`](jevplanner/physics.py) |
| **L0 safety** | every tick | forces "return to depot" at low battery | [`mission.py`](jevplanner/mission.py) |

Jev never writes prose. Every ~2.5 s it gets a text description of the world and **three typed questions**, and answers with a probability per option:

```text
next_job : choice  options are rebuilt each call from the planner's live numbers, e.g.
           "Deliver URGENT medical supplies to the Clinic. Planned route 141 m, ETA 27 s, uses ~47% battery,
            leaving ~32%; a further ~38% is then needed to fly home. HARD DEADLINE in 31 s."
speed    : choice  eco | normal | urgent
risk     : score   low | moderate | high | critical
```

The planner prices every candidate goal and feeds route length, ETA and battery cost back into Jev's prompt, so the layers form a closed loop:
**Jev picks goals, the planner prices them.**

---

## The math

<details open>
<summary><b>L2 · Planning: weighted A* on a voxel city</b></summary>

The world is a grid with resolution $`r = 2`$ m. A voxel $`(x,y,z)`$ is **blocked** if it is inside a building footprint inflated by a margin $`m = 2.5`$ m (and 2 m vertically), at ground level, or inside an active no-fly cylinder:

```math
\text{blocked}(v) = \bigvee_{b} \Big[ |x-c^b_x| < h^b_x + m \;\wedge\; |y-c^b_y| < h^b_y + m \;\wedge\; z < H_b + 2 \Big] \;\vee\; \bigvee_{k \in \text{active}} \Big[ (x-c^k_x)^2 + (y-c^k_y)^2 < (R_k + m)^2 \Big]
```

Moving between neighbouring voxels (26-connected) costs distance, with vertical motion weighted 1.6x, plus a penalty for hugging obstacles:

```math
c(u \to v) = r\sqrt{\Delta x^2 + \Delta y^2 + (1.6\,\Delta z)^2} + 0.7\,r\cdot \mathbf{1}[v \in \text{near-obstacle}]
```

The search inflates the heuristic, so it is **weighted A\*** [[8]](#references) with $`w = 1.25`$, which bounds the path cost at $`w`$ times the optimum:

```math
f(v) = g(v) + w\,h(v), \qquad h(v) = r\sqrt{\Delta x^2 + \Delta y^2 + (1.6\,\Delta z)^2}, \qquad \text{cost(path)} \le w \cdot \text{cost}^{*}
```

Waypoints are then **string-pulled** (greedy line-of-sight shortcuts). The follower tracks a carrot point $`\ell = \mathrm{clip}(0.6\,v_{\text{mode}},\,3,\,6)`$ metres ahead of the drone's projection onto the path, with a braking limit that brings it to rest at the goal ($`d`$ is the remaining path length):

```math
v_{\text{lim}} = \min\!\Big(v_{\text{mode}},\; \sqrt{2 \cdot 1.4 \cdot d} + 0.7\Big)
```
</details>

<details open>
<summary><b>L1 · Control: geometric position / attitude controller on SO(3)</b></summary>

The structure follows the geometric quadrotor controller of Lee, Leok and McClamroch [[7]](#references). The position error is clipped so the commanded speed saturates at $`v_{\text{lim}}`$, then a PD law gives a desired acceleration (tilt limited to 38 degrees):

```math
\mathbf{a} = K_p\,\mathrm{clip}\big(\mathbf{e},\; v_{\text{lim}} K_d / K_p\big) - K_d\,\mathbf{v}, \qquad
\mathbf{a}_{\text{des}} = \mathbf{a} + g\,\mathbf{e}_3, \qquad
\|\mathbf{a}_{xy}\| \le g\tan 38^\circ
```

The thrust direction defines the desired attitude $`R_d = [\mathbf{x}_b\;\mathbf{y}_b\;\mathbf{z}_b]`$ with $`\mathbf{z}_b = \mathbf{a}_{\text{des}} / \|\mathbf{a}_{\text{des}}\|`$. Collective thrust and body torque are:

```math
T = m\,\mathbf{a}_{\text{des}} \cdot R\,\mathbf{e}_3, \qquad
\mathbf{e}_R = \tfrac{1}{2}\big(R_d^{\top} R - R^{\top} R_d\big)^{\vee}, \qquad
\boldsymbol{\tau} = J\big(-K_R\,\mathbf{e}_R - K_\omega\,\boldsymbol{\omega}\big) + \boldsymbol{\omega} \times J\boldsymbol{\omega}
```

An X-configuration mixer allocates thrust and torque to the four rotors (arm 0.2 m, yaw coefficient $`k = 0.016`$), and each rotor responds with first-order motor lag ($`\tau_m = 30`$ ms):

```math
\begin{bmatrix} T \\ \tau_x \\ \tau_y \\ \tau_z \end{bmatrix} =
\begin{bmatrix} 1 & 1 & 1 & 1 \\ y_1 & y_2 & y_3 & y_4 \\ -x_1 & -x_2 & -x_3 & -x_4 \\ s_1 k & s_2 k & s_3 k & s_4 k \end{bmatrix}
\begin{bmatrix} f_1 \\ f_2 \\ f_3 \\ f_4 \end{bmatrix}, \qquad
\dot f_i = \frac{f_i^{\text{cmd}} - f_i}{\tau_m}, \quad f_i \in [0,\,8]\ \text{N}
```

Gains: $`K_p = 6,\ K_d = 4,\ K_R = 60,\ K_\omega = 10`$. Physics runs at 500 Hz in MuJoCo [[9]](#references), the controller at 100 Hz.
</details>

<details open>
<summary><b>Battery model and the feasibility rule Jev is asked to respect</b></summary>

Battery drains in proportion to total rotor thrust (about 1.5 %/s hovering, since the rotors sum to roughly $`mg \approx 14.7`$ N):

```math
\dot B = -0.105 \sum_{i=1}^{4} f_i \quad [\%/\text{s}]
```

For decision-making, a leg of planned length $`L`$ metres is priced as $`\text{ETA} = L/6 + 3`$ seconds and $`\text{need} = 1.75 \cdot \text{ETA}`$ percent. A job $`j`$ is **feasible** only if it leaves enough to fly home plus a reserve:

```math
B - \text{need}(j) - \text{home}(j) \ge 10\,\%
```

where $`\text{home}(j)`$ is the planner's own cost of the route from the job back to the depot. L0 overrides everything and latches "return to depot" if $`B < 8\%`$.
</details>

<details>
<summary><b>Oracle, regret and calibration (how decisions are scored)</b></summary>

For the $`n`$ remaining jobs, the oracle enumerates every ordering (with optional recharge stops) and finds the fastest feasible plan:

```math
T^{*} = \min_{\pi \in S_n,\ \text{recharge}} T(\pi) \quad \text{subject to battery and deadline constraints}
```

A dispatcher that picks first job $`c`$ has **regret** $`\rho(c) = T^{*}(\text{first}=c) - T^{*}`$ seconds (capped, with an extra penalty if $`c`$ admits no feasible plan). It "agrees" with the oracle if $`c`$ is optimal or $`\rho < 0.75`$ s.

Jev returns a probability $`p_i`$ for its chosen job. Over $`N`$ decisions with outcomes $`y_i = \mathbf{1}[\text{agree}]`$, binned into $`B`$ confidence bins, calibration is summarised by expected calibration error [[6]](#references) and the Brier score:

```math
\text{ECE} = \sum_{b=1}^{B} \frac{n_b}{N}\,\big|\,\text{acc}_b - \text{conf}_b\,\big|, \qquad
\text{Brier} = \frac{1}{N}\sum_{i=1}^{N} (p_i - y_i)^2
```

Success rates carry 95 % **Wilson** score intervals [[10]](#references), and paired comparisons use an exact two-sided **sign test**:

```math
\tilde p \pm \frac{z\sqrt{\hat p(1-\hat p)/n + z^2/4n^2}}{1 + z^2/n}, \quad \tilde p = \frac{\hat p + z^2/2n}{1 + z^2/n}; \qquad
p_{\text{sign}} = \min\!\Big(1,\; 2\sum_{i=0}^{k}\binom{n}{i}2^{-n}\Big), \ k = \min(\text{wins},\text{losses})
```
</details>

---

## Results

> ### TLDR
>
> - **The hierarchy works.** Across 24 held-out randomised city missions, Jev (as strategic layer) **delivered all 4 packages and landed in 23/24**; a greedy dispatcher with no battery look-ahead completed **0/24**.
> - **Jev is *not* better than a competent hand-written dispatcher here.** The rules baseline (given the *same* numbers Jev sees) went **24/24**, agreed with the oracle slightly more often (**89% vs 86%**, not significance-tested) and was **~8.5 s faster** per mission. The honest claim is "Jev matches a hand-engineered policy while being specified in a sentence of language, not code."
> - **Jev's confidence is usable.** Its stated probabilities roughly track how often it matches the exhaustive-search oracle (**ECE 0.061**), with some overconfidence in the 0.95-0.99 bin (about 80% agreement).
> - **The planner and a battery-aware strategist clearly earn their place; L0 is untested here.** Without the planner the drone "succeeds" 24/24 *but flies through buildings for 27.5 s per mission* (0/24 clean). A strategist with no battery look-ahead (greedy) runs out of power every time. The L0 supervisor never triggered, so these runs say nothing about its value.
> - **Analytics caught a real bug.** v1 scored 21/24 because my prompt ranked the deadline above battery safety. After fixing it, a re-run on **different, held-out seeds** scored 23/24. Different seeds means this is not a controlled before/after (see below).
> - **Cheap.** About **\$0.0016 per mission**, \$0.197 for both full campaigns (5,727 Jev calls). No GPU needed.

Randomised missions: storm and no-fly timing/size/position, medical deadline, start battery 72-100 %, wind. Every configuration flies the **same** scenario for a given seed. Seeds 25-48 are **held out**: they were not looked at while the prompt was being fixed. (Seed 0 is the demo scenario used during development and is not part of any statistic.)

| term | meaning |
|---|---|
| **success** | all 4 deliveries made **and** the drone landed at the depot without running out of battery |
| **clean success** | success **and** never inside a building and under 2 s inside a no-fly zone (zones can appear around the drone) |
| **oracle agreement** | fraction of decisions where the chosen first job is optimal under exhaustive search (or within 0.75 s of it) |
| **regret** | seconds lost versus the oracle's best plan for the chosen first job (capped; extra penalty if it admits no feasible plan) |

| configuration | success | clean success* | deadline met | time (s) | oracle agreement | mean regret | cost / mission |
|---|---|---|---|---|---|---|---|
| **Jev hierarchy (L0-L3)** | 23/24 (96 %) | 19/24 | 22/24 | 139 | 86 % | 8.2 s | \$0.0016 |
| Rule-based dispatcher | 24/24 (100 %) | 20/24 | 22/24 | 129 | 89 % | 1.9 s | - |
| Greedy dispatcher | **0/24** | 0/24 | 24/24 | - | 62 % | 36.3 s | - |
| Jev, **no A\* planner** | 24/24 | **0/24** | 24/24 | 106 | - | - | \$0.0012 |
| Jev, no L0 safety | 23/24 | 19/24 | 22/24 | 138 | 85 % | 8.5 s | \$0.0016 |

<sub>*clean = all delivered, landed, never inside a building, under 2 s inside a no-fly zone. Intervals and paired tests: [`docs/RESULTS.md`](docs/RESULTS.md).</sub>

<div align="center">
<img src="docs/analysis.png" width="980" alt="Monte-Carlo analysis: success, deadlines, time, battery margin, violations, oracle agreement, calibration, regret CDF, latency">
</div>

### Reading the figure
<table>
<tr><td width="50%">

**Success and safety**
- *Success (light) vs clean success (solid)* separates "finished" from "finished without cheating". The no-planner ablation is the big gap.
- *Airspace violations* shows that exact cheat: 27.5 s inside buildings and 7.3 s in no-fly zones.
- *Lowest battery* shows the safety margin each policy leaves; greedy hits 0 %.

</td><td width="50%">

**Judgment quality**
- *Oracle agreement / regret* scores each decision against exhaustive search.
- *Calibration* is the reliability diagram: points on the dashed diagonal mean "confidence = accuracy".
- *Regret CDF*: most decisions cost 0 s; the tail is where Jev loses time.

</td></tr>
</table>

### What the numbers say (and don't)

- **Jev vs rules:** success is a statistical tie (23/24 vs 24/24; sign test p = 1.0). On the 23 seeds both finished, Jev was slower in 20 and faster in 1: mean -8.5 s (95 % CI -15.8 to -1.8 s).
- **It never uses the `urgent` speed mode**, even on the two seeds that missed the deadline (seed 30 was missed by both Jev and the rules dispatcher; on seed 31 only Jev was late, by 2.2 s). A real gap in how it trades battery against time.
- **L0 is a null result.** It never triggered in Jev's runs, and the one Jev crash (seed 35) happened with L0 on: an 8 % trip level is too late when the drone is far from the depot. A distance-aware trip level would be the fix.

---

## What the analytics found (v1 &rarr; v2)

<table>
<tr><th></th><th>v1 (seeds 1-24)</th><th>v2 (seeds 25-48, held out)</th></tr>
<tr><td><b>Prompt priority</b></td><td>1. hard-deadline delivery &nbsp; 2. battery</td><td>1. <b>battery safety (hard constraint)</b> &nbsp; 2. deadline</td></tr>
<tr><td><b>Jev success</b></td><td>21/24 (88 %)</td><td>23/24 (96 %)</td></tr>
<tr><td><b>Rules success</b></td><td>23/24 (96 %)</td><td>24/24 (100 %)</td></tr>
<tr><td><b>Jev calibration (ECE)</b></td><td>0.128</td><td>0.061</td></tr>
</table>

All three v1 Jev failures had the same shape: a low start battery (~79 %), Jev flew the urgent medical run to the far corner, and died before it could get home. The cause was my prompt, not the model: it listed the deadline as priority 1 and battery as priority 2, and Jev followed it. I made battery safety a hard constraint and re-evaluated on **fresh seeds** rather than the same ones, so the fix is not tuned on its own test set. v1 is archived in [`docs/v1/`](docs/v1/).

> **Read this table as direction, not effect size.** v1 and v2 use different scenarios, so the numbers are not a controlled before/after: the rules baseline also moved from 96 % to 100 % purely from the scenario draw, and the ECE change could come from the seeds as much as from the prompt. The stronger evidence is qualitative: all three v1 failures had one identical cause that traces directly to the prompt wording. A controlled test (re-running the fixed prompt on seeds 1-24) was not done.

---

## Run it

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt      # Windows; .venv/bin/ on Linux
echo OPENROUTER_API_KEY=sk-or-... > .env      # .env is git-ignored; never commit it

python run_demo.py                  # live Jev, seed 0 -> out/demo.mp4 + out/summary.png + out/decision_log.json
python run_demo.py --policy rules   # offline hand-written dispatcher
python rollout.py --seeds 1-24 --workers 6     # Monte-Carlo (resumable, one JSON per rollout)
python analyze.py                   # -> docs/analysis.png, docs/RESULTS.md
python scripts/annotate_video.py out/demo.mp4 docs/demo.mp4   # burn in the explanatory overlays
```

One Jev call (3 typed questions) is about **\$0.000035** and ~0.35 s; a mission is ~45 calls = **\$0.0016**. Each 120-rollout campaign (72 Jev missions) cost about \$0.10.
Rollouts are CPU/API bound: **a GPU is not used**. On a Linux VM: `bash scripts/vm_rollout.sh 1-96 8` (finished rollouts are skipped, so spot pre-emption is harmless).

The annotation captions in `scripts/annotate_video.py` are tied to the recorded seed-0 run; if you re-record, update the `CAPTIONS` list.

```text
jevplanner/   world.py (city, jobs, zones)      planner.py (A*)          physics.py (MuJoCo + controller)
              strategist.py (Jev + baselines)   oracle.py (search)       scenario.py   mission.py   hud.py
run_demo.py   rollout.py   analyze.py   scripts/ (annotate_video, make_architecture, vm_rollout)
docs/         demo.mp4  analysis.png  RESULTS.md  architecture.png  v1/
```

## Caveats

Simulation only. Buildings are visual: the physics has no collisions, so building clearance is *measured*, not enforced. The battery model is a simple thrust-proportional drain. Jev is reached through an alpha endpoint (`typesafe/jev-1.13`) that may change, and each call sends the mission's text state to OpenRouter / TypeSafe AI. This is an independent project, not affiliated with or endorsed by TypeSafe AI or OpenRouter. The oracle uses Jev's own cost model, so it scores judgment, not the accuracy of the model itself. 24 scenarios give wide confidence intervals; differences of a task or two are noise. Jev's speed, cost and benchmark figures quoted from other sources are vendor-reported; the figures in this repo are our own measurements.

## References

1. DataCamp, "Jev: TypeSafe's System One Model Explained" (vendor-reported speed/cost figures, limitations, and the note that no independent evaluation exists yet): https://www.datacamp.com/blog/system-one-models-jev
2. Wikipedia, "Jev (AI model)" (output types, RLCD training, release details): https://en.wikipedia.org/wiki/Jev_(AI_model)
3. M. Ahn et al., "Do As I Can, Not As I Say: Grounding Language in Robotic Affordances" (SayCan), 2022. arXiv:[2204.01691](https://arxiv.org/abs/2204.01691)
4. K. Valmeekam, A. Olmo, S. Sreedharan, S. Kambhampati, "Large Language Models Still Can't Plan (A Benchmark for LLMs on Planning and Reasoning about Change)", 2022. arXiv:[2206.10498](https://arxiv.org/abs/2206.10498)
5. S. Kadavath et al., "Language Models (Mostly) Know What They Know", 2022. arXiv:[2207.05221](https://arxiv.org/abs/2207.05221)
6. C. Guo, G. Pleiss, Y. Sun, K. Q. Weinberger, "On Calibration of Modern Neural Networks", ICML 2017. arXiv:[1706.04599](https://arxiv.org/abs/1706.04599)
7. T. Lee, M. Leok, N. H. McClamroch, "Geometric Tracking Control of a Quadrotor UAV on SE(3)", CDC 2010. arXiv:[1003.2005](https://arxiv.org/abs/1003.2005)
8. I. Pohl, "Heuristic search viewed as path finding in a graph", Artificial Intelligence 1(3-4), 1970.
9. E. Todorov, T. Erez, Y. Tassa, "MuJoCo: A physics engine for model-based control", IROS 2012.
10. E. B. Wilson, "Probable inference, the law of succession, and statistical inference", J. American Statistical Association 22(158), 1927.
11. E. Gat, "On Three-Layer Architectures", in *Artificial Intelligence and Mobile Robots*, AAAI Press / MIT Press, 1998.
12. J. Liang et al., "Code as Policies: Language Model Programs for Embodied Control", 2022. arXiv:[2209.07753](https://arxiv.org/abs/2209.07753)
13. G. Chen, X. Yu, N. Ling, L. Zhong, "TypeFly: Flying Drones with Large Language Model", 2023. arXiv:[2312.14950](https://arxiv.org/abs/2312.14950)
14. B. Liu et al., "LLM+P: Empowering Large Language Models with Optimal Planning Proficiency", 2023. arXiv:[2304.11477](https://arxiv.org/abs/2304.11477)
15. A. Z. Ren et al., "Robots That Ask For Help: Uncertainty Alignment for Large Language Model Planners" (KnowNo), CoRL 2023. arXiv:[2307.01928](https://arxiv.org/abs/2307.01928)
16. K. Tian et al., "Just Ask for Calibration: Strategies for Eliciting Calibrated Confidence Scores from Language Models Fine-Tuned with Human Feedback", EMNLP 2023. arXiv:[2305.14975](https://arxiv.org/abs/2305.14975)
17. OpenRouter model list and per-token prices, retrieved 2026-10-02: https://openrouter.ai/api/v1/models
