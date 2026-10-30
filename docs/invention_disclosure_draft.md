# Invention disclosure working draft

Status: technical briefing for the team and a qualified patent professional.
Human inventors, dates of conception, ownership and legal claim scope are unconfirmed.
See `prior_art_screening.md` before asserting technical originality.

## Technical problem

Tool permission and historical server trust alone do not establish that a particular
invocation remains tied to an accepted causal context, or that a new observed behavior
should be allowed to train a runtime model.

## Implemented mechanism candidates

### Context-bound, single-use pre-dispatch authorization

The trusted issuer creates a claim binding accepted causal evidence, session, server,
tool, intent, argument digest, predecessor and expiry. The gateway validates this
binding and consumes the claim atomically before upstream dispatch. Invalid evidence,
expiry or replay denies the invocation; failed dispatch does not restore the claim.
Evidence: `sentinel/provenance.py`, `sentinel/gateway.py`, provenance and runtime tests.

### Capability-scoped enforcement with reviewed adaptation

Trust is associated with a server/tool pair. A problematic capability can be restricted
while unrelated capabilities remain available. New argument-shape observations enter
candidate memory. Promotion requires the configured identity evidence, attestation and,
in the current default policy, scoped operator review. New incidents revoke relevant
reviews; approved recovery probes do not train the model.
Evidence: `sentinel/novelty.py`, `sentinel/approvals.py`, promotion/recovery/gateway tests.

## Technical effects to measure

Prevention of repeated dispatch, reduction in collateral benign blocking, prevention
of unapproved model updates, legitimate-adaptation cost and processing/storage overhead.
Functional tests exist. Population effects and novelty-study superiority must be tied
to completed result artifacts; no numerical benefit is claimed here.

## Boundaries and alternatives

The implementation uses process-local locks and memory. Durable consumed-token storage,
cryptographic issuer identities and distributed deployments are possible future designs,
not implemented embodiments. Manifest echo is not hardware attestation. The lexical
intent score is not a causal counterfactual model.

## Information the human team must supply

- Each person's specific conception contribution and dated supporting evidence.
- Earliest disclosures, presentations, repository visibility history and agreements.
- Institution/employer ownership obligations and funding arrangements.
- Full prior-art claim mapping, filing jurisdiction and professional advice.

This draft describes implemented mechanisms; it does not identify legal inventors,
draft final legal claims, establish patentability or certify freedom to operate.
