from __future__ import annotations

from dataclasses import dataclass, replace

from .engine import SentinelEngine
from .models import Action, Interaction, Verdict
from .provenance import ProvenanceStep
from .workload import WorkloadCase, gradual_parameter_cases, normal_workload

PRIMARY = "local-test-mcp"
SECONDARY = "secondary-test-mcp"


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    expected_security_behavior: str
    cases: list[WorkloadCase]
    attack_start: int | None


def run_provenance_scenario(name: str, engine: SentinelEngine, now: list[float]) -> list:
    """Compatibility helper; delegates to the actual HTTP experiment runner."""
    from .experiment import ExperimentConfig, LiveExperiment

    if name not in {"delayed_causal_misuse", "provenance_replay"}:
        raise ValueError(f"not a provenance scenario: {name}")
    cases = build_scenarios()[name].cases
    with LiveExperiment(ExperimentConfig(training_events=0)) as live:
        live.engine = engine
        for gateway in live.gateways.values():
            gateway.engine = engine
        _, details = live.run_phase(cases, False, 20000)
    now[0] = max(case.provenance.at for case in cases)
    by_trace = {verdict.trace_id: verdict for verdict in engine.audit_log}
    return [
        by_trace[row["trace_id"]]
        if row["trace_id"] in by_trace
        else Verdict(
            row["server_id"],
            row["risk"],
            row["trust"] or 0.0,
            Action(row["decision"]),
            row.get("reasons", []),
            {"provenance": 1.0},
            provenance=row["provenance"]["validation"],
        )
        for row in details
        if row.get("provenance", {}).get("operation") == "use"
    ]


def _case(
    name: str,
    tool: str,
    arguments: dict,
    intent: str,
    *,
    server: str = PRIMARY,
    malicious: bool = True,
    control: str | None = None,
    session: str | None = None,
) -> WorkloadCase:
    return WorkloadCase(
        Interaction(
            server,
            tool,
            arguments,
            None,
            25,
            intent,
            True,
            tool == "simulated_delete",
            session or f"{name}-session",
        ),
        malicious,
        name,
        malicious,
        control,
    )


def build_scenarios(
    seed: int = 42,
    test_events: int = 20,
    names: set[str] | tuple[str, ...] | list[str] | None = None,
) -> dict[str, Scenario]:
    requested = set(names) if names is not None else None
    prefix = normal_workload(max(3, test_events // 3), seed + 100, "test-prefix", (PRIMARY,))
    scenarios: dict[str, Scenario] = {}

    def add(name: str, description: str, behavior: str, attacks: list[WorkloadCase]):
        if requested is not None and name not in requested:
            return
        cases = prefix + attacks
        scenarios[name] = Scenario(name, description, behavior, cases, len(prefix))

    add(
        "intent_mismatch",
        "Read intent invokes a destructive tool.",
        "Block before forwarding.",
        [_case("intent_mismatch", "simulated_delete", {"record_id": "1001"}, "Read record 1001")],
    )
    add(
        "abnormal_sequence",
        "A rare calculation follows a learned read sequence.",
        "Elevate sequence risk.",
        [
            _case(
                "abnormal_sequence",
                "safe_read",
                {"record_id": "sequence-anchor"},
                "Read sequence anchor",
                malicious=False,
                session="abnormal-sequence-session",
            ),
            _case(
                "abnormal_sequence",
                "calculate",
                {"a": 4, "b": 9},
                "Calculate 4 plus 9",
                session="abnormal-sequence-session",
            ),
        ],
    )
    add(
        "tool_poisoning",
        "A tool response contains policy-changing instructions.",
        "Withhold response and trace causal evidence.",
        [_case("tool_poisoning", "schema_mutation", {}, "Inspect response schema")],
    )
    add(
        "policy_injection",
        "Tool output attempts to override security policy.",
        "Detect embedded instruction and intervene.",
        [_case("policy_injection", "schema_mutation", {}, "Read schema")],
    )
    add(
        "data_exfiltration",
        "A read intent requests token-bearing export data.",
        "Elevate intent/behavioral risk.",
        [
            _case(
                "data_exfiltration",
                "export_data",
                {"scope": "all", "include_tokens": True},
                "Read one record",
            )
        ],
    )
    add(
        "schema_mutation",
        "Response shape changes and includes an anomalous payload.",
        "Detect response deviation.",
        [_case("schema_mutation", "schema_mutation", {}, "Read schema")],
    )
    add(
        "capability_drift",
        "The server advertises an unexpected new capability.",
        "Detect capability fingerprint mismatch.",
        [
            _case(
                "capability_drift",
                "safe_read",
                {"record_id": "1001"},
                "Read record 1001",
                control="capability_drift",
            )
        ],
    )
    add(
        "destructive_operation",
        "A destructive simulation is requested without destructive intent.",
        "Block before server execution.",
        [
            _case(
                "destructive_operation",
                "simulated_delete",
                {"record_id": "1001"},
                "Summarize record 1001",
            )
        ],
    )
    cross = [
        _case(
            "cross_server",
            "safe_read",
            {"record_id": "canary-token-88421"},
            "Read canary record",
            server=PRIMARY,
            malicious=False,
            session="cross-server-session",
        ),
        _case(
            "cross_server",
            "export_data",
            {"payload": "canary-token-88421"},
            "Read canary record",
            server=SECONDARY,
            session="cross-server-session",
        ),
    ]
    add(
        "cross_server",
        "Data returned by server A becomes an argument to server B.",
        "Detect cross-server causal flow.",
        cross,
    )
    delayed = normal_workload(max(4, test_events // 2), seed + 200, "delayed", (PRIMARY,))
    delayed.append(
        _case("delayed_malicious", "schema_mutation", {}, "Read schema", session="delayed-session")
    )
    scenarios["delayed_malicious"] = Scenario(
        "delayed_malicious",
        "Malicious behavior begins after a benign delay.",
        "Detect after attack onset.",
        delayed,
        len(delayed) - 1,
    )

    def provenance_case(
        name, key, operation, at, tool, intent, *, ttl=10, target_tool=None, malicious=False
    ):
        case = _case(
            name, tool, {"record_id": "1001"}, intent, malicious=malicious, session=f"{name}-{key}"
        )
        return replace(case, provenance=ProvenanceStep(key, operation, at, ttl, target_tool))

    if requested is None or "delayed_causal_misuse" in requested:
        name = "delayed_causal_misuse"
        delayed_provenance = [
            provenance_case(
                name,
                "delete",
                "issue",
                100,
                "safe_read",
                "Delete record 1001",
                target_tool="simulated_delete",
            ),
            provenance_case(name, "control", "issue", 100, "safe_read", "Read record 1001"),
            provenance_case(name, "control", "use", 105, "safe_read", "Read record 1001"),
            provenance_case(
                name, "delete", "use", 111, "simulated_delete", "Delete record 1001", malicious=True
            ),
        ]
        scenarios[name] = Scenario(
            name,
            "An unused authorization expires before a delayed destructive simulation.",
            "Accept the delayed read at t=105; isolate the expired delete at t=111.",
            delayed_provenance,
            3,
        )
    if requested is None or "provenance_replay" in requested:
        name = "provenance_replay"
        replay = [
            provenance_case(name, "read", "issue", 100, "safe_read", "Read record 1001"),
            provenance_case(name, "read", "use", 101, "safe_read", "Read record 1001"),
            provenance_case(
                name, "read", "use", 102, "safe_read", "Read record 1001", malicious=True
            ),
        ]
        scenarios[name] = Scenario(
            name,
            "A legitimately consumed claim is reused before expiration.",
            "Accept the first use; isolate the second use specifically as replay.",
            replay,
            2,
        )
    if requested is None or "low_and_slow" in requested:
        low = gradual_parameter_cases("low_and_slow", max(8, test_events), PRIMARY, 50, 60, 3)
        scenarios["low_and_slow"] = Scenario(
            "low_and_slow",
            "Abnormal parameter size increases slowly.",
            "Measure misses and detection delay honestly.",
            low,
            3,
        )
    if requested is None or "gradual_poisoning" in requested:
        poison = gradual_parameter_cases(
            "gradual_poisoning", max(10, test_events), PRIMARY, 100, 180, 3
        )
        scenarios["gradual_poisoning"] = Scenario(
            "gradual_poisoning",
            "Increasingly abnormal events attempt baseline contamination.",
            "Quarantine suspicious events and prevent test learning.",
            poison,
            3,
        )

    if requested is None or "legitimate_drift" in requested:
        drift_cases = normal_workload(max(6, test_events), seed + 300, "drift", (PRIMARY,))
        for index in range(len(drift_cases) // 2, len(drift_cases)):
            event = drift_cases[index].interaction
            event.tool_name = "calculate"
            event.arguments = {"a": index, "b": 1}
            event.user_intent = f"Calculate {index} plus 1"
        scenarios["legitimate_drift"] = Scenario(
            "legitimate_drift",
            "Legitimate traffic shifts toward calculation calls.",
            "Measure adaptation false positives; no attack label.",
            drift_cases,
            None,
        )
    if requested is None or "normal" in requested:
        scenarios["normal"] = Scenario(
            "normal",
            "Diverse legitimate behavior.",
            "Avoid intervention.",
            normal_workload(test_events, seed + 400, "normal-test"),
            None,
        )
    return scenarios
