import numpy as np
import pytest

from jevplanner.planner import Planner
from jevplanner.world import make_buildings, make_jobs, make_zones


@pytest.fixture(scope="session")
def buildings():
    return make_buildings()


@pytest.fixture()
def jobs():
    return make_jobs()


@pytest.fixture()
def zones():
    return make_zones()


@pytest.fixture()
def planner(buildings):
    """Fresh planner per test: set_zones() mutates its occupancy."""
    return Planner(buildings)


def pt(x, y, z):
    return np.array([x, y, z], dtype=float)
