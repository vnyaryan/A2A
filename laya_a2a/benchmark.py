"""Paired, sequential router evaluation on labeled incident scenarios."""
from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .core import Incident, Router, RuleRouter
from .dataset import TARGETS, Scenario, load_scenarios


@dataclass(frozen=True)
class Row:
    case_id: str
    split: str
    category: str
    expected_target: str
    predicted_target: str | None
    expected_severity: int
    predicted_severity: int | None
    expected_escalate: bool
    predicted_escalate: bool | None
    confidence: float | None
    latency_ms: float
    error: str | None


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    pos = (len(sorted_values) - 1) * p
    low = math.floor(pos)
    return sorted_values[low] + (sorted_values[math.ceil(pos)] - sorted_values[low]) * (pos - low)


def observed(case: Scenario) -> Incident:
    incident = case.incident
    return Incident(incident.incident_id, incident.cpu, incident.error_rate,
                    incident.database_latency, incident.network_latency,
                    incident.security_alert, missing_fields=incident.missing_fields)


def evaluate(router: Router, cases: list[Scenario], warmup: int = 0) -> tuple[list[Row], dict]:
    if not cases or warmup < 0:
        raise ValueError("Nonempty cases and nonnegative warmup required")
    # Warmup costs are excluded, and each router should use the same selected cases.
    for i in range(warmup):
        router.decide(observed(cases[i % len(cases)]))
    rows = []
    for case in cases:
        start = time.perf_counter_ns()
        try:
            prediction = router.decide(observed(case))
            if prediction.target not in TARGETS or not isinstance(prediction.severity, int) or not 1 <= prediction.severity <= 5 or not isinstance(prediction.escalate, bool):
                raise ValueError("invalid decision fields")
            row = Row(case.case_id, case.split, case.category, case.target, prediction.target,
                      case.severity, prediction.severity, case.escalate, prediction.escalate,
                      prediction.confidence, (time.perf_counter_ns() - start) / 1e6, None)
        except Exception as exc:
            row = Row(case.case_id, case.split, case.category, case.target, None,
                      case.severity, None, case.escalate, None, None,
                      (time.perf_counter_ns() - start) / 1e6, f"{type(exc).__name__}: {exc}")
        rows.append(row)
    return rows, summarize(rows)


def summarize(rows: list[Row]) -> dict:
    if not rows:
        raise ValueError("Cannot summarize empty rows")
    n = len(rows)
    valid = [r for r in rows if r.error is None]
    routing_correct = sum(r.predicted_target == r.expected_target for r in valid)
    classes = sorted({r.expected_target for r in rows})
    f1_values = []
    for label in classes:
        tp = sum(r.predicted_target == label and r.expected_target == label for r in rows)
        fp = sum(r.predicted_target == label and r.expected_target != label for r in rows)
        fn = sum(r.predicted_target != label and r.expected_target == label for r in rows)
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        f1_values.append(2 * precision * recall / (precision + recall) if precision + recall else 0)
    escalation_positives = sum(r.expected_escalate for r in rows)
    escalation_tp = sum(r.expected_escalate and r.predicted_escalate is True for r in rows)
    # A "resolved" workflow is a correct specialist route without escalation;
    # a human-labeled case completes by appropriate escalation.
    workflow_success = sum(
        (r.expected_escalate and r.predicted_escalate is True)
        or (not r.expected_escalate and r.predicted_escalate is False and r.predicted_target == r.expected_target)
        for r in rows
    )
    elapsed_ms = sum(r.latency_ms for r in rows)
    return {
        "cases": n,
        "invalid_outputs": n - len(valid),
        "routing_accuracy": routing_correct / n,
        "routing_macro_f1": statistics.mean(f1_values),
        "escalation_recall": escalation_tp / escalation_positives if escalation_positives else None,
        "escalation_accuracy": sum(r.predicted_escalate == r.expected_escalate for r in valid) / n,
        "severity_mae": sum(abs(r.predicted_severity - r.expected_severity) for r in valid) / n if valid else None,
        "workflow_completion": workflow_success / n,
        "wrong_agent_calls": sum(not r.expected_escalate and r.predicted_escalate is False and r.predicted_target != r.expected_target for r in valid),
        "latency_ms": {"p50": percentile([r.latency_ms for r in rows], .5),
                       "p95": percentile([r.latency_ms for r in rows], .95),
                       "p99": percentile([r.latency_ms for r in rows], .99)},
        "sequential_decisions_per_second": n * 1000 / elapsed_ms if elapsed_ms else None,
        "categories": {category: {"count": sum(r.category == category for r in rows),
                                  "routing_accuracy": sum(r.category == category and r.predicted_target == r.expected_target for r in rows) / sum(r.category == category for r in rows)}
                       for category in sorted({r.category for r in rows})},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate routing with no LLM or vLLM")
    parser.add_argument("--dataset", type=Path, default=Path(__file__).resolve().parents[1] / "data/scenarios.jsonl")
    parser.add_argument("--split", choices=["development", "calibration", "test", "all"], default="test")
    parser.add_argument("--router", choices=["rules", "laya"], default="rules")
    parser.add_argument("--checkpoint", choices=["english", "typed-decisions"], default="english")
    parser.add_argument("--warmup", type=int, default=0)
    parser.add_argument("--out", type=Path, default=Path("results"))
    args = parser.parse_args()
    cases = [case for case in load_scenarios(args.dataset) if args.split == "all" or case.split == args.split]
    if args.router == "laya":
        from .laya_router import LayaRouter
        router = LayaRouter(checkpoint=args.checkpoint)
    else:
        router = RuleRouter()
    rows, metrics = evaluate(router, cases, args.warmup)
    args.out.mkdir(parents=True, exist_ok=True)
    run_name = f"{args.router}_{args.checkpoint if args.router == 'laya' else 'baseline'}_{args.split}"
    with (args.out / f"{run_name}.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0])))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    report = {"run": run_name, "metrics": metrics, "metadata": {
        "python": platform.python_version(), "platform": platform.platform(),
        "dataset": str(args.dataset), "warmup_calls": args.warmup,
        "timing_scope": "per decision including input construction and validation; model load excluded",
        "dataset_limitation": "24 synthetic cases; related variants occur across splits",
        "confidence_calibration": "not measured: confidence is not verified as correctness probability",
    }}
    (args.out / f"{run_name}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
