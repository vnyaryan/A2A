import unittest

from laya_a2a.core import Incident
from laya_a2a.laya_router import LayaRouter


class PredictorStub:
    def __init__(self, response):
        self.response = response
        self.state = None
        self.questions = None

    def predict(self, state, questions):
        self.state, self.questions = state, questions
        return self.response


def response(target="database_agent", confidence=.8, score=3.0, noul=.2):
    return {"answers": {"target": {"choice": target, "confidence": confidence},
                        "severity": {"score": score}, "escalate": {"noul": noul}}}


class AdapterContractTests(unittest.TestCase):
    def test_sdk_shape_and_label_isolation(self):
        stub = PredictorStub(response())
        result = LayaRouter(stub).decide(Incident("I1", database_latency=800, actual_owner="network_agent"))
        self.assertEqual((result.target, result.severity, result.confidence), ("database_agent", 4, .8))
        self.assertNotIn("actual_owner", stub.state)
        self.assertEqual({q["type"] for q in stub.questions.values()}, {"choice", "score", "noul"})

    def test_escalation(self):
        self.assertTrue(LayaRouter(PredictorStub(response(noul=.9))).decide(Incident("I2")).escalate)

    def test_invalid_target_fails_closed(self):
        with self.assertRaises(ValueError):
            LayaRouter(PredictorStub(response(target="unregistered"))).decide(Incident("I3"))

    def test_invalid_probability_fails_closed(self):
        with self.assertRaises(ValueError):
            LayaRouter(PredictorStub(response(confidence=float("nan")))).decide(Incident("I4"))
