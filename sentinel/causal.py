from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from typing import Any

TOKEN = re.compile(r"[a-zA-Z0-9_@.-]{4,}")
INSTRUCTION = re.compile(
    r"(ignore|override|bypass).{0,30}(instruction|policy|system|security)", re.I
)
GENERIC_RECORD_ID = re.compile(r"^(?:record[-_]?)?\d+$|^record$", re.I)


def _tokens(value: Any) -> set[str]:
    # Schema field names describe structure, not values propagated by a caller.
    # Matching keys such as record_id creates false flow edges across servers.
    if isinstance(value, dict):
        return set().union(*(_tokens(item) for item in value.values())) if value else set()
    if isinstance(value, (list, tuple)):
        return set().union(*(_tokens(item) for item in value)) if value else set()
    if type(value) in (int, float):
        value = str(value)
    if not isinstance(value, str):
        return set()
    return {item.lower() for item in TOKEN.findall(value)}


@dataclass(slots=True)
class CausalNode:
    node_id: str
    kind: str
    server_id: str
    tool_name: str
    digest: str
    session_id: str = "default"
    intent: str = ""


@dataclass(slots=True)
class CausalEdge:
    source: str
    target: str
    relation: str
    weight: float


@dataclass(slots=True)
class CausalEvidence:
    trace_id: str
    risk: float
    reasons: list[str]
    edges: list[CausalEdge]


class TemporalCausalGraph:
    """Bounded provenance graph that detects cross-call and cross-server influence."""

    def __init__(
        self,
        history_size: int = 32,
        *,
        max_nodes: int = 10_000,
        causal_requires_response_origin: bool = False,
    ):
        if type(max_nodes) is not int or max_nodes < 1:
            raise ValueError("max_nodes must be positive")
        self.max_nodes = max_nodes
        self.causal_requires_response_origin = bool(causal_requires_response_origin)
        self.nodes: dict[str, CausalNode] = {}
        self.edges: list[CausalEdge] = []
        self.history: dict[str, deque[tuple[CausalNode, set[str], set[str]]]] = defaultdict(
            lambda: deque(maxlen=history_size)
        )
        self.sequence = 0
        self.read_permissions = {}
        self.permission_clock = time.monotonic

    def authorize_read(
        self,
        *,
        source_server,
        source_tool,
        destination_server,
        destination_tool,
        session_id,
        arguments,
        ttl=60,
    ):
        """Trusted application API. Never derive grants from request metadata."""
        if any(
            not isinstance(v, str) or not v or len(v) > 256
            for v in (source_server, source_tool, destination_server, destination_tool, session_id)
        ):
            raise ValueError("explicit nonempty permission scope required")
        if (
            not isinstance(arguments, dict)
            or type(ttl) not in (int, float)
            or not math.isfinite(ttl)
            or not 0 < ttl <= 3600
        ):
            raise ValueError("exact arguments and finite TTL in (0, 3600] required")
        from .validation import validate_json

        validate_json(arguments)
        now = self.permission_clock()
        self.read_permissions = {
            k: v for k, v in self.read_permissions.items() if now < v["expires"]
        }
        if len(self.read_permissions) >= self.max_nodes:
            raise ValueError("flow permission capacity exhausted")
        key = secrets.token_hex(16)
        self.read_permissions[key] = dict(
            source_server=source_server,
            source_tool=source_tool,
            destination_server=destination_server,
            destination_tool=destination_tool,
            session_id=session_id,
            arguments=json.dumps(arguments, sort_keys=True, allow_nan=False),
            expires=now + ttl,
        )
        return key

    def revoke_read(self, permission_id):
        self.read_permissions.pop(permission_id, None)

    def _read_permission(self, prior, event):
        if event.side_effect:
            return None
        now = self.permission_clock()
        for key, grant in list(self.read_permissions.items()):
            if now >= grant["expires"]:
                del self.read_permissions[key]
                continue
            if (
                grant["source_server"] == prior.server_id
                and grant["source_tool"] == prior.tool_name
                and grant["destination_server"] == event.server_id
                and grant["destination_tool"] == event.tool_name
                and grant["session_id"] == event.session_id
                and grant["arguments"]
                == json.dumps(event.arguments, sort_keys=True, allow_nan=False)
            ):
                return key
        return None

    def observe(self, event: Any) -> CausalEvidence:
        self.sequence += 1
        material = json.dumps(
            {
                "server": event.server_id,
                "tool": event.tool_name,
                "args": event.arguments,
                "response": event.response,
                "sequence": self.sequence,
            },
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(material.encode()).hexdigest()
        trace_id = digest[:16]
        node = CausalNode(
            trace_id,
            "interaction",
            event.server_id,
            event.tool_name,
            digest,
            event.session_id,
            event.user_intent,
        )
        argument_tokens = _tokens(event.arguments)
        response_tokens = _tokens(event.response)
        reasons: list[str] = []
        evidence_edges: list[CausalEdge] = []
        risk = 0.0

        for prior, _, prior_response in self.history[event.session_id]:
            overlap = argument_tokens & prior_response
            if not overlap:
                continue
            if self.causal_requires_response_origin and prior.server_id != event.server_id:
                overlap = {tok for tok in overlap if not GENERIC_RECORD_ID.match(tok)}
                if not overlap:
                    continue
            weight = min(1.0, len(overlap) / max(1, len(argument_tokens)))
            relation = (
                "cross_server_data_flow"
                if prior.server_id != event.server_id
                else "derived_parameter"
            )
            edge = CausalEdge(prior.node_id, trace_id, relation, weight)
            evidence_edges.append(edge)
            if prior.server_id != event.server_id:
                permission = self._read_permission(prior, event)
                if permission:
                    edge.relation = "authorized_cross_server_read"
                    reasons.append(f"cross-server read authorized by {permission}")
                    continue
                # Any unexplained cross-server propagation is material; overlap
                # strength raises it toward a high-confidence causal anomaly.
                risk = max(risk, 0.60 + 0.4 * weight)
                reasons.append(f"cross-server data flow from {prior.server_id}")

        response_text = json.dumps(event.response, default=str)
        if INSTRUCTION.search(response_text):
            risk = max(risk, 0.78)
            reasons.append("policy-like instruction embedded in tool response")

        previous = self.history[event.session_id][-1][0] if self.history[event.session_id] else None
        if previous is not None:
            evidence_edges.append(CausalEdge(previous.node_id, trace_id, "precedes", 1.0))
        self.nodes[trace_id] = node
        self.edges.extend(evidence_edges)
        self.history[event.session_id].append((node, argument_tokens, response_tokens))
        if len(self.nodes) > self.max_nodes:
            oldest = next(iter(self.nodes))
            removed = self.nodes.pop(oldest)
            self.edges = [edge for edge in self.edges if oldest not in (edge.source, edge.target)]
            history = self.history[removed.session_id]
            self.history[removed.session_id] = deque(
                (item for item in history if item[0].node_id != oldest), maxlen=history.maxlen
            )
            if not self.history[removed.session_id]:
                del self.history[removed.session_id]
        return CausalEvidence(
            trace_id, min(1.0, risk), list(dict.fromkeys(reasons)), evidence_edges
        )

    def trace(self, trace_id: str) -> dict[str, Any]:
        node = self.nodes[trace_id]
        return {
            "node": asdict(node),
            "incoming": [asdict(edge) for edge in self.edges if edge.target == trace_id],
        }
