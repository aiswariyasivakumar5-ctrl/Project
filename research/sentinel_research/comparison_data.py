from __future__ import annotations

import copy
import random
from dataclasses import dataclass

from .ml_features import simulated_response
from sentinel.models import Interaction
from .scenarios import build_scenarios
from .workload import WorkloadCase, normal_workload

ATTACK_FAMILIES = [
    "intent_mismatch",
    "abnormal_sequence",
    "tool_poisoning",
    "policy_injection",
    "data_exfiltration",
    "schema_mutation",
    "capability_drift",
    "destructive_operation",
    "cross_server",
    "delayed_malicious",
    "low_and_slow",
    "gradual_poisoning",
]


@dataclass(frozen=True)
class DatasetRow:
    interaction: Interaction
    malicious: bool
    scenario: str


@dataclass(frozen=True)
class ComparisonDataset:
    train: list[DatasetRow]
    validation: list[DatasetRow]
    test: list[DatasetRow]


def _row(case: WorkloadCase, scenario: str | None = None) -> DatasetRow:
    event = copy.deepcopy(case.interaction)
    event.response = simulated_response(event)
    event.capability_digest = "cap-v2" if case.control == "capability_drift" else "cap-v1"
    return DatasetRow(event, case.malicious, scenario or case.scenario)


def _normal_rows(count: int, seed: int, phase: str) -> list[DatasetRow]:
    return [_row(case, "normal") for case in normal_workload(count, seed, phase)]


def build_comparison_dataset(
    seed: int, train_size: int = 5000, validation_size: int = 1000, test_size: int = 3000
) -> ComparisonDataset:
    if min(train_size, validation_size, test_size) <= 0:
        raise ValueError("Dataset sizes must be positive")
    train = _normal_rows(train_size, seed, "comparison-train")
    validation = _normal_rows(validation_size, seed + 1, "comparison-validation")
    normal_test = _normal_rows(test_size // 2, seed + 2, "comparison-test")
    templates = build_scenarios(seed + 3, max(20, test_size // len(ATTACK_FAMILIES)))
    rng = random.Random(seed + 4)
    attacks: list[DatasetRow] = []
    target_per_family = max(1, (test_size - len(normal_test)) // len(ATTACK_FAMILIES))
    for family in ATTACK_FAMILIES:
        scenario = templates[family]
        tail = scenario.cases[scenario.attack_start or 0 :]
        malicious_templates = [case for case in tail if case.malicious]
        benign_context = [case for case in tail if not case.malicious]
        for index in range(target_per_family):
            session = f"comparison-{family}-{index}"
            if family in {"cross_server", "abnormal_sequence"}:
                token = f"canary-token-{seed}-{index}"
                for context in benign_context:
                    copied = copy.deepcopy(context)
                    copied.interaction.session_id = session
                    if family == "cross_server":
                        copied.interaction.arguments = {"record_id": token}
                    attacks.append(_row(copied, family))
            template = copy.deepcopy(malicious_templates[index % len(malicious_templates)])
            template.interaction.session_id = session
            if family == "cross_server":
                template.interaction.arguments = {"payload": f"canary-token-{seed}-{index}"}
            elif "record_id" in template.interaction.arguments:
                template.interaction.arguments["record_id"] = (
                    f"attack-{family}-{rng.randint(0, 1_000_000)}"
                )
            template.interaction.latency_ms += rng.uniform(-3, 8)
            attacks.append(_row(template, family))
    test = normal_test + attacks
    return ComparisonDataset(train, validation, test)
