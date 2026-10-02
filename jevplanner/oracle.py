"""Exhaustive-search oracle: what is the best order for the remaining jobs *right now*?

The oracle sees the same planner costs and battery model that Jev is shown in its job
descriptions, then enumerates every ordering of the remaining deliveries (with lazy
recharge insertion and an optional recharge up front) and returns the minimum-time feasible
sequence. Comparing any dispatcher's choice to it gives a per-decision *regret* in seconds
and an agreement label, which is what the calibration analysis is built on.
"""

from __future__ import annotations

import itertools
import math
from typing import Dict, List, Optional

import numpy as np

from .planner import Planner, path_length

V_EST, RATE_EST, CHARGE_S, RESERVE = 6.0, 1.75, 6.0, 10.0
SERVICE = {"deliver": 3.0, "depot": 2.0}


class Oracle:
    def __init__(self, planner: Planner, jobs):
        self.planner, self.jobs = planner, {j.key: j for j in jobs}
        self.cache: Dict[tuple, float] = {}

    def _len(self, a: str, b: str) -> float:
        key = (self.planner.version, a, b)
        if key not in self.cache:
            ja, jb = self.jobs[a], self.jobs[b]
            p = self.planner.plan(np.array([ja.x, ja.y, 4.0]), np.array([jb.x, jb.y, 4.0]))
            self.cache[key] = path_length(p) if p is not None else math.inf
        return self.cache[key]

    def _leg(self, loc: str, dst: str, opts, ):
        """(eta, battery_need) for a leg; leg from the live position uses Jev's own option numbers."""
        if loc == "pos":
            o = opts.get(dst)
            if o is None or not o.reachable:
                return math.inf, math.inf
            return o.eta, o.need
        L = self._len(loc, dst)
        if not math.isfinite(L):
            return math.inf, math.inf
        eta = L / V_EST + (SERVICE["depot"] + 1.0 if dst == "depot" else SERVICE["deliver"])
        return eta, eta * RATE_EST

    def home_need(self, key: str) -> float:
        """Battery % to fly from a job back to the depot along the planner's current route."""
        return self._leg(key, "depot", {})[1]

    def _simulate(self, order: List[str], battery: float, opts, deadlines: Dict[str, float], recharge_first: bool):
        t, b, loc, ok = 0.0, battery, "pos", True
        first = order[0]
        if recharge_first:
            eta, need = self._leg(loc, "depot", opts)
            if not math.isfinite(eta) or b - need < 5:
                return math.inf, False, "depot"
            t, b, loc, first = t + eta + CHARGE_S, 100.0, "depot", "depot"
        for j in order:
            eta, need = self._leg(loc, j, opts)
            _, home = self._leg(j, "depot", opts)
            if not math.isfinite(eta) or not math.isfinite(home):
                return math.inf, False, first
            if b - need - home < RESERVE and loc != "depot":
                e2, n2 = self._leg(loc, "depot", opts)
                if not math.isfinite(e2) or b - n2 < 5:
                    ok = False
                else:
                    if first == order[0] and not recharge_first and j == order[0]:
                        first = "depot"
                    t, b, loc = t + e2 + CHARGE_S, 100.0, "depot"
                eta, need = self._leg(loc, j, opts)
            if b - need - home < 5:
                ok = False
            t, b, loc = t + eta, b - need, j
            if j in deadlines and t > deadlines[j]:
                ok = False
                t += 100.0
        e3, n3 = self._leg(loc, "depot", opts)
        return t + (e3 if math.isfinite(e3) else 1e3), ok, first

    def evaluate(self, opts, battery: float, pending: List[str], chosen: Optional[str], deadlines: Dict[str, float]):
        if not pending:
            return dict(best_first="depot", best_time=0.0, chosen_time=0.0, regret=0.0, agree=chosen == "depot", feasible=True)
        best = (True, math.inf, None)
        chosen_best = (True, math.inf)
        for perm in itertools.permutations(pending):
            for rf in (False, True):
                t, ok, first = self._simulate(list(perm), battery, opts, deadlines, rf)
                key = (not ok, t)
                if key < (best[0], best[1]):
                    best = (not ok, t, first)
                if (chosen == first) and key < chosen_best:
                    chosen_best = key
        best_time = best[1]
        chosen_time = chosen_best[1] if chosen_best[1] < math.inf else best_time + 100.0
        regret = max(0.0, min(chosen_time - best_time, 150.0)) + (60.0 if chosen_best[0] and not best[0] else 0.0)
        return dict(best_first=best[2], best_time=best_time, chosen_time=chosen_time, regret=regret,
                    agree=(chosen == best[2]) or regret < 0.75, feasible=not best[0])
