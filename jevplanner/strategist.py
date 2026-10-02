"""L3 - strategic layer: Jev picks the next job, the speed mode and rates mission risk.

Jev is a typed-decision model: it never writes prose. Each call gives it a free-text world
description plus typed questions and it returns calibrated probabilities. Here the answer
set for `next_job` is built fresh every call from the planner's live route costs, so the
strategist and the planner form a closed loop: Jev chooses goals, the planner prices them.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from .jev_client import JevClient, Question

SPEED_MODES = {"eco": 4.5, "normal": 7.0, "urgent": 9.5}
RISK_LEVELS = ["low", "moderate", "high", "critical"]


@dataclass
class Option:
    key: str
    label: str
    note: str
    length: float            # planned route length (m), nan if unreachable
    eta: float               # seconds, including delivery hover
    need: float              # battery % to fly the leg
    home: float              # battery % needed to get home afterwards
    deadline_left: Optional[float] = None
    reachable: bool = True
    is_depot: bool = False


@dataclass
class Decision:
    choice: str
    probs: Dict[str, float] = field(default_factory=dict)
    speed: str = "normal"
    risk: str = "low"
    source: str = "jev"
    latency: float = 0.0
    state_text: str = ""
    confidence: float = 0.0


def describe(o: Option, battery: float, all_done: bool) -> str:
    if not o.reachable:
        return f"{o.label}: UNREACHABLE right now (the route is blocked by a no-fly zone). Cannot be chosen."
    if o.is_depot:
        if all_done:
            return (f"Return to the depot and land - ALL deliveries are complete. Route {o.length:.0f} m, "
                    f"ETA {o.eta:.0f} s, uses ~{o.need:.0f}% battery.")
        return (f"Fly back to the depot and recharge to 100% (takes ~6 s on the pad). Route {o.length:.0f} m, "
                f"ETA {o.eta:.0f} s, uses ~{o.need:.0f}% battery. Costs time but resets the battery.")
    after = battery - o.need
    s = (f"Deliver {o.note} to the {o.label}. Planned route {o.length:.0f} m, ETA {o.eta:.0f} s, uses ~{o.need:.0f}% "
         f"battery, leaving ~{after:.0f}%; a further ~{o.home:.0f}% is then needed to fly home.")
    if o.deadline_left is not None:
        s += f" HARD DEADLINE in {o.deadline_left:.0f} s" + (" - at risk!" if o.deadline_left < o.eta + 8 else ".")
    if after - o.home < 8:
        s += " WARNING: battery would be dangerously low afterwards."
    return s


def greedy(options: Dict[str, Option], battery: float, all_done: bool) -> Decision:
    """Naive baseline: nearest-first, deadline-aware, but with no battery look-ahead."""
    score = {}
    for k, o in options.items():
        if not o.reachable:
            continue
        s = -o.eta
        if o.deadline_left is not None:
            s += 40
        if o.is_depot:
            s = -1e3 if not all_done else 60
        score[k] = s
    if not score:
        return Decision(choice="depot", source="heuristic")
    m = max(score.values())
    e = {k: math.exp((v - m) / 8.0) for k, v in score.items()}
    z = sum(e.values())
    probs = {k: v / z for k, v in e.items()}
    best = max(probs, key=probs.get)
    return Decision(choice=best, probs=probs, speed="normal", risk="low", source="greedy", confidence=probs[best])


def rules(options: Dict[str, Option], battery: float, all_done: bool) -> Decision:
    """Competent hand-written dispatcher: deadline first, battery look-ahead, then cheapest ETA."""
    reach = {k: o for k, o in options.items() if o.reachable}
    if not reach:
        return Decision(choice="depot", source="rules")
    if all_done:
        return Decision(choice="depot", probs={"depot": 1.0}, source="rules", confidence=1.0)
    feasible = {k: o for k, o in reach.items() if not o.is_depot and battery - o.need - o.home >= 10}
    urgent = [k for k, o in feasible.items() if o.deadline_left is not None]
    if urgent:
        pick = urgent[0]
    elif feasible:
        pick = min(feasible, key=lambda k: feasible[k].eta)
    else:
        pick = "depot" if "depot" in reach else next(iter(reach))
    probs = {k: (1.0 if k == pick else 0.0) for k in reach}
    margin = min([battery - o.need - o.home for o in feasible.values()] or [0.0])
    risk = "low" if margin > 35 else ("moderate" if margin > 20 else ("high" if margin > 10 else "critical"))
    dl = [o for o in reach.values() if o.deadline_left is not None]
    speed = "urgent" if dl and dl[0].deadline_left < dl[0].eta + 10 else ("eco" if battery < 35 else "normal")
    return Decision(choice=pick, probs=probs, speed=speed, risk=risk, source="rules", confidence=1.0)


heuristic = greedy


class Strategist:
    def __init__(self, client: Optional[JevClient] = None, policy: str = "jev"):
        self.client = client
        self.policy = policy          # "jev" | "rules" | "greedy"
        self.calls = 0
        self.fails = 0
        self.latencies = []

    def decide(self, t: float, pos, battery: float, jobs_done: int, jobs_total: int, options: Dict[str, Option],
               current: Optional[str], hazards: str, all_done: bool) -> Decision:
        descs = {k: describe(o, battery, all_done) for k, o in options.items() if o.reachable}
        if not descs:
            descs = {"depot": describe(options["depot"], battery, all_done)}
        state = (f"Delivery drone over a dense city, t={t:.0f}s. Battery {battery:.0f}%. "
                 f"Position ({pos[0]:.0f},{pos[1]:.0f}), altitude {pos[2]:.0f} m. "
                 f"Deliveries complete: {jobs_done} of {jobs_total}. "
                 f"Current job: {current or 'none'}. Hazards: {hazards}")
        if self.client is None or self.policy != "jev":
            d = (rules if self.policy == "rules" else greedy)(options, battery, all_done)
            d.state_text = state
            return d
        qs = {
            "next_job": Question(
                "choice",
                "You are the strategic dispatcher of a delivery drone. Choose the NEXT job. Rules in priority order: "
                "(1) SAFETY IS A HARD CONSTRAINT: never choose a job if, after doing it, the battery left minus the "
                "battery needed to fly home would be under about 10% - recharge at the depot FIRST instead, even for an "
                "urgent delivery (a drone that runs out of battery delivers nothing); "
                "(2) otherwise a hard-deadline medical delivery must be done before its deadline; "
                "(3) otherwise take the delivery with the smallest ETA; "
                "(4) when all deliveries are complete, return to the depot. Never choose a job that is unreachable.", descs),
            "speed": Question(
                "choice",
                "Pick a flight speed mode. 'eco' saves battery (use when battery is tight and no deadline is at risk), "
                "'normal' is the default, 'urgent' burns more battery (use only when a deadline is at risk).",
                ["eco", "normal", "urgent"]),
            "risk": Question(
                "score",
                "Rate the overall mission risk right now, considering battery margin, deadlines and hazards.",
                RISK_LEVELS),
        }
        t0 = time.time()
        try:
            try:
                ans = self.client.decide(state, qs)
            except Exception:
                time.sleep(1.0)
                ans = self.client.decide(state, qs)
            self.calls += 1
            self.latencies.append(time.time() - t0)
            nj = ans["next_job"]
            probs = {k: float(v) for k, v in nj.probabilities.items()} or {nj.choice: 1.0}
            choice = nj.choice if nj.choice in descs else max(probs, key=probs.get)
            risk = RISK_LEVELS[int(max(0, min(3, round(ans["risk"].score))))]
            return Decision(choice=choice, probs=probs, speed=ans["speed"].choice or "normal", risk=risk,
                            source="jev", latency=time.time() - t0, state_text=state, confidence=nj.confidence)
        except Exception as e:  # network/API trouble must never crash the vehicle
            self.fails += 1
            print(f"   [Jev unavailable: {e}] falling back to rules")
            d = rules(options, battery, all_done)
            d.source = "fallback"
            d.state_text = state
            return d
