# Project status — October 23, 2026

Conference preparation: opt-in learning admission, 18 focused tests and a 40-case
functional demo added. The combined policy matches the standard transactional
baseline; no novelty or superiority is established. See
`learning_admission_prototype.md` and `conference_handoff_20261023.md`.
The corrected publication-scale run failed at 137/330 phases on a timeout.
The following October 16 pilot results remain unchanged.

Latest local stage: 480-cell offline verification-budget pilot completed; all 243
tests passed in 245.614 seconds. No planned comparison is significant after Holm
correction. First-available selection has lower mean malicious ingestion than
uncertainty; all fixed-probe recalls remain at zero. See `verification_budget.md`.
The live publication-scale matrix remains a separate unfinished run. No new
production defaults or historical outcomes were changed by this pilot.

Current additions: opt-in application-verified learning and its 100-cell synthetic
comparison are complete. The simple verified-immediate control matches combined
ingestion protection and adapts faster; incorrect responses still reach the caller.
See `verified_learning.md`. No permissioned real traces/server are available.

Validation: final full suite 235/235 passed in 227.487 seconds. Dependency check
and retained-research verification (43 files) passed. Commit `4e5cdb3` passed all
four Windows/Ubuntu and Python 3.11/3.14 jobs in GitHub run `38915893770`.
Draft PR #11 is open; independent review and merge are not claimed.

Targeted original-source comparison and an independent-review handoff are in
`prior_art_comparison_20261016.md` and `independent_review_packet.md`. Neither is
a completed independent review or a patentability conclusion.

The full-scale October 16 run failed after 20/330 phases on rejected provenance
issuance. A runner-only correction preserves denial rather than minting a claim;
the separate rerun subsequently failed at 137/330 phases on a timeout.
Do not aggregate the partial run.

The records below are historical snapshots, not current test counts.

Operator approval timing: 12 cells completed with immediate, delayed and withheld
simulated review. Clean-drift learning remained censored under all schedules;
admission recovery was five event steps. See `review_timing.md` for the eligibility
limitation and interpretation of simulated review counts.

Learning attribution is implemented in the sequential adaptation runner, including
buffered promotion replay. All 16 diagnostic cells have complete attribution; no
malicious learning updates occurred. Immediate eligible and gated policies remain
indistinguishable by these update counts. See `learning_attribution.md`.

Latest policy extension: exact expiring cross-server read permissions and trust
updates based on current evidence are implemented. All 201 tests passed. Two
16-cell diagnostics completed: grants reduced benign intervention to 3.33–16.67%,
while the no-grant control remained at 100%. Hidden-intent malicious intervention
was zero with grants. These are exploratory one-seed results; see `flow_policy.md`.

Enrollment investigation completed: repeated payload values within reused sessions
trigger the cross-server flow policy; historical trust then reinforces restrictions.
A schema-key tokenization defect is corrected, but the separate rerun still has
100% benign interventions. See `enrollment_investigation.md`; adaptation remains open.

Adaptation diagnostic: all 16 cells completed with 100% benign intervention and
zero updates. Initial audit evidence shows capability isolation already active
after enrollment. This prevents an adaptation comparison; enrollment trust needs
investigation. See `adaptation_protocol.md` and
`../results/adaptation/diagnostic-20261003/README.md`.

Dataset expansion: 1,050,380 additional synthetic input records across 20 seeds,
22 test scenarios and 480 compressed shards. Split totals: 200,000 TRAIN,
40,000 VALIDATION, 810,380 TEST. These are not new performance results or
independent runtime traces. See `dataset_expansion.md` and `../datasets/README.md`.
Latest full-suite rerun: **187 tests passed in 92.714 seconds**. The preceding run
had one Windows socket-abort error, documented without changing tests/timeouts.

The visual dashboard is implemented and browser-verified against safe mock servers
and actual HTTP gateways. All 184 tests passed in 91.357 seconds; the wheel contains
its frontend assets. See `dashboard.md` and `dashboard_verification.md`. Research
experiments, independent traces and human approval gates remain open below.

September 25 continuation: final full suite **177 tests passed in 57.248 seconds**; dependency
checks passed and all 43 retained-evidence files passed verification. An
unchanged-settings full-scale rerun failed while opening a local TCP connection
after one of 330 phase records; its partial artifacts and failure note are kept
in `results/novelty/publication-scale-20260925`. New runner instrumentation records
exact phase/request context on subsequent failures without retries or retuning.
A two-scenario, single-seed instrumented diagnostic then completed successfully;
it does not establish a root cause or replace the full matrix.
Pinned MCPSecBench inspection found prompt specifications, not usable event-level
runtime traces. Full-matrix inference, independent evaluation and human gates
remain unfinished. See the README's September 25 section.

September 21 history: PR #5 merged at `d6d1884`. The research-completion branch adds a
primary-endpoint statistical reporter, vector figure generator, automated technical
review, preliminary prior-art screen, invention-disclosure draft and paper draft.
175 tests passed locally. The publication-scale exploratory attempt failed on an HTTP timeout;
complete analysis/figures, independent runtime data and human approvals remain open.
See the README's September 21 section for commands and precise completion criteria.

The earlier candidate snapshot below is preserved as historical evidence.

Implementation snapshot: GitHub `main` at
`ecdf974f585a23170d2c8fc685b60923ea166517`, including the merged gateway
completion milestone. This is the current integration-freeze candidate, not an
approved release or preregistered experiment.

Scope boundary: all work accepted through `be68d6f` remains included. Further work
is limited to completing, fixing, testing and documenting the agreed project.
Additional features, mechanisms or policy requirements need an explicit user request.

Overall completion was estimated at roughly **75%** for planning discussions.
This is a judgment about the agreed prototype/research scope, not a computed
completion metric, security score or production-readiness assessment. Remaining
research and review work has variable effort; use the checklist below for decisions.

## Completed implementation

- [x] Repository audit, roadmap and contribution log.
- [x] Behavioral, intent and causal analysis with protected online learning.
- [x] Pre-dispatch provenance authorization and replay protection.
- [x] Opt-in capability trust and dual-memory integration in the live HTTP gateway.
- [x] Eight deterministic adversarial scenarios and component ablations.
- [x] Separated TRAIN/VALIDATION/TEST/ADAPTIVE phases and checkpoint restoration.
- [x] Attestation expiry, server binding and atomic single-use verification.
- [x] Strict JSON/HTTP framing, tool metadata and interaction validation.
- [x] Bounded evidence retention and fail-closed identity admission.
- [x] Connection limits and request socket deadlines, with documented limitations.
- [x] Operator review and fresh attestation for novel memory promotion.
- [x] Reviewed capability recovery without training the model.
- [x] Capability-scoped review invalidation after new incidents.
- [x] Base-engine attestation failures block learning; novelty enrollment honors memory capacity.
- [x] Development experiments, documentation and regression coverage.
- [x] Verify CI for `bc70a3b` and access for all five listed team accounts.
- [x] Draft the experiment protocol for team review (not formally preregistered).
- [x] Implement optional validation-only secondary score calibration, persisted before TEST.

## Verified evidence

- **170 tests passed** on September 20 from an exported GitHub `origin/main`
  snapshot, including gateway component-switch, audit-evidence and live partial-
  isolation regressions. The run used the reproducibility environment on Windows.
- The preceding implementation `bc70a3b` passed all four fresh-runner CI jobs:
  Windows/Ubuntu × Python 3.11/3.14.
  [Main run](https://github.com/snehathesingh-stack/MCP-Runtime-Sentinel/actions/runs/35252538627)
  and [feature run](https://github.com/snehathesingh-stack/MCP-Runtime-Sentinel/actions/runs/35252538837).
- Collaborator access is verified. Pending invitations cannot be listed with the
  current account (HTTP 403); no access settings or invitations were changed.
- CLI calibration smoke completed in `artifacts/validation-protocol-smoke-20260917/`
  with a saved calibration artifact and separate score report. This tiny synthetic
  run verifies execution, not research performance or publication evidence.
- Dependencies and retained-research verification passed (43 files). Historical
  results remain unchanged.
- Development matrices are smoke evidence. Preventing model updates is distinct
  from denying attacks; approval-required mode also withholds learning of legitimate
  changes until reviewed. Statistical superiority and production security have not
  been established by these runs.

## Remaining work, in order

1. [ ] Complete mechanism/threat-model reviews.
2. [ ] Review/finalize the drafted hypotheses, metrics, seeds and comparisons; formally preregister.
3. [ ] Obtain team approval of the implemented validation-only workflow and proposed protocol settings.
4. [ ] Obtain team approval of the experimental commit and freeze a release/tag.
5. [ ] Run publication-scale novelty experiments and independent MCP trace evaluation.
6. [ ] Generate final novelty tables, figures, limitations and claims audit.
7. [ ] Complete prior-art review before publication/disclosure decisions.

Protocol preparation and validation-workflow implementation are complete within
the agreed scope. Team approval, external review and preregistration are not implied by
an implementation commit. Deployment authentication, durable audit export and
additional transports remain future work.

## Documentation map and maintenance

- [Team checklist and freeze criteria](team_workplan.md)
- [Runtime boundary hardening](runtime_hardening.md)
- [Runtime controls and lifecycle corrections](runtime_controls.md)
- [Novelty runner and assumptions](novelty_experiments.md)
- [Draft evaluation protocol](novelty_protocol.md)
- [Historical development findings](novelty_development_findings.md)
- [Contribution evidence](contribution_log.md)

Update this snapshot, the README summary and the detailed checklist when a
milestone changes behavior, validation evidence or remaining work. Keep earlier
milestone documents dated; mark superseded behavior rather than rewriting old
experimental findings as if they described the current policy.

The integration lead's candidate evidence and sign-off form are maintained in
[integration_freeze_candidate.md](integration_freeze_candidate.md).

## September 18 — Member 4 local gateway handoff

Existing component switches now reach the live wrapper via GatewayConfig and CLI.
Audits include blocked capability context, evaluated novelty claims and dispatch
failure records. Six new gateway regressions bring the local passing suite to
170 tests (Linux/Python 3.12). See `gateway_completion.md` for the handoff,
`gateway_pull_request.md` for the review draft. Upstream CI and teammate approval
remain pending; publication experiments and prior-art review are not completed by
this engineering milestone.
