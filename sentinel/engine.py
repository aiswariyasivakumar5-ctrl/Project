from __future__ import annotations

import hashlib
import math
import threading
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from functools import partial

import numpy as np

from .attestation import AttestationManager
from .causal import TemporalCausalGraph
from .detectors import OnlineStandardizer, SequenceModel, TinyAutoencoder
from .features import extract_features, intent_mismatch
from .models import Action, Interaction, Verdict
from .provenance import ProvenanceLedger
from .retention import RetentionConfig, StateCapacityError


@dataclass
class ServerProfile:
    scaler: OnlineStandardizer
    autoencoder: TinyAutoencoder
    trusted_count: int = 0
    quarantined_count: int = 0
    trust: float = 0.75
    error_mean: float = 0.0
    error_m2: float = 0.0

    def update_error(self, error: float) -> None:
        self.trusted_count += 1
        delta = error - self.error_mean
        self.error_mean += delta / self.trusted_count
        self.error_m2 += delta * (error - self.error_mean)

    @property
    def error_std(self) -> float:
        if self.trusted_count < 2:
            return 0.5
        # A conservative floor avoids treating harmless latency jitter as a
        # high-confidence anomaly while the online model is still settling.
        return max(0.5, math.sqrt(self.error_m2 / (self.trusted_count - 1)))


@dataclass(frozen=True)
class EngineConfig:
    intent: bool = True
    causal: bool = True
    attestation: bool = True
    uncertainty: bool = True
    quarantine: bool = True
    causal_requires_response_origin: bool = False


class SentinelEngine:
    def __init__(
        self,
        warmup_events: int = 20,
        config: EngineConfig | None = None,
        *,
        provenance_clock: Callable[[], float] | None = None,
        retention: RetentionConfig | None = None,
    ):
        self.warmup_events = warmup_events
        self.config = config or EngineConfig()
        self.profiles: dict[str, ServerProfile] = {}
        self.retention = retention or RetentionConfig()
        self.identities: dict[str, set[str]] = {}
        self.sessions: set[str] = set()
        self.sequence = SequenceModel(self.retention.transitions_per_session)
        self.audit_log = deque(maxlen=self.retention.audit_records)
        self.quarantine = defaultdict(partial(deque, maxlen=self.retention.quarantine_per_server))
        self.causal_graph = TemporalCausalGraph(
            max_nodes=self.retention.causal_nodes,
            causal_requires_response_origin=self.config.causal_requires_response_origin,
        )
        self.attestation = AttestationManager()
        self.provenance = ProvenanceLedger(
            provenance_clock, self.causal_graph, max_claims=self.retention.provenance_claims
        )
        self.lock = threading.RLock()

    def __getstate__(self):
        return {key: value for key, value in self.__dict__.items() if key != "lock"}

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.lock = threading.RLock()

    def admit(self, server_id: str, session_id: str, tool_name: str) -> None:
        """Reserve bounded identities; never evict trust to restart warm-up."""
        with self.lock:
            tools = self.identities.get(server_id, set())
            if server_id not in self.identities and len(self.identities) >= self.retention.servers:
                raise StateCapacityError("server capacity exhausted")
            if session_id not in self.sessions and len(self.sessions) >= self.retention.sessions:
                raise StateCapacityError("session capacity exhausted")
            if tool_name not in tools and len(tools) >= self.retention.tools_per_server:
                raise StateCapacityError("tool capacity exhausted")
            self.identities.setdefault(server_id, set()).add(tool_name)
            self.sessions.add(session_id)

    def issue_provenance(self, origin_trace_id: str, target: Interaction, *, ttl: float = 300):
        """Trusted application authorizes a target using an accepted intent event."""
        if not any(
            v.trace_id == origin_trace_id
            and v.action in {Action.ALLOW, Action.OBSERVE}
            and v.components.get("failure") == 0
            for v in self.audit_log
        ):
            raise ValueError("provenance origin must be an accepted engine event")
        predecessor = next(
            (
                edge.source
                for edge in self.causal_graph.edges
                if edge.target == origin_trace_id and edge.relation == "precedes"
            ),
            None,
        )
        return self.provenance.issue(
            origin_trace_id,
            target.user_intent,
            target.session_id,
            target.server_id,
            target.tool_name,
            target.arguments,
            predecessor=predecessor,
            ttl=ttl,
        )

    def _profile(self, server_id: str, dimension: int) -> ServerProfile:
        if server_id not in self.profiles:
            digest = hashlib.sha256(server_id.encode("utf-8")).digest()
            seed = int.from_bytes(digest[:8], "big") & 0x7FFFFFFF
            self.profiles[server_id] = ServerProfile(
                OnlineStandardizer(dimension), TinyAutoencoder(dimension, seed=seed)
            )
        return self.profiles[server_id]

    @staticmethod
    def _action(risk: float, warmup: bool) -> Action:
        # Enrollment is not an allow-list. It suppresses low-risk model noise,
        # but material intent/causal/policy risk is enforced immediately.
        if warmup and risk < 0.45:
            return Action.OBSERVE
        if risk >= 0.82:
            return Action.ISOLATE
        if risk >= 0.65:
            return Action.SANDBOX
        if risk >= 0.45:
            return Action.CONFIRM
        return Action.ALLOW

    def evaluate(
        self, event: Interaction, learn: bool = True, trusted_enrollment: bool = False
    ) -> Verdict:
        self.admit(event.server_id, event.session_id, event.tool_name)
        raw = extract_features(event)
        profile = self._profile(event.server_id, len(raw))
        warmup = profile.trusted_count < self.warmup_events
        normalized = profile.scaler.transform(raw) if profile.scaler.count else np.zeros_like(raw)
        reconstruction_error = profile.autoencoder.error(normalized)
        if warmup:
            behavior = min(1.0, reconstruction_error / 4.0)
        else:
            z_score = max(0.0, (reconstruction_error - profile.error_mean) / profile.error_std)
            behavior = 1.0 - math.exp(-z_score / 3.0)
        intent = (
            intent_mismatch(event.user_intent, event.tool_name, event.arguments)
            if self.config.intent
            else 0.0
        )
        sequence = self.sequence.anomaly(event.session_id, event.tool_name)
        causal = self.causal_graph.observe(event)
        provenance_risk = 0.0
        provenance_reason = None
        provenance_evidence = None
        if event.provenance_id is not None:
            result = self.provenance.validate(
                event.provenance_id,
                intent=event.user_intent,
                session_id=event.session_id,
                server_id=event.server_id,
                tool_name=event.tool_name,
                arguments=event.arguments,
                current_trace_id=causal.trace_id,
                event_timestamp=event.timestamp,
            )
            provenance_evidence = {
                "claim_id": event.provenance_id,
                "valid": result.valid,
                "reason": result.reason,
                "claim": asdict(result.claim) if result.claim else None,
            }
            if not result.valid:
                provenance_risk = 1.0
                provenance_reason = result.reason
        causal_risk = causal.risk if self.config.causal else 0.0
        impact = 1.0 if event.side_effect else 0.25
        failure = 0.0 if event.success else 1.0
        coverage_uncertainty = max(
            0.0, 1.0 - profile.trusted_count / max(1, self.warmup_events * 3)
        )
        boundary_uncertainty = max(0.0, 1.0 - abs(behavior - 0.5) * 2.0)
        uncertainty = (
            float(np.clip(0.65 * coverage_uncertainty + 0.35 * boundary_uncertainty, 0, 1))
            if self.config.uncertainty
            else 0.0
        )
        attestation_failed = False
        attestation_passed = False
        if self.config.attestation and event.attestation_challenge_id:
            attestation_passed = self.attestation.verify(
                event.attestation_challenge_id,
                event.capability_digest or "",
                event.attestation_echo or "",
                server_id=event.server_id,
            )
            attestation_failed = not attestation_passed
        capability_changed = self.config.attestation and bool(
            event.capability_digest
            and event.server_id in self.attestation.enrolled
            and event.capability_digest != self.attestation.enrolled[event.server_id]
        )
        attestation_risk = 1.0 if attestation_failed or capability_changed else 0.0
        risk = float(
            np.clip(
                0.34 * behavior
                + 0.20 * intent
                + 0.10 * sequence
                + 0.16 * causal_risk
                + 0.08 * impact
                + 0.05 * failure
                + 0.07 * attestation_risk,
                0,
                1,
            )
        )
        risk = max(risk, 0.82 if provenance_risk else risk)
        if causal_risk >= 0.60:
            risk = max(risk, 0.50)
        if attestation_passed and not provenance_risk:
            risk *= 0.75
        action = self._action(risk, warmup)
        protected_learning = risk < 0.42
        safe_to_learn = (
            learn
            and not provenance_risk
            and not attestation_risk
            and event.success
            and (trusted_enrollment or protected_learning or not self.config.quarantine)
        )
        reasons = []
        for label, value, threshold in (
            ("behavioral deviation", behavior, 0.55),
            ("intent mismatch", intent, 0.70),
            ("unusual tool sequence", sequence, 0.70),
            ("failed invocation", failure, 0.5),
            ("causal propagation anomaly", causal_risk, 0.60),
            ("behavioral attestation failed", attestation_risk, 0.5),
        ):
            if value >= threshold:
                reasons.append(label)
        if self.config.causal:
            reasons.extend(causal.reasons)
        if provenance_reason:
            reasons.append(provenance_reason)
        if safe_to_learn:
            self.learn_approved(event)
        elif risk >= 0.42 or not event.success or attestation_risk:
            profile.quarantined_count += 1
            self.quarantine[event.server_id].append(event)
            profile.trust = max(0.0, profile.trust - (0.04 + 0.12 * risk))
        challenge = None
        should_challenge = (
            self.config.attestation
            and not warmup
            and not event.attestation_challenge_id
            and (uncertainty >= 0.55 or causal_risk >= 0.60 or risk >= 0.55)
        )
        if should_challenge:
            issued = self.attestation.issue(event.server_id)
            challenge = issued.to_dict() if issued else None
        verdict = Verdict(
            event.server_id,
            risk,
            profile.trust,
            action,
            reasons,
            {
                "behavior": behavior,
                "intent": intent,
                "sequence": sequence,
                "causal": causal_risk,
                "impact": impact,
                "failure": failure,
                "attestation": attestation_risk,
                "provenance": provenance_risk,
            },
            safe_to_learn,
            causal.trace_id,
            uncertainty,
            challenge,
            provenance_evidence,
        )
        self.audit_log.append(verdict)
        return verdict

    def learn_approved(self, event: Interaction, *, update_sequence: bool = True) -> None:
        """Trusted in-process learning hook; never observes or revalidates an event.

        The caller must already have approved this event. Historical promotions
        must not rewind the live session sequence or append new causal nodes.
        """
        if not event.success:
            raise ValueError("failed events cannot be approved for learning")
        self.admit(event.server_id, event.session_id, event.tool_name)
        raw = extract_features(event)
        profile = self._profile(event.server_id, len(raw))
        profile.scaler.update(raw)
        trained = profile.autoencoder.train_one(profile.scaler.transform(raw))
        profile.update_error(trained)
        if update_sequence:
            self.sequence.update(event.session_id, event.tool_name)
        self.attestation.enroll(event.server_id, event.capability_digest)
        profile.trust = min(1.0, profile.trust + 0.008)

    def server_status(self, server_id: str) -> dict[str, float | int]:
        profile = self.profiles[server_id]
        return {
            "trust_score": profile.trust,
            "trusted_events": profile.trusted_count,
            "quarantined_events": profile.quarantined_count,
        }
