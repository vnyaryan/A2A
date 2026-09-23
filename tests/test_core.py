import unittest
from laya_a2a.core import Coordinator, Incident, RuleRouter


class CoreTests(unittest.TestCase):
    def test_success(self):
        result = Coordinator(RuleRouter()).run(Incident("I1", database_latency=850, actual_owner="database_agent"))
        self.assertEqual(result.status, "resolved")
        self.assertEqual([m.sequence for m in result.messages], list(range(1, len(result.messages)+1)))

    def test_wrong_route(self):
        result = Coordinator(RuleRouter()).run(Incident("I2", database_latency=850, actual_owner="network_agent"))
        self.assertEqual((result.status, result.wrong_agent_calls), ("escalated", 1))

    def test_ground_truth_is_hidden(self):
        class Spy:
            def decide(self, incident):
                assert incident.actual_owner is None
                return RuleRouter().decide(incident)
        Coordinator(Spy()).run(Incident("I3", security_alert=True, actual_owner="security_agent"))

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            Incident("I4", error_rate=2)
