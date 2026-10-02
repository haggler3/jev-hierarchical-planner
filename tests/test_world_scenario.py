import math

import pytest

from jevplanner.scenario import Scenario, make_scenario
from jevplanner.world import CEILING, HALF, make_buildings, make_jobs, make_zones


def test_city_has_nine_blocks_on_a_regular_grid(buildings):
    assert len(buildings) == 9
    assert {b.cx for b in buildings} == {13.0, 39.0, 65.0}
    assert {b.cy for b in buildings} == {13.0, 39.0, 65.0}
    assert all(b.hx == HALF and b.hy == HALF for b in buildings)


def test_streets_are_ten_metres_wide(buildings):
    xs = sorted({b.cx for b in buildings})
    gaps = [(b - a) - 2 * HALF for a, b in zip(xs, xs[1:])]
    assert gaps == [10.0, 10.0]


def test_some_towers_can_be_overflown_and_some_cannot(buildings):
    overflyable = [b for b in buildings if b.h + 2 <= CEILING]
    tall = [b for b in buildings if b.h + 2 > CEILING]
    assert len(overflyable) == 3 and len(tall) == 6


def test_jobs_include_urgent_clinic_and_depot_at_origin(jobs):
    by = {j.key: j for j in jobs}
    assert set(by) == {"clinic", "cafe", "apartment", "bakery", "depot"}
    assert by["clinic"].deadline == 60.0 and by["cafe"].deadline is None
    assert by["depot"].kind == "depot" and (by["depot"].x, by["depot"].y) == (0, 0)
    assert all(not j.done for j in jobs)


def test_zones_start_inactive_and_in_time_order(zones):
    assert [z.key for z in zones] == ["storm", "heli"]
    assert not any(z.active for z in zones)
    assert zones[0].t_on < zones[1].t_on


def test_seed_zero_is_the_canonical_demo_scenario():
    assert make_scenario(0) == Scenario(seed=0)


def test_scenarios_are_reproducible_per_seed():
    assert make_scenario(7) == make_scenario(7)
    assert make_scenario(7) != make_scenario(8)


@pytest.mark.parametrize("seed", range(1, 41))
def test_random_scenarios_stay_in_documented_ranges(seed):
    sc = make_scenario(seed)
    assert 8 <= sc.storm_t <= 24 and 26 <= sc.heli_t <= 50
    assert 12 <= sc.storm_r <= 16.5 and 8 <= sc.heli_r <= 11
    assert 46 <= sc.deadline <= 72
    assert 72 <= sc.battery0 <= 100
    assert 0.3 <= sc.wind <= 1.6


@pytest.mark.parametrize("seed", range(1, 41))
def test_no_job_pad_is_buried_inside_a_no_fly_zone(seed):
    sc = make_scenario(seed)
    for j in make_jobs():
        for cx, cy, r in ((*sc.storm_xy, sc.storm_r), (*sc.heli_xy, sc.heli_r)):
            assert math.hypot(j.x - cx, j.y - cy) > r + 5.5
