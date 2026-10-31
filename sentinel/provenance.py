"""Single-use intent claims, bound to the engine's existing causal evidence."""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from typing import Any

from .causal import TemporalCausalGraph


@dataclass
class ScenarioClock:
    value: float = 100.0

    def __call__(self) -> float:
        return self.value


@dataclass(frozen=True)
class ProvenanceStep:
    key: str
    operation: str
    at: float
    ttl: float = 10.0
    target_tool: str | None = None


@dataclass(frozen=True, slots=True)
class ProvenanceClaim:
    claim_id: str
    intent: str
    event_id: str
    session_id: str
    server_id: str
    tool_name: str
    arguments_digest: str
    predecessor: str | None
    created_at: float
    expires_at: float | None = None
    uses: int = 0


@dataclass(frozen=True, slots=True)
class ProvenanceResult:
    valid: bool
    reason: str
    claim: ProvenanceClaim | None = None


def _finite(value: Any) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _digest(value: Any) -> str:
    # Do not coerce unsupported Python objects into strings that can collide
    # with actual JSON arguments.
    def check(item: Any) -> None:
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            for child in item:
                check(child)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                check(child)
            return
        raise ValueError("provenance requires finite JSON data")

    check(value)
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


class ProvenanceLedger:
    """Trusted in-process issuer; clock is trusted, Interaction timestamps are not.

    A standalone ledger supports claim links for legacy callers. Engine ledgers
    always receive the existing causal graph and require actual graph evidence.
    """

    def __init__(
        self,
        clock: Callable[[], float] | None = None,
        graph: TemporalCausalGraph | None = None,
        *,
        max_claims: int = 10_000,
    ):
        if type(max_claims) is not int or max_claims < 1:
            raise ValueError("max_claims must be positive")
        self.max_claims = max_claims
        self.clock = clock or time.time
        self.graph = graph
        self.claims: dict[str, ProvenanceClaim] = {}
        self.consumed: set[str] = set()
        self._issued: dict[str, ProvenanceClaim] = {}
        self._last_time: dict[str, float] = {}
        self._invalid: dict[str, str] = {}
        self._evidence: dict[str, tuple[str, str | None]] = {}
        self._lock = threading.RLock()

    def __getstate__(self) -> dict[str, Any]:
        # Experiment validation checkpoints deepcopy engines.
        return {key: value for key, value in self.__dict__.items() if key != "_lock"}

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)
        self._lock = threading.RLock()

    def _graph_evidence(self, claim: ProvenanceClaim) -> tuple[str, str | None]:
        assert self.graph is not None
        origin = self.graph.nodes.get(claim.event_id)
        if origin is None:
            raise ValueError("unknown originating causal event")
        if (origin.session_id, origin.server_id, origin.intent) != (
            claim.session_id,
            claim.server_id,
            claim.intent,
        ):
            raise ValueError("originating causal context mismatch")
        predecessor_digest = None
        if claim.predecessor is not None:
            prior = self.graph.nodes.get(claim.predecessor)
            if prior is None:
                raise ValueError("unknown causal predecessor")
            if (prior.session_id, prior.server_id) != (claim.session_id, claim.server_id):
                raise ValueError("causal predecessor context mismatch")
            if not any(
                edge.source == prior.node_id
                and edge.target == origin.node_id
                and edge.relation == "precedes"
                for edge in self.graph.edges
            ):
                raise ValueError("invalid causal predecessor relation")
            predecessor_digest = _digest(asdict(prior))
        return _digest(asdict(origin)), predecessor_digest

    def issue(
        self,
        event_id: str,
        intent: str,
        session_id: str,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        predecessor: str | None = None,
        ttl: float | None = 300,
        created_at: float | None = None,
    ) -> ProvenanceClaim:
        with self._lock:
            now = self.clock() if created_at is None else created_at
            if not _finite(now):
                raise ValueError("creation time must be finite")
            if ttl is not None and (not _finite(ttl) or ttl <= 0 or not _finite(now + ttl)):
                raise ValueError("TTL must be positive and finite")
            if not all(
                isinstance(item, str) and item
                for item in (event_id, intent, session_id, server_id, tool_name)
            ):
                raise ValueError("provenance identities must be nonempty strings")
            if predecessor is not None and (not isinstance(predecessor, str) or not predecessor):
                raise ValueError("invalid causal predecessor ID")
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be an object")
            claim_id = secrets.token_hex(16)
            claim = ProvenanceClaim(
                claim_id,
                intent,
                event_id,
                session_id,
                server_id,
                tool_name,
                _digest(arguments),
                predecessor,
                now,
                None if ttl is None else now + ttl,
            )
            evidence = self._graph_evidence(claim) if self.graph is not None else None
            while len(self._issued) >= self.max_claims:
                oldest = next(iter(self._issued))
                for store in (
                    self.claims,
                    self._issued,
                    self._last_time,
                    self._invalid,
                    self._evidence,
                ):
                    store.pop(oldest, None)
                self.consumed.discard(oldest)
            # Evicted IDs become unknown and can never authorize a call again.
            if evidence is not None:
                self._evidence[claim_id] = evidence
            self.claims[claim_id] = self._issued[claim_id] = claim
            self._last_time[claim_id] = now
            return claim

    def validate(
        self,
        claim_id: str,
        *,
        intent: str,
        session_id: str,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        now: float | None = None,
        consume: bool = True,
        current_trace_id: str | None = None,
        event_timestamp: float | None = None,
        preflight: bool = False,
    ) -> ProvenanceResult:
        with self._lock:
            if not isinstance(claim_id, str) or not claim_id:
                return ProvenanceResult(False, "malformed provenance ID")
            claim = self.claims.get(claim_id)
            original = self._issued.get(claim_id)
            if original is None:
                return ProvenanceResult(False, "unknown provenance")
            expected = replace(original, uses=int(claim_id in self.consumed))
            if claim != expected:
                return ProvenanceResult(False, "provenance claim tampered", original)
            if claim_id in self._invalid:
                return ProvenanceResult(False, self._invalid[claim_id], claim)
            if claim_id in self.consumed:
                return ProvenanceResult(False, "provenance replay", claim)
            current = self.clock() if now is None else now
            reason = None
            if not _finite(current) or (
                event_timestamp is not None and not _finite(event_timestamp)
            ):
                reason = "invalid provenance timestamp"
            elif current < self._last_time[claim_id]:
                reason = "provenance clock rollback"
            elif claim.expires_at is not None and current >= claim.expires_at:
                reason = "stale provenance"
            if reason:
                # An expired/clock-invalid claim can never be revived by rollback.
                self._invalid[claim_id] = reason
                return ProvenanceResult(False, reason, claim)
            self._last_time[claim_id] = current
            if claim.intent != intent:
                return ProvenanceResult(False, "provenance intent mismatch", claim)
            if (claim.session_id, claim.server_id, claim.tool_name) != (
                session_id,
                server_id,
                tool_name,
            ):
                return ProvenanceResult(False, "provenance context mismatch", claim)
            if self.graph is not None:
                try:
                    if self._graph_evidence(claim) != self._evidence[claim_id]:
                        raise ValueError("causal evidence tampered")
                    if preflight:
                        history = self.graph.history.get(session_id)
                        if not history:
                            raise ValueError("missing current causal session")
                        current_trace_id = history[-1][0].node_id
                    if current_trace_id is not None:
                        # Follow the graph's actual same-session precedence edges;
                        # matching IDs/context alone do not prove ancestry.
                        pending, visited = [current_trace_id], set()
                        while pending:
                            trace = pending.pop()
                            node = self.graph.nodes.get(trace)
                            if (
                                trace in visited
                                or node is None
                                or node.session_id != claim.session_id
                            ):
                                continue
                            visited.add(trace)
                            pending.extend(
                                edge.source
                                for edge in self.graph.edges
                                if edge.target == trace and edge.relation == "precedes"
                            )
                        if claim.event_id not in visited or (
                            current_trace_id == claim.event_id and not preflight
                        ):
                            raise ValueError("origin is not a causal ancestor of current event")
                except ValueError as exc:
                    return ProvenanceResult(False, str(exc), claim)
            elif claim.predecessor:
                predecessor = self.claims.get(claim.predecessor)
                if predecessor is None:
                    return ProvenanceResult(False, "unknown causal predecessor", claim)
                if (predecessor.session_id, predecessor.server_id) != (
                    claim.session_id,
                    claim.server_id,
                ):
                    return ProvenanceResult(False, "causal predecessor context mismatch", claim)
            try:
                if not isinstance(arguments, dict) or claim.arguments_digest != _digest(arguments):
                    return ProvenanceResult(False, "provenance argument mismatch", claim)
            except (ValueError, TypeError, RecursionError):
                return ProvenanceResult(False, "malformed provenance arguments", claim)
            if consume:
                self.consumed.add(claim_id)
                self.claims[claim_id] = replace(claim, uses=1)
            return ProvenanceResult(True, "valid provenance", self.claims[claim_id])
