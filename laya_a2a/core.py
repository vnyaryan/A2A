from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class Incident:
    incident_id: str
    cpu: float = 0
    error_rate: float = 0
    database_latency: float = 0
    network_latency: float = 0
    security_alert: bool = False
    actual_owner: str | None = None  # Simulator label; never passed to a model.
    missing_fields: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.incident_id or not 0 <= self.cpu <= 100 or not 0 <= self.error_rate <= 1:
            raise ValueError("Invalid incident fields")
        if self.database_latency < 0 or self.network_latency < 0:
            raise ValueError("Latencies must be nonnegative")
        allowed = {"cpu", "error_rate", "database_latency", "network_latency", "security_alert"}
        if set(self.missing_fields) - allowed or len(set(self.missing_fields)) != len(self.missing_fields):
            raise ValueError("Invalid missing_fields")


@dataclass(frozen=True)
class Decision:
    target: str
    severity: int
    escalate: bool
    reason: str
    confidence: float | None = None


@dataclass(frozen=True)
class Message:
    sequence: int
    sender: str
    recipient: str
    kind: str
    payload: Mapping[str, Any] = field(default_factory=dict)


class Router(Protocol):
    def decide(self, incident: Incident) -> Decision: ...


class RuleRouter:
    def decide(self, incident: Incident) -> Decision:
        observed = lambda name: name not in incident.missing_fields
        if len(incident.missing_fields) >= 4:
            target, reason = "human", "insufficient telemetry"
        elif observed("security_alert") and incident.security_alert:
            target, reason = "security_agent", "security alert"
        elif observed("database_latency") and incident.database_latency > 500:
            target, reason = "database_agent", "database latency"
        elif observed("network_latency") and incident.network_latency > 300:
            target, reason = "network_agent", "network latency"
        elif (observed("error_rate") and incident.error_rate > .1) or (observed("cpu") and incident.cpu > 90):
            target, reason = "application_agent", "application health"
        else:
            target, reason = "human", "no matching threshold"
        severity = 5 if incident.security_alert or incident.error_rate > .3 else 4 if incident.error_rate > .1 or incident.database_latency > 500 else 2
        return Decision(target, severity, target == "human", reason)


@dataclass(frozen=True)
class Outcome:
    status: str
    messages: tuple[Message, ...]
    wrong_agent_calls: int


class Coordinator:
    def __init__(self, router: Router):
        self.router = router

    def run(self, incident: Incident) -> Outcome:
        messages: list[Message] = []

        def send(sender: str, recipient: str, kind: str, **payload: Any):
            messages.append(Message(len(messages) + 1, sender, recipient, kind, payload))

        # Keep simulator labels out of decision input.
        observed = Incident(incident.incident_id, incident.cpu, incident.error_rate,
                            incident.database_latency, incident.network_latency, incident.security_alert,
                            missing_fields=incident.missing_fields)
        send("monitoring_agent", "coordinator", "observation", incident_id=incident.incident_id)
        decision = self.router.decide(observed)
        send("coordinator", decision.target, "route", severity=decision.severity, reason=decision.reason)
        if decision.escalate or decision.target == "human":
            send("coordinator", "human", "escalation", reason=decision.reason)
            return Outcome("escalated", tuple(messages), 0)
        if decision.target not in {"security_agent", "database_agent", "network_agent", "application_agent"}:
            raise ValueError("Unknown agent target")
        success = decision.target == incident.actual_owner
        send(decision.target, "verification_agent", "investigation", remediated=success)
        send("verification_agent", "coordinator", "verification", verified=success)
        if not success:
            send("coordinator", "human", "escalation", reason="unverified remediation")
        return Outcome("resolved" if success else "escalated", tuple(messages), int(not success))
