"""Adapter for the official Laya Python SDK; imports Laya only when instantiated."""
from __future__ import annotations

import math
from typing import Any, Protocol

from .core import Decision, Incident


AGENTS = {"database_agent", "network_agent", "application_agent", "security_agent", "human"}
QUESTIONS = {
    "target": {
        "type": "choice",
        "instructions": "Which specialist should investigate this incident first?",
        "criteria": {
            "database_agent": "database connection or query latency",
            "network_agent": "network transport or network latency",
            "application_agent": "application CPU usage or application error rate",
            "security_agent": "explicit security alert or attack",
            "human": "unclear owner, insufficient evidence or conflicting signals",
        },
    },
    "severity": {
        "type": "score",
        "instructions": "How severe is this incident?",
        "criteria": ["1 informational", "2 low", "3 medium", "4 high", "5 critical"],
    },
    "escalate": {
        "type": "noul",
        "instructions": "Should this incident be sent to a human instead of automated specialist investigation?",
    },
}


class Predictor(Protocol):
    def predict(self, state: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]: ...


def _probability(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a numeric probability")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise ValueError(f"{name} must be finite and in [0, 1]")
    return result


class LayaRouter:
    def __init__(self, predictor: Predictor | None = None, *, checkpoint: str = "english"):
        if predictor is None:
            try:
                import laya
            except ImportError as exc:
                raise RuntimeError("Install the model dependencies with: pip install 'laya>=0.3.7,<0.4'") from exc
            if checkpoint == "english":
                predictor = laya.load("convaiinnovations/laya")
            elif checkpoint == "typed-decisions":
                predictor = laya.load("convaiinnovations/laya", subfolder="typed-decisions")
            else:
                raise ValueError("checkpoint must be english or typed-decisions")
        self.predictor = predictor

    def decide(self, incident: Incident) -> Decision:
        # Explicit allowlist: simulator ground truth cannot leak into the model.
        state = {
            "incident_id": incident.incident_id,
            "cpu_pct": None if "cpu" in incident.missing_fields else incident.cpu,
            "error_rate": None if "error_rate" in incident.missing_fields else incident.error_rate,
            "database_latency_ms": None if "database_latency" in incident.missing_fields else incident.database_latency,
            "network_latency_ms": None if "network_latency" in incident.missing_fields else incident.network_latency,
            "security_alert": None if "security_alert" in incident.missing_fields else incident.security_alert,
        }
        result = self.predictor.predict(state, QUESTIONS)
        answers = result["answers"]
        target = answers["target"]["choice"]
        if target not in AGENTS:
            raise ValueError(f"Laya returned unknown agent: {target!r}")
        confidence = _probability(answers["target"]["confidence"], "routing confidence")
        score = answers["severity"]["score"]
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            raise ValueError("severity score must be finite")
        # The documented score for a five-item rubric is zero-indexed, 0..4.
        if not 0 <= score <= 4:
            raise ValueError("severity score must be 0..4")
        severity = min(5, max(1, math.floor(score + .5) + 1))
        escalate_probability = _probability(answers["escalate"]["noul"], "escalation probability")
        # Threshold is provisional and must be calibrated on a distinct split.
        escalate = target == "human" or escalate_probability >= .5
        return Decision(target, severity, escalate, "Laya typed decisions", confidence)
