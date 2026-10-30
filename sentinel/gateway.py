from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import ipaddress
import json
import logging
import math
import os
import re
import secrets
import ssl
import tempfile
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import FrameType
from typing import Any, NoReturn, cast
from urllib.parse import urlsplit

import numpy as np

from .audit_log import AuditLog
from .engine import SentinelEngine
from .features import intent_mismatch
from .http_limits import (
    BoundedHTTPServer,
    budget,
    remaining,
    request_budget,
    socket_deadline,
    timed_lock,
    validate_timeout,
)
from .jsonrpc import JsonRpcError, fingerprint, parse_request, validate_response
from .models import Action, Interaction
from .novelty import NoveltyConfig
from .policy import PreExecutionPolicy
from .retention import StateCapacityError
from .validation import PayloadTooLargeError, load_json, read_body, validate_json

SUPPORTED_METHODS = {"initialize", "notifications/initialized", "tools/list", "tools/call"}
OPERATOR_GATED_METHODS = {"ping", "resources/list", "resources/read", "prompts/list", "prompts/get"}
SUPPORTED_METHODS |= OPERATOR_GATED_METHODS
BLOCKING_ACTIONS = {Action.CONFIRM, Action.SANDBOX, Action.ISOLATE}
STATE_SCHEMA_VERSION = 1
MAX_STATE_FILE_BYTES = 32 * 1024 * 1024


def _safe_protocol_header(value: str, maximum: int) -> bool:
    return (
        0 < len(value) <= maximum
        and value.isascii()
        and all(0x21 <= ord(char) < 0x7F for char in value)
    )


@dataclass(slots=True)
class GatewayConfig:
    upstream_url: str
    server_id: str
    timeout_seconds: float = 5.0
    max_request_bytes: int = 1_048_576
    fail_closed: bool = True
    novelty: bool = False
    require_provenance: bool = False
    request_timeout_seconds: float = 10.0
    max_connections: int = 32
    novelty_config: NoveltyConfig = field(default_factory=NoveltyConfig)
    auth_token: str | None = None
    client_auth_token: str | None = None
    confirm_timeout_seconds: float = 60.0
    max_pending_actions: int = 1000
    resolved_action_ttl_seconds: float = 3600.0
    # Tool execution is an explicit operator policy. Upstream MCP annotations
    # are advisory and cannot grant a tool permission to execute.
    allowed_tools: tuple[str, ...] = ()
    allowed_hosts: tuple[str, ...] = ()
    allowed_origins: tuple[str, ...] = ()
    allowed_methods: tuple[str, ...] = ()
    upstream_headers: tuple[tuple[str, str], ...] = ()
    audit_log_path: str | None = None
    audit_log_max_bytes: int = 10_485_760
    log_level: str = "INFO"
    log_file: str | None = None
    rate_limit: float = 0.0
    rate_burst: int = 0
    session_ttl_seconds: float = 3600.0
    tls_cert: str | None = None
    tls_key: str | None = None
    tls_client_ca: str | None = None
    insecure_allow_plaintext: bool = False
    trust_proxy_headers: bool = False
    credentials_file: str | None = None
    policy_file: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.novelty_config, NoveltyConfig):
            raise ValueError("novelty_config must be a NoveltyConfig")
        for key, value in asdict(self.novelty_config).items():
            if key == "unreviewed_trust_floor":
                if type(value) not in (int, float) or not 0 <= value <= 1:
                    raise ValueError("unreviewed_trust_floor must be a float between 0 and 1")
            elif type(value) is not bool:
                raise ValueError("novelty component switches must be booleans")
        validate_timeout(self.timeout_seconds)
        validate_timeout(self.request_timeout_seconds)
        validate_timeout(self.confirm_timeout_seconds)
        validate_timeout(self.resolved_action_ttl_seconds)
        validate_timeout(self.session_ttl_seconds)
        if not math.isfinite(self.rate_limit) or self.rate_limit < 0:
            raise ValueError("rate_limit must be a finite nonnegative number")
        if type(self.rate_burst) is not int or self.rate_burst < 0:
            raise ValueError("rate_burst must be a nonnegative integer")
        if self.rate_limit and self.rate_burst < 1:
            raise ValueError("rate_burst must be positive when rate limiting is enabled")
        if self.audit_log_max_bytes < 1024:
            raise ValueError("audit_log_max_bytes must be at least 1024")
        if self.log_level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("invalid log_level")
        if type(self.max_pending_actions) is not int or self.max_pending_actions < 1:
            raise ValueError("max_pending_actions must be a positive integer")
        if self.auth_token is not None and (
            not isinstance(self.auth_token, str) or len(self.auth_token) < 4
        ):
            raise ValueError("auth_token must be a string of at least 4 characters")
        if self.client_auth_token is not None and (
            not isinstance(self.client_auth_token, str) or len(self.client_auth_token) < 32
        ):
            raise ValueError("client_auth_token must be at least 32 characters")
        if (
            self.auth_token is not None
            and self.client_auth_token is not None
            and hmac.compare_digest(self.auth_token.encode(), self.client_auth_token.encode())
        ):
            raise ValueError("operator and MCP client credentials must be different")
        if bool(self.tls_cert) != bool(self.tls_key):
            raise ValueError("tls_cert and tls_key must be configured together")
        if self.tls_client_ca and not self.tls_cert:
            raise ValueError("tls_client_ca requires TLS server credentials")
        if (
            not isinstance(self.allowed_tools, tuple)
            or any(not isinstance(tool, str) or not tool.strip() for tool in self.allowed_tools)
            or len(set(self.allowed_tools)) != len(self.allowed_tools)
        ):
            raise ValueError("allowed_tools must be a tuple of unique, nonempty tool names")
        for field_name, values in (
            ("allowed_hosts", self.allowed_hosts),
            ("allowed_origins", self.allowed_origins),
            ("allowed_methods", self.allowed_methods),
        ):
            if (
                not isinstance(values, tuple)
                or any(not isinstance(value, str) or not value.strip() for value in values)
                or len(set(values)) != len(values)
            ):
                raise ValueError(f"{field_name} must be a tuple of unique, nonempty strings")
        if any(method not in OPERATOR_GATED_METHODS for method in self.allowed_methods):
            raise ValueError("allowed_methods contains a method that is not operator-gated")
        if not isinstance(self.upstream_headers, tuple) or any(
            not isinstance(mapping, tuple)
            or len(mapping) != 2
            or any(not isinstance(part, str) for part in mapping)
            for mapping in self.upstream_headers
        ):
            raise ValueError("upstream_headers must be a tuple of (header, environment name) pairs")
        seen_header_names: set[str] = set()
        protected_headers = {
            "host",
            "content-length",
            "transfer-encoding",
            "content-type",
            "accept",
            "mcp-session-id",
            "mcp-protocol-version",
        }
        for header_name, env_name in self.upstream_headers:
            token_chars = "!#$%&'*+-.^_`|~"
            if (
                not header_name
                or not header_name.isascii()
                or not all(char.isalnum() or char in token_chars for char in header_name)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env_name)
                or header_name.lower() in protected_headers
                or header_name.lower() in seen_header_names
            ):
                raise ValueError("upstream_headers must contain unique safe NAME=ENV_VAR mappings")
            seen_header_names.add(header_name.lower())
        for value in (self.max_connections, self.max_request_bytes):
            if type(value) is not int or value < 1:
                raise ValueError("connection and byte limits must be positive integers")
        parsed = urlsplit(self.upstream_url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("upstream must be an HTTP(S) URL without embedded credentials")


@dataclass(slots=True)
class PendingAction:
    action_id: str
    trace_id: str | None
    session_id: str
    server_id: str
    tool_name: str | None
    arguments: dict[str, Any]
    upstream_response: bytes | None
    created_at: float
    expires_at: float
    status: str = "pending"  # "pending", "approved", "denied", "expired"
    reasons: list[str] = field(default_factory=list)
    reviewed_by: str | None = None
    reviewed_at: float | None = None
    containment: str | None = None

    def to_dict(self, include_payload: bool = False) -> dict[str, Any]:
        data = {
            "action_id": self.action_id,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "server_id": self.server_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "reasons": list(self.reasons or []),
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "containment": self.containment,
        }
        if include_payload and self.upstream_response:
            try:
                data["response"] = json.loads(self.upstream_response.decode("utf-8"))
            except Exception:
                data["response_bytes"] = len(self.upstream_response)
        return data


@dataclass(slots=True)
class UpstreamSessionBinding:
    owner: str
    upstream_session_id: str
    protocol_version: str | None
    created_at: float = field(default_factory=time.monotonic)
    last_used: float = field(default_factory=time.monotonic)


@dataclass(slots=True)
class GatewayAudit:
    timestamp: float
    session_id: str
    server_id: str
    method: str
    request_id: Any
    tool_name: str | None
    parameter_fingerprint: str
    response_fingerprint: str | None
    latency_ms: float
    forwarded: bool
    decision: str
    trace_id: str | None = None
    anomaly_score: float | None = None
    uncertainty: float | None = None
    intent_risk: float | None = None
    causal_risk: float | None = None
    capability_risk: float | None = None
    trust_score: float | None = None
    reasons: list[str] | None = None
    challenge: dict[str, Any] | None = None
    attestation_verified: bool | None = None
    analysis_latency_ms: float | None = None
    provenance: dict[str, Any] | None = None
    novelty: dict[str, Any] | None = None


class SentinelGateway:
    def __init__(
        self,
        config: GatewayConfig,
        engine: SentinelEngine | None = None,
        *,
        session_identity: Callable[[dict[str, str]], str | None] | None = None,
    ):
        self.config = config
        self.engine = engine or SentinelEngine()
        from .novelty import NoveltySentinelEngine

        self.novelty = (
            NoveltySentinelEngine(self.engine, config=config.novelty_config)
            if config.novelty
            else None
        )
        # An embedding application may resolve authenticated independent sessions.
        # Raw X-Sentinel-Session values never establish independence by themselves.
        self.session_identity = session_identity
        self.audit: deque[GatewayAudit] = deque(maxlen=self.engine.retention.audit_records)
        self.tool_metadata: dict[str, dict[str, Any]] = {}
        self.capability_digest: str | None = None
        self.learning_enabled = True
        self.trusted_enrollment = False
        # Research runner may inject deterministic workload latency while the
        # audit continues to record measured transport latency separately.
        self.telemetry_latency_override_ms: float | None = None
        self.in_process_forwarder: Callable[[dict[str, Any]], tuple[int, bytes, str]] | None = None
        self.pending_actions: dict[str, PendingAction] = {}
        self._approval_events: dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._session_lock = threading.RLock()
        self._upstream_sessions: dict[str, UpstreamSessionBinding] = {}
        self._uses_upstream_sessions = False
        self.audit_sink = (
            AuditLog(config.audit_log_path, max_bytes=config.audit_log_max_bytes)
            if config.audit_log_path
            else None
        )
        self.logger = logging.getLogger("sentinel.gateway")
        self.logger.setLevel(getattr(logging, config.log_level.upper()))
        self._rate_lock = threading.Lock()
        self._rate_buckets: dict[str, tuple[float, float]] = {}
        self.metrics: dict[str, Any] = {
            "requests": {},
            "latency_count": 0,
            "latency_sum_ms": 0.0,
            "latency_buckets": {bound: 0 for bound in (10, 50, 100, 500, 1000, "+Inf")},
            "upstream_errors": 0,
            "lock_wait_ms": 0.0,
        }
        self.baseline_loaded = False
        self.state_path: Path | None = None
        self.policy = PreExecutionPolicy(config.policy_file) if config.policy_file else None
        self.client_credentials = (
            self._credentials_from_file(config.credentials_file) if config.credentials_file else {}
        )
        self.auth_failures: dict[str, list[float]] = {}
        self._auth_lock = threading.Lock()

    def reload_client_credentials(self) -> None:
        if self.config.credentials_file:
            try:
                self.client_credentials = self._credentials_from_file(self.config.credentials_file)
            except ValueError as exc:
                self.logger.error(
                    json.dumps({"event": "credentials_reload_failed", "reason": str(exc)})
                )

    @staticmethod
    def _credentials_from_file(path: str | Path) -> dict[str, str]:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot load credentials file: {exc}") from exc
        if not isinstance(raw, dict) or not raw or len(raw) > 10000:
            raise ValueError("credentials file must be a nonempty hash-to-client-id object")
        if any(
            not isinstance(key, str)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", key)
            or not isinstance(value, str)
            or not value
            or len(value) > 128
            for key, value in raw.items()
        ):
            raise ValueError("credentials entries must map SHA-256 token hashes to client ids")
        return {key.lower(): value for key, value in raw.items()}

    def _persist_configured_state(self) -> None:
        if self.state_path is not None:
            self.save_state(self.state_path)

    def _sweep_upstream_sessions(self) -> None:
        now = time.monotonic()
        for downstream_id, binding in list(self._upstream_sessions.items()):
            if now - binding.last_used >= self.config.session_ttl_seconds:
                self._upstream_sessions.pop(downstream_id, None)

    def _await_preexecution_approval(
        self, session_id: str, tool: str, arguments: dict[str, Any], trace_id: str | None
    ) -> str:
        action = self.create_pending_action(
            trace_id, session_id, tool, arguments, b"", ["pre-execution approval required"]
        )
        event = threading.Event()
        with self._lock:
            current = self.pending_actions.get(action.action_id)
            wait_for_approval = current is not None and current.status == "pending"
            if wait_for_approval:
                self._approval_events[action.action_id] = event
        # Register the event only if the action is still pending. An operator
        # can approve it as soon as it becomes visible; checking under the same
        # lock closes the gap between action creation and waiter registration.
        resolved = (
            event.wait(min(self.config.confirm_timeout_seconds, remaining()))
            if wait_for_approval
            else True
        )
        with self._lock:
            self._approval_events.pop(action.action_id, None)
            current = self.pending_actions.get(action.action_id)
            if not resolved and current is not None and current.status == "pending":
                current.status = "expired"
                current.upstream_response = None
            status = current.status if current else "expired"
        self._persist_configured_state()
        return status

    def _append_audit(self, record: GatewayAudit) -> None:
        self.audit.append(record)
        with self._rate_lock:
            decisions = self.metrics["requests"]
            decisions[record.decision] = decisions.get(record.decision, 0) + 1
            self.metrics["latency_count"] += 1
            self.metrics["latency_sum_ms"] += record.latency_ms
            for bound in (10, 50, 100, 500, 1000):
                if record.latency_ms <= bound:
                    self.metrics["latency_buckets"][bound] += 1
            self.metrics["latency_buckets"]["+Inf"] += 1
        self.logger.info(
            json.dumps(
                {
                    "event": "mcp_request",
                    "request_id": record.request_id,
                    "session": record.session_id,
                    "tool": record.tool_name,
                    "decision": record.decision,
                    "latency_ms": record.latency_ms,
                    "reasons": record.reasons,
                },
                separators=(",", ":"),
            )
        )
        if self.audit_sink:
            self.audit_sink.append(asdict(record))

    def allow_rate(self, key: str) -> tuple[bool, float]:
        if not self.config.rate_limit:
            return True, 0.0
        now = time.monotonic()
        with self._rate_lock:
            if key not in self._rate_buckets and len(self._rate_buckets) >= 100_000:
                cutoff = now - max(60.0, self.config.rate_burst / self.config.rate_limit)
                self._rate_buckets = {
                    name: item for name, item in self._rate_buckets.items() if item[1] >= cutoff
                }
                if len(self._rate_buckets) >= 100_000:
                    return False, 60.0
            tokens, updated = self._rate_buckets.get(key, (float(self.config.rate_burst), now))
            tokens = min(
                float(self.config.rate_burst), tokens + (now - updated) * self.config.rate_limit
            )
            if tokens < 1:
                self._rate_buckets[key] = (tokens, now)
                return False, (1 - tokens) / self.config.rate_limit
            self._rate_buckets[key] = (tokens - 1, now)
            return True, 0.0

    @contextmanager
    def _engine_lock(self) -> Any:
        started = time.perf_counter()
        with timed_lock(self.engine.lock):
            waited = (time.perf_counter() - started) * 1000
            with self._rate_lock:
                self.metrics["lock_wait_ms"] += waited
            yield

    def create_pending_action(
        self,
        trace_id: str | None,
        session_id: str,
        tool: str | None,
        arguments: dict[str, Any],
        upstream_response: bytes,
        reasons: list[str] | None = None,
        containment: str | None = None,
    ) -> PendingAction:
        with self._lock:
            self._sweep_pending_actions()
            if len(self.pending_actions) >= self.config.max_pending_actions:
                resolved = sorted(
                    (
                        action
                        for action in self.pending_actions.values()
                        if action.status != "pending"
                    ),
                    key=self._action_resolution_time,
                )
                while resolved and len(self.pending_actions) >= self.config.max_pending_actions:
                    self.pending_actions.pop(resolved.pop(0).action_id, None)
            if len(self.pending_actions) >= self.config.max_pending_actions:
                raise StateCapacityError("pending action capacity exhausted")
            now = time.time()
            action_id = f"act-{uuid.uuid4().hex[:12]}"
            action = PendingAction(
                action_id=action_id,
                trace_id=trace_id,
                session_id=session_id,
                server_id=self.config.server_id,
                tool_name=tool,
                arguments=arguments,
                upstream_response=upstream_response,
                created_at=now,
                expires_at=now + self.config.confirm_timeout_seconds,
                status="pending",
                reasons=list(reasons or []),
                containment=containment,
            )
            self.pending_actions[action_id] = action
            self._persist_configured_state()
            return action

    @staticmethod
    def _action_resolution_time(action: PendingAction) -> float:
        return action.reviewed_at or action.expires_at

    def _sweep_pending_actions(self) -> None:
        now = time.time()
        remove: list[str] = []
        for action_id, action in self.pending_actions.items():
            if action.status == "pending" and now >= action.expires_at:
                action.status = "expired"
                action.upstream_response = None
            if action.status != "pending":
                resolved_at = self._action_resolution_time(action)
                if now - resolved_at >= self.config.resolved_action_ttl_seconds:
                    remove.append(action_id)
        for action_id in remove:
            del self.pending_actions[action_id]

    def get_pending_actions(self) -> list[dict[str, Any]]:
        with self._lock:
            self._sweep_pending_actions()
            return [act.to_dict(include_payload=False) for act in self.pending_actions.values()]

    def get_action(self, action_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._sweep_pending_actions()
            act = self.pending_actions.get(action_id)
            if not act:
                return None
            return act.to_dict(include_payload=(act.status == "approved"))

    def approve_action(self, action_id: str, reviewer: str = "operator") -> dict[str, Any]:
        with self._lock:
            self._sweep_pending_actions()
            act = self.pending_actions.get(action_id)
            if not act:
                raise KeyError(f"Pending action not found: {action_id}")
            if act.status == "expired":
                raise ValueError(f"Action {action_id} has expired")
            if act.status != "pending":
                raise ValueError(f"Action {action_id} already resolved as {act.status}")
            act.status = "approved"
            act.reviewed_by = reviewer
            act.reviewed_at = time.time()
            event = self._approval_events.get(act.action_id)
            if event:
                event.set()
            self._persist_configured_state()
            return act.to_dict(include_payload=True)

    def deny_action(
        self, action_id: str, reviewer: str = "operator", reason: str = "operator denied"
    ) -> dict[str, Any]:
        with self._lock:
            self._sweep_pending_actions()
            act = self.pending_actions.get(action_id)
            if not act:
                raise KeyError(f"Pending action not found: {action_id}")
            if act.status == "expired":
                raise ValueError(f"Action {action_id} has expired")
            if act.status != "pending":
                raise ValueError(f"Action {action_id} already resolved as {act.status}")
            act.status = "denied"
            act.reviewed_by = reviewer
            act.reviewed_at = time.time()
            act.upstream_response = None
            if reason not in act.reasons:
                act.reasons.append(reason)
            event = self._approval_events.get(act.action_id)
            if event:
                event.set()
            self._persist_configured_state()
            return act.to_dict(include_payload=False)

    def export_state(self) -> dict[str, Any]:
        with self._lock, self.engine.lock:
            engine_state = {
                "profiles": {
                    server: {
                        "trusted_count": p.trusted_count,
                        "quarantined_count": p.quarantined_count,
                        "trust": p.trust,
                        "error_mean": p.error_mean,
                        "error_m2": p.error_m2,
                        "dimension": len(p.scaler.mean)
                        if getattr(p.scaler, "mean", None) is not None
                        else 16,
                        "scaler": {
                            "count": p.scaler.count,
                            "mean": p.scaler.mean.tolist(),
                            "m2": p.scaler.m2.tolist(),
                        },
                        "autoencoder": {
                            "w1": p.autoencoder.w1.tolist(),
                            "b1": p.autoencoder.b1.tolist(),
                            "w2": p.autoencoder.w2.tolist(),
                            "b2": p.autoencoder.b2.tolist(),
                        },
                    }
                    for server, p in self.engine.profiles.items()
                },
                "sessions": list(self.engine.sessions) if hasattr(self.engine, "sessions") else [],
                "identities": {k: list(v) for k, v in self.engine.identities.items()}
                if hasattr(self.engine, "identities")
                else {},
            }
            novelty_state = None
            if self.novelty:
                novelty_state = {
                    "capabilities": {
                        f"{s}:{t}": {
                            "trust": state.trust,
                            "accepted": state.accepted,
                            "restricted": state.restricted,
                        }
                        for (s, t), state in self.novelty.capabilities.states.items()
                    },
                }
            return {
                "schema_version": STATE_SCHEMA_VERSION,
                "server_id": self.config.server_id,
                "exported_at": time.time(),
                "engine": engine_state,
                "novelty": novelty_state,
                "tool_metadata": self.tool_metadata,
                "capability_digest": self.capability_digest,
                "pending_actions": [
                    {
                        **action.to_dict(include_payload=False),
                        "upstream_response_b64": base64.b64encode(
                            action.upstream_response or b""
                        ).decode("ascii"),
                    }
                    for action in self.pending_actions.values()
                ],
            }

    @staticmethod
    def _state_mac(state: dict[str, Any], key: str) -> str:
        unsigned = {name: value for name, value in state.items() if name != "hmac_sha256"}
        canonical = json.dumps(
            unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        return hmac.digest(key.encode("utf-8"), canonical, "sha256").hex()

    @staticmethod
    def _state_mapping(value: Any, name: str) -> dict[str, Any]:
        if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
            raise ValueError(f"{name} must be an object with string keys")
        return value

    @staticmethod
    def _state_count(value: Any, name: str) -> int:
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
        return value

    @staticmethod
    def _state_number(
        value: Any, name: str, *, minimum: float | None = None, maximum: float | None = None
    ) -> float:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
        result = float(value)
        if minimum is not None and result < minimum:
            raise ValueError(f"{name} is below its allowed range")
        if maximum is not None and result > maximum:
            raise ValueError(f"{name} exceeds its allowed range")
        return result

    def _validate_state(self, state: Any) -> dict[str, Any]:
        try:
            validate_json(state, max_depth=64, max_items=1_000_000)
            if not isinstance(state, dict):
                raise ValueError("root must be an object")
            serialized_size = len(json.dumps(state, allow_nan=False).encode("utf-8"))
            if serialized_size > MAX_STATE_FILE_BYTES:
                raise ValueError("state exceeds maximum size")

            key = os.environ.get("MCP_SENTINEL_STATE_KEY")
            signature = state.get("hmac_sha256")
            if key is not None:
                if not key:
                    raise ValueError("MCP_SENTINEL_STATE_KEY must not be empty")
                if not isinstance(signature, str) or len(signature) != 64:
                    raise ValueError("state is unsigned or has an invalid HMAC")
                if not hmac.compare_digest(signature, self._state_mac(state, key)):
                    raise ValueError("state HMAC verification failed")

            required_top = {
                "schema_version",
                "server_id",
                "exported_at",
                "engine",
                "novelty",
                "tool_metadata",
                "capability_digest",
            }
            optional_top = {"hmac_sha256", "pending_actions"}
            if set(state) - (required_top | optional_top) or not required_top.issubset(state):
                raise ValueError("state fields do not match the supported schema")
            if (
                type(state["schema_version"]) is not int
                or state["schema_version"] != STATE_SCHEMA_VERSION
            ):
                raise ValueError(f"unsupported schema version {state.get('schema_version')!r}")
            if not isinstance(state["server_id"], str) or not 0 < len(state["server_id"]) <= 256:
                raise ValueError("server_id must be a nonempty string of at most 256 characters")
            self._state_number(state["exported_at"], "exported_at", minimum=0)

            engine = self._state_mapping(state["engine"], "engine")
            if set(engine) != {"profiles", "sessions", "identities"}:
                raise ValueError("engine fields do not match the supported schema")
            profiles: dict[str, Any] = {}
            for server, raw in self._state_mapping(engine["profiles"], "engine.profiles").items():
                if not 0 < len(server) <= 256:
                    raise ValueError(
                        "profile server id must be nonempty and at most 256 characters"
                    )
                profile = self._state_mapping(raw, f"profile {server}")
                required_profile = {
                    "trusted_count",
                    "quarantined_count",
                    "trust",
                    "error_mean",
                    "error_m2",
                    "dimension",
                    "scaler",
                    "autoencoder",
                }
                if set(profile) != required_profile:
                    raise ValueError(f"profile {server} fields do not match the schema")
                dimension = profile["dimension"]
                if type(dimension) is not int or not 1 <= dimension <= 128:
                    raise ValueError(f"profile {server} has invalid feature dimension")
                prepared = {
                    "trusted_count": self._state_count(profile["trusted_count"], "trusted_count"),
                    "quarantined_count": self._state_count(
                        profile["quarantined_count"], "quarantined_count"
                    ),
                    "trust": self._state_number(profile["trust"], "trust", minimum=0, maximum=1),
                    "error_mean": self._state_number(
                        profile["error_mean"], "error_mean", minimum=0
                    ),
                    "error_m2": self._state_number(profile["error_m2"], "error_m2", minimum=0),
                    "dimension": dimension,
                }
                scaler = self._state_mapping(profile["scaler"], f"profile {server}.scaler")
                if set(scaler) != {"count", "mean", "m2"}:
                    raise ValueError(f"profile {server} scaler fields are invalid")
                prepared["scaler_count"] = self._state_count(scaler["count"], "scaler.count")
                for name in ("mean", "m2"):
                    array = np.asarray(scaler[name])
                    if array.shape != (dimension,) or array.dtype.kind not in "iuf":
                        raise ValueError(
                            f"profile {server} scaler {name} has invalid shape or values"
                        )
                    prepared[f"scaler_{name}"] = array.astype(float)
                autoencoder = self._state_mapping(
                    profile["autoencoder"], f"profile {server}.autoencoder"
                )
                if set(autoencoder) != {"w1", "b1", "w2", "b2"}:
                    raise ValueError(f"profile {server} autoencoder fields are invalid")
                shapes = {
                    "w1": (dimension, 5),
                    "b1": (5,),
                    "w2": (5, dimension),
                    "b2": (dimension,),
                }
                for name, shape in shapes.items():
                    array = np.asarray(autoencoder[name])
                    if array.shape != shape or array.dtype.kind not in "iuf":
                        raise ValueError(
                            f"profile {server} autoencoder {name} has invalid shape or values"
                        )
                    prepared[name] = array.astype(float)
                profiles[server] = prepared

            sessions = engine["sessions"]
            if (
                not isinstance(sessions, list)
                or len(sessions) > 1_000_000
                or any(
                    not isinstance(value, str) or not 0 < len(value) <= 512 for value in sessions
                )
            ):
                raise ValueError("engine.sessions must be a bounded list of nonempty strings")
            if len(profiles) > self.engine.retention.servers:
                raise ValueError("engine.profiles exceeds configured server capacity")
            if len(sessions) > self.engine.retention.sessions or len(set(sessions)) != len(
                sessions
            ):
                raise ValueError("engine.sessions exceeds capacity or contains duplicates")
            identities = self._state_mapping(engine["identities"], "engine.identities")
            if any(
                not isinstance(server, str)
                or not 0 < len(server) <= 256
                or not isinstance(names, list)
                or any(not isinstance(name, str) or not 0 < len(name) <= 256 for name in names)
                or len(names) > self.engine.retention.tools_per_server
                or len(set(names)) != len(names)
                for server, names in identities.items()
            ):
                raise ValueError("engine.identities must map server ids to tool-name lists")
            if len(identities) > self.engine.retention.servers:
                raise ValueError("engine.identities exceeds configured server capacity")

            novelty = state["novelty"]
            if novelty is not None:
                novelty = self._state_mapping(novelty, "novelty")
                if set(novelty) != {"capabilities"}:
                    raise ValueError("novelty fields do not match the schema")
                capabilities = self._state_mapping(novelty["capabilities"], "novelty.capabilities")
                for name, raw_capability in capabilities.items():
                    if len(name.split(":", 1)) != 2 or not all(name.split(":", 1)):
                        raise ValueError("capability keys must contain server and tool names")
                    capability = self._state_mapping(raw_capability, f"capability {name}")
                    if set(capability) != {"trust", "accepted", "restricted"}:
                        raise ValueError(f"capability {name} fields are invalid")
                    self._state_number(
                        capability["trust"], "capability.trust", minimum=0, maximum=1
                    )
                    self._state_count(capability["accepted"], "capability.accepted")
                    self._state_count(capability["restricted"], "capability.restricted")
            metadata = self._state_mapping(state["tool_metadata"], "tool_metadata")
            if any(
                not isinstance(name, str) or not isinstance(value, dict)
                for name, value in metadata.items()
            ):
                raise ValueError("tool_metadata must map names to objects")
            digest = state["capability_digest"]
            if digest is not None and not isinstance(digest, str):
                raise ValueError("capability_digest must be a string or null")
            if state["server_id"] != self.config.server_id:
                raise ValueError("state server_id does not match this gateway")
            pending_actions: list[PendingAction] = []
            raw_actions = state.get("pending_actions", [])
            if (
                not isinstance(raw_actions, list)
                or len(raw_actions) > self.config.max_pending_actions
            ):
                raise ValueError("pending_actions must be a bounded list")
            action_ids: set[str] = set()
            for raw_action in raw_actions:
                action = self._state_mapping(raw_action, "pending action")
                required_action = {
                    "action_id",
                    "trace_id",
                    "session_id",
                    "server_id",
                    "tool_name",
                    "arguments",
                    "created_at",
                    "expires_at",
                    "status",
                    "reasons",
                    "reviewed_by",
                    "reviewed_at",
                    "containment",
                    "upstream_response_b64",
                }
                if set(action) != required_action:
                    raise ValueError("pending action fields do not match schema")
                if action["status"] not in {"pending", "approved", "denied", "expired"}:
                    raise ValueError("pending action has invalid status")
                if not all(
                    isinstance(action[name], str) and 0 < len(action[name]) <= maximum
                    for name, maximum in (
                        ("action_id", 128),
                        ("session_id", 512),
                        ("server_id", 256),
                    )
                ):
                    raise ValueError("pending action identifiers must be nonempty strings")
                if action["action_id"] in action_ids:
                    raise ValueError("pending action IDs must be unique")
                action_ids.add(action["action_id"])
                if action.get("trace_id") is not None and (
                    not isinstance(action["trace_id"], str) or len(action["trace_id"]) > 256
                ):
                    raise ValueError("pending action trace_id is invalid")
                if action.get("tool_name") is not None and (
                    not isinstance(action["tool_name"], str)
                    or not 0 < len(action["tool_name"]) <= 256
                ):
                    raise ValueError("pending action tool_name is invalid")
                if action.get("reviewed_by") is not None and (
                    not isinstance(action["reviewed_by"], str) or len(action["reviewed_by"]) > 128
                ):
                    raise ValueError("pending action reviewer is invalid")
                if action.get("containment") is not None and (
                    not isinstance(action["containment"], str) or len(action["containment"]) > 128
                ):
                    raise ValueError("pending action containment is invalid")
                if action["server_id"] != self.config.server_id:
                    raise ValueError("pending action server_id does not match this gateway")
                if not isinstance(action["arguments"], dict) or not isinstance(
                    action["reasons"], list
                ):
                    raise ValueError("pending action payload is malformed")
                if len(action["reasons"]) > 100 or any(
                    not isinstance(reason, str) or len(reason) > 1024
                    for reason in action["reasons"]
                ):
                    raise ValueError("pending action reasons must be strings")
                created = self._state_number(action["created_at"], "pending created_at", minimum=0)
                expires = self._state_number(action["expires_at"], "pending expires_at", minimum=0)
                reviewed = action["reviewed_at"]
                if reviewed is not None:
                    reviewed = self._state_number(reviewed, "pending reviewed_at", minimum=0)
                if (
                    not isinstance(action["upstream_response_b64"], str)
                    or len(action["upstream_response_b64"]) > 2 * self.config.max_request_bytes
                ):
                    raise ValueError("pending action response is too large")
                try:
                    response = base64.b64decode(action["upstream_response_b64"], validate=True)
                except (ValueError, TypeError) as exc:
                    raise ValueError("pending action response is malformed") from exc
                if len(response) > self.config.max_request_bytes:
                    raise ValueError("pending action response exceeds configured limit")
                pending_actions.append(
                    PendingAction(
                        action["action_id"],
                        action.get("trace_id"),
                        action["session_id"],
                        action["server_id"],
                        action.get("tool_name"),
                        action["arguments"],
                        response or None,
                        created,
                        expires,
                        action["status"],
                        list(action["reasons"]),
                        action.get("reviewed_by"),
                        reviewed,
                        action.get("containment"),
                    )
                )
            return {
                "profiles": profiles,
                "sessions": sessions,
                "identities": identities,
                "novelty": novelty,
                "tool_metadata": metadata,
                "capability_digest": digest,
                "pending_actions": pending_actions,
            }
        except (TypeError, KeyError, OverflowError, RecursionError) as exc:
            raise ValueError(f"Invalid gateway state: {exc}") from exc
        except ValueError as exc:
            raise ValueError(f"Invalid gateway state: {exc}") from exc

    def import_state(self, state: dict[str, Any]) -> None:
        prepared = self._validate_state(state)
        with self._lock, self.engine.lock:
            for server, profile in prepared["profiles"].items():
                model = self.engine._profile(server, profile["dimension"])
                for name in (
                    "trusted_count",
                    "quarantined_count",
                    "trust",
                    "error_mean",
                    "error_m2",
                ):
                    setattr(model, name, profile[name])
                model.scaler.count = profile["scaler_count"]
                model.scaler.mean = profile["scaler_mean"]
                model.scaler.m2 = profile["scaler_m2"]
                for name in ("w1", "b1", "w2", "b2"):
                    setattr(model.autoencoder, name, profile[name])
            self.engine.sessions.update(prepared["sessions"])
            for server, names in prepared["identities"].items():
                self.engine.identities.setdefault(server, set()).update(names)
            if self.novelty and prepared["novelty"]:
                from .novelty import CapabilityState

                for name, capability in prepared["novelty"]["capabilities"].items():
                    server, tool = name.split(":", 1)
                    self.novelty.capabilities.states[(server, tool)] = CapabilityState(
                        trust=float(capability["trust"]),
                        accepted=capability["accepted"],
                        restricted=capability["restricted"],
                    )
            self.tool_metadata = prepared["tool_metadata"]
            self.capability_digest = prepared["capability_digest"]
            now = time.time()
            self.pending_actions = {
                action.action_id: action
                for action in prepared["pending_actions"]
                if action.status != "pending" or action.expires_at > now
            }
            self._sweep_pending_actions()

    def save_state(self, filepath: str | Path) -> None:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        state = self.export_state()
        key = os.environ.get("MCP_SENTINEL_STATE_KEY")
        if key is not None:
            if not key:
                raise ValueError("MCP_SENTINEL_STATE_KEY must not be empty")
            state["hmac_sha256"] = self._state_mac(state, key)
        content = json.dumps(state, indent=2, allow_nan=False).encode("utf-8")
        if len(content) > MAX_STATE_FILE_BYTES:
            raise ValueError("Gateway state exceeds maximum file size")

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
            ) as temporary:
                temp_path = Path(temporary.name)
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temp_path, path)
            temp_path = None
            if os.name != "nt":
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass

    def load_state(self, filepath: str | Path) -> None:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"State file not found: {path}")
        with path.open("rb") as state_file:
            content = state_file.read(MAX_STATE_FILE_BYTES + 1)
        if len(content) > MAX_STATE_FILE_BYTES:
            raise ValueError("Gateway state file exceeds maximum size")
        try:
            data = load_json(content)
        except ValueError as exc:
            raise ValueError(f"Invalid gateway state JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("Invalid gateway state: root must be an object")
        self.import_state(data)

    def _novelty_audit(self, tool: str | None) -> dict[str, Any] | None:
        if self.novelty is None:
            return None
        with self.engine.lock:
            state = self.novelty.capabilities.states.get((self.config.server_id, tool))
            return {
                "capability": tool,
                "capability_trust": state.trust if state else None,
                "memory_disposition": "not-evaluated",
                "config": asdict(self.novelty.config),
            }

    def _read_sse_response(self, response: http.client.HTTPResponse, request_id: Any) -> bytes:
        if request_id is None:
            return b""
        buffer = bytearray()
        total_bytes = 0
        while True:
            raw = bytes(buffer)
            delimiters = ((b"\r\n\r\n", 4), (b"\n\n", 2))
            found = [(raw.find(delimiter), length) for delimiter, length in delimiters]
            found = [(index, size) for index, size in found if index >= 0]
            if found:
                end, delimiter_size = min(found, key=lambda item: item[0])
                event = bytes(buffer[:end])
                del buffer[: end + delimiter_size]
                try:
                    lines = event.decode("utf-8").replace("\r\n", "\n").split("\n")
                    data = []
                    for line in lines:
                        if line.startswith("data:"):
                            value = line[5:]
                            data.append(value[1:] if value.startswith(" ") else value)
                    if not data:
                        continue
                    message = load_json("\n".join(data).encode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    continue
                if isinstance(message, dict) and message.get("id") == request_id:
                    body = json.dumps(message, separators=(",", ":"), allow_nan=False).encode()
                    if len(body) > self.config.max_request_bytes:
                        raise JsonRpcError(-32052, "Upstream SSE response exceeds size limit")
                    return body
                continue

            remaining(self.config.timeout_seconds)
            chunk = response.read1(min(65536, self.config.max_request_bytes - total_bytes + 1))
            if not chunk:
                raise JsonRpcError(
                    -32053, "Upstream SSE ended without a matching JSON-RPC response"
                )
            total_bytes += len(chunk)
            if total_bytes > self.config.max_request_bytes:
                raise JsonRpcError(-32052, "Upstream SSE stream exceeds size limit")
            buffer.extend(chunk)

    def _forward(
        self,
        payload: dict[str, Any] | bytes,
        *,
        upstream_session_id: str | None = None,
        protocol_version: str | None = None,
        request_id: Any = None,
    ) -> tuple[int, bytes, str, dict[str, str]]:
        with budget(self.config.timeout_seconds):
            if isinstance(payload, bytes):
                try:
                    request_payload = load_json(payload)
                except ValueError as exc:
                    raise JsonRpcError(-32600, "Invalid JSON-RPC request") from exc
            else:
                request_payload = payload
            if request_id is None:
                request_id = request_payload.get("id")
            if self.in_process_forwarder is not None:
                status, body, content_type = self.in_process_forwarder(request_payload)
                return status, body, content_type, {}
            return self._forward_with_budget(
                request_payload,
                upstream_session_id=upstream_session_id,
                protocol_version=protocol_version,
                request_id=request_id,
            )

    def _forward_with_budget(
        self,
        payload: dict[str, Any],
        *,
        upstream_session_id: str | None = None,
        protocol_version: str | None = None,
        request_id: Any = None,
    ) -> tuple[int, bytes, str, dict[str, str]]:
        body = json.dumps(payload, separators=(",", ":")).encode()
        target = urlsplit(self.config.upstream_url)
        connection_type = (
            http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
        )
        if target.hostname is None:
            raise JsonRpcError(-32600, "Invalid upstream host")
        connection = connection_type(
            target.hostname, target.port, timeout=remaining(self.config.timeout_seconds)
        )
        request_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if upstream_session_id is not None:
            request_headers["Mcp-Session-Id"] = upstream_session_id
        if protocol_version is not None:
            request_headers["MCP-Protocol-Version"] = protocol_version
        for header_name, env_name in self.config.upstream_headers:
            value = os.environ.get(env_name)
            if (
                value is None
                or not value.isascii()
                or len(value) > 8192
                or any(ord(char) < 32 and char != "\t" for char in value)
                or "\r" in value
                or "\n" in value
            ):
                raise JsonRpcError(-32056, "Configured upstream credential is unavailable")
            request_headers[header_name] = value
        try:
            connection.connect()
            remaining(self.config.timeout_seconds)
            with socket_deadline(connection.sock, self.config.timeout_seconds):
                path = target.path or "/"
                if target.query:
                    path += "?" + target.query
                connection.request(
                    "POST",
                    path,
                    body=body,
                    headers=request_headers,
                )
                response = connection.getresponse()
                content_type = response.headers.get("Content-Type", "")
                response_headers: dict[str, str] = {}
                for header_name in ("Mcp-Session-Id", "MCP-Protocol-Version"):
                    values = response.headers.get_all(header_name, [])
                    if len(values) > 1 or any(
                        not _safe_protocol_header(value, 256) for value in values
                    ):
                        raise JsonRpcError(-32053, "Malformed upstream session headers")
                    if values:
                        response_headers[header_name] = values[0]
                if content_type.lower().split(";", 1)[0].strip() == "text/event-stream":
                    data = self._read_sse_response(response, request_id)
                    content_type = "application/json"
                else:
                    data = response.read(self.config.max_request_bytes + 1)
                if len(data) > self.config.max_request_bytes:
                    raise JsonRpcError(-32052, "Upstream response exceeds size limit")
                remaining(self.config.timeout_seconds)
                return response.status, data, content_type, response_headers
        except (OSError, http.client.HTTPException) as exc:
            raise JsonRpcError(-32050, "MCP upstream unavailable") from exc
        finally:
            connection.close()

    def _execute_attestation(self, challenge: dict[str, Any]) -> bool:
        payload = {
            "jsonrpc": "2.0",
            "id": f"sentinel-{challenge['challenge_id']}",
            "method": "sentinel/attest",
            "params": {"nonce": challenge["nonce"]},
        }
        try:
            status, body, _, _ = self._forward(payload)
            if status != 200 or len(body) > self.config.max_request_bytes:
                return False
            response = validate_response(load_json(body), payload["id"])
            result = response.get("result", {})
            return bool(
                self.engine.attestation.verify(
                    challenge["challenge_id"],
                    result.get("capability_digest", ""),
                    result.get("echo", ""),
                    server_id=self.config.server_id,
                )
            )
        except (ValueError, AttributeError):
            return False
        finally:
            self.engine.attestation.discard(challenge["challenge_id"])

    def _preflight_block(self, tool: str, arguments: dict[str, Any], intent: str) -> str | None:
        if tool not in self.config.allowed_tools:
            return "tool is not in the operator-configured allowlist"
        metadata = self.tool_metadata.get(tool, {})
        annotations = metadata.get("annotations", {}) if isinstance(metadata, dict) else {}
        destructive = bool(annotations.get("destructiveHint"))
        intent_risk = intent_mismatch(intent, tool, arguments)
        profile = self.engine.profiles.get(self.config.server_id)
        if self.novelty and self.novelty.config.capability_trust:
            state = self.novelty.capabilities.states.get((self.config.server_id, tool))
            if state and state.trust < 0.15:
                return "capability trust below isolation threshold"
        elif profile and profile.trust < 0.15:
            return "server trust below isolation threshold"
        if destructive and intent_risk >= 0.70:
            return "destructive tool conflicts with stated intent"
        return None

    def _recovery_event(
        self,
        tool: str,
        arguments: dict[str, Any],
        intent: str,
        identity: str = "review",
    ) -> Interaction:
        if self.novelty is None or not self.novelty.config.capability_trust:
            raise ValueError("capability novelty engine required")
        annotations = self.tool_metadata.get(tool, {}).get("annotations", {})
        if annotations.get("readOnlyHint") is not True or annotations.get("destructiveHint", False):
            raise ValueError("recovery probe must be a reviewed read-only tool")
        if not isinstance(identity, str) or not 0 < len(identity) <= 96:
            raise ValueError("independent recovery identity required")
        event = Interaction.from_dict(
            dict(
                server_id=self.config.server_id,
                tool_name=tool,
                arguments=arguments,
                response={},
                latency_ms=0,
                user_intent=intent,
                session_id="recovery:" + identity,
                capability_digest=self.capability_digest,
            )
        )
        if intent_mismatch(intent, tool, arguments) >= 0.70:
            raise ValueError("recovery probe conflicts with intent")
        return event

    def begin_recovery(
        self,
        tool: str,
        arguments: dict[str, Any],
        intent: str,
        *,
        reviewer: str,
        evidence_ref: str,
        ttl: float = 300,
    ) -> None:
        """Operator-only embedding API; deliberately has no HTTP/client-header route."""
        novelty = self.novelty
        if novelty is None:
            raise ValueError("capability novelty engine required")
        with self.engine.lock:
            event = self._recovery_event(tool, arguments, intent)
            novelty.begin_recovery(event, reviewer=reviewer, evidence_ref=evidence_ref, ttl=ttl)

    @request_budget
    def probe_recovery(
        self,
        tool: str,
        arguments: dict[str, Any],
        intent: str,
        *,
        independent_identity: str,
    ) -> dict[str, Any]:
        """Run an authorized diagnostic probe; its response never goes to a caller."""
        novelty = self.novelty
        if novelty is None:
            raise ValueError("capability novelty engine required")
        with timed_lock(self.engine.lock):
            event = self._recovery_event(tool, arguments, intent, independent_identity)
            if novelty.recovery_approvals.get(novelty.recovery_key(event)) is None:
                raise ValueError("active recovery review required before dispatch")
            self.engine.admit(event.server_id, event.session_id, event.tool_name)
            payload = {
                "jsonrpc": "2.0",
                "id": "sentinel-recovery",
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            }
            started = time.perf_counter()
            try:
                status, body, _, _ = self._forward(payload)
                if status != 200 or len(body) > self.config.max_request_bytes:
                    raise ValueError("recovery upstream failure")
                response = validate_response(load_json(body), payload["id"])
                result = response.get("result")
                if not isinstance(result, dict) or type(result.get("isError", False)) is not bool:
                    raise ValueError("invalid recovery response")
                event.response = result
                event.success = not result.get("isError", False)
                event.latency_ms = (
                    (time.perf_counter() - started) * 1000
                    if self.telemetry_latency_override_ms is None
                    else self.telemetry_latency_override_ms
                )
                challenge = self.engine.attestation.issue(self.config.server_id)
                attested = bool(challenge and self._execute_attestation(challenge.to_dict()))
                remaining()
                verdict = novelty.evaluate_recovery(
                    event, independent_session=independent_identity, attested=attested
                )
            except Exception:
                novelty.invalidate_reviews(event, "recovery transport or analysis failure")
                raise
            with self._lock:
                self._append_audit(
                    GatewayAudit(
                        time.time(),
                        event.session_id,
                        event.server_id,
                        "sentinel/recovery-probe",
                        payload["id"],
                        tool,
                        fingerprint(arguments),
                        fingerprint(result),
                        event.latency_ms,
                        True,
                        verdict.action.value,
                        trace_id=verdict.trace_id,
                        reasons=verdict.reasons,
                        provenance=verdict.provenance,
                        attestation_verified=attested,
                    )
                )
            return cast(dict[str, Any], verdict.to_dict())

    @request_budget
    def handle(self, body: bytes, headers: dict[str, str]) -> tuple[int, bytes, dict[str, str]]:
        if not 0 < len(body) <= self.config.max_request_bytes:
            raise JsonRpcError(-32600, "Request size is invalid")
        request = parse_request(body)
        if request.method not in SUPPORTED_METHODS:
            raise JsonRpcError(-32601, "Method not supported by this gateway", request.request_id)
        if (
            request.method in OPERATOR_GATED_METHODS
            and request.method not in self.config.allowed_methods
        ):
            raise JsonRpcError(
                -32601, "Method is not enabled by the gateway operator", request.request_id
            )
        if request.notification != (request.method == "notifications/initialized"):
            raise JsonRpcError(-32600, "Invalid request/notification form", request.request_id)
        session_id = headers.get("x-sentinel-session", "default")
        intent = headers.get("x-sentinel-intent", "unspecified intent")
        if (
            not isinstance(session_id, str)
            or not 0 < len(session_id) <= 128
            or not isinstance(intent, str)
            or not 0 < len(intent) <= 2048
        ):
            raise JsonRpcError(-32600, "Invalid session or intent header", request.request_id)
        downstream_mcp_session = headers.get("mcp-session-id")
        protocol_version = headers.get("mcp-protocol-version")
        if downstream_mcp_session is not None and (
            not _safe_protocol_header(downstream_mcp_session, 256)
        ):
            raise JsonRpcError(-32600, "Invalid MCP session id", request.request_id)
        if protocol_version is not None and (not _safe_protocol_header(protocol_version, 128)):
            raise JsonRpcError(-32600, "Invalid MCP protocol version", request.request_id)
        owner = headers.get("x-sentinel-authenticated-client", session_id)
        upstream_session_id = None
        if request.method == "initialize":
            if downstream_mcp_session is not None:
                raise JsonRpcError(
                    -32600, "Initialize must not include an MCP session id", request.request_id
                )
        elif downstream_mcp_session is not None:
            with self._session_lock:
                self._sweep_upstream_sessions()
                binding = self._upstream_sessions.get(downstream_mcp_session)
                if binding is not None:
                    binding.last_used = time.monotonic()
            if binding is None or binding.owner != owner:
                with self._lock:
                    self._append_audit(
                        GatewayAudit(
                            time.time(),
                            session_id,
                            self.config.server_id,
                            request.method,
                            request.request_id,
                            None,
                            fingerprint(request.params),
                            None,
                            0.0,
                            False,
                            Action.ISOLATE.value,
                            reasons=["unknown MCP session"],
                        )
                    )
                return 404, b'{"error":"unknown MCP session"}', {"Content-Type": "application/json"}
            upstream_session_id = binding.upstream_session_id
            protocol_version = protocol_version or binding.protocol_version
        elif self._uses_upstream_sessions:
            raise JsonRpcError(-32600, "MCP session id is required", request.request_id)
        started = time.perf_counter()
        tool = request.params.get("name") if request.method == "tools/call" else None
        arguments = (
            request.params.get("arguments", {})
            if request.method == "tools/call"
            else request.params
        )
        if not isinstance(arguments, dict) or (
            request.method == "tools/call" and (not isinstance(tool, str) or not tool)
        ):
            raise JsonRpcError(-32602, "Invalid params", request.request_id)
        block_reason = None
        policy_requires_approval = False
        if tool:
            with self._engine_lock():
                block_reason = self._preflight_block(tool, arguments, intent)
                if not block_reason:
                    try:
                        self.engine.admit(self.config.server_id, session_id, tool)
                    except StateCapacityError as exc:
                        block_reason = str(exc)
            if self.policy is not None and not block_reason:
                policy_reasons, policy_requires_approval = self.policy.evaluate(
                    tool, arguments, owner
                )
                if policy_reasons:
                    block_reason = "; ".join(policy_reasons)
        provenance_evidence = None
        if tool and not block_reason:
            claim_id = headers.get("x-sentinel-provenance")
            if claim_id is None and self.config.require_provenance:
                block_reason = "provenance required"
            elif claim_id is not None:
                # Atomic single use before dispatch. Even an upstream timeout
                # consumes authorization: execution may already have occurred.
                with self._engine_lock():
                    result = self.engine.provenance.validate(
                        claim_id,
                        intent=intent,
                        session_id=session_id,
                        server_id=self.config.server_id,
                        tool_name=tool,
                        arguments=arguments,
                        preflight=True,
                    )
                provenance_evidence = {
                    "claim_id": claim_id,
                    "valid": result.valid,
                    "reason": result.reason,
                    "claim": asdict(result.claim) if result.claim else None,
                }
                if not result.valid:
                    block_reason = result.reason
        if block_reason:
            record = GatewayAudit(
                time.time(),
                session_id,
                self.config.server_id,
                request.method,
                request.request_id,
                tool,
                fingerprint(arguments),
                None,
                0.0,
                False,
                Action.ISOLATE.value,
                anomaly_score=0.82,
                reasons=[block_reason],
                provenance=provenance_evidence,
                novelty=self._novelty_audit(tool),
            )
            with self._lock:
                self._append_audit(record)
            error = JsonRpcError(-32041, "Sentinel blocked request", request.request_id).response(
                {"reason": block_reason}
            )
            return 200, json.dumps(error).encode(), {"X-Sentinel-Decision": "isolate"}

        if tool and policy_requires_approval:
            try:
                approval_status = self._await_preexecution_approval(
                    session_id, tool, arguments, None
                )
            except StateCapacityError:
                approval_status = "capacity-exhausted"
            if approval_status != "approved":
                reason = "pre-execution approval was not granted"
                record = GatewayAudit(
                    time.time(),
                    session_id,
                    self.config.server_id,
                    request.method,
                    request.request_id,
                    tool,
                    fingerprint(arguments),
                    None,
                    0.0,
                    False,
                    Action.ISOLATE.value,
                    reasons=[reason],
                )
                with self._lock:
                    self._append_audit(record)
                error = JsonRpcError(
                    -32043, "Sentinel isolated request", request.request_id
                ).response({"decision": "isolate", "reason": reason})
                return 200, json.dumps(error).encode(), {"X-Sentinel-Decision": "isolate"}

        try:
            status, response_body, content_type, upstream_headers = self._forward(
                request.raw,
                upstream_session_id=upstream_session_id,
                protocol_version=protocol_version,
                request_id=request.request_id,
            )
        except (JsonRpcError, TimeoutError, OSError):
            with self._rate_lock:
                self.metrics["upstream_errors"] += 1
            # Dispatch was attempted; an upstream side effect may have occurred.
            # Preflight authorization remains consumed, even when no reply arrives.
            record = GatewayAudit(
                time.time(),
                session_id,
                self.config.server_id,
                request.method,
                request.request_id,
                tool,
                fingerprint(arguments),
                None,
                (time.perf_counter() - started) * 1000,
                True,
                "error",
                reasons=["upstream dispatch failed"],
                provenance=provenance_evidence,
                novelty=self._novelty_audit(tool),
            )
            with self._lock:
                self._append_audit(record)
            raise
        latency_ms = (time.perf_counter() - started) * 1000
        if len(response_body) > self.config.max_request_bytes:
            raise JsonRpcError(-32052, "Upstream response exceeds size limit", request.request_id)
        if request.notification:
            with self._lock:
                self._append_audit(
                    GatewayAudit(
                        time.time(),
                        session_id,
                        self.config.server_id,
                        request.method,
                        None,
                        tool,
                        fingerprint(arguments),
                        None,
                        latency_ms,
                        True,
                        "forward",
                    )
                )
            return status, response_body, {"Content-Type": content_type or "application/json"}
        try:
            upstream = validate_response(load_json(response_body), request.request_id)
        except JsonRpcError:
            raise
        except ValueError as exc:
            raise JsonRpcError(
                -32053, "Malformed upstream JSON-RPC response", request.request_id
            ) from exc

        upstream_session_header = upstream_headers.pop("Mcp-Session-Id", None)
        response_protocol_version = upstream_headers.get("MCP-Protocol-Version")
        if request.method == "initialize" and response_protocol_version is None:
            initialize_result = upstream.get("result")
            if isinstance(initialize_result, dict):
                negotiated = initialize_result.get("protocolVersion")
                if negotiated is not None:
                    if not isinstance(negotiated, str) or not _safe_protocol_header(
                        negotiated, 128
                    ):
                        raise JsonRpcError(
                            -32053,
                            "Malformed upstream MCP protocol version",
                            request.request_id,
                        )
                    response_protocol_version = negotiated
        downstream_session_header = None
        if request.method == "initialize" and upstream_session_header is not None:
            if not _safe_protocol_header(upstream_session_header, 256):
                raise JsonRpcError(-32053, "Malformed upstream MCP session id", request.request_id)
            with self._session_lock:
                self._sweep_upstream_sessions()
                if len(self._upstream_sessions) >= self.engine.retention.sessions or any(
                    item.upstream_session_id == upstream_session_header
                    for item in self._upstream_sessions.values()
                ):
                    return (
                        503,
                        b'{"error":"MCP session capacity unavailable"}',
                        {"Content-Type": "application/json"},
                    )
                downstream_session_header = secrets.token_urlsafe(32)
                self._upstream_sessions[downstream_session_header] = UpstreamSessionBinding(
                    owner=owner,
                    upstream_session_id=upstream_session_header,
                    protocol_version=response_protocol_version or protocol_version,
                )
                self._uses_upstream_sessions = True

        if request.method == "tools/list" and "result" in upstream:
            tools = (
                upstream["result"].get("tools") if isinstance(upstream["result"], dict) else None
            )
            metadata = {}
            if not isinstance(tools, list):
                raise JsonRpcError(-32053, "Malformed tool list", request.request_id)
            for item in tools:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("name"), str)
                    or not item["name"]
                    or item["name"] in metadata
                    or not isinstance(item.get("annotations", {}), dict)
                ):
                    raise JsonRpcError(-32053, "Malformed tool metadata", request.request_id)
                annotations = item.get("annotations", {})
                if any(
                    type(annotations[key]) is not bool
                    for key in (
                        "destructiveHint",
                        "readOnlyHint",
                        "idempotentHint",
                        "openWorldHint",
                    )
                    if key in annotations
                ):
                    raise JsonRpcError(-32053, "Malformed tool annotations", request.request_id)
                metadata[item["name"]] = item
            with self._lock:
                self.tool_metadata = metadata
                self.capability_digest = fingerprint(tools)
            # Do not advertise tools this gateway will deny at call time.
            upstream["result"]["tools"] = [
                item for item in tools if item["name"] in self.config.allowed_tools
            ]
            response_body = json.dumps(upstream, separators=(",", ":")).encode()

        verdict = None
        analysis_latency_ms = None
        attestation_verified = None
        if request.method == "tools/call":
            if "result" in upstream and (
                not isinstance(upstream["result"], dict)
                or type(upstream["result"].get("isError", False)) is not bool
            ):
                raise JsonRpcError(-32053, "Malformed tool result", request.request_id)
            success = "result" in upstream and not (
                isinstance(upstream["result"], dict) and upstream["result"].get("isError", False)
            )
            response_value = upstream.get("result", upstream.get("error"))
            metadata = self.tool_metadata.get(tool, {}) if isinstance(tool, str) else {}
            annotations = metadata.get("annotations", {}) if isinstance(metadata, dict) else {}
            event = Interaction(
                self.config.server_id,
                tool,
                arguments,
                response_value,
                self.telemetry_latency_override_ms
                if self.telemetry_latency_override_ms is not None
                else latency_ms,
                intent,
                success,
                bool(annotations.get("destructiveHint"))
                and not bool(annotations.get("readOnlyHint")),
                session_id,
                time.time(),
                self.capability_digest,
                headers.get("x-sentinel-challenge-id"),
                headers.get("x-sentinel-attestation-echo"),
                # Already consumed by trusted preflight; do not validate twice.
                provenance_id=None,
            )
            try:
                analysis_started = time.perf_counter()
                with self._engine_lock():
                    if self.novelty:
                        identity = self.session_identity(headers) if self.session_identity else None
                        if self.learning_enabled and identity:
                            challenge = self.engine.attestation.issue(self.config.server_id)
                            if challenge:
                                attestation_verified = self._execute_attestation(
                                    challenge.to_dict()
                                )
                        extended = self.novelty.evaluate(
                            event,
                            learn=self.learning_enabled,
                            trusted_enrollment=self.trusted_enrollment,
                            attested=attestation_verified is True,
                            independent_session=identity or "",
                        )
                        verdict = extended.as_verdict()
                        novelty_claim = self.novelty.provenance.trace(extended.claim_id)
                    else:
                        verdict = self.engine.evaluate(
                            event,
                            learn=self.learning_enabled,
                            trusted_enrollment=self.trusted_enrollment,
                        )
                    if provenance_evidence is not None:
                        verdict.provenance = {**(verdict.provenance or {}), **provenance_evidence}
                analysis_latency_ms = (time.perf_counter() - analysis_started) * 1000
            except Exception as exc:
                if self.config.fail_closed:
                    raise JsonRpcError(
                        -32055, "Sentinel analysis failure", request.request_id
                    ) from exc

        if verdict and verdict.challenge:
            attestation_verified = self._execute_attestation(verdict.challenge)
        remaining()
        record = GatewayAudit(
            time.time(),
            session_id,
            self.config.server_id,
            request.method,
            request.request_id,
            tool,
            fingerprint(arguments),
            fingerprint(upstream),
            latency_ms,
            True,
            verdict.action.value
            if verdict
            else ("forward-unscored" if request.method in OPERATOR_GATED_METHODS else "forward"),
            verdict.trace_id if verdict else None,
            verdict.anomaly_score if verdict else None,
            verdict.uncertainty if verdict else None,
            verdict.components.get("intent") if verdict else None,
            verdict.components.get("causal") if verdict else None,
            verdict.components.get("attestation") if verdict else None,
            verdict.trust_score if verdict else None,
            verdict.reasons if verdict else None,
            verdict.challenge if verdict else None,
            attestation_verified,
            analysis_latency_ms,
            verdict.provenance if verdict else None,
        )
        if verdict and self.novelty:
            record.novelty = {
                **(self._novelty_audit(tool) or {}),
                "claim_id": extended.claim_id,
                "claim": novelty_claim,
                "capability_trust": extended.capability_trust,
                "memory_disposition": extended.memory_disposition,
                "promoted_events": extended.promoted_events,
                "counterfactual_risk": extended.counterfactual_risk,
            }
        with self._lock:
            self._append_audit(record)
        response_headers = {
            "Content-Type": content_type or "application/json",
            "X-Sentinel-Decision": (
                "forward-unscored" if request.method in OPERATOR_GATED_METHODS else record.decision
            ),
        }
        if downstream_session_header is not None:
            response_headers["Mcp-Session-Id"] = downstream_session_header
        if response_protocol_version is not None:
            response_headers["MCP-Protocol-Version"] = response_protocol_version
        if verdict and verdict.trace_id:
            response_headers["X-Sentinel-Trace"] = verdict.trace_id
        if verdict and verdict.action in BLOCKING_ACTIONS:
            if verdict.action == Action.CONFIRM:
                try:
                    action = self.create_pending_action(
                        verdict.trace_id,
                        session_id,
                        tool,
                        arguments,
                        response_body,
                        verdict.reasons,
                    )
                except StateCapacityError:
                    reason = "pending action capacity exhausted; response withheld"
                    record.decision = Action.ISOLATE.value
                    record.reasons = [*(record.reasons or []), reason]
                    response_headers["X-Sentinel-Decision"] = Action.ISOLATE.value
                    blocked = JsonRpcError(
                        -32043, "Sentinel isolated request", request.request_id
                    ).response(
                        {
                            "decision": Action.ISOLATE.value,
                            "trace_id": verdict.trace_id,
                            "reasons": record.reasons,
                        }
                    )
                    return 200, json.dumps(blocked).encode(), response_headers
                blocked = JsonRpcError(
                    -32042, "Sentinel confirmation required", request.request_id
                ).response(
                    {
                        "decision": "confirm",
                        "action_id": action.action_id,
                        "trace_id": verdict.trace_id,
                        "reasons": verdict.reasons,
                        "challenge": verdict.challenge,
                        "expires_at": action.expires_at,
                    }
                )
                return 200, json.dumps(blocked).encode(), response_headers
            elif verdict.action == Action.SANDBOX:
                record.decision = "contained-withheld"
                response_headers["X-Sentinel-Decision"] = "contained-withheld"
                response_headers["X-Sentinel-Containment"] = "response-withheld"
                # Deprecated compatibility aliases retained for one release.
                response_headers["X-Sentinel-Sandbox"] = "true"
                response_headers["X-Sentinel-Sandbox-Containment"] = "isolated"
                blocked = JsonRpcError(
                    -32042, "Sentinel contained and withheld the response", request.request_id
                ).response(
                    {
                        "decision": "contained-withheld",
                        "containment": "response-withheld",
                        "trace_id": verdict.trace_id,
                        "reasons": verdict.reasons,
                        "challenge": verdict.challenge,
                        # Deprecated compatibility alias retained for one release.
                        "sandbox_contained": True,
                    }
                )
                return 200, json.dumps(blocked).encode(), response_headers
            else:
                blocked = JsonRpcError(
                    -32042, "Sentinel withheld MCP response", request.request_id
                ).response(
                    {
                        "decision": "isolate",
                        "trace_id": verdict.trace_id,
                        "reasons": verdict.reasons,
                        "challenge": verdict.challenge,
                    }
                )
                return 200, json.dumps(blocked).encode(), response_headers
        return status, response_body, response_headers


def make_gateway_handler(gateway: SentinelGateway) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _trusted_host_origin(self) -> bool:
            if len(self.headers.get_all("Host", [])) != 1:
                return False
            host_header = self.headers.get("Host", "")
            address = self.server.server_address
            if not isinstance(address, tuple):
                return False
            bound_host, bound_port = address[:2]
            local_hosts = {f"{bound_host}:{bound_port}"}
            if bound_host in ("127.0.0.1", "::1", "localhost"):
                local_hosts.update(
                    (f"127.0.0.1:{bound_port}", f"localhost:{bound_port}", f"[::1]:{bound_port}")
                )
            allowed_hosts = set(gateway.config.allowed_hosts) or local_hosts
            if host_header not in allowed_hosts:
                return False
            origin = self.headers.get("Origin")
            if len(self.headers.get_all("Origin", [])) > 1:
                return False
            if origin is None:
                return True
            if origin in gateway.config.allowed_origins:
                return True
            scheme = (
                self.headers.get(
                    "X-Forwarded-Proto", "https" if gateway.config.tls_cert else "http"
                )
                if gateway.config.trust_proxy_headers
                else ("https" if gateway.config.tls_cert else "http")
            )
            if (
                gateway.config.trust_proxy_headers
                and len(self.headers.get_all("X-Forwarded-Proto", [])) > 1
            ):
                return False
            return origin == f"{scheme}://{host_header}" and host_header in local_hosts

        def _drain_body(self) -> None:
            if getattr(self, "_body_read", False):
                return
            self._body_read = True
            try:
                lengths = self.headers.get_all("Content-Length", [])
                if lengths and lengths[0].strip().isdigit():
                    length = int(lengths[0].strip())
                    if 0 < length <= gateway.config.max_request_bytes:
                        self.rfile.read(length)
                    else:
                        self.close_connection = True
            except Exception:
                self.close_connection = True

        def _send(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
            self._drain_body()
            self.send_response(status)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            if self.close_connection:
                self.send_header("Connection", "close")
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _authenticate(self) -> bool:
            token = gateway.config.auth_token
            if not token:
                self._send(
                    401,
                    json.dumps(
                        {
                            "error": "unauthorized",
                            "reason": "No gateway auth_token configured (fail-closed default)",
                        }
                    ).encode(),
                    {"Content-Type": "application/json"},
                )
                return False
            auth_values = self.headers.get_all("Authorization", [])
            auth_header = auth_values[0] if len(auth_values) == 1 else ""
            if not auth_header.startswith("Bearer "):
                limited = self._record_auth_failure()
                self._send(
                    429 if limited else 401,
                    json.dumps(
                        {"error": "unauthorized", "reason": "Missing Bearer authorization header"}
                    ).encode(),
                    {
                        "Content-Type": "application/json",
                        **({"Retry-After": "60"} if limited else {}),
                    },
                )
                return False
            provided = auth_header[7:].strip()
            if not hmac.compare_digest(provided.encode("utf-8"), token.encode("utf-8")):
                limited = self._record_auth_failure()
                self._send(
                    429 if limited else 401,
                    json.dumps(
                        {"error": "unauthorized", "reason": "Invalid bearer token"}
                    ).encode(),
                    {
                        "Content-Type": "application/json",
                        **({"Retry-After": "60"} if limited else {}),
                    },
                )
                return False
            return True

        def _record_auth_failure(self) -> bool:
            peer = (
                str(self.client_address[0]) if isinstance(self.client_address, tuple) else "unknown"
            )
            now = time.monotonic()
            with gateway._auth_lock:
                failures = [
                    stamp for stamp in gateway.auth_failures.get(peer, []) if now - stamp < 60
                ]
                failures.append(now)
                if len(gateway.auth_failures) >= 10_000 and peer not in gateway.auth_failures:
                    gateway.auth_failures = {
                        name: stamps
                        for name, stamps in gateway.auth_failures.items()
                        if stamps and now - stamps[-1] < 60
                    }
                    if len(gateway.auth_failures) >= 10_000:
                        return True
                gateway.auth_failures[peer] = failures
            gateway.logger.warning(
                json.dumps(
                    {"event": "authentication_failure", "peer": peer, "count": len(failures)}
                )
            )
            gateway._append_audit(
                GatewayAudit(
                    timestamp=time.time(),
                    session_id=peer[:128],
                    server_id=gateway.config.server_id,
                    method="authentication_failure",
                    request_id=None,
                    tool_name=None,
                    parameter_fingerprint=fingerprint({}),
                    response_fingerprint=None,
                    latency_ms=0.0,
                    forwarded=False,
                    decision="error",
                    reasons=["authentication failure"],
                )
            )
            return len(failures) > 10

        def _authenticate_client(self) -> bool:
            token = gateway.config.client_auth_token
            if not token and not gateway.client_credentials:
                self._send(
                    503,
                    json.dumps(
                        {
                            "error": "service_unavailable",
                            "reason": "Client authentication is not configured",
                        }
                    ).encode(),
                    {"Content-Type": "application/json"},
                )
                return False
            auth_values = self.headers.get_all("Authorization", [])
            auth_header = auth_values[0] if len(auth_values) == 1 else ""
            if not auth_header.startswith("Bearer "):
                limited = self._record_auth_failure()
                self._send(
                    429 if limited else 401,
                    json.dumps(
                        {"error": "unauthorized", "reason": "Missing Bearer client credential"}
                    ).encode(),
                    {
                        "Content-Type": "application/json",
                        "WWW-Authenticate": "Bearer",
                        **({"Retry-After": "60"} if limited else {}),
                    },
                )
                return False
            provided = auth_header[7:].strip()
            client_id = "single-client"
            valid = False
            if gateway.client_credentials:
                digest = hashlib.sha256(provided.encode("utf-8")).hexdigest()
                for token_hash, mapped_client in gateway.client_credentials.items():
                    matched = hmac.compare_digest(digest, token_hash)
                    if matched:
                        valid = True
                        client_id = mapped_client
            elif token:
                valid = hmac.compare_digest(provided.encode("utf-8"), token.encode("utf-8"))
            if not valid:
                if self._record_auth_failure():
                    self._send(
                        429,
                        b'{"error":"authentication temporarily limited"}',
                        {"Content-Type": "application/json", "Retry-After": "60"},
                    )
                    return False
                self._send(
                    401,
                    json.dumps(
                        {"error": "unauthorized", "reason": "Invalid client credential"}
                    ).encode(),
                    {"Content-Type": "application/json", "WWW-Authenticate": "Bearer"},
                )
                return False
            self._authenticated_client_id = client_id
            return True

        def do_GET(self) -> None:  # noqa: N802
            if not self._trusted_host_origin():
                self._send(
                    403,
                    json.dumps(
                        {"error": "forbidden", "reason": "Untrusted Host or Origin"}
                    ).encode(),
                    {"Content-Type": "application/json"},
                )
                return
            if self.path in ("/livez", "/health"):
                self._send(
                    200,
                    json.dumps({"status": "ok"}).encode(),
                    {"Content-Type": "application/json"},
                )
            elif self.path == "/readyz":
                target = urlsplit(gateway.config.upstream_url)
                ready = gateway.baseline_loaded and target.hostname is not None
                if ready and target.hostname is not None:
                    try:
                        connection_type = (
                            http.client.HTTPSConnection
                            if target.scheme == "https"
                            else http.client.HTTPConnection
                        )
                        probe = connection_type(
                            target.hostname,
                            target.port,
                            timeout=min(2.0, gateway.config.timeout_seconds),
                        )
                        probe.connect()
                        probe.close()
                    except OSError:
                        ready = False
                self._send(
                    200 if ready else 503,
                    json.dumps({"status": "ready" if ready else "not_ready"}).encode(),
                    {"Content-Type": "application/json"},
                )
            elif self.path == "/metrics":
                if not self._authenticate():
                    return
                with gateway._rate_lock:
                    decisions = dict(gateway.metrics["requests"])
                    latency_count = gateway.metrics["latency_count"]
                    latency_sum = gateway.metrics["latency_sum_ms"]
                    latency_buckets = dict(gateway.metrics["latency_buckets"])
                    errors = gateway.metrics["upstream_errors"]
                    lock_wait = gateway.metrics["lock_wait_ms"]
                lines = [
                    "# HELP mcp_sentinel_requests_total Requests by gateway decision.",
                    "# TYPE mcp_sentinel_requests_total counter",
                ]
                lines.extend(
                    f'mcp_sentinel_requests_total{{decision="{name}"}} {count}'
                    for name, count in sorted(decisions.items())
                )
                lines.extend(
                    (
                        "# TYPE mcp_sentinel_upstream_errors_total counter",
                        f"mcp_sentinel_upstream_errors_total {errors}",
                        "# TYPE mcp_sentinel_pending_actions gauge",
                        f"mcp_sentinel_pending_actions {len(gateway.get_pending_actions())}",
                        "# TYPE mcp_sentinel_lock_wait_milliseconds_total counter",
                        f"mcp_sentinel_lock_wait_milliseconds_total {lock_wait:.3f}",
                    )
                )
                lines.extend(
                    (
                        "# TYPE mcp_sentinel_request_latency_milliseconds histogram",
                        f"mcp_sentinel_request_latency_milliseconds_count {latency_count}",
                        f"mcp_sentinel_request_latency_milliseconds_sum {latency_sum:.3f}",
                    )
                )
                for bound in (10, 50, 100, 500, 1000, float("inf")):
                    label = "+Inf" if math.isinf(bound) else str(int(bound))
                    lines.append(
                        f'mcp_sentinel_request_latency_milliseconds_bucket{{le="{label}"}} '
                        f"{latency_buckets['+Inf' if label == '+Inf' else int(label)]}"
                    )
                self._send(
                    200,
                    ("\n".join(lines) + "\n").encode(),
                    {"Content-Type": "text/plain; version=0.0.4; charset=utf-8"},
                )
            elif self.path == "/v1/audit":
                if not self._authenticate():
                    return
                with gateway._lock:
                    body = json.dumps([asdict(item) for item in gateway.audit]).encode()
                self._send(200, body, {"Content-Type": "application/json"})
            elif self.path == "/v1/pending":
                if not self._authenticate():
                    return
                actions = gateway.get_pending_actions()
                self._send(200, json.dumps(actions).encode(), {"Content-Type": "application/json"})
            elif self.path.startswith("/v1/pending/"):
                if not self._authenticate():
                    return
                action_id = self.path.split("/v1/pending/")[1].split("/")[0]
                action = gateway.get_action(action_id)
                if not action:
                    self._send(
                        404,
                        json.dumps({"error": "not found", "action_id": action_id}).encode(),
                        {"Content-Type": "application/json"},
                    )
                    return
                self._send(200, json.dumps(action).encode(), {"Content-Type": "application/json"})
            else:
                self._send(404, b"")

        def do_POST(self) -> None:  # noqa: N802
            if not self._trusted_host_origin():
                self._send(
                    403,
                    json.dumps(
                        {"error": "forbidden", "reason": "Untrusted Host or Origin"}
                    ).encode(),
                    {"Content-Type": "application/json"},
                )
                return
            if self.path.startswith("/v1/pending/"):
                if not self._authenticate():
                    return
                parts = self.path.strip("/").split("/")
                if len(parts) == 4 and parts[0] == "v1" and parts[1] == "pending":
                    action_id = parts[2]
                    command = parts[3]
                    try:
                        if command == "approve":
                            result = gateway.approve_action(action_id)
                            self._send(
                                200,
                                json.dumps(result).encode(),
                                {"Content-Type": "application/json"},
                            )
                            return
                        elif command == "deny":
                            result = gateway.deny_action(action_id)
                            self._send(
                                200,
                                json.dumps(result).encode(),
                                {"Content-Type": "application/json"},
                            )
                            return
                    except KeyError:
                        self._send(
                            404,
                            json.dumps({"error": "not found", "action_id": action_id}).encode(),
                            {"Content-Type": "application/json"},
                        )
                        return
                    except ValueError as exc:
                        self._send(
                            409,
                            json.dumps({"error": "conflict", "reason": str(exc)}).encode(),
                            {"Content-Type": "application/json"},
                        )
                        return
                self._send(
                    404,
                    json.dumps({"error": "invalid control endpoint"}).encode(),
                    {"Content-Type": "application/json"},
                )
                return

            if not self._authenticate_client():
                return
            auth_value = self.headers.get("Authorization", "")[7:].strip()
            client_key = "client:" + hashlib.sha256(auth_value.encode()).hexdigest()
            allowed, retry = gateway.allow_rate(client_key)
            session_value = self.headers.get("X-Sentinel-Session", "default")
            if allowed:
                session_hash = hashlib.sha256(session_value.encode()).hexdigest()
                allowed, retry = gateway.allow_rate(client_key + ":session:" + session_hash)
            if not allowed:
                self._send(
                    429,
                    b'{"error":"rate limit exceeded"}',
                    {
                        "Content-Type": "application/json",
                        "Retry-After": str(max(1, math.ceil(retry))),
                    },
                )
                return
            try:
                body = read_body(
                    self, gateway.config.max_request_bytes, gateway.config.timeout_seconds
                )
                self._body_read = True
                for name in self.headers.keys():
                    values = self.headers.get_all(name) or []
                    lower_name = name.lower()
                    if (
                        lower_name.startswith("x-sentinel-")
                        or lower_name in {"mcp-session-id", "mcp-protocol-version"}
                    ) and len(values) != 1:
                        raise JsonRpcError(-32600, "Duplicate Sentinel header")
                status, response, response_headers = gateway.handle(
                    body,
                    {
                        **{k.lower(): v for k, v in self.headers.items()},
                        "x-sentinel-authenticated-client": getattr(
                            self, "_authenticated_client_id", "single-client"
                        ),
                    },
                )
                self._send(status, response, response_headers)
            except JsonRpcError as exc:
                with gateway._rate_lock:
                    decisions = gateway.metrics["requests"]
                    decisions["error"] = decisions.get("error", 0) + 1
                gateway.logger.warning(
                    json.dumps(
                        {
                            "event": "mcp_request_rejected",
                            "request_id": exc.request_id,
                            "decision": "error",
                            "latency_ms": 0,
                            "reasons": [str(exc)],
                        },
                        separators=(",", ":"),
                    )
                )
                self._send(
                    200,
                    json.dumps(exc.response()).encode(),
                    {"Content-Type": "application/json", "X-Sentinel-Decision": "error"},
                )
            except PayloadTooLargeError:
                self.close_connection = True
                self._send(
                    413,
                    json.dumps(JsonRpcError(-32600, "Payload Too Large").response()).encode(),
                    {"Content-Type": "application/json"},
                )
            except (ValueError, TimeoutError):
                self.close_connection = True
                self._send(
                    400,
                    json.dumps(JsonRpcError(-32600, "Invalid request body").response()).encode(),
                    {"Content-Type": "application/json"},
                )
            except (BrokenPipeError, ConnectionResetError):
                return

        def log_message(self, format: str, *args: object) -> None:
            # Access-log format contains client address/path but no credentials or payload.
            gateway.logger.debug(json.dumps({"event": "http_access", "message": format % args}))

    return Handler


def create_gateway_server(
    config: GatewayConfig,
    engine: SentinelEngine | None = None,
    host: str = "127.0.0.1",
    port: int = 8788,
) -> tuple[BoundedHTTPServer, SentinelGateway]:
    try:
        loopback = host.lower() == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if not loopback and not config.tls_cert and not config.insecure_allow_plaintext:
        raise ValueError(
            "refusing non-loopback plaintext bind; configure TLS or explicitly allow plaintext"
        )
    if config.log_file:
        handler = logging.FileHandler(config.log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger("sentinel.gateway").addHandler(handler)
    gateway = SentinelGateway(config, engine)
    server = BoundedHTTPServer(
        (host, port),
        make_gateway_handler(gateway),
        max_connections=config.max_connections,
        request_timeout=config.request_timeout_seconds,
    )
    if config.tls_cert and config.tls_key:
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(config.tls_cert, config.tls_key)
            if config.tls_client_ca:
                context.load_verify_locations(config.tls_client_ca)
                context.verify_mode = ssl.CERT_REQUIRED
            server.socket = context.wrap_socket(server.socket, server_side=True)
        except BaseException:
            server.server_close()
            raise
    return server, gateway


def serve_gateway(
    config: GatewayConfig,
    host: str = "127.0.0.1",
    port: int = 8788,
    state_file: str | Path | None = None,
    autosave_seconds: float = 30.0,
) -> None:
    """Serve the gateway; if state_file is given, load the learned baseline on
    start (when the file exists) and persist it periodically and on shutdown."""
    if not config.client_auth_token and not config.credentials_file:
        raise ValueError(
            "Refusing to start gateway without client authentication; configure client_auth_token"
        )
    if not config.auth_token or len(config.auth_token) < 32:
        raise ValueError(
            "Refusing to start gateway without a strong operator credential "
            "(at least 32 characters)"
        )
    if state_file is None:
        raise ValueError("Refusing to start gateway without a trained --state-file baseline")
    state_path = Path(state_file)
    if not state_path.is_file():
        raise FileNotFoundError(f"Trained baseline state file not found: {state_path}")
    server, gateway = create_gateway_server(config, host=host, port=port)
    try:
        gateway.load_state(state_path)
        gateway.state_path = state_path
        profile = gateway.engine.profiles.get(config.server_id)
        if profile is None or profile.trusted_count < gateway.engine.warmup_events:
            raise ValueError("Baseline has insufficient trusted enrollment for this server")
        gateway.baseline_loaded = True
        print(f"Loaded trained baseline from {state_path}")
    except Exception:
        server.server_close()
        raise
    if state_file:
        stop = threading.Event()

        def _autosave() -> None:
            while not stop.wait(autosave_seconds):
                try:
                    gateway.save_state(state_path)
                except OSError as exc:
                    print(f"warning: could not save state: {exc}")

        autosave_thread = threading.Thread(target=_autosave, daemon=True)
        autosave_thread.start()
    else:  # guarded above; retained for type narrowing
        stop = None
        autosave_thread = None
    scheme = "https" if config.tls_cert else "http"
    if scheme == "http" and host not in ("127.0.0.1", "::1", "localhost"):
        gateway.logger.warning(json.dumps({"event": "insecure_plaintext_bind", "host": host}))
    print(f"Sentinel MCP gateway on {scheme}://{host}:{port} -> {config.upstream_url}")
    if threading.current_thread() is threading.main_thread():
        import signal

        def _terminate(signum: int, frame: FrameType | None) -> NoReturn:
            # Make SIGTERM (Docker/systemd stop) save state like Ctrl+C.
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, _terminate)
        if hasattr(signal, "SIGHUP") and config.credentials_file:
            signal.signal(signal.SIGHUP, lambda signum, frame: gateway.reload_client_credentials())
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.drain(config.request_timeout_seconds)
        if stop is not None:
            stop.set()
            if autosave_thread is not None:
                autosave_thread.join(timeout=config.request_timeout_seconds + 1)
            gateway.save_state(state_path)
            print(f"Saved baseline to {state_path}")
        server.server_close()


DEFAULT_BASELINE_CALLS = [
    {"tool": "safe_read", "arguments": {"record_id": "1"}, "intent": "Read one record"},
    {"tool": "calculate", "arguments": {"a": 1, "b": 2}, "intent": "Add two numbers"},
]


def build_baseline(
    config: GatewayConfig,
    state_file: str | Path,
    calls: list[dict[str, Any]] | None = None,
    rounds: int = 60,
) -> dict[str, Any]:
    """Replay known-benign calls through the real gateway pipeline against the
    upstream server (trusted enrollment) and save the learned baseline."""
    calls = calls or DEFAULT_BASELINE_CALLS
    # Baseline calls are explicit operator-supplied training inputs. Permit
    # those exact tools for this isolated enrollment run.
    approved_tools: set[str] = set(config.allowed_tools)
    approved_tools.update(str(call["tool"]) for call in calls)
    config = replace(
        config,
        allowed_tools=tuple(sorted(approved_tools)),
    )
    gateway = SentinelGateway(config)
    gateway.trusted_enrollment = True
    session_headers: dict[str, dict[str, str]] = {}
    for index in range(4):
        session_key = f"baseline-{index}"
        headers = {
            "x-sentinel-session": session_key,
            "x-sentinel-intent": "baseline enrollment",
        }
        initialize = {
            "jsonrpc": "2.0",
            "id": f"initialize-{index}",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "mcp-runtime-sentinel-baseline", "version": "0.2.0"},
            },
        }
        _, _, response_headers = gateway.handle(json.dumps(initialize).encode(), headers)
        if response_headers.get("Mcp-Session-Id"):
            headers["mcp-session-id"] = response_headers["Mcp-Session-Id"]
        if response_headers.get("MCP-Protocol-Version"):
            headers["mcp-protocol-version"] = response_headers["MCP-Protocol-Version"]
        session_headers[session_key] = headers
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        gateway.handle(json.dumps(initialized_notification).encode(), headers)
        listing = {
            "jsonrpc": "2.0",
            "id": f"tools-list-{index}",
            "method": "tools/list",
            "params": {},
        }
        gateway.handle(json.dumps(listing).encode(), headers)
    sent = 0
    for i in range(rounds):
        for j, call in enumerate(calls):
            body = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": f"b{i}-{j}",
                    "method": "tools/call",
                    "params": {"name": call["tool"], "arguments": call.get("arguments", {})},
                }
            ).encode()
            session_key = f"baseline-{(i + j) % 4}"
            headers = {
                **session_headers[session_key],
                "x-sentinel-intent": call.get("intent", "unspecified intent"),
            }
            gateway.handle(body, headers)
            sent += 1
    gateway.trusted_enrollment = False
    gateway.save_state(state_file)
    profile = gateway.engine.profiles.get(config.server_id)
    return {
        "calls_replayed": sent,
        "trained_events": profile.trusted_count if profile else 0,
        "state_file": str(state_file),
    }
