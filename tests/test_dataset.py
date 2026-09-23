import unittest
from pathlib import Path

from laya_a2a.dataset import load_scenarios
from laya_a2a.core import RuleRouter, Coordinator

DATA = Path(__file__).resolve().parents[1] / "data" / "scenarios.jsonl"


class DatasetTests(unittest.TestCase):
    def test_splits_and_categories(self):
        cases = load_scenarios(DATA)
        self.assertEqual(len(cases), 24)
        self.assertEqual({case.split for case in cases}, {"development", "calibration", "test"})
        self.assertTrue(all(len([case for case in cases if case.split == split]) == 8
                            for split in ("development", "calibration", "test")))
        self.assertEqual({case.category for case in cases}, {"clear", "ambiguous", "conflicting", "missing"})
        self.assertEqual(len({case.case_id for case in cases}), len(cases))

    def test_ground_truth_never_reaches_router(self):
        class Spy:
            def decide(self, incident):
                self.assertIsNone(incident.actual_owner)
                return RuleRouter().decide(incident)

            def assertIsNone(self, value):
                assert value is None

        for case in load_scenarios(DATA):
            Coordinator(Spy()).run(case.incident)

    def test_missing_signal_is_not_encoded_as_zero(self):
        class Spy:
            def decide(self, incident):
                assert "cpu" in incident.missing_fields
                return RuleRouter().decide(incident)

        case = next(case for case in load_scenarios(DATA) if case.case_id == "missing-c")
        Coordinator(Spy()).run(case.incident)
