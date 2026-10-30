from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from .approvals import ReviewApprovals
from .engine import EngineConfig, SentinelEngine
from .models import Action, Interaction, Verdict


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _terms(value: Any) -> set[str]:
    text = json.dumps(value, sort_keys=True, default=str).lower()
    return {x for x in "".join(c if c.isalnum() else " " for c in text).split() if len(x) > 2}


@dataclass(slots=True)
class ProvenanceClaim:
    claim_id: str
    trace_id: str
    session_id: str
    server_id: str
    capability: str
    intent_digest: str
    input_digest: str
    output_digest: str
    intent_support: float
    counterfactual_risk: float
    reasons: tuple[str, ...]


class IntentProvenanceLedger:
    """Retained evidence window binding intent, capability, inputs, and outputs."""

    def __init__(self, max_claims: int = 10_000):
        self.max_claims = max_claims
        self.claims: dict[str, ProvenanceClaim] = {}

    def observe(self, event: Interaction, trace_id: str) -> ProvenanceClaim:
        intent, operation = (
            _terms(event.user_intent),
            _terms({"tool": event.tool_name, "args": event.arguments}),
        )
        support = len(intent & operation) / max(1, len(operation))
        risk = min(1.0, (1.0 - support) * (1.0 if event.side_effect else 0.35))
        reasons = ("capability lacks direct support from stated intent",) if support < 0.20 else ()
        material = {
            "trace": trace_id,
            "session": event.session_id,
            "server": event.server_id,
            "capability": event.tool_name,
            "intent": _hash(event.user_intent),
            "input": _hash(event.arguments),
            "output": _hash(event.response),
        }
        claim = ProvenanceClaim(
            _hash(material)[:24],
            trace_id,
            event.session_id,
            event.server_id,
            event.tool_name,
            material["intent"],
            material["input"],
            material["output"],
            support,
            risk,
            reasons,
        )
        self.claims[claim.claim_id] = claim
        while len(self.claims) > self.max_claims:
            del self.claims[next(iter(self.claims))]
        return claim

    def trace(self, claim_id: str) -> dict[str, Any]:
        return asdict(self.claims[claim_id])


@dataclass(slots=True)
class CapabilityState:
    trust: float = 0.75
    accepted: int = 0
    restricted: int = 0


class CapabilityTrustController:
    def __init__(
        self,
        *,
        recoverable_trust: bool = True,
        corroborate_causal: bool = True,
        unreviewed_trust_floor: float = 0.20,
        legacy_mode: bool = False,
    ):
        self.states: dict[tuple[str, str], CapabilityState] = {}
        self.recoverable_trust = recoverable_trust
        self.corroborate_causal = corroborate_causal
        self.unreviewed_trust_floor = unreviewed_trust_floor
        self.legacy_mode = legacy_mode
        self.causal_history: dict[tuple[str, str], list[int]] = defaultdict(list)
        self.call_count: dict[tuple[str, str], int] = defaultdict(int)

    def decide(
        self,
        event: Interaction,
        risk: float,
        uncertainty: float,
        components: dict[str, Any] | None = None,
        reasons: list[str] | tuple[str, ...] | None = None,
    ) -> tuple[Action, CapabilityState]:
        key = (event.server_id, event.tool_name)
        state = self.states.setdefault(key, CapabilityState())
        effective = max(
            risk, 1 - state.trust, 0.65 if event.side_effect and uncertainty >= 0.55 else 0
        )
        action = SentinelEngine._action(effective, False)

        if self.legacy_mode:
            if action == Action.ALLOW:
                state.accepted += 1
                state.trust = min(1.0, state.trust + 0.006 * (1 - risk))
            else:
                state.restricted += 1
                current = max(risk, 0.65 if event.side_effect and uncertainty >= 0.55 else 0)
                if SentinelEngine._action(current, False) != Action.ALLOW:
                    state.trust = max(0.0, state.trust - 0.05 - 0.10 * risk)
            return action, state

        self.call_count[key] += 1
        current = max(risk, 0.65 if event.side_effect and uncertainty >= 0.55 else 0)
        current_action = SentinelEngine._action(current, False)

        if action == Action.ALLOW:
            state.accepted += 1
            state.trust = min(1.0, state.trust + 0.006 * (1 - risk))
        else:
            state.restricted += 1
            if current_action == Action.ALLOW:
                # 1. Recoverable trust:
                # Event itself is clean/benign. Action was restricted solely by historical
                # trust (1 - trust >= 0.45). Allow bounded recovery so historical trust
                # cannot permanently dominate as an absorbing state.
                if self.recoverable_trust:
                    state.trust = min(1.0, state.trust + 0.006 * (1 - risk))
            else:
                # 2. Corroborated causal penalties:
                # Do not penalize trust on an uncorroborated causal hard-floor flag alone;
                # require corroboration from at least one other orthogonal detector signal
                # or a repeated flag within a window.
                penalize = True
                has_policy_instruction = bool(
                    reasons
                    and any("policy" in r.lower() or "instruction" in r.lower() for r in reasons)
                )
                causal_risk = 0.0
                other_signals = False
                if components is not None:
                    causal_risk = components.get("causal", 0.0) or 0.0
                    other_signals = (
                        (components.get("behavior", 0.0) or 0.0) >= 0.55
                        or (components.get("intent", 0.0) or 0.0) >= 0.70
                        or (components.get("sequence", 0.0) or 0.0) >= 0.70
                        or bool(components.get("attestation", 0.0))
                        or bool(components.get("provenance", 0.0))
                        or has_policy_instruction
                    )

                if self.corroborate_causal:
                    if causal_risk >= 0.50 and not other_signals:
                        history = self.causal_history[key]
                        history.append(self.call_count[key])
                        recent = [t for t in history if self.call_count[key] - t <= 10]
                        self.causal_history[key] = recent
                        if len(recent) < 3:
                            penalize = False

                if penalize:
                    # 3. Trust floor against unreviewed isolation:
                    # Benign false alarms cannot drive trust below the unreviewed floor
                    # (preventing them from reaching isolation <= 0.18 on their own).
                    # Genuinely severe attacks or incidents can drive trust to 0.0.
                    is_incident_attack = risk >= 0.65 or has_policy_instruction or other_signals
                    floor = (
                        0.0
                        if is_incident_attack
                        else (
                            min(state.trust, 0.55)
                            if not other_signals
                            else self.unreviewed_trust_floor
                        )
                    )
                    state.trust = max(floor, state.trust - 0.05 - 0.10 * risk)

        return action, state


@dataclass
class Candidate:
    sessions: set[str] = field(default_factory=set)
    events: list[Interaction] = field(default_factory=list)
    attested: bool = False
    rejected: bool = False
    intent_digest: str = ""


class DualMemoryAdapter:
    def __init__(self, minimum_sessions: int = 3, *, max_entries: int = 4096):
        if type(minimum_sessions) is not int or minimum_sessions < 1:
            raise ValueError("minimum_sessions must be positive")
        self.max_entries = max_entries
        self.minimum_sessions = minimum_sessions
        self.trusted: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.candidates: dict[tuple[str, str, str], Candidate] = {}

    def _full(self) -> bool:
        return (
            len(self.candidates) + sum(len(items) for items in self.trusted.values())
            >= self.max_entries
        )

    @staticmethod
    def fingerprint(event: Interaction) -> str:
        shape = {k: type(v).__name__ for k, v in sorted(event.arguments.items())}
        return _hash({"tool": event.tool_name, "shape": shape, "cap": event.capability_digest})[:20]

    def reject(self, event: Interaction) -> None:
        key = (event.server_id, event.tool_name, self.fingerprint(event))
        if key not in self.candidates and self._full():
            return
        candidate = self.candidates.setdefault(key, Candidate())
        candidate.rejected = True
        candidate.events.clear()

    def observe(
        self,
        event: Interaction,
        risk: float,
        attested: bool,
        enrollment: bool,
        independent_session: str | None = None,
        *,
        promotion_approved: bool = True,
        require_fresh_attestation: bool = False,
    ) -> tuple[str, tuple[Interaction, ...]]:
        cap, fp = (event.server_id, event.tool_name), self.fingerprint(event)
        if not event.success:
            return "rejected", ()
        if enrollment:
            # The caller already enrolled this event in the approved model.
            if fp not in self.trusted.get(cap, ()) and self._full():
                return "capacity", ()
            self.trusted[cap].add(fp)
            return "trusted-enrollment", ()
        if fp in self.trusted.get(cap, ()) and risk < 0.42:
            return "trusted-existing", (event,)
        if (*cap, fp) not in self.candidates and self._full():
            return "capacity", ()
        key = (*cap, fp)
        candidate = self.candidates.setdefault(key, Candidate())
        intent_digest = _hash(event.user_intent)
        if candidate.intent_digest and candidate.intent_digest != intent_digest:
            candidate.rejected = True
            candidate.events.clear()
        candidate.intent_digest = intent_digest
        if risk >= 0.42 or candidate.rejected:
            candidate.rejected = True
            return "rejected", ()
        identity = event.session_id if independent_session is None else independent_session
        if identity and len(candidate.sessions) < self.minimum_sessions:
            candidate.sessions.add(identity)
        candidate.attested |= attested
        if len(candidate.events) < 32:
            candidate.events.append(copy.deepcopy(event))
        if len(candidate.sessions) >= self.minimum_sessions and candidate.attested:
            if not promotion_approved:
                return "awaiting-approval", ()
            if require_fresh_attestation and not attested:
                return "awaiting-attestation", ()
            promoted = tuple(candidate.events)
            self.trusted[cap].add(fp)
            del self.candidates[key]
            return "promoted", promoted
        return "candidate", ()


@dataclass(slots=True)
class NoveltyVerdict:
    base: Verdict
    action: Action
    capability_trust: float
    fused_risk: float
    claim_id: str
    counterfactual_risk: float
    memory_disposition: str
    promoted_events: int
    reasons: tuple[str, ...]

    def as_verdict(self) -> Verdict:
        return replace(
            self.base,
            action=self.action,
            anomaly_score=self.fused_risk,
            trust_score=self.capability_trust,
            reasons=list(self.reasons),
            components={**self.base.components, "counterfactual": self.counterfactual_risk},
        )


@dataclass(frozen=True)
class NoveltyConfig:
    intent_provenance: bool = True
    capability_trust: bool = True
    dual_memory: bool = True
    require_promotion_approval: bool = True
    recoverable_trust: bool = True
    corroborate_causal: bool = True
    unreviewed_trust_floor: float = 0.20
    legacy_capability_trust: bool = False
    causal_requires_response_origin: bool = False


class NoveltySentinelEngine:
    """Opt-in layer; approved Sentinel behavior and results remain unchanged."""

    def __init__(
        self,
        base: SentinelEngine | None = None,
        minimum_sessions: int = 3,
        config: NoveltyConfig | None = None,
    ):
        self.config = config or NoveltyConfig()
        if base is not None:
            self.base = base
            if self.config.causal_requires_response_origin:
                self.base.causal_graph.causal_requires_response_origin = True
        else:
            engine_cfg = EngineConfig(
                causal_requires_response_origin=self.config.causal_requires_response_origin
            )
            self.base = SentinelEngine(config=engine_cfg)
        self.provenance = IntentProvenanceLedger(self.base.retention.provenance_claims)
        self.capabilities = CapabilityTrustController(
            recoverable_trust=self.config.recoverable_trust,
            corroborate_causal=self.config.corroborate_causal,
            unreviewed_trust_floor=self.config.unreviewed_trust_floor,
            legacy_mode=self.config.legacy_capability_trust,
        )
        self.memory = DualMemoryAdapter(
            minimum_sessions, max_entries=self.base.retention.memory_entries
        )
        self.approvals = ReviewApprovals(self.base.retention.memory_entries)
        self.recovery_approvals = ReviewApprovals(self.base.retention.memory_entries)
        self.recovery_sessions: dict[tuple, set[str]] = {}

    def approval_key(self, event):
        return (
            event.server_id,
            event.tool_name,
            self.memory.fingerprint(event),
            _hash(event.user_intent),
        )

    def approve_promotion(self, event, *, reviewer, evidence_ref, ttl=300):
        """Operator grants reviewed shape/intent/manifest learning authority."""
        with self.base.lock:
            if (
                not event.capability_digest
                or self.base.attestation.enrolled.get(event.server_id) != event.capability_digest
            ):
                raise ValueError("promotion approval requires the enrolled manifest")
            self.approvals.grant(
                self.approval_key(event), reviewer=reviewer, evidence_ref=evidence_ref, ttl=ttl
            )

    def revoke_promotion(self, event):
        with self.base.lock:
            self.approvals.consume(self.approval_key(event))
            self.memory.trusted.get((event.server_id, event.tool_name), set()).discard(
                self.memory.fingerprint(event)
            )
            self.memory.reject(event)

    def recovery_key(self, event):
        return (*self.approval_key(event), _hash(event.arguments))

    def begin_recovery(self, event, *, reviewer, evidence_ref, ttl=300):
        """Authorize exact read-only probes after incident review; not a trust reset."""
        with self.base.lock:
            if (
                event.side_effect
                or not event.capability_digest
                or self.base.attestation.enrolled.get(event.server_id) != event.capability_digest
            ):
                raise ValueError(
                    "recovery requires a reviewed read-only probe on the enrolled manifest"
                )
            state = self.capabilities.states.get((event.server_id, event.tool_name))
            if state is None or state.trust >= 0.55:
                raise ValueError("capability is not restricted")
            key = self.recovery_key(event)
            self.recovery_approvals.grant(
                key, reviewer=reviewer, evidence_ref=evidence_ref, ttl=ttl
            )
            self.recovery_sessions = {
                k: v
                for k, v in self.recovery_sessions.items()
                if k in self.recovery_approvals.entries
            }
            self.recovery_sessions[key] = set()

    def cancel_recovery(self, event):
        with self.base.lock:
            key = self.recovery_key(event)
            self.recovery_approvals.consume(key)
            self.recovery_sessions.pop(key, None)

    def invalidate_reviews(self, event, reason):
        """An observed incident supersedes reviews for this capability only."""
        with self.base.lock:
            capability = (event.server_id, event.tool_name)
            counts = {}
            for name, registry in (
                ("promotion", self.approvals),
                ("recovery", self.recovery_approvals),
            ):
                keys = [key for key in registry.entries if key[:2] == capability]
                for key in keys:
                    registry.consume(key)
                counts[name] = len(keys)
            for key in list(self.recovery_sessions):
                if key[:2] == capability:
                    del self.recovery_sessions[key]
            if any(counts.values()):
                for key, candidate in self.memory.candidates.items():
                    if key[:2] == capability:
                        candidate.sessions.clear()
                        candidate.events.clear()
                        candidate.attested = False
            return {"reason": reason, "revoked": counts}

    def evaluate_recovery(self, event, *, independent_session, attested):
        """Trusted probe path. Never trains or restores candidate-learning authority."""
        with self.base.lock:
            key = self.recovery_key(event)
            approval = self.recovery_approvals.get(key)
            if (
                approval is None
                or not isinstance(independent_session, str)
                or not independent_session
            ):
                raise ValueError("active recovery review and independent identity required")
            base = self.base.evaluate(event, learn=False)
            claim = self.provenance.observe(event, base.trace_id)
            counterfactual = claim.counterfactual_risk if self.config.intent_provenance else 0
            risk = 1 - (1 - base.anomaly_score) * (1 - 0.55 * counterfactual)
            safe = (
                event.success
                and not event.side_effect
                and attested
                and risk < 0.42
                and not base.components["provenance"]
                and not base.components["attestation"]
                and event.capability_digest == self.base.attestation.enrolled.get(event.server_id)
            )
            recovered = False
            if not safe:
                invalidation = self.invalidate_reviews(event, "unsafe recovery probe")
                disposition = "recovery-failed"
            else:
                sessions = self.recovery_sessions.setdefault(key, set())
                sessions.add(independent_session)
                recovered = len(sessions) >= self.memory.minimum_sessions
                disposition = "recovered" if recovered else "recovery-probe"
                if recovered:
                    self.capabilities.states[(event.server_id, event.tool_name)].trust = 0.65
                    self.cancel_recovery(event)
            base.action = Action.OBSERVE if recovered else Action.CONFIRM
            base.anomaly_score = risk
            base.trust_score = self.capabilities.states[(event.server_id, event.tool_name)].trust
            base.baseline_updated = False
            base.provenance = {"recovery_review": asdict(approval), "disposition": disposition}
            if not safe:
                base.provenance["review_invalidation"] = invalidation
            base.reasons.append(disposition)
            return base

    def evaluate(
        self,
        event: Interaction,
        *,
        trusted_enrollment: bool = False,
        attested: bool = False,
        learn: bool = True,
        independent_session: str | None = None,
    ) -> NoveltyVerdict:
        with self.base.lock:
            return self._evaluate(
                event,
                trusted_enrollment=trusted_enrollment,
                attested=attested,
                learn=learn,
                independent_session=independent_session,
            )

    def _evaluate(
        self,
        event: Interaction,
        *,
        trusted_enrollment=False,
        attested=False,
        learn=True,
        independent_session=None,
    ):
        # attested is a trusted in-process assertion, never a client header.
        base = self.base.evaluate(event, learn=False)
        claim = self.provenance.observe(event, base.trace_id or _hash(event)[:16])
        counterfactual = claim.counterfactual_risk if self.config.intent_provenance else 0.0
        fused = 1 - (1 - base.anomaly_score) * (1 - 0.55 * counterfactual)
        incident = (
            not event.success
            or fused >= 0.42
            or base.components["provenance"]
            or base.components["attestation"]
        )
        if incident:
            invalidation = self.invalidate_reviews(event, "new capability incident")
            if any(invalidation["revoked"].values()):
                base.provenance = {**(base.provenance or {}), "review_invalidation": invalidation}
        if self.config.capability_trust:
            action, state = self.capabilities.decide(
                event, fused, base.uncertainty, components=base.components, reasons=base.reasons
            )
        else:
            action = self.base._action(fused, False)
            state = CapabilityState(base.trust_score)
        disposition, promoted = "frozen", ()
        eligible = (
            event.success
            and not base.components["provenance"]
            and not base.components["attestation"]
        )
        if learn and eligible and trusted_enrollment:
            disposition, _ = self.memory.observe(event, fused, attested, True)
            if disposition == "trusted-enrollment":
                self.base.learn_approved(event)
                base.baseline_updated = True
        elif learn and eligible and action == Action.ALLOW:
            if self.config.dual_memory:
                approval = (
                    self.approvals.get(self.approval_key(event))
                    if self.config.require_promotion_approval
                    else None
                )
                disposition, promoted = self.memory.observe(
                    event,
                    fused,
                    attested,
                    False,
                    independent_session,
                    promotion_approved=approval is not None
                    or not self.config.require_promotion_approval,
                    require_fresh_attestation=self.config.require_promotion_approval,
                )
                if disposition == "promoted" and approval is not None:
                    self.approvals.consume(self.approval_key(event))
                    base.provenance = {
                        **(base.provenance or {}),
                        "promotion_review": asdict(approval),
                    }
            elif fused < 0.42:
                disposition, promoted = "ungated", (event,)
            for item in promoted:
                self.base.learn_approved(item, update_sequence=disposition != "promoted")
            base.baseline_updated = bool(promoted)
        elif learn:
            disposition = "rejected"
            if self.config.dual_memory:
                self.memory.reject(event)
        reasons = tuple(
            dict.fromkeys(
                [*base.reasons, *(claim.reasons if self.config.intent_provenance else ())]
            )
        )
        # Accepted-origin checks must see the effective enforcement decision.
        base.action = action
        return NoveltyVerdict(
            base,
            action,
            state.trust,
            fused,
            claim.claim_id,
            counterfactual,
            disposition,
            len(promoted),
            reasons,
        )
