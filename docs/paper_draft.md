# MCP Runtime Sentinel: Context-Bound Authorization and Evidence-Gated Runtime Adaptation

Working manuscript, September 21, 2026. Author list, affiliations and target venue
are to be supplied by the team. Novelty-study results must be inserted only after
the complete matrix and statistical report finish. This draft is not submission-ready.

## Abstract

AI agents that invoke external tools require runtime controls beyond initial access
permissions. We present MCP Runtime Sentinel, a research gateway that combines
behavioral reconstruction error, intent consistency, temporal dependencies, runtime
trust and quarantine-protected learning. Its extension binds tool invocations to
single-use causal-context claims, isolates trust by capability and conditions model
adaptation on retained evidence and optional operator review. We evaluate the original
prototype using five-seed synthetic comparisons and preserve both favorable and
adverse outcomes. At its retained operating threshold, the original Sentinel reports
F1 0.7999, recall 0.6667 and false-positive rate approximately 0.0001, while a dense
autoencoder obtains higher recall with substantially more false positives. A separate
live-gateway study evaluates six configurations across eight adversarial/control
scenarios with independent frozen and adaptive phases. That larger study is in progress;
no new aggregate performance claim is made here. The evidence supports an inspectable
prototype and explicit security/learning tradeoffs, subject to synthetic workloads,
limited statistical power and a restricted MCP transport implementation.

## 1. Introduction

Tool authorization determines whether an action is permitted, but runtime evidence
also depends on how the request relates to accepted context, earlier tool outputs
and a server's changing behavior. Monitoring creates a second problem when observed
traffic is used for training: an attacker may influence the baseline itself. Sentinel
examines these enforcement and adaptation questions together.

Our contribution is an implemented and testable combination of per-invocation
authorization, capability-scoped enforcement and evidence-gated adaptation. We do not
claim to originate anomaly detection, provenance, quarantine or MCP gateways. The
evaluation distinguishes attack intervention, benign collateral denial and model
updates, which are not interchangeable measures of protection.

## 2. Related work

[MCP Guardian](https://arxiv.org/abs/2504.12757) studies an MCP security layer.
[MindGuard](https://arxiv.org/abs/2508.20412) uses decision dependence graphs and
attention-derived signals to track and attribute metadata poisoning. Sentinel operates
at a tool gateway and does not require attention access. [Rosado's capability-pinning
disclosure](https://www.tdcommons.org/dpubs_series/10604/) describes identity-bound
tool-surface pins, structural-change checks and reapproval. Sentinel's implementation
instead focuses on per-call authorization consumption and learning-state transitions;
it lacks that disclosure's cryptographic workload identity. These differences require
full-text comparison before stronger originality claims. See `prior_art_screening.md`.

The October 16 [targeted comparison](prior_art_comparison_20261016.md) adds
[ShieldMCP](https://aclanthology.org/2026.acl-industry.58/), whose proxy, dependency
tracking and tool-change reauthorization overlap broad Sentinel descriptions.
Single-use invocation authorization and learning-evidence lifecycle remain candidate
technical distinctions requiring independent review, not established originality.

## 3. Threat model

The adversary may control tool responses, misuse a capability, replay or delay a claim,
rotate raw sessions, or coordinate multiple compromised identities. The gateway and
its issuer are trusted, as is the initial enrollment dataset. Test labels are not
provided to the detector. Identity independence is supplied by an in-process fixture;
caller-controlled headers cannot manufacture trusted identities in that fixture.

The system does not defend a compromised gateway process, establish remote hardware
integrity, or reverse side effects that occurred before response inspection. Network
authentication, durable audit and distributed operation are outside the prototype.

## 4. Design and implementation

Requests pass through metadata and preflight checks before upstream dispatch. Optional
required-provenance mode demands an issuer claim binding session, server, tool, intent,
arguments, expiry and causal predecessor. Claim consumption is atomic and occurs before
dispatch, so an upstream failure does not make it reusable. Retention eviction or
invalid causal evidence fails closed.

The base engine combines behavioral, intent, sequence, causal, capability and attestation
signals. Server trust evolves over calls. The extension adds per-server/tool trust to
reduce collateral restriction of unrelated capabilities. Its intent-support term is
lexical overlap, despite the internal name `counterfactual_risk`; it is not an estimated
causal counterfactual.

Dual memory separates candidates from accepted argument shapes. Candidate promotion
uses independent identities and attestation; the current default additionally requires
scoped operator approval and fresh attestation. Incidents invalidate relevant reviews.
Recovery uses approved read-only probes and does not train the model. The research
variant named `full` intentionally retains the earlier policy without operator approval;
`approval_required` evaluates the current default in a fixture with no approvals.

## 5. Evaluation method

The original comparisons and ablations remain in `results/final` and `results/tables`.
The new protocol uses seeds 42, 123, 456, 789 and 1001, six variants, eight scenarios,
5,000 TRAIN events, 1,000 benign VALIDATION events and a requested scenario size of
3,000. Actual emitted sizes must be reported. Every scenario TEST and ADAPTIVE phase
restores an independent post-TRAIN checkpoint. Frozen phases are checked for unchanged
learning-state hashes.

Actual gateway interventions are primary runtime outcomes. Secondary score decisions
use the validation 99th percentile (`higher`, strict greater-than), fixed before TEST.
Seeds are the unit of inference. The four planned primary comparisons are capability
FPR, single-actor poisoning updates, coordinated-server recall and multi-actor poisoning
updates under operator review. We use paired exact sign-flip tests with Holm correction
and 95% seed-bootstrap intervals with 20,000 resamples and RNG seed 2026. Five nonzero
pairs imply minimum two-sided p=0.0625. Undefined metrics and undetected attacks are
reported explicitly. The new execution is exploratory; it is not externally preregistered.

## 6. Retained results and tradeoffs

The original Sentinel's F1 0.7999 is below dense autoencoder F1 0.8944, with much lower
observed FPR (approximately 0.0001 versus 0.0783). Removing causal scoring raises recall
to 0.9167 and F1 to 0.9127 but raises FPR to 0.0789. This is a calibration interaction,
not evidence that causal information intrinsically harms detection. A tied validation
score mass at 0.50 affects strict high-quantile threshold decisions.

Isolation Forest's retained AUROC of approximately 0.8899 indicates useful ordering,
while zero recall at its selected threshold indicates an ineffective operating point.
Ranking quality does not guarantee useful decisions at a particular validation threshold.
The existing diagnosis and validation-only fusion study are retained; thresholds have
not been retuned using these test findings.

The original model misses capability drift, low-and-slow behavior, gradual poisoning
in frozen TEST and abnormal sequence behavior. Quarantine's prevention of model updates
in adaptive poisoning does not imply detection of those same events. Sequence baselines
use fixed encoders with trained reconstruction heads and must not be described as fully
end-to-end trained LSTM or Transformer networks.

### New novelty results: pending complete execution

Insert the generated `statistics.json`, primary-comparison table and scenario figures
after completeness validation. Report unfavorable effects and no-difference outcomes.
Do not substitute the retained offline numbers for the new live-gateway results.

Separate descriptive development controls completed 100 cells across five training-
order seeds, four policies and five arithmetic streams. Application-side result
verification prevented malicious-source learning in those fixtures. The simpler
verified-immediate policy matched verified dual memory's ingestion protection and
adapted faster. Neither blocked the incorrect responses. These controls establish
neither general poisoning resistance nor a benefit attributable to combined memory
gating. See `verified_learning.md`; no significance claims are made for that study.

The October 16 publication-scale attempt failed at 20/330 phases when the runner
assumed a rejected origin could issue provenance. A runner-only correction records
the failed issuance and preserves subsequent attempted calls without granting
authority. Failed-run artifacts remain retained; a corrected full rerun is separate.
Denial of an origin is not evidence of expired/replay detection on a valid claim.

## 7. Limitations

Synthetic fixtures and five seeds constrain generalization. Behaviorally identical
malicious and benign actions can be indistinguishable. Attestation is a manifest echo,
not proof of benign execution. Argument-shape trust does not establish value safety.
Claims and audit state are bounded and process-local. Supported HTTP JSON-RPC behavior
does not constitute complete MCP transport support. Sequential local latency does not
measure production capacity; gateway latency alone is not direct-server overhead.
Bootstrap coverage is descriptive, and constant synthetic outcomes can yield degenerate
intervals. Independently sourced runtime traces and a formal prior-art review remain open.

## 8. Reproducibility and conclusion

The repository stores code, tests, configuration, source/workload hashes and retained
per-seed artifacts. `docs/novelty_protocol.md` documents the study settings; the README
gives reporting commands. Sentinel demonstrates how context-bound authorization and
reviewed model adaptation can be examined within a gateway prototype. Broader efficacy
and legal originality remain questions for independent evidence and professional review.
