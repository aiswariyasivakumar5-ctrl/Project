from __future__ import annotations

import argparse
import json
import os

from .ablation import AblationConfig, analyze_existing_baselines, run_ablation_matrix
from .audit_log import verify_audit_log
from .benchmark import print_benchmark
from .compare import CompareConfig, generate_report, run_comparison
from .diagnostics import write_diagnostics
from .engine import SentinelEngine
from .experiment import ExperimentConfig, run_experiment
from .fusion_study import FusionStudyConfig, run_fusion_study
from .gateway import GatewayConfig, build_baseline, serve_gateway
from .gateway_benchmark import print_gateway_benchmark, run_gateway_benchmark
from .mock_server import serve_mock
from .novelty import NoveltyConfig
from .plots import generate_figures
from .research_tables import generate_research_tables
from .service import serve
from .simulator import attack_events, normal_events
from .tradeoff_analysis import TradeoffConfig, run_tradeoff_analysis


def _parse_upstream_header(value: str) -> tuple[str, str]:
    header_name, separator, env_name = value.partition("=")
    if not separator or not header_name or not env_name:
        raise argparse.ArgumentTypeError(
            "use NAME=ENV_VAR; provide the secret through the environment"
        )
    return header_name, env_name


def run_demo(training_events: int) -> None:
    engine = SentinelEngine(warmup_events=min(20, training_events))
    for event in normal_events(training_events):
        engine.evaluate(event)
    print(f"Trained on {training_events} normal interactions\n")
    for label, event in attack_events():
        print(f"{label}: {json.dumps(engine.evaluate(event).to_dict(), indent=2)}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="mcp-sentinel")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="train and evaluate synthetic attacks")
    demo.add_argument("--training-events", type=int, default=100)
    dashboard = commands.add_parser(
        "dashboard", help="local-only visual demo with safe mock MCP servers"
    )
    dashboard.add_argument("--port", type=int, default=8765)
    service = commands.add_parser("serve", help="start the JSON evaluation API")
    service.add_argument("--host", default="127.0.0.1")
    service.add_argument("--port", type=int, default=8787)
    service.add_argument("--request-timeout", type=float, default=10.0)
    service.add_argument("--max-connections", type=int, default=32)
    benchmark = commands.add_parser("benchmark", help="run the reproducible MVP benchmark")
    benchmark.add_argument("--training-events", type=int, default=100)
    benchmark.add_argument("--test-events", type=int, default=100)
    gateway = commands.add_parser("gateway", help="run the MCP JSON-RPC gateway")
    gateway.add_argument("--upstream", required=True)
    gateway.add_argument("--server-id", required=True)
    gateway.add_argument("--host", default="127.0.0.1")
    gateway.add_argument("--port", type=int, default=8788)
    gateway.add_argument("--timeout", type=float, default=5.0)
    gateway.add_argument("--request-timeout", type=float, default=10.0)
    gateway.add_argument("--max-connections", type=int, default=32)
    gateway.add_argument(
        "--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"), default="INFO"
    )
    gateway.add_argument("--log-file")
    gateway.add_argument("--audit-log")
    gateway.add_argument("--audit-log-max-bytes", type=int, default=10_485_760)
    gateway.add_argument(
        "--rate-limit",
        type=float,
        default=0.0,
        help="per-client and per-session requests per second; 0 disables",
    )
    gateway.add_argument("--rate-burst", type=int, default=0)
    gateway.add_argument("--session-ttl", type=float, default=3600.0)
    gateway.add_argument(
        "--client-credentials",
        dest="credentials_file",
        help="JSON mapping SHA-256 token hashes to client ids",
    )
    gateway.add_argument("--tls-cert")
    gateway.add_argument("--tls-key")
    gateway.add_argument("--tls-client-ca", help="require client certificates issued by this CA")
    gateway.add_argument("--insecure-allow-plaintext", action="store_true")
    gateway.add_argument("--trust-proxy-headers", action="store_true")
    gateway.add_argument("--policy-file", help="optional JSON pre-execution policy")
    gateway.add_argument(
        "--auth-token",
        default=os.environ.get("MCP_SENTINEL_OPERATOR_TOKEN"),
        help="operator Bearer credential (or MCP_SENTINEL_OPERATOR_TOKEN env var)",
    )
    gateway.add_argument(
        "--client-auth-token",
        default=os.environ.get("MCP_SENTINEL_CLIENT_TOKEN"),
        help="Bearer credential for MCP callers (or MCP_SENTINEL_CLIENT_TOKEN env var)",
    )
    gateway.add_argument(
        "--allow-tool",
        action="append",
        default=[],
        metavar="NAME",
        help="explicitly allow an upstream tool to execute; repeat for each approved tool",
    )
    gateway.add_argument(
        "--allow-method",
        action="append",
        default=[],
        choices=("ping", "resources/list", "resources/read", "prompts/list", "prompts/get"),
        help="explicitly enable an otherwise denied MCP method; repeat for each method",
    )
    gateway.add_argument(
        "--upstream-header",
        action="append",
        type=_parse_upstream_header,
        default=[],
        metavar="NAME=ENV_VAR",
        help="read an upstream header value from the named environment variable",
    )
    gateway.add_argument(
        "--allowed-host",
        action="append",
        default=[],
        metavar="HOST:PORT",
        help="allowed public Host value for a remote/reverse-proxy deployment",
    )
    gateway.add_argument(
        "--allowed-origin",
        action="append",
        default=[],
        metavar="ORIGIN",
        help="allowed browser Origin for a remote/reverse-proxy deployment",
    )
    gateway.add_argument(
        "--state-file",
        default=None,
        help="load the learned baseline from this file on start (if present) and save it "
        "periodically and on shutdown; create one with the 'baseline' command",
    )
    gateway.add_argument(
        "--novelty", action="store_true", help="enable capability trust and evidence-gated learning"
    )
    gateway.add_argument(
        "--require-provenance",
        action="store_true",
        help="require trusted-issuer authorization for every tool call",
    )
    for component in (
        "intent-provenance",
        "capability-trust",
        "dual-memory",
        "require-promotion-approval",
    ):
        gateway.add_argument(
            "--" + component,
            action=argparse.BooleanOptionalAction,
            default=True,
            help="novelty component switch (requires --novelty)",
        )
    mock = commands.add_parser("mock-server", help="run the safe local MCP test server")
    mock.add_argument("--host", default="127.0.0.1")
    mock.add_argument("--port", type=int, default=8790)
    mock.add_argument("--streamable-http", action="store_true")
    mock.add_argument("--require-sessions", action="store_true")
    baseline = commands.add_parser(
        "baseline", help="pre-train a gateway baseline from known-benign calls"
    )
    baseline.add_argument("--upstream", required=True)
    baseline.add_argument("--server-id", required=True)
    baseline.add_argument("--state-file", required=True)
    baseline.add_argument(
        "--calls-file",
        default=None,
        help='JSONL of benign calls: {"tool":..., "arguments":{...}, "intent":...}; '
        "defaults to the safe_read/calculate calls of the bundled mock server",
    )
    baseline.add_argument("--rounds", type=int, default=60)
    baseline.add_argument("--timeout", type=float, default=5.0)
    baseline.add_argument("--novelty", action="store_true")
    baseline.add_argument(
        "--upstream-header",
        action="append",
        type=_parse_upstream_header,
        default=[],
        metavar="NAME=ENV_VAR",
    )
    gateway_benchmark = commands.add_parser(
        "gateway-benchmark", help="compare direct and proxied MCP calls"
    )
    gateway_benchmark.add_argument("--requests", type=int, default=100)
    experiment = commands.add_parser(
        "experiment", help="run reproducible workloads through the real gateway"
    )
    experiment.add_argument("--seed", type=int, default=42)
    experiment.add_argument("--scenario", default="all")
    experiment.add_argument("--training-events", type=int, default=100)
    experiment.add_argument("--validation-events", type=int, default=40)
    experiment.add_argument("--test-events", type=int, default=40)
    experiment.add_argument("--baseline", choices=["sentinel", "rules"], default="sentinel")
    experiment.add_argument("--output", default="results")
    experiment.add_argument("--without-intent", action="store_true")
    experiment.add_argument("--without-causal", action="store_true")
    experiment.add_argument("--without-attestation", action="store_true")
    experiment.add_argument("--without-uncertainty", action="store_true")
    experiment.add_argument("--without-quarantine", action="store_true")
    novelty = commands.add_parser(
        "novelty-study", help="run isolated live-gateway novelty ablations"
    )
    novelty.add_argument("--seeds", default="42")
    novelty.add_argument(
        "--variants",
        default="baseline,full,without_intent_provenance,without_capability_trust,without_dual_memory",
    )
    novelty.add_argument("--scenarios", default="all")
    novelty.add_argument("--training-events", type=int, default=100)
    novelty.add_argument("--validation-events", type=int, default=40)
    novelty.add_argument("--test-events", type=int, default=12)
    novelty.add_argument(
        "--validation-fpr",
        type=float,
        help=(
            "optional benign-validation FPR target for secondary score metrics; "
            "does not change gateway policy"
        ),
    )
    novelty.add_argument("--output", required=True, help="new output directory (must not exist)")
    compare = commands.add_parser("compare", help="run offline Sentinel and ML baseline comparison")
    compare.add_argument("--seeds", default="42,123,456,789,1001")
    compare.add_argument("--train-size", type=int, default=5000)
    compare.add_argument("--validation-size", type=int, default=1000)
    compare.add_argument("--test-size", type=int, default=3000)
    compare.add_argument(
        "--models",
        default="sentinel,isolation_forest,one_class_svm,dense_autoencoder,lstm,transformer",
    )
    compare.add_argument("--validation-fpr", type=float, default=0.01)
    compare.add_argument("--output", default="results/baselines")
    report = commands.add_parser("report", help="generate a Markdown conference comparison table")
    report.add_argument("--results", default="results/baselines")
    report.add_argument("--output")
    ablate = commands.add_parser("ablate", help="run publication-scale Sentinel ablations")
    ablate.add_argument("--seeds", default="42,123,456,789,1001")
    ablate.add_argument("--train-size", type=int, default=5000)
    ablate.add_argument("--validation-size", type=int, default=1000)
    ablate.add_argument("--test-size", type=int, default=3000)
    ablate.add_argument("--output", default="results/ablations_publication")
    ablate.add_argument("--bootstrap-resamples", type=int, default=20000)
    analyze = commands.add_parser(
        "analyze", help="add confidence intervals, paired tests, and diagnostics"
    )
    analyze.add_argument("--baselines", default="results/baselines_publication")
    analyze.add_argument("--output", default="results/statistical_analysis")
    analyze.add_argument("--bootstrap-resamples", type=int, default=20000)
    figures = commands.add_parser("figures", help="generate dependency-free SVG conference figures")
    figures.add_argument("--baselines", default="results/baselines_publication")
    figures.add_argument("--ablations", default="results/ablations_publication")
    figures.add_argument("--output", default="results/figures")
    figures.add_argument("--gateway-requests", type=int, default=100)
    tables = commands.add_parser(
        "research-tables", help="generate conference data tables with intervals and tests"
    )
    verify_audit = commands.add_parser("verify-audit", help="verify a hash-chained JSONL audit log")
    verify_audit.add_argument("path")
    tables.add_argument("--baselines", default="results/baselines_publication")
    tables.add_argument("--ablations", default="results/ablations_publication")
    tables.add_argument("--statistics", default="results/statistical_analysis")
    tables.add_argument("--output", default="results/tables")
    tradeoff = commands.add_parser(
        "tradeoff-diagnostic", help="run frozen Sentinel trust/threshold diagnostics"
    )
    tradeoff.add_argument("--seeds", default="42,123,456,789,1001")
    tradeoff.add_argument("--train-size", type=int, default=5000)
    tradeoff.add_argument("--validation-size", type=int, default=1000)
    tradeoff.add_argument("--test-size", type=int, default=3000)
    tradeoff.add_argument("--validation-fpr", type=float, default=0.01)
    tradeoff.add_argument("--output", default="results/tradeoff_diagnostics")
    fusion = commands.add_parser("fusion-study", help="evaluate validation-only fusion candidates")
    fusion.add_argument("--seeds", default="42,123,456,789,1001")
    fusion.add_argument("--train-size", type=int, default=5000)
    fusion.add_argument("--validation-size", type=int, default=1000)
    fusion.add_argument("--test-size", type=int, default=3000)
    fusion.add_argument("--validation-fpr", type=float, default=0.01)
    fusion.add_argument("--gateway-requests", type=int, default=100)
    fusion.add_argument("--output", default="results/fusion_study")
    args = parser.parse_args()
    if args.command == "demo":
        run_demo(args.training_events)
    elif args.command == "dashboard":
        from .dashboard import serve_dashboard

        serve_dashboard(args.port)
    elif args.command == "benchmark":
        print_benchmark(args.training_events, args.test_events)
    elif args.command == "gateway":
        serve_gateway(
            GatewayConfig(
                args.upstream,
                args.server_id,
                args.timeout,
                auth_token=args.auth_token,
                client_auth_token=args.client_auth_token,
                novelty=args.novelty,
                require_provenance=args.require_provenance,
                allowed_tools=tuple(args.allow_tool),
                allowed_methods=tuple(args.allow_method),
                upstream_headers=tuple(args.upstream_header),
                log_level=args.log_level,
                log_file=args.log_file,
                audit_log_path=args.audit_log,
                audit_log_max_bytes=args.audit_log_max_bytes,
                rate_limit=args.rate_limit,
                rate_burst=args.rate_burst,
                session_ttl_seconds=args.session_ttl,
                credentials_file=args.credentials_file,
                tls_cert=args.tls_cert,
                tls_key=args.tls_key,
                tls_client_ca=args.tls_client_ca,
                insecure_allow_plaintext=args.insecure_allow_plaintext,
                trust_proxy_headers=args.trust_proxy_headers,
                policy_file=args.policy_file,
                allowed_hosts=tuple(args.allowed_host),
                allowed_origins=tuple(args.allowed_origin),
                request_timeout_seconds=args.request_timeout,
                max_connections=args.max_connections,
                novelty_config=NoveltyConfig(
                    args.intent_provenance,
                    args.capability_trust,
                    args.dual_memory,
                    args.require_promotion_approval,
                ),
            ),
            args.host,
            args.port,
            state_file=args.state_file,
        )
    elif args.command == "baseline":
        calls = None
        if args.calls_file:
            calls = [
                json.loads(line) for line in open(args.calls_file, encoding="utf-8") if line.strip()
            ]
        result = build_baseline(
            GatewayConfig(
                args.upstream,
                args.server_id,
                args.timeout,
                novelty=args.novelty,
                upstream_headers=tuple(args.upstream_header),
            ),
            args.state_file,
            calls,
            args.rounds,
        )
        print(json.dumps(result, indent=2))
    elif args.command == "mock-server":
        serve_mock(
            args.host,
            args.port,
            streamable_http=args.streamable_http,
            require_sessions=args.require_sessions,
        )
    elif args.command == "gateway-benchmark":
        print_gateway_benchmark(args.requests)
    elif args.command == "experiment":
        config = ExperimentConfig(
            args.seed,
            args.scenario,
            args.training_events,
            args.validation_events,
            args.test_events,
            args.baseline,
            args.output,
            not args.without_intent,
            not args.without_causal,
            not args.without_attestation,
            not args.without_uncertainty,
            not args.without_quarantine,
        )
        results = run_experiment(config)
        print(
            json.dumps(
                [
                    {
                        "experiment_id": item["experiment_id"],
                        "scenario": item["scenario"]["name"],
                        "metrics": item["metrics"],
                    }
                    for item in results
                ],
                indent=2,
            )
        )
    elif args.command == "novelty-study":
        from .novelty_experiment import NoveltyStudyConfig, run_novelty_study
        from .novelty_scenarios import build_novelty_scenarios

        config = NoveltyStudyConfig(
            seeds=tuple(int(value) for value in args.seeds.split(",")),
            variants=tuple(value.strip() for value in args.variants.split(",")),
            scenarios=tuple(build_novelty_scenarios())
            if args.scenarios == "all"
            else tuple(value.strip() for value in args.scenarios.split(",")),
            training_events=args.training_events,
            validation_events=args.validation_events,
            test_events=args.test_events,
            output=args.output,
            validation_fpr=args.validation_fpr,
        )
        print(json.dumps(run_novelty_study(config), indent=2))
    elif args.command == "compare":
        config = CompareConfig(
            tuple(int(value) for value in args.seeds.split(",") if value.strip()),
            args.train_size,
            args.validation_size,
            args.test_size,
            tuple(value.strip() for value in args.models.split(",") if value.strip()),
            args.validation_fpr,
            args.output,
        )
        comparison = run_comparison(config)
        print(json.dumps(comparison["aggregate"], indent=2))
    elif args.command == "report":
        print(generate_report(args.results, args.output))
    elif args.command == "ablate":
        result = run_ablation_matrix(
            AblationConfig(
                tuple(int(value) for value in args.seeds.split(",") if value.strip()),
                args.train_size,
                args.validation_size,
                args.test_size,
                0.01,
                args.output,
                args.bootstrap_resamples,
            )
        )
        print(json.dumps(result["aggregate"], indent=2))
    elif args.command == "analyze":
        root = __import__("pathlib").Path(args.output)
        root.mkdir(parents=True, exist_ok=True)
        statistics = analyze_existing_baselines(
            args.baselines, str(root / "baseline_statistics.json"), args.bootstrap_resamples
        )
        diagnostics = write_diagnostics(str(root / "diagnostics.json"))
        print(json.dumps({"statistics": statistics, "diagnostics": diagnostics}, indent=2))
    elif args.command == "figures":
        performance = run_gateway_benchmark(args.gateway_requests)
        print(
            json.dumps(
                generate_figures(args.baselines, args.ablations, args.output, performance), indent=2
            )
        )
    elif args.command == "research-tables":
        print(
            json.dumps(
                generate_research_tables(
                    args.baselines, args.ablations, args.statistics, args.output
                ),
                indent=2,
            )
        )
    elif args.command == "tradeoff-diagnostic":
        result = run_tradeoff_analysis(
            TradeoffConfig(
                tuple(int(value) for value in args.seeds.split(",") if value.strip()),
                args.train_size,
                args.validation_size,
                args.test_size,
                args.validation_fpr,
                args.output,
            )
        )
        print(
            json.dumps(
                {
                    "output": args.output,
                    "seeds": len(result["seeds"]),
                    "figures": result["figures"],
                },
                indent=2,
            )
        )
    elif args.command == "fusion-study":
        result = run_fusion_study(
            FusionStudyConfig(
                tuple(int(value) for value in args.seeds.split(",") if value.strip()),
                args.train_size,
                args.validation_size,
                args.test_size,
                args.validation_fpr,
                args.gateway_requests,
                args.output,
            )
        )
        print(
            json.dumps(
                {"aggregate": result["aggregate"], "gateway": result["gateway_control"]}, indent=2
            )
        )
    elif args.command == "verify-audit":
        valid, detail = verify_audit_log(args.path)
        print(json.dumps({"valid": valid, "detail": detail}))
        if not valid:
            raise SystemExit(1)
    else:
        serve(
            args.host,
            args.port,
            max_connections=args.max_connections,
            request_timeout=args.request_timeout,
        )


if __name__ == "__main__":
    main()
