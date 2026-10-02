"""Integration tests of the L3 -> L2 -> L1 loop. Short simulated horizons keep them to a few seconds."""

import mujoco
import numpy as np
import pytest

from jevplanner import mission as M
from jevplanner.scenario import Scenario, make_scenario
from jevplanner.strategist import Strategist

pytestmark = pytest.mark.slow


def build(tmp_path, monkeypatch, t_max, policy="rules", scenario=None, safety=True, planner_mode="astar", oracle=False):
    monkeypatch.setattr(M, "T_MAX", t_max)
    return M.Mission(Strategist(None, policy), record=False, out=tmp_path, scenario=scenario or make_scenario(0),
                     planner_mode=planner_mode, use_oracle=oracle, safety=safety, verbose=False)


def test_first_decision_goes_to_the_urgent_clinic_and_the_drone_climbs(tmp_path, monkeypatch):
    ms = build(tmp_path, monkeypatch, 6.0)
    ms.run()
    assert ms.current == "clinic" and ms.phase == "transit"
    assert ms.pos[2] > 2.0 and np.linalg.norm(ms.pos[:2]) > 5.0
    assert ms.battery < 100.0 and not ms.crashed and not ms.finished


def test_runs_are_deterministic_for_a_given_seed(tmp_path, monkeypatch):
    a = build(tmp_path, monkeypatch, 5.0, scenario=make_scenario(3)); a.run()
    b = build(tmp_path, monkeypatch, 5.0, scenario=make_scenario(3)); b.run()
    assert np.allclose(a.pos, b.pos) and a.battery == pytest.approx(b.battery) and a.replans == b.replans


def test_start_battery_comes_from_the_scenario(tmp_path, monkeypatch):
    ms = build(tmp_path, monkeypatch, 0.01, scenario=Scenario(seed=1, battery0=81.5))
    assert ms.battery == pytest.approx(81.5)


def test_scenario_overrides_zone_geometry_and_deadline(tmp_path, monkeypatch):
    sc = Scenario(seed=1, storm_t=9.0, storm_xy=(40.0, 41.0), storm_r=12.0, deadline=50.0)
    ms = build(tmp_path, monkeypatch, 0.01, scenario=sc)
    assert (ms.zones[0].cx, ms.zones[0].cy, ms.zones[0].r, ms.zones[0].t_on) == (40.0, 41.0, 12.0, 9.0)
    assert ms.jd["clinic"].deadline == 50.0


def test_zone_activates_on_schedule_and_the_planner_is_told(tmp_path, monkeypatch):
    ms = build(tmp_path, monkeypatch, 3.0, scenario=Scenario(seed=1, storm_t=1.0))
    v0 = ms.planner.version
    ms.run()
    assert ms.zones[0].active and not ms.zones[1].active
    assert ms.planner.version > v0
    assert any("THUNDERSTORM" in e or "appears" in e for e in ms.events)


# greedy ignores the battery, so only the L0 supervisor can send it home: this isolates L0 from the policy.
def test_low_battery_triggers_the_safety_override_and_latches(tmp_path, monkeypatch):
    ms = build(tmp_path, monkeypatch, 1.0, policy="greedy")
    ms.battery = 7.5
    ms.run()
    assert ms.safety_overrides >= 1 and ms.current == "depot" and ms.l0_latch


def test_safety_override_can_be_disabled_for_the_ablation(tmp_path, monkeypatch):
    ms = build(tmp_path, monkeypatch, 1.0, policy="greedy", safety=False)
    ms.battery = 7.5
    ms.run()
    assert ms.safety_overrides == 0 and not ms.l0_latch and ms.current == "clinic"


def test_healthy_battery_never_trips_the_override(tmp_path, monkeypatch):
    ms = build(tmp_path, monkeypatch, 2.0, policy="greedy")
    ms.run()
    assert ms.safety_overrides == 0 and not ms.l0_latch


def test_latched_override_ignores_a_policy_that_wants_to_keep_delivering(tmp_path, monkeypatch):
    ms = build(tmp_path, monkeypatch, 3.0, policy="greedy")
    ms.data.qpos[:3] = [40.0, 0.0, 10.0]          # start far from home so the drone stays in transit
    mujoco.mj_forward(ms.model, ms.data)
    ms.battery = 7.5
    ms.run()                         # greedy keeps proposing a delivery every 2.5 s; the latch keeps the depot
    assert ms.current == "depot" and ms.switches == 0 and len(ms.decisions) >= 2
    assert all(d["applied"] is None for d in ms.decisions)


def test_straight_line_ablation_ignores_zones_and_flies_a_two_point_path(tmp_path, monkeypatch):
    ms = build(tmp_path, monkeypatch, 3.0, planner_mode="straight")
    ms.run()
    assert ms.path is not None and len(ms.path) == 2 and ms.oracle is None


def test_oracle_scores_each_decision_when_enabled(tmp_path, monkeypatch):
    ms = build(tmp_path, monkeypatch, 3.0, oracle=True)
    ms.run()
    first = ms.decisions[0]
    assert first["choice"] == "clinic"                       # rules: deadline job first
    assert first["oracle_first"] in {"clinic", "cafe", "apartment", "bakery", "depot"}
    assert isinstance(first["agree"], bool) and first["regret"] >= 0
    assert first["agree"] == (first["choice"] == first["oracle_first"] or first["regret"] < 0.75)


def test_result_dict_has_the_fields_the_analysis_needs(tmp_path, monkeypatch):
    ms = build(tmp_path, monkeypatch, 3.0, oracle=True)
    ms.run()
    r = ms.result()
    for k in ("seed", "policy", "planner", "outcome", "success", "deliveries", "t_total", "deadline_met", "min_battery",
              "bld_viol_s", "zone_viol_s", "agree", "mean_regret", "cost", "decisions"):
        assert k in r
    assert r["policy"] == "rules" and r["outcome"] == "timeout" and r["success"] is False and r["deliveries"] == 0


def test_clearance_is_negative_inside_a_building_and_positive_in_a_street(tmp_path, monkeypatch):
    ms = build(tmp_path, monkeypatch, 0.01)
    assert ms.clearance(np.array([13.0, 13.0, 5.0])) < 0
    assert ms.clearance(np.array([26.0, 26.0, 5.0])) > 0
