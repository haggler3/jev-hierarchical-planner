import numpy as np
import pytest

from conftest import pt
from jevplanner.planner import PathFollower, path_length
from jevplanner.world import BOUNDS, Zone


def dense_samples(path, step=0.5):
    pts = []
    for a, b in zip(path[:-1], path[1:]):
        n = max(2, int(np.linalg.norm(b - a) / step))
        pts.extend(a + t * (b - a) for t in np.linspace(0, 1, n))
    return np.array(pts)


def test_building_interior_is_blocked_and_street_centre_is_free(planner):
    assert not planner._free(planner._cell(pt(13, 13, 6)))      # inside a 14 m tower
    assert planner._free(planner._cell(pt(26, 26, 4)))          # street intersection


def test_buildings_are_inflated_by_the_safety_margin(planner):
    # block edge is x=21; 1 m outside is still blocked at low altitude, the street centre is not
    assert not planner._free(planner._cell(pt(22, 13, 4)))
    assert planner._free(planner._cell(pt(26, 13, 4)))


def test_low_blocks_can_be_overflown_but_tall_ones_cannot(planner):
    assert planner._free(planner._cell(pt(39, 39, 16)))         # 12 m block, above 12+2
    assert not planner._free(planner._cell(pt(13, 39, 20)))     # 28 m tower, ceiling is 20


def test_ground_level_is_never_free(planner):
    assert not planner._free((16, 16, 0))


def test_plan_reaches_the_goal_through_free_space(planner):
    p = planner.plan(pt(0, 0, 0.1), pt(52, 52, 4))
    assert p is not None and len(p) >= 2
    assert np.allclose(p[-1][:2], [52, 52]) and p[-1][2] == pytest.approx(4.0)
    assert all(planner.segment_free(a, b) for a, b in zip(p[:-1], p[1:]))
    assert 85 <= path_length(p) <= 105          # ~93 m through the street grid


def test_path_is_never_shorter_than_the_straight_line(planner):
    start, goal = pt(0, 0, 0.1), pt(78, 26, 4)
    p = planner.plan(start, goal)
    assert path_length(p) >= np.linalg.norm(goal - start) - 1e-6


def test_path_stays_inside_the_world(planner):
    p = planner.plan(pt(0, 0, 0.1), pt(26, 78, 4))
    lo, hi = BOUNDS
    assert (p[:, :2] >= lo).all() and (p[:, :2] <= hi).all() and (p[:, 2] <= 20.0 + 1e-6).all()


def test_tall_tower_is_routed_around_not_through(planner):
    p = planner.plan(pt(0, 39, 4), pt(26, 39, 4))
    assert p is not None
    assert all(planner.segment_free(a, b) for a, b in zip(p[:-1], p[1:]))
    assert path_length(p) > 26 + 4              # a straight line would be 26 m


def test_active_zone_forces_a_detour_that_stays_outside_it(planner):
    base = planner.plan(pt(0, 0, 0.1), pt(52, 52, 4))
    planner.set_zones([Zone("storm", "s", 39, 39, 15, 0.0, active=True)])
    detour = planner.plan(pt(0, 0, 0.1), pt(52, 52, 4))
    assert detour is not None and path_length(detour) > path_length(base) + 20
    d = np.linalg.norm(dense_samples(detour)[:, :2] - np.array([39, 39]), axis=1)
    assert d.min() >= 15.0


def test_inactive_zone_changes_nothing(planner):
    a = planner.plan(pt(0, 0, 0.1), pt(52, 52, 4))
    planner.set_zones([Zone("storm", "s", 39, 39, 15, 0.0, active=False)])
    b = planner.plan(pt(0, 0, 0.1), pt(52, 52, 4))
    assert path_length(a) == pytest.approx(path_length(b))


def test_goal_buried_in_a_zone_is_unreachable(planner):
    planner.set_zones([Zone("big", "b", 52, 52, 14, 0.0, active=True)])
    assert planner.plan(pt(0, 0, 0.1), pt(52, 52, 4)) is None


def test_new_zone_makes_an_existing_path_blocked(planner):
    p = planner.plan(pt(0, 0, 0.1), pt(52, 52, 4))
    assert not planner.path_blocked(p)
    planner.set_zones([Zone("on-route", "o", p[1][0], p[1][1], 6, 0.0, active=True)])
    assert planner.path_blocked(p)


def test_set_zones_bumps_version_for_cache_invalidation(planner):
    v = planner.version
    planner.set_zones([])
    assert planner.version == v + 1


def test_path_length_edge_cases():
    assert path_length(None) == 0.0
    assert path_length(np.array([[0, 0, 0.0]])) == 0.0
    assert path_length(np.array([[0, 0, 0.0], [3, 4, 0]])) == pytest.approx(5.0)


class TestPathFollower:
    def test_carrot_leads_the_projection_by_the_lookahead(self):
        f = PathFollower(np.array([[0, 0, 0.0], [10, 0, 0]]))
        carrot, remaining = f.carrot(pt(2, 1, 0), 3.0)
        assert np.allclose(carrot, [5, 0, 0]) and remaining == pytest.approx(8.0)

    def test_carrot_is_clamped_at_the_goal(self):
        f = PathFollower(np.array([[0, 0, 0.0], [10, 0, 0]]))
        carrot, remaining = f.carrot(pt(9.9, 0, 0), 5.0)
        assert np.allclose(carrot, [10, 0, 0]) and remaining == pytest.approx(0.1, abs=1e-6)

    def test_follows_around_a_corner_and_advances_the_segment_index(self):
        f = PathFollower(np.array([[0, 0, 0.0], [4, 0, 0], [4, 4, 0]]))
        carrot, remaining = f.carrot(pt(4, 1, 0), 2.0)
        assert f.idx == 1 and np.allclose(carrot, [4, 3, 0]) and remaining == pytest.approx(3.0)

    def test_progress_never_goes_backwards(self):
        f = PathFollower(np.array([[0, 0, 0.0], [10, 0, 0]]))
        s1 = f.progress(pt(6, 0, 0))
        s2 = f.progress(pt(3, 0, 0))
        assert s2 >= 3.0 - 1e-9 and s1 == pytest.approx(6.0)

    def test_total_matches_path_length(self):
        path = np.array([[0, 0, 0.0], [3, 4, 0], [3, 4, 12]])
        assert PathFollower(path).total == pytest.approx(path_length(path))


def test_vertical_moves_are_penalised_so_a_low_block_is_circled_not_climbed(planner):
    # Climbing 10 m over the 12 m block and back down costs more (1.6x vertical weight) than a ~19 m sidestep.
    p = planner.plan(pt(26, 39, 4), pt(52, 39, 4))
    assert p[:, 2].max() < 10.0 and path_length(p) < 60
