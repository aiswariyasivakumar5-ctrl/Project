"""Runtime-only command line interface."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from .audit_log import verify_audit_log
from .gateway import GatewayConfig, build_baseline, serve_gateway
from .http_limits import validate_timeout
from .service import serve


def _parse_upstream_header(value: str) -> tuple[str, str]:
    header_name, separator, env_name = value.partition("=")
    if not separator or not header_name or not env_name:
        raise argparse.ArgumentTypeError(
            "use NAME=ENV_VAR; provide the secret through the environment"
        )
    return header_name, env_name


def _runtime_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mcp-sentinel")
    commands = parser.add_subparsers(dest="command", required=True)

    gateway = commands.add_parser("gateway", help="run the MCP HTTP JSON-RPC gateway")
    gateway.add_argument("--upstream", required=True)
    gateway.add_argument("--server-id", required=True)
    gateway.add_argument("--host", default="127.0.0.1")
    gateway.add_argument("--port", type=int, default=8788)
    gateway.add_argument("--timeout", type=float, default=5.0)
    gateway.add_argument("--request-timeout", type=float, default=10.0)
    gateway.add_argument("--max-connections", type=int, default=32)
    gateway.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default="INFO",
    )
    gateway.add_argument("--log-file")
    gateway.add_argument("--audit-log")
    gateway.add_argument("--audit-log-max-bytes", type=int, default=10_485_760)
    gateway.add_argument("--rate-limit", type=float, default=0.0)
    gateway.add_argument("--rate-burst", type=int, default=0)
    gateway.add_argument("--session-ttl", type=float, default=3600.0)
    gateway.add_argument("--client-credentials", dest="credentials_file")
    gateway.add_argument("--tls-cert")
    gateway.add_argument("--tls-key")
    gateway.add_argument("--tls-client-ca")
    gateway.add_argument("--insecure-allow-plaintext", action="store_true")
    gateway.add_argument("--trust-proxy-headers", action="store_true")
    gateway.add_argument("--policy-file")
    gateway.add_argument(
        "--enable-learning",
        action="store_true",
        help="enable online learning explicitly; disabled by default",
    )
    gateway.add_argument("--auth-token", default=os.environ.get("MCP_SENTINEL_OPERATOR_TOKEN"))
    gateway.add_argument("--client-auth-token", default=os.environ.get("MCP_SENTINEL_CLIENT_TOKEN"))
    gateway.add_argument("--allow-tool", action="append", default=[])
    gateway.add_argument("--allow-method", action="append", default=[])
    gateway.add_argument(
        "--upstream-header", action="append", type=_parse_upstream_header, default=[]
    )
    gateway.add_argument("--allowed-host", action="append", default=[])
    gateway.add_argument("--allowed-origin", action="append", default=[])
    gateway.add_argument("--state-file", required=True)
    gateway.add_argument("--novelty", action="store_true")
    gateway.add_argument("--require-provenance", action="store_true")
    for component in (
        "intent-provenance",
        "capability-trust",
        "dual-memory",
        "require-promotion-approval",
    ):
        gateway.add_argument("--" + component, action=argparse.BooleanOptionalAction, default=True)

    baseline = commands.add_parser("baseline", help="enroll and manage approved baselines")
    baseline.add_argument(
        "action",
        nargs="?",
        choices=("enroll", "export", "approve", "rollback"),
        default="enroll",
    )
    baseline.add_argument("--upstream")
    baseline.add_argument("--server-id")
    baseline.add_argument("--state-file", required=True)
    baseline.add_argument("--output")
    baseline.add_argument("--version-file")
    baseline.add_argument("--actor")
    baseline.add_argument("--audit-log")
    baseline.add_argument("--calls-file")
    baseline.add_argument("--policy-file")
    baseline.add_argument("--rounds", type=int, default=60)
    baseline.add_argument("--timeout", type=float, default=5.0)
    baseline.add_argument("--novelty", action="store_true")
    baseline.add_argument(
        "--upstream-header", action="append", type=_parse_upstream_header, default=[]
    )

    api = commands.add_parser("serve", help="start the JSON evaluation API")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8787)
    api.add_argument("--request-timeout", type=float, default=10.0)
    api.add_argument("--max-connections", type=int, default=32)

    audit = commands.add_parser("verify-audit", help="verify a hash-chained JSONL audit log")
    audit.add_argument("path")
    return parser


def _dispatch_runtime(args: argparse.Namespace) -> None:
    if args.command == "gateway":
        validate_timeout(args.timeout)
        from .novelty import NoveltyConfig

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
                enable_learning=args.enable_learning,
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
        if args.action != "enroll":
            from .baseline import manage_baseline

            manage_baseline(
                args.action,
                args.state_file,
                actor=args.actor,
                audit_log=args.audit_log,
                output=args.output,
                version_file=args.version_file,
            )
            return
        if not args.upstream or not args.server_id:
            raise SystemExit("baseline enroll requires --upstream and --server-id")
        calls = None
        if args.calls_file:
            calls = [
                json.loads(line)
                for line in Path(args.calls_file).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        result = build_baseline(
            GatewayConfig(
                args.upstream,
                args.server_id,
                args.timeout,
                novelty=args.novelty,
                upstream_headers=tuple(args.upstream_header),
                policy_file=args.policy_file,
            ),
            args.state_file,
            calls,
            args.rounds,
        )
        print(json.dumps(result, indent=2))
    elif args.command == "serve":
        serve(
            args.host,
            args.port,
            max_connections=args.max_connections,
            request_timeout=args.request_timeout,
        )
    elif args.command == "verify-audit":
        valid, detail = verify_audit_log(args.path)
        print(json.dumps({"valid": valid, "detail": detail}))
        if not valid:
            raise SystemExit(1)


def main(argv: Sequence[str] | None = None) -> None:
    args = _runtime_parser().parse_args(argv)
    _dispatch_runtime(args)


if __name__ == "__main__":
    main()
