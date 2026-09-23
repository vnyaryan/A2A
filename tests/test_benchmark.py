import unittest
from pathlib import Path

from laya_a2a.benchmark import evaluate, percentile, summarize
from laya_a2a.core import Decision, RuleRouter
from laya_a2a.dataset import load_scenarios

DATA = Path(__file__).resolve().parents[1] / "data/scenarios.jsonl"


class BenchmarkTests(unittest.TestCase):
    def test_matching_cases_and_valid_denominator(self):
        cases = [c for c in load_scenarios(DATA) if c.split == "test"]
        rows, metrics = evaluate(RuleRouter(), cases)
        self.assertEqual([r.case_id for r in rows], [c.case_id for c in cases])
        self.assertEqual(metrics["cases"], 8)
        self.assertEqual(metrics["routing_accuracy"], 7 / 8)
        self.assertEqual(metrics["invalid_outputs"], 0)

    def test_error_counted_as_miss(self):
        class FailingRouter:
            def decide(self, incident):
                raise RuntimeError("inference failed")

        rows, metrics = evaluate(FailingRouter(), load_scenarios(DATA)[:2])
        self.assertEqual(metrics["invalid_outputs"], 2)
        self.assertEqual(metrics["routing_accuracy"], 0)
        self.assertEqual(metrics["workflow_completion"], 0)
        self.assertTrue(all(r.error for r in rows))

    def test_no_ground_truth_in_benchmark_router_input(self):
        class Spy:
            def decide(self, incident):
                assert incident.actual_owner is None
                return Decision("human", 2, True, "fallback")

        evaluate(Spy(), load_scenarios(DATA)[:1])

    def test_percentile_interpolation(self):
        self.assertEqual(percentile([10, 20, 30], .95), 29)
