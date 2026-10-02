"""The city: tall towers, street canyons, a flight ceiling, jobs and no-fly zones."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

CEILING = 20.0                   # regulatory flight ceiling (m); towers above ~18 m cannot be overflown
BOUNDS = (-6.0, 84.0)            # world extent in x and y (m)
CENTERS = [13.0, 39.0, 65.0]     # block centres on a 26 m pitch -> 10 m wide streets
HALF = 8.0                       # block half-size
HEIGHTS = [[14, 28, 24],         # HEIGHTS[ix][iy] in metres; 12-16 m blocks can be overflown
           [30, 12, 26],
           [22, 16, 30]]


@dataclass
class Building:
    cx: float
    cy: float
    hx: float
    hy: float
    h: float


@dataclass
class Job:
    key: str
    label: str
    x: float
    y: float
    kind: str                    # "deliver" | "depot"
    note: str
    deadline: Optional[float] = None
    done: bool = False


@dataclass
class Zone:
    key: str
    label: str
    cx: float
    cy: float
    r: float
    t_on: float
    active: bool = False


def make_buildings() -> List[Building]:
    return [Building(cx, cy, HALF, HALF, float(HEIGHTS[i][j]))
            for i, cx in enumerate(CENTERS) for j, cy in enumerate(CENTERS)]


def make_jobs() -> List[Job]:
    return [
        Job("clinic", "Clinic", 52, 52, "deliver", "URGENT medical supplies", deadline=60.0),
        Job("cafe", "Cafe", 0, 52, "deliver", "hot food order"),
        Job("apartment", "Apartment", 78, 26, "deliver", "parcel for a resident"),
        Job("bakery", "Bakery", 26, 78, "deliver", "fresh bread order"),
        Job("depot", "Depot", 0, 0, "depot", "home base with charging pad"),
    ]


def make_zones() -> List[Zone]:
    return [
        Zone("storm", "Thunderstorm cell", 39, 39, 15, t_on=14.0),
        Zone("heli", "Police helicopter no-fly zone", 65, 20, 10, t_on=36.0),
    ]
