from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .features import SENSITIVE, intent_mismatch
from .gateway import GatewayAudit
from .workload import WorkloadCase


@dataclass(frozen=True)
class BaselineDecision:
    score: float
    intervene: bool


class Baseline(Protocol):
    name: str

    def decide(self, case: WorkloadCase, audit: GatewayAudit) -> BaselineDecision: ...


class SentinelBaseline:
    name = "complete_sentinel"

    def decide(self, case: WorkloadCase, audit: GatewayAudit) -> BaselineDecision:
        score = audit.anomaly_score or 0.0
        return BaselineDecision(score, audit.decision in {"confirm", "sandbox", "isolate"})


class RuleBaseline:
    """Lightweight transparent rule baseline; no learned behavior or causal state."""

    name = "rules"

    def decide(self, case: WorkloadCase, audit: GatewayAudit) -> BaselineDecision:
        event = case.interaction
        sensitive = bool(SENSITIVE.search(str(event.arguments)))
        mismatch = intent_mismatch(event.user_intent, event.tool_name, event.arguments)
        destructive = event.tool_name == "simulated_delete"
        score = max(1.0 if sensitive else 0.0, 0.9 if destructive and mismatch >= 0.7 else 0.0)
        return BaselineDecision(score, score >= 0.5)


BASELINES = {"sentinel": SentinelBaseline, "rules": RuleBaseline}


PLANNED_BASELINES = [
    "isolation_forest",
    "one_class_svm",
    "dense_autoencoder",
    "lstm_sequence",
    "transformer_sequence",
    "graph_only",
]
