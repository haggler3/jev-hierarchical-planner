import numpy as np
import pytest

from jevplanner import strategist as S
from jevplanner.jev_client import Answer
from jevplanner.strategist import Option, Strategist, describe, greedy, rules


def opt(key, eta, need, home=20.0, deadline_left=None, reachable=True, depot=False, length=60.0):
    return Option(key, key.capitalize(), "parcel", length, eta, need, home, deadline_left, reachable, depot)


def pool(**over):
    base = {"cafe": opt("cafe", 10, 18), "bakery": opt("bakery", 14, 25), "depot": opt("depot", 8, 14, 0, depot=True)}
    base.update(over)
    return base


# ---------- describe() ----------
def test_describe_mentions_route_eta_battery_and_return_cost():
    text = describe(opt("cafe", 10, 18, home=25), battery=80, all_done=False)
    assert "60 m" in text and "ETA 10 s" in text and "~18%" in text and "~25%" in text and "~62%" in text


def test_describe_flags_unreachable_jobs():
    assert "UNREACHABLE" in describe(opt("cafe", 0, 0, reachable=False), 80, False)


def test_describe_flags_deadline_and_whether_it_is_at_risk():
    safe = describe(opt("clinic", 10, 18, deadline_left=60), 90, False)
    risky = describe(opt("clinic", 10, 18, deadline_left=12), 90, False)
    assert "HARD DEADLINE in 60 s." in safe and "at risk" not in safe
    assert "at risk" in risky


def test_describe_warns_when_battery_would_be_dangerously_low():
    assert "WARNING" in describe(opt("cafe", 10, 40, home=40), battery=80, all_done=False)
    assert "WARNING" not in describe(opt("cafe", 10, 10, home=10), battery=80, all_done=False)


def test_describe_depot_wording_depends_on_whether_work_remains():
    d = opt("depot", 8, 14, 0, depot=True)
    assert "recharge" in describe(d, 40, all_done=False)
    assert "ALL deliveries are complete" in describe(d, 40, all_done=True)


# ---------- baselines ----------
def test_greedy_takes_the_nearest_job_and_ignores_the_battery():
    d = greedy(pool(), battery=5, all_done=False)         # 5% battery: greedy does not care
    assert d.choice == "cafe" and d.source == "greedy"
    assert d.probs["cafe"] == pytest.approx(max(d.probs.values())) and sum(d.probs.values()) == pytest.approx(1)


def test_greedy_goes_home_only_when_everything_is_done():
    assert greedy({"depot": opt("depot", 8, 14, 0, depot=True)}, 50, all_done=True).choice == "depot"


def test_greedy_skips_unreachable_options():
    d = greedy(pool(cafe=opt("cafe", 1, 1, reachable=False)), 90, False)
    assert d.choice == "bakery"


def test_rules_prefers_the_deadline_job_when_feasible():
    options = pool(clinic=opt("clinic", 30, 52, home=20, deadline_left=70))
    assert rules(options, 100, False).choice == "clinic"


def test_rules_recharges_instead_of_a_battery_infeasible_job():
    options = {"clinic": opt("clinic", 30, 52, home=20, deadline_left=70), "depot": opt("depot", 8, 14, 0, depot=True)}
    assert rules(options, battery=60, all_done=False).choice == "depot"       # 60 - 52 - 20 < 10 reserve


def test_rules_prefers_a_feasible_job_over_an_infeasible_urgent_one():
    options = pool(clinic=opt("clinic", 30, 52, home=20, deadline_left=70))
    assert rules(options, battery=60, all_done=False).choice == "cafe"        # clinic infeasible, cafe fine


def test_rules_returns_home_when_all_done_and_handles_empty_reachability():
    assert rules(pool(), 90, all_done=True).choice == "depot"
    assert rules({"cafe": opt("cafe", 0, 0, reachable=False)}, 90, False).choice == "depot"


def test_rules_speed_and_risk_follow_battery_and_deadline():
    urgent = rules(pool(clinic=opt("clinic", 30, 30, home=10, deadline_left=35)), 100, False)
    assert urgent.speed == "urgent"
    low = rules({"cafe": opt("cafe", 5, 5, home=10)}, battery=34, all_done=False)   # 19% margin, battery < 35
    assert low.speed == "eco" and low.risk == "high"
    healthy = rules({"cafe": opt("cafe", 5, 5, home=10)}, battery=100, all_done=False)
    assert healthy.speed == "normal" and healthy.risk == "low"


@pytest.mark.parametrize("battery,risk", [(60, "low"), (45, "moderate"), (30, "high"), (22, "critical")])
def test_rules_risk_thresholds_follow_the_battery_margin(battery, risk):
    # margin = battery - 15; low if margin > 35, moderate if > 20, high if > 10, else critical
    assert rules({"cafe": opt("cafe", 5, 5, home=10)}, battery, False).risk == risk


# ---------- Strategist with a fake Jev client ----------
class FakeClient:
    def __init__(self, answers=None, boom=0):
        self.answers, self.boom, self.calls, self.last_questions = answers, boom, 0, None

    def decide(self, state, questions):
        self.calls += 1
        self.last_questions = questions
        if self.calls <= self.boom:
            raise RuntimeError("network down")
        return self.answers


def answers(choice="cafe", probs=None, speed="eco", risk=2.4):
    return {"next_job": Answer("choice", choice=choice, probabilities=probs or {"cafe": 0.7, "bakery": 0.2, "depot": 0.1},
                               confidence=0.7),
            "speed": Answer("choice", choice=speed), "risk": Answer("score", score=risk)}


def decide(strat, options=None):
    return strat.decide(10.0, np.array([5.0, 5.0, 4.0]), 70.0, 1, 4, options or pool(), None, "none", False)


def test_strategist_maps_typed_answers_into_a_decision():
    s = Strategist(FakeClient(answers()), "jev")
    d = decide(s)
    assert (d.choice, d.speed, d.risk, d.source) == ("cafe", "eco", "high", "jev")
    assert d.probs["cafe"] == pytest.approx(0.7) and d.confidence == pytest.approx(0.7)
    assert s.calls == 1 and len(s.latencies) == 1 and "Battery 70%" in d.state_text


@pytest.mark.parametrize("score,label", [(-3, "low"), (0.4, "low"), (1.2, "moderate"), (2.6, "critical"), (9.0, "critical")])
def test_risk_score_is_rounded_and_clamped_to_a_label(score, label):
    d = decide(Strategist(FakeClient(answers(risk=score)), "jev"))
    assert d.risk == (label if score != 2.6 else "critical")


def test_choice_outside_the_offered_options_is_repaired_to_the_most_probable_one():
    bad = answers(choice="not-an-option", probs={"cafe": 0.2, "bakery": 0.7, "depot": 0.1})
    assert decide(Strategist(FakeClient(bad), "jev")).choice == "bakery"


def test_unreachable_jobs_are_not_offered_to_jev():
    client = FakeClient(answers())
    decide(Strategist(client, "jev"), pool(cafe=opt("cafe", 0, 0, reachable=False)))
    offered = set(client.last_questions["next_job"].options)
    assert "cafe" not in offered and {"bakery", "depot"} <= offered


def test_questions_have_the_expected_typed_shapes():
    client = FakeClient(answers())
    decide(Strategist(client, "jev"))
    q = client.last_questions
    assert q["next_job"].type == "choice" and isinstance(q["next_job"].options, dict)
    assert q["speed"].type == "choice" and q["speed"].options == ["eco", "normal", "urgent"]
    assert q["risk"].type == "score" and q["risk"].options == S.RISK_LEVELS


def test_prompt_puts_battery_safety_above_the_deadline():
    client = FakeClient(answers())
    decide(Strategist(client, "jev"))
    text = client.last_questions["next_job"].instructions
    assert text.index("SAFETY IS A HARD CONSTRAINT") < text.index("hard-deadline")


def test_one_transient_failure_is_retried(monkeypatch):
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    client = FakeClient(answers(), boom=1)
    s = Strategist(client, "jev")
    d = decide(s)
    assert client.calls == 2 and d.source == "jev" and s.fails == 0


def test_persistent_failure_falls_back_to_the_rules_policy(monkeypatch):
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    s = Strategist(FakeClient(answers(), boom=99), "jev")
    d = decide(s)
    assert d.source == "fallback" and s.fails == 1 and s.calls == 0 and d.choice in pool()


def test_non_jev_policies_never_touch_the_client():
    client = FakeClient(answers())
    assert decide(Strategist(client, "rules")).source == "rules"
    assert decide(Strategist(client, "greedy")).source == "greedy"
    assert client.calls == 0


def test_all_options_unreachable_still_offers_the_depot():
    client = FakeClient(answers(probs={"depot": 1.0}, choice="depot"))
    options = {"cafe": opt("cafe", 0, 0, reachable=False), "depot": opt("depot", 0, 0, reachable=False, depot=True)}
    # the depot description is offered even if marked unreachable, so the model is never asked an empty question
    decide(Strategist(client, "jev"), options)
    assert list(client.last_questions["next_job"].options) == ["depot"]
