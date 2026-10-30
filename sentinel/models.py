from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from .validation import validate_json


# Preserve str(Enum) compatibility for callers that rely on "Action.ALLOW".
class Action(str, Enum):  # noqa: UP042
    ALLOW = "allow"
    OBSERVE = "observe"
    CONFIRM = "confirm"
    SANDBOX = "sandbox"
    ISOLATE = "isolate"


@dataclass(slots=True)
class Interaction:
    server_id: str
    tool_name: str
    arguments: dict[str, Any]
    response: Any
    latency_ms: float
    user_intent: str
    success: bool = True
    side_effect: bool = False
    session_id: str = "default"
    timestamp: float | None = None
    capability_digest: str | None = None
    attestation_challenge_id: str | None = None
    attestation_echo: str | None = None
    provenance_id: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Interaction:
        validate_json(value)
        if not isinstance(value, dict):
            raise ValueError("interaction must be an object")
        event = cls(**value)
        for name, limit in (
            ("server_id", 256),
            ("tool_name", 256),
            ("session_id", 128),
            ("user_intent", 2048),
        ):
            item = getattr(event, name)
            if not isinstance(item, str) or not 0 < len(item) <= limit:
                raise ValueError(f"invalid {name}")
        if not isinstance(event.arguments, dict):
            raise ValueError("arguments must be an object")
        if type(event.success) is not bool or type(event.side_effect) is not bool:
            raise ValueError("success and side_effect must be booleans")
        for name in ("latency_ms", "timestamp"):
            item = getattr(event, name)
            if item is None and name == "timestamp":
                continue
            if type(item) not in (int, float) or not 0 <= item <= 1e15:
                raise ValueError(f"invalid {name}")
        for name in (
            "capability_digest",
            "attestation_challenge_id",
            "attestation_echo",
            "provenance_id",
        ):
            item = getattr(event, name)
            if item is not None and (not isinstance(item, str) or not 0 < len(item) <= 256):
                raise ValueError(f"invalid {name}")
        return event


@dataclass(slots=True)
class Verdict:
    server_id: str
    anomaly_score: float
    trust_score: float
    action: Action
    reasons: list[str] = field(default_factory=list)
    components: dict[str, float] = field(default_factory=dict)
    baseline_updated: bool = False
    trace_id: str | None = None
    uncertainty: float = 0.0
    challenge: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["action"] = self.action.value
        return result
