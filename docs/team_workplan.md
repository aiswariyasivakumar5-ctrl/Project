# Team work plan and research freeze

## Purpose

This file is the shared source of truth for the five-person MCP Runtime Sentinel
team. Update it through reviewed pull requests. GitHub activity alone does not
establish research authorship or patent inventorship.

## Team and current access

| GitHub account | Working role | Access status |
|---|---|---|
| `snehathesingh-stack` | Integration lead and evidence custodian | Owner |
| `230069` | Intent provenance and counterfactual review | Accepted |
| `aiswariyasivakumar5-ctrl` | Dual-memory and poisoning review | Write access verified |
| `shamkumar8209-cpu` | Capability-level gateway integration | Write access verified |
| `SourabhiPrabakaran` | Adversarial scenarios and experiment design | Write access verified |

Roles describe planned work, not authorship or inventorship. Record actual work in
`docs/contribution_log.md`.

GitHub collaborator listing verified September 17, 2026: all five listed accounts
have access (`230069` and three collaborators: write; owner: admin). The current
account cannot read pending invitations (HTTP 403); this does not negate verified
access. No permissions or invitations were changed.

## Frozen research scope

User scope constraint: previously implemented additions remain accepted. Future
work must stay within the agreed scope; no new features, mechanisms or policy
requirements without an explicit request. Correctness fixes and verification of
existing functionality remain in scope.

The primary system is an MCP runtime security gateway combining:

1. intent-conditioned behavioral and causal monitoring;
2. uncertainty-triggered behavioral attestation;
3. quarantine-protected online learning;
4. hash-linked intent provenance;
5. capability-specific trust and enforcement; and
6. evidence-gated candidate-to-trusted memory promotion.

Do not add federated learning, hardware/TEE attestation, general collusion learning,
or additional model families before the novelty evaluation is complete. Such ideas
belong in future work unless the team formally changes the scope before experiment
freeze.

## Work sequence

Runtime hardening progress is tracked in `runtime_hardening.md` and
`runtime_controls.md`. The following engineering items are implemented, pending review:

- [x] Bounded audit, causal, provenance and quarantine retention; fail-closed identity admission.
- [x] Total socket request budgets and connection/concurrency admission limits.
- [x] Trusted operator approval for novel memory promotion (new default policy).
- [x] Reviewed capability recovery without model training or automatic trust resets.
- [x] Fresh attestation at reviewed promotion; capability-scoped review invalidation after new incidents.
- [x] Consistent learning guards for attestation failures and full novelty enrollment memory.

- [x] Merge the opt-in novelty implementation into `main`.
- [x] All listed collaborators have repository access (verified collaborator listing).
- [ ] Each technical owner reviews their assigned mechanism on a separate branch.
- [x] Integrate capability-level decisions into the live MCP gateway (opt-in `--novelty`; pending team review).
- [x] Implement the adversarial scenario catalog and regression tests (coverage and threat-model review remain pending; see `novelty_experiments.md`).
- [ ] Review threat assumptions and resolve defects through pull requests.
- [x] Run the complete test suite (170 tests pass from an exported `origin/main`
  snapshot at `ecdf974`; preceding `bc70a3b` passed four fresh CI jobs).
- [ ] Approve and freeze a release commit/tag.
- [ ] Preregister novelty hypotheses, metrics, seeds, and statistical comparisons.
- [x] Prepare a reviewable draft protocol (`novelty_protocol.md`); formal registration remains pending.
- [x] Implement validation-only quantile selection for secondary score metrics, independent of gateway policy.
- [ ] Run publication-scale novelty experiments without test-set tuning.
- [ ] Generate tables, figures, limitations, and claims audit.
- [ ] Complete prior-art review before public disclosure or conference submission.

## Required branch workflow

1. Branch from the latest `main`.
2. Keep one assigned concern per branch.
3. Add tests for behavioral changes.
4. Run the complete suite before requesting review.
5. Open a pull request into `main` and request at least one teammate review.
6. Record conception and implementation facts in the contribution log.
7. Do not rewrite or delete retained research results.

## Experiment freeze criteria

Final novelty experiments may begin only when all boxes below are checked:

- [x] Gateway exercises the novelty engine end to end (live mock-server regression test).
- [x] Novelty scoring, capability trust and dual-memory components have actual ablation switches in the live study runner; claim authorization is not ablated.
- [x] Attack generators are deterministic under recorded seeds.
- [x] Train, validation, test, and adaptive phases are explicitly separated.
- [x] Optional secondary score threshold fits benign VALIDATION only and is saved before TEST; gateway bands remain fixed.
- [x] Test evaluation performs no learning; declared adaptive runs restore an independent post-TRAIN checkpoint.
- [x] Metrics and paired statistical comparisons are specified in advance in
  `novelty_protocol.md`; formal registration and team approval remain open gates.
- [x] Full suite passes from fresh CI environments (`bc70a3b`: Windows/Ubuntu, Python 3.11/3.14).
- [ ] Team approves a commit hash as the frozen experimental implementation.

The current integration candidate is `ecdf974f585a23170d2c8fc685b60923ea166517`.
This records a candidate, not team approval or a release freeze. See
`integration_freeze_candidate.md` for the evidence and required sign-offs.

## Communication rule

October 3: the requested local visual dashboard is complete and browser-verified;
all 184 tests pass. It runs safe mock scenarios through real gateways, not production
servers. This closes the demo UI task only; experiment and human review gates remain.

September 25 update: 177 tests pass, including two new failure-recording/output-
preservation regressions. The full-scale rerun failed after one phase record on
TCP connect timeout. Runner diagnostics now retain exact phase/request context.
External-data schema/license inspection is documented at a pinned revision, but
does not supply runtime traces. Publication experiments and human review boxes
remain unchecked; no new performance or significance claim is supported.

September 21 execution update: the integration lead completed an automated technical
review and research drafts, and added primary-comparison reporting and plotting scripts.
These are prepared artifacts, not teammate sign-offs. The full-scale exploratory run
failed after seven phase records on a client HTTP timeout; final results/figures and
release approval remain unchecked. See README and `technical_review_20260921.md`.

Use the shared ChatGPT Project for discussion, but place every final decision,
protocol, correction, and result interpretation in this private repository so it is
dated, reviewable, and reproducible.

Current implementation and verification evidence are summarized in
[project_status.md](project_status.md). Keep that summary and the README aligned
with this checklist when milestones land.
