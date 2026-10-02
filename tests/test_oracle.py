import math

import pytest

from jevplanner.oracle import Oracle
from jevplanner.strategist import Option


def opt(key, eta, need, home=0.0, deadline_left=None, reachable=True, depot=False):
    return Option(key, key, "", 50.0, eta, need, home, deadline_left, reachable, depot)


@pytest.fixture()
def oracle(planner, jobs):
    return Oracle(planner, jobs)


def test_no_pending_jobs_agrees_only_with_returning_home(oracle):
    assert oracle.evaluate({}, 80, [], "depot", {})["agree"] is True
    assert oracle.evaluate({}, 80, [], "clinic", {})["agree"] is False


def test_deadline_job_must_go_first(oracle):
    opts = {"clinic": opt("clinic", 10, 17), "cafe": opt("cafe", 5, 9), "depot": opt("depot", 8, 14, depot=True)}
    best = oracle.evaluate(opts, 100, ["cafe", "clinic"], "clinic", {"clinic": 12})
    assert best["best_first"] == "clinic" and best["agree"] and best["regret"] == pytest.approx(0, abs=0.75)
    wrong = oracle.evaluate(opts, 100, ["cafe", "clinic"], "cafe", {"clinic": 12})
    assert wrong["best_first"] == "clinic" and not wrong["agree"] and wrong["regret"] > 10


def test_low_battery_forces_a_recharge_first(oracle):
    opts = {"apartment": opt("apartment", 20, 35), "depot": opt("depot", 10, 17.5, depot=True)}
    r = oracle.evaluate(opts, 30, ["apartment"], "depot", {})
    assert r["best_first"] == "depot" and r["feasible"] and r["agree"]
    flying = oracle.evaluate(opts, 30, ["apartment"], "apartment", {})
    assert not flying["agree"] and flying["regret"] > 0


def test_unreachable_option_is_never_the_oracles_first_choice(oracle):
    opts = {"cafe": opt("cafe", 5, 9, reachable=False), "bakery": opt("bakery", 8, 14),
            "depot": opt("depot", 8, 14, depot=True)}
    r = oracle.evaluate(opts, 100, ["cafe", "bakery"], "bakery", {})
    assert r["best_first"] != "cafe"


def test_regret_is_never_negative_and_agreement_implies_small_regret(oracle):
    opts = {"cafe": opt("cafe", 5, 9), "bakery": opt("bakery", 9, 16), "depot": opt("depot", 8, 14, depot=True)}
    for chosen in ("cafe", "bakery", "depot"):
        r = oracle.evaluate(opts, 90, ["cafe", "bakery"], chosen, {})
        assert r["regret"] >= 0
        if r["agree"] and chosen == r["best_first"]:
            assert r["regret"] == pytest.approx(0, abs=0.75)


def test_home_need_is_finite_for_a_reachable_job_and_cached_per_zone_state(oracle, planner):
    h = oracle.home_need("clinic")
    assert math.isfinite(h) and h > 0
    n = len(oracle.cache)
    oracle.home_need("clinic")
    assert len(oracle.cache) == n                   # served from the cache
    planner.set_zones([])
    oracle.home_need("clinic")
    assert len(oracle.cache) == n + 1               # new planner version -> recomputed


def test_ten_percent_reserve_decides_between_recharging_and_flying_on(oracle):
    """The oracle recharges first when a job would leave less than the 10% reserve, and flies on when it just clears it."""
    opts = {"apartment": opt("apartment", 3, 5), "depot": opt("depot", 5, 9, depot=True)}
    home = oracle.home_need("apartment")
    just_under = oracle.evaluate(opts, 5 + home + 7, ["apartment"], "apartment", {})     # 7% margin < 10%
    just_over = oracle.evaluate(opts, 5 + home + 14, ["apartment"], "apartment", {})     # 14% margin >= 10%
    assert just_under["best_first"] == "depot" and not just_under["agree"]
    assert just_over["best_first"] == "apartment" and just_over["agree"]
