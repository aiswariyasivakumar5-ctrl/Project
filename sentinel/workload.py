from __future__ import annotations

import random
from dataclasses import dataclass

from .models import Interaction
from .provenance import ProvenanceStep


@dataclass(frozen=True)
class WorkloadCase:
    interaction: Interaction
    malicious: bool
    scenario: str
    expected_intervention: bool
    control: str | None = None
    provenance: ProvenanceStep | None = None


def normal_workload(
    count: int,
    seed: int,
    phase: str = "train",
    servers: tuple[str, ...] = ("local-test-mcp", "secondary-test-mcp"),
) -> list[WorkloadCase]:
    rng = random.Random(seed)
    result: list[WorkloadCase] = []
    session_count = max(6, min(200, count // 20 or 6))
    for index in range(count):
        weights = [0.75, 0.25] if len(servers) == 2 else None
        server = rng.choices(servers, weights=weights, k=1)[0]
        rare_calculation = index > 2 and rng.random() < 0.18
        if rare_calculation:
            a, b = rng.randint(0, 50), rng.randint(0, 50)
            tool, arguments, intent = "calculate", {"a": a, "b": b}, f"Calculate {a} plus {b}"
        else:
            record = f"record-{rng.randint(1000, 1020)}"
            tool, arguments, intent = "safe_read", {"record_id": record}, f"Read record {record}"
        event = Interaction(
            server,
            tool,
            arguments,
            None,
            max(2.0, rng.gauss(18 if server == servers[0] else 27, 4)),
            intent,
            True,
            False,
            f"{phase}-session-{index % session_count}",
            1_700_000_000 + index,
        )
        result.append(WorkloadCase(event, False, "normal", False))
    return result


def gradual_parameter_cases(
    name: str, count: int, server: str, start_size: int, step: int, malicious_from: int
) -> list[WorkloadCase]:
    cases = []
    for index in range(count):
        size = min(start_size + index * step, 10_000)
        malicious = index >= malicious_from
        value = "record-1001" if not malicious else "x" * size
        event = Interaction(
            server,
            "safe_read",
            {"record_id": value},
            None,
            20 + index,
            "Read record 1001",
            True,
            False,
            f"{name}-session",
            1_700_100_000 + index,
        )
        cases.append(
            WorkloadCase(event, malicious, name, malicious, "poison_attempt" if malicious else None)
        )
    return cases
