from __future__ import annotations

import copy
import json
import threading
import time
import urllib.request
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from .baselines import BASELINES
from sentinel.engine import EngineConfig, SentinelEngine
from sentinel.gateway import GatewayConfig, SentinelGateway, create_gateway_server
from .metrics import Observation, calculate_metrics
from .mock_server import MockMcpState, create_mock_server, handle_mock_payload
from .mock_server import tools as mock_tools
from sentinel.provenance import ScenarioClock
from .scenarios import PRIMARY, SECONDARY, Scenario, build_scenarios
from .workload import WorkloadCase, normal_workload

_HARNESS_CLIENT_TOKEN = "experiment-client-token-0123456789abcdef"


@dataclass(frozen=True)
class ExperimentConfig:
    seed: int = 42
    scenario: str = "all"
    training_events: int = 100
    validation_events: int = 40
    test_events: int = 40
    baseline: str = "sentinel"
    output: str = "results"
    intent: bool = True
    causal: bool = True
    attestation: bool = True
    uncertainty: bool = True
    quarantine: bool = True
    in_process: bool = False

    def engine_config(self) -> EngineConfig:
        return EngineConfig(
            self.intent, self.causal, self.attestation, self.uncertainty, self.quarantine
        )


class LiveExperiment:
    def __init__(self, config: ExperimentConfig, in_process: bool | None = None):
        self.config = config
        self.in_process = getattr(config, "in_process", False) if in_process is None else in_process
        self.engine = SentinelEngine(
            min(20, max(5, config.training_events // 5)), config.engine_config()
        )
        self.servers: list[Any] = []
        self.states: dict[str, MockMcpState] = {}
        self.gateways: dict[str, SentinelGateway] = {}
        self.urls: dict[str, str] = {}
        self.provenance_clock: ScenarioClock | None = None
        self.provenance_claims: dict[str, str] = {}
        self.allowed_tools = tuple(tool["name"] for tool in mock_tools(MockMcpState()))

    def __enter__(self):
        for server_id in (PRIMARY, SECONDARY):
            if self.in_process:
                state = MockMcpState()
                gateway = SentinelGateway(
                    GatewayConfig(
                        f"http://127.0.0.1:mock-{server_id}",
                        server_id,
                        timeout_seconds=3,
                        allowed_tools=self.allowed_tools,
                        client_auth_token=_HARNESS_CLIENT_TOKEN,
                    ),
                    self.engine,
                )

                def _forward_mock(st):
                    return lambda payload: handle_mock_payload(st, payload)

                gateway.in_process_forwarder = _forward_mock(state)
                self.states[server_id] = state
                self.gateways[server_id] = gateway
                self.urls[server_id] = f"inprocess://{server_id}"
            else:
                mock, state = create_mock_server()
                threading.Thread(target=mock.serve_forever, daemon=True).start()
                upstream = f"http://127.0.0.1:{mock.server_address[1]}"
                gateway_server, gateway = create_gateway_server(
                    GatewayConfig(
                        upstream,
                        server_id,
                        timeout_seconds=3,
                        allowed_tools=self.allowed_tools,
                        client_auth_token=_HARNESS_CLIENT_TOKEN,
                    ),
                    self.engine,
                    port=0,
                )
                threading.Thread(target=gateway_server.serve_forever, daemon=True).start()
                self.servers.extend([gateway_server, mock])
                self.states[server_id] = state
                self.gateways[server_id] = gateway
                self.urls[server_id] = f"http://127.0.0.1:{gateway_server.server_address[1]}"
            self._rpc(server_id, "initialize", {"protocolVersion": "2025-06-18"}, 1, "Initialize")
            self._rpc(server_id, "tools/list", {}, 2, "List tools")
        return self

    def __exit__(self, exc_type, exc, tb):
        for server in self.servers:
            server.shutdown()
            server.server_close()

    def _rpc(
        self,
        server_id: str,
        method: str,
        params: dict[str, Any],
        request_id: int,
        intent: str,
        session: str = "experiment",
        provenance_id: str | None = None,
    ) -> tuple[dict[str, Any], float]:
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_HARNESS_CLIENT_TOKEN}",
            "X-Sentinel-Intent": intent,
            "X-Sentinel-Session": session,
        }
        if provenance_id is not None:
            headers["X-Sentinel-Provenance"] = provenance_id
        started = time.perf_counter()
        if self.in_process:
            gateway = self.gateways[server_id]
            body = json.dumps(payload).encode()
            status, resp_bytes, _ = gateway.handle(body, {k.lower(): v for k, v in headers.items()})
            return json.loads(resp_bytes), (time.perf_counter() - started) * 1000
        request = urllib.request.Request(
            self.urls[server_id],
            json.dumps(payload).encode(),
            method="POST",
            headers=headers,
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read()), (time.perf_counter() - started) * 1000

    def execute(
        self, case: WorkloadCase, request_id: int, learn: bool, trusted_enrollment: bool = False
    ) -> tuple[Observation, dict[str, Any]]:
        server_id = case.interaction.server_id
        gateway = self.gateways[server_id]
        gateway.learning_enabled = learn
        gateway.trusted_enrollment = trusted_enrollment
        gateway.telemetry_latency_override_ms = case.interaction.latency_ms
        step = case.provenance
        claim_id = case.interaction.provenance_id
        before = None
        if step is not None:
            if self.provenance_clock is None:
                raise ValueError("provenance cases must execute within run_phase")
            self.provenance_clock.value = step.at
            if step.operation == "use":
                claim_id = self.provenance_claims[step.key]
                retained = self.engine.provenance.claims.get(claim_id)
                before = asdict(retained) if retained is not None else None
            elif step.operation != "issue":
                raise ValueError("unknown provenance operation")
        if case.control == "capability_drift":
            self.states[server_id].capability_version = 2
            self._rpc(
                server_id,
                "tools/list",
                {},
                request_id - 1,
                "List updated tools",
                case.interaction.session_id,
            )
        params = {"name": case.interaction.tool_name, "arguments": case.interaction.arguments}
        response, total_latency = self._rpc(
            server_id,
            "tools/call",
            params,
            request_id,
            case.interaction.user_intent,
            case.interaction.session_id,
            claim_id,
        )
        audit = gateway.audit[-1]
        issued = None
        issuance_error = None
        if step is not None and step.operation == "issue":
            target = replace(
                case.interaction, tool_name=step.target_tool or case.interaction.tool_name
            )
            try:
                issued = self.engine.issue_provenance(audit.trace_id, target, ttl=step.ttl)
            except ValueError as exc:
                # A denied origin is an experimental outcome, not authority to
                # mint a claim. Do not hide unrelated implementation failures.
                if str(exc) != "provenance origin must be an accepted engine event":
                    raise
                issuance_error = str(exc)
            # Keep the subsequent attempted calls in the workload, explicitly
            # carrying an unknown claim rather than silently omitting provenance.
            self.provenance_claims[step.key] = (
                issued.claim_id if issued else "unissued-fixture-" + uuid.uuid4().hex
            )
        decision = BASELINES[self.config.baseline]().decide(case, audit)
        observation = Observation(
            case.malicious,
            decision.intervene,
            decision.score,
            audit.trust_score or 0.0,
            audit.uncertainty or 0.0,
            total_latency,
            audit.analysis_latency_ms or 0.0,
            request_id,
        )
        detail = {
            "index": request_id,
            "scenario": case.scenario,
            "malicious": case.malicious,
            "server_id": server_id,
            "session_id": case.interaction.session_id,
            "tool": case.interaction.tool_name,
            "parameter_fingerprint": audit.parameter_fingerprint,
            "trace_id": audit.trace_id,
            "risk": decision.score,
            "trust": audit.trust_score,
            "uncertainty": audit.uncertainty,
            "components": {
                "intent": audit.intent_risk,
                "causal": audit.causal_risk,
                "capability": audit.capability_risk,
            },
            "decision": audit.decision,
            "baseline_intervention": decision.intervene,
            "forwarded": audit.forwarded,
            "latency_ms": total_latency,
            "analysis_latency_ms": audit.analysis_latency_ms,
            "response_error": response.get("error"),
        }
        if step is not None:
            detail["reasons"] = audit.reasons
            detail["provenance"] = {
                "operation": step.operation,
                "time": step.at,
                "claim_id": issued.claim_id if issued else claim_id,
                "before": before,
                "issued": asdict(issued) if issued else None,
                "issuance_error": issuance_error,
                "claim_available_before_use": before is not None
                if step.operation == "use"
                else None,
                "validation": audit.provenance,
            }
        return observation, detail

    def run_phase(
        self,
        cases: list[WorkloadCase],
        learn: bool,
        start_id: int,
        trusted_enrollment: bool = False,
    ) -> tuple[list[Observation], list[dict[str, Any]]]:
        observations, details = [], []
        original_clock = self.engine.provenance.clock
        if any(case.provenance is not None for case in cases):
            self.provenance_clock = ScenarioClock()
            self.provenance_claims = {}
            self.engine.provenance.clock = self.provenance_clock
        try:
            for offset, case in enumerate(cases):
                observation, detail = self.execute(
                    case, start_id + offset, learn, trusted_enrollment
                )
                observations.append(replace(observation, index=offset))
                details.append(detail)
        finally:
            self.engine.provenance.clock = original_clock
            self.provenance_clock = None
        return observations, details


def _profile_totals(engine: SentinelEngine) -> tuple[int, int]:
    return (
        sum(profile.trusted_count for profile in engine.profiles.values()),
        sum(profile.quarantined_count for profile in engine.profiles.values()),
    )


def run_one(config: ExperimentConfig, scenario: Scenario) -> dict[str, Any]:
    identity_config = asdict(config)
    identity_config.pop("output", None)
    identity_hash = uuid.uuid5(uuid.NAMESPACE_DNS, str(identity_config) + scenario.name).hex[:8]
    experiment_id = f"{scenario.name}-s{config.seed}-{identity_hash}"
    with LiveExperiment(config) as live:
        train = normal_workload(config.training_events, config.seed, "train")
        validation = normal_workload(config.validation_events, config.seed + 1, "validation")
        live.run_phase(train, True, 1_000, trusted_enrollment=True)
        trained_after_train, quarantined_after_train = _profile_totals(live.engine)
        post_train_engine = copy.deepcopy(live.engine)
        validation_observations, _ = live.run_phase(validation, False, 10_000)
        live.engine = post_train_engine
        for gateway in live.gateways.values():
            gateway.engine = post_train_engine
        trusted_before_test, quarantined_before_test = _profile_totals(live.engine)
        adaptive_phase = scenario.name in {"legitimate_drift", "gradual_poisoning"}
        test_observations, decisions = live.run_phase(scenario.cases, adaptive_phase, 20_000)
        trusted_after_test, quarantined_after_test = _profile_totals(live.engine)
        metrics = calculate_metrics(test_observations, scenario.attack_start)
        validation_metrics = calculate_metrics(validation_observations)
    result = {
        "experiment_id": experiment_id,
        "seed": config.seed,
        "configuration": asdict(config),
        "engine_components": asdict(config.engine_config()),
        "baseline": config.baseline,
        "scenario": {
            "name": scenario.name,
            "description": scenario.description,
            "expected_security_behavior": scenario.expected_security_behavior,
            "attack_start": scenario.attack_start,
        },
        "dataset_sizes": {
            "train": len(train),
            "validation": len(validation),
            "test": len(scenario.cases),
        },
        "phase_policy": {
            "train_learns": True,
            "validation_learns": False,
            "test_learns": adaptive_phase,
            "note": "Drift/poisoning use a labeled adaptive phase; "
            "held-out security tests never learn.",
        },
        "baseline_state": {
            "trusted_after_train": trained_after_train,
            "trusted_before_test": trusted_before_test,
            "trusted_after_test": trusted_after_test,
            "quarantined_after_train": quarantined_after_train,
            "quarantined_before_test": quarantined_before_test,
            "quarantined_after_test": quarantined_after_test,
        },
        "validation_metrics": validation_metrics,
        "metrics": metrics,
        "decisions": decisions,
        "failures": [],
    }
    return result


def run_experiment(config: ExperimentConfig) -> list[dict[str, Any]]:
    if config.baseline not in BASELINES:
        raise ValueError(f"Unknown baseline: {config.baseline}")
    scenarios = build_scenarios(config.seed, config.test_events)
    selected = (
        list(scenarios.values()) if config.scenario == "all" else [scenarios[config.scenario]]
    )
    results = [run_one(config, scenario) for scenario in selected]
    root = Path(config.output)
    root.mkdir(parents=True, exist_ok=True)
    for result in results:
        scenario_name = result["scenario"]["name"]
        folder = root / scenario_name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{result['experiment_id']}.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
    summary = [
        {
            "experiment_id": item["experiment_id"],
            "scenario": item["scenario"]["name"],
            "precision": item["metrics"]["precision"],
            "recall": item["metrics"]["recall"],
            "f1": item["metrics"]["f1"],
            "fpr": item["metrics"]["false_positive_rate"],
        }
        for item in results
    ]
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (root / "summary.txt").write_text(
        "\n".join(
            f"{row['scenario']}: precision={row['precision']:.3f} recall={row['recall']:.3f} "
            f"f1={row['f1']:.3f} fpr={row['fpr']:.3f}"
            for row in summary
        ),
        encoding="utf-8",
    )
    return results
