"""Thin Python client for TypeSafe AI's Jev decision model.

Jev is reachable through OpenRouter's alpha "decisions" endpoint, not the
normal /chat/completions path. Given free-text `state` plus a set of typed
questions (noul / choice / score), it returns a typed answer with a
calibrated probability per question -- no prose. The endpoint is alpha and
may change.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import requests

DECISIONS_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "typesafe/jev-1.13"


@dataclass
class Question:
    type: str  # "noul" | "choice" | "score"
    instructions: str
    options: Optional[object] = None  # choice labels (list) or {label: description} dict; score levels low->high


@dataclass
class Answer:
    type: str
    noul: float = 0.0
    choice: str = ""
    score: float = 0.0
    legend: Dict[str, str] = field(default_factory=dict)
    probabilities: Dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0


def _to_wire_question(q: Question) -> dict:
    wire: dict = {"type": q.type, "instructions": q.instructions}
    if q.type == "choice" and q.options:
        wire["criteria"] = dict(q.options) if isinstance(q.options, dict) else {opt: opt for opt in q.options}
    elif q.type == "score" and q.options:
        wire["criteria"] = q.options
    return wire


class JevClient:
    """Calls Jev's typed-decision endpoint. Costs are tiny (well under
    $0.0001/call) and latency is sub-second, so it's meant to be called once
    per simulation tick rather than rationed like a full chat turn."""

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL, timeout: float = 10.0):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("decisions: no OPENROUTER_API_KEY configured")
        self.model = model
        self.timeout = timeout
        self.total_cost = 0.0
        self.calls = 0

    def decide(self, state: str, questions: Dict[str, Question]) -> Dict[str, Answer]:
        if not questions:
            raise ValueError("decisions: at least one question is required")

        body = {
            "model": self.model,
            "state": state,
            "questions": {name: _to_wire_question(q) for name, q in questions.items()},
        }
        resp = requests.post(
            DECISIONS_ENDPOINT,
            json=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            try:
                msg = resp.json().get("error", {}).get("message") or f"HTTP {resp.status_code}"
            except Exception:
                msg = f"HTTP {resp.status_code}"
            raise RuntimeError(f"decisions: {msg}")

        data = resp.json()
        self.calls += 1
        try:
            self.total_cost += float(data.get("usage", {}).get("cost", 0.0) or 0.0)
        except (TypeError, ValueError):
            pass
        answers: Dict[str, Answer] = {}
        for name, raw in data.get("answers", {}).items():
            answers[name] = Answer(
                type=raw.get("type", ""),
                noul=raw.get("noul", 0.0),
                choice=raw.get("choice", ""),
                score=raw.get("score", 0.0),
                legend=raw.get("legend", {}) or {},
                probabilities=raw.get("probabilities", {}) or {},
                confidence=raw.get("confidence", 0.0),
            )
        return answers
