"""Randomised-but-reproducible mission scenarios for Monte-Carlo evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .world import make_jobs


@dataclass
class Scenario:
    seed: int
    storm_t: float = 14.0
    storm_xy: tuple = (39.0, 39.0)
    storm_r: float = 15.0
    heli_t: float = 36.0
    heli_xy: tuple = (65.0, 20.0)
    heli_r: float = 10.0
    deadline: float = 60.0
    battery0: float = 100.0
    wind: float = 1.0


def make_scenario(seed: int) -> Scenario:
    """Seed 0 is the canonical demo scenario; seeds >= 1 jitter events, deadline, battery and wind."""
    if seed == 0:
        return Scenario(seed=0)
    rng = np.random.default_rng(1000 + seed)
    jobs = make_jobs()
    for _ in range(100):
        sc = Scenario(
            seed=seed,
            storm_t=float(rng.uniform(8, 24)), storm_xy=(float(39 + rng.uniform(-6, 6)), float(39 + rng.uniform(-6, 6))),
            storm_r=float(rng.uniform(12, 16.5)),
            heli_t=float(rng.uniform(26, 50)), heli_xy=(float(65 + rng.uniform(-4, 4)), float(20 + rng.uniform(-5, 5))),
            heli_r=float(rng.uniform(8, 11)),
            deadline=float(rng.uniform(46, 72)), battery0=float(rng.uniform(72, 100)), wind=float(rng.uniform(0.3, 1.6)))
        clear = all(math.hypot(j.x - cx, j.y - cy) > r + 5.5 for j in jobs
                    for cx, cy, r in ((*sc.storm_xy, sc.storm_r), (*sc.heli_xy, sc.heli_r)))
        if clear:
            return sc
    return Scenario(seed=seed)
