import pytest

from jevplanner import jev_client as jc
from jevplanner.jev_client import JevClient, Question, _to_wire_question


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code, self._payload = status, payload or {}

    def json(self):
        return self._payload


def ok_payload(cost=0.00004):
    return {"answers": {"next_job": {"type": "choice", "choice": "cafe", "confidence": 0.8,
                                     "probabilities": {"cafe": 0.8, "bakery": 0.2}, "legend": {"cafe": "x"}},
                        "risk": {"type": "score", "score": 1.4},
                        "ready": {"type": "noul", "noul": 0.91}},
            "usage": {"cost": cost}}


def test_choice_list_becomes_identity_criteria():
    w = _to_wire_question(Question("choice", "pick", ["a", "b"]))
    assert w == {"type": "choice", "instructions": "pick", "criteria": {"a": "a", "b": "b"}}


def test_choice_dict_keeps_its_per_option_descriptions():
    w = _to_wire_question(Question("choice", "pick", {"a": "the first", "b": "the second"}))
    assert w["criteria"] == {"a": "the first", "b": "the second"}


def test_score_levels_are_sent_as_an_ordered_array():
    assert _to_wire_question(Question("score", "rate", ["low", "high"]))["criteria"] == ["low", "high"]


def test_noul_has_no_criteria():
    assert "criteria" not in _to_wire_question(Question("noul", "is it?"))


def test_missing_api_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        JevClient()


def test_key_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    assert JevClient().api_key == "test-key-not-real"


def test_empty_question_set_is_rejected():
    with pytest.raises(ValueError):
        JevClient(api_key="k").decide("state", {})


def test_decide_sends_the_expected_request_and_parses_every_answer_type(monkeypatch):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, json=json, headers=headers, timeout=timeout)
        return FakeResponse(200, ok_payload())

    monkeypatch.setattr(jc.requests, "post", fake_post)
    client = JevClient(api_key="k", model="typesafe/test")
    out = client.decide("the state", {"next_job": Question("choice", "pick", ["cafe", "bakery"]),
                                      "risk": Question("score", "rate", ["low", "high"]),
                                      "ready": Question("noul", "ready?")})
    assert seen["url"] == jc.DECISIONS_ENDPOINT and seen["headers"]["Authorization"] == "Bearer k"
    assert seen["json"]["model"] == "typesafe/test" and seen["json"]["state"] == "the state"
    assert set(seen["json"]["questions"]) == {"next_job", "risk", "ready"}
    assert out["next_job"].choice == "cafe" and out["next_job"].probabilities["bakery"] == 0.2
    assert out["next_job"].confidence == 0.8 and out["risk"].score == 1.4 and out["ready"].noul == 0.91


def test_cost_and_call_count_accumulate(monkeypatch):
    monkeypatch.setattr(jc.requests, "post", lambda *a, **k: FakeResponse(200, ok_payload(0.00003)))
    c = JevClient(api_key="k")
    for _ in range(3):
        c.decide("s", {"r": Question("noul", "?")})
    assert c.calls == 3 and c.total_cost == pytest.approx(0.00009)


def test_http_error_message_is_surfaced(monkeypatch):
    monkeypatch.setattr(jc.requests, "post", lambda *a, **k: FakeResponse(429, {"error": {"message": "rate limited"}}))
    with pytest.raises(RuntimeError, match="rate limited"):
        JevClient(api_key="k").decide("s", {"r": Question("noul", "?")})


def test_http_error_without_a_body_falls_back_to_the_status_code(monkeypatch):
    class Broken(FakeResponse):
        def json(self):
            raise ValueError("no json")

    monkeypatch.setattr(jc.requests, "post", lambda *a, **k: Broken(502))
    with pytest.raises(RuntimeError, match="HTTP 502"):
        JevClient(api_key="k").decide("s", {"r": Question("noul", "?")})
