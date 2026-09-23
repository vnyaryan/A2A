"""Curated evaluation examples; labels are never included in model input."""
import json
from dataclasses import dataclass
from pathlib import Path
from .core import Incident

TARGETS = {"human", "database_agent", "network_agent", "application_agent", "security_agent"}
SPLITS = {"development", "calibration", "test"}
CATEGORIES = {"clear", "ambiguous", "conflicting", "missing"}
STATE_FIELDS = {"cpu", "error_rate", "database_latency", "network_latency", "security_alert", "missing_fields"}


@dataclass(frozen=True)
class Scenario:
    case_id: str
    family: str
    split: str
    category: str
    incident: Incident
    target: str
    severity: int
    escalate: bool
    rationale: str


def load_scenarios(path: str | Path) -> list[Scenario]:
    cases = []
    seen = set()
    with Path(path).open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            raw = json.loads(line)
            case_id = raw["id"]
            if case_id in seen:
                raise ValueError(f"Duplicate case id: {case_id}")
            seen.add(case_id)
            state, label = raw["state"], raw["label"]
            if set(state) - STATE_FIELDS:
                raise ValueError(f"Unexpected input fields on line {number}")
            if raw["split"] not in SPLITS or raw["category"] not in CATEGORIES or label["target"] not in TARGETS:
                raise ValueError(f"Invalid split, category or target on line {number}")
            if not isinstance(label["escalate"], bool) or not isinstance(label["severity"], int) or not 1 <= label["severity"] <= 5:
                raise ValueError(f"Invalid label on line {number}")
            incident = Incident(incident_id=case_id, **state)
            cases.append(Scenario(case_id, raw["family"], raw["split"], raw["category"], incident,
                                  label["target"], label["severity"], label["escalate"], raw["rationale"]))
    if not cases:
        raise ValueError("Empty scenario dataset")
    return cases
