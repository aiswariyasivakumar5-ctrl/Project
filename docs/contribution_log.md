# Contribution and conception log

This is an evidence record, not a legal conclusion. Complete one entry per material
idea or implementation. Do not infer inventorship from commit counts, job titles,
supervision, testing, or funding. A qualified patent professional must determine
inventorship from the claims ultimately pursued.

## Entry template

Copy this section for each contribution:

### YYYY-MM-DD — Short contribution title

- **Contributor(s):** Full legal name and GitHub account
- **Type:** conception / implementation / experiment / analysis / documentation
- **Problem addressed:**
- **Original technical idea contributed:**
- **Implementation performed:**
- **Evidence:** issue, pull request, commit, dated note, or meeting record
- **Related proposed patent claim or paper section:**
- **Reviewed by:**
- **Notes or disputes:**

## Initial records requiring team confirmation

### 2026-08-31 — Approved MCP Runtime Sentinel research prototype

- **Contributor(s):** To be completed by the team
- **Type:** conception, implementation, experiment, analysis, documentation
- **Problem addressed:** Runtime trust and anomaly detection for MCP servers
- **Original technical idea contributed:** Confirm the originators of each component
- **Implementation performed:** Initial repository commit `f7594af`
- **Evidence:** repository history and retained research artifacts
- **Related proposed patent claim or paper section:** Existing Sentinel architecture
- **Reviewed by:** Pending all team members
- **Notes or disputes:** Do not assign inventorship until individual contributions are recorded

### 2026-09-01 — Evidence-gated capability trust extension

- **Contributor(s):** To be confirmed; repository commit currently identifies Sneha Singh as author
- **Type:** conception and implementation must be distinguished by the team
- **Problem addressed:** Server-wide trust and immediate online learning lack capability isolation and evidence-gated adaptation
- **Original technical idea contributed:** Identify contributors to provenance claims, capability trust, and dual-memory promotion separately
- **Implementation performed:** Novelty extension commit `2fcd16b`
- **Evidence:** pull request `#1`, source, tests, and `docs/novelty_milestone.md`
- **Related proposed patent claim or paper section:** Evidence-gated capability-level runtime trust
- **Reviewed by:** Pending technical-owner reviews
- **Notes or disputes:** AI-assisted implementation does not determine human inventorship

## Decision log

### 2026-09-17 — Three-step validation preparation (pending review)

- **Contributor(s):** AI-assisted implementation requested in the `230069` workspace; human attribution requires team confirmation.
- **Type:** read-only verification, protocol drafting and existing evaluation-workflow completion.
- **Implementation performed:** verified all four CI jobs for `bc70a3b` and access for all listed collaborators; drafted `novelty_protocol.md`; added optional validation-only secondary score calibration using the existing comparison quantile rule.
- **Evidence:** branch `feature/validation-protocol`, `tests/test_validation_calibration.py`, saved pre-TEST calibration artifacts and separate score reports. Main CI evidence: run `35252538627`.
- **Reviewed by:** Pending team review. Draft is not preregistered; no publication-scale experiment, release freeze, invitation mutation or teammate message was performed. Stopped after the three requested steps.

### 2026-09-17 — Existing learning-guard consistency (pending review)

- **Contributor(s):** AI-assisted implementation requested in the `230069` workspace; human attribution requires team confirmation.
- **Type:** correctness fixes, regression testing and documentation within accepted scope.
- **Implementation performed:** prevent base-engine learning on failed attestation/manifest checks; make novelty enrollment honor its existing memory-capacity rejection.
- **Evidence:** branch `fix/learning-guard-consistency`, `tests/test_learning_guards.py`. Regressions reproduced before the fixes; positive controls preserve explicit ablation and existing-shape enrollment behavior.
- **Reviewed by:** Pending teammate review; no new feature, detector, threshold or experimental-freeze approval.

### 2026-09-17 — Review evidence lifecycle corrections (pending review)

- **Contributor(s):** AI-assisted implementation requested in the `230069` workspace; human attribution requires team confirmation.
- **Type:** security corrections and regression testing.
- **Implementation performed:** reproduced stale-attestation promotion and recovery-after-new-incident defects; require fresh evidence for reviewed promotion, invalidate affected pending reviews and recovery progress, prevent novelty enrollment on failed attestation/manifest checks.
- **Evidence:** branch `fix/review-evidence-lifecycle`, promotion/recovery regression tests, `docs/runtime_controls.md`.
- **Reviewed by:** Pending teammate review. Prior runtime-controls commit `25b79d3` passed GitHub CI on both feature and main branches.

### 2026-09-17 — Retention, HTTP limits and reviewed adaptation (pending review)

- **Contributor(s):** AI-assisted implementation requested in the `230069` workspace; human attribution requires team confirmation.
- **Type:** implementation, regression testing and development evaluation.
- **Implementation performed:** bounded evidence stores and identity admission, request budgets and connection limits, scoped promotion approvals, reviewed non-learning capability recovery, explicit approval-required research variant.
- **Evidence:** branch `feature/runtime-controls`, `docs/runtime_controls.md`, retention/HTTP-limit/promotion/recovery regression tests.
- **Reviewed by:** Pending technical-owner review; no experiment-freeze approval or inventorship assignment.

### 2026-09-17 — Runtime boundary hardening (pending review)

- **Contributor(s):** AI-assisted implementation requested in the `230069` workspace; human attribution requires team confirmation.
- **Type:** implementation, security regression testing and documentation.
- **Implementation performed:** expiring server-bound atomic attestation, pending-challenge capacity, strict JSON/HTTP framing, validated interaction and tool metadata boundaries.
- **Evidence:** branch `feature/runtime-hardening`, `tests/test_http_hardening.py`, `docs/runtime_hardening.md`.
- **Reviewed by:** Pending teammate review; no experiment-freeze approval.

### 2026-09-17 — Live novelty experiment framework (pending review)

- **Contributor(s):** AI-assisted implementation requested in the `230069` workspace; human attribution requires team confirmation.
- **Type:** implementation, scenario design, development experiments and regression testing.
- **Implementation performed:** live baseline/full/component-ablation runner, complete checkpoint restoration, eight deterministic scenarios, trusted identity fixtures, immutable output reservation and per-seed exploratory reporting. Corrected capability-ablation preflight and sticky candidate rejection discovered during integration.
- **Evidence:** branch `feature/novelty-experiment-framework`, `sentinel/novelty_experiment.py`, `sentinel/novelty_scenarios.py`, `tests/test_novelty_experiment.py`, `docs/novelty_experiments.md`.
- **Reviewed by:** Pending; this entry does not approve an experiment freeze or assign inventorship.

### 2026-09-17 — Runtime correctness and opt-in gateway integration (pending review)

- **Contributor(s):** AI-assisted local implementation requested in the `230069` workspace; human conception/attribution requires team confirmation.
- **Type:** implementation, regression testing, metric correction and documentation.
- **Implementation performed:** pre-dispatch provenance consumption, warm-up/error learning fixes, notification validation, exactly-once novelty updates, opt-in gateway integration, separate AUROC correction artifact and CI configuration.
- **Evidence:** local branch `fix/runtime-correctness-and-novelty`, `tests/test_runtime_regressions.py`, `docs/runtime_continuation.md`, `results/corrections/auroc-v1.json`.
- **Reviewed by:** Pending teammate review; no claim of inventorship or experiment-freeze approval.

| Date | Decision | Participants | Evidence |
|---|---|---|---|
| 2026-09-01 | Keep repository private during patent planning | To confirm | Repository visibility |
| 2026-09-01 | Freeze novelty around provenance, capability trust, and dual memory | To confirm | `docs/team_workplan.md` |
| 2026-09-01 | Preserve approved Sentinel results as an unchanged control | To confirm | Retained result artifacts |

### 2026-09-18 — Member 4 gateway integration completion (pending team review)

- **Contributor(s):** User-requested AI-assisted implementation; human attribution requires team confirmation.
- **Type:** gateway integration, regression testing and documentation.
- **Implementation performed:** expose existing novelty component configuration through GatewayConfig/CLI; enrich rejected/evaluated-call audit evidence; audit upstream dispatch failures; live partial-isolation regression.
- **Evidence:** local snapshot branch `feature/gateway-completion`, `tests/test_gateway_completion.py`, `docs/gateway_completion.md`, supplied patch. Local branch does not contain original upstream history.
- **Reviewed by:** Pending teammate review. No claim of conception, inventorship, GitHub merge, release freeze or experimental approval.

### 2026-09-20 — Integration-freeze candidate preparation

- **Contributor(s):** Sneha Singh (`snehathesingh-stack`), with AI-assisted documentation and verification at her request.
- **Type:** integration, verification and documentation.
- **Problem addressed:** The repository status documents still described a local gateway handoff and an older 164-test snapshot after pull request #4 had merged.
- **Original technical idea contributed:** No new research mechanism or patent conception is asserted by this administrative integration record.
- **Implementation performed:** reconciled the work plan, README and project status with GitHub `main`; identified the exact integration candidate; recorded machine-verifiable freeze evidence and preserved all human review, preregistration and release gates.
- **Evidence:** `ecdf974f585a23170d2c8fc685b60923ea166517`, 170-test exported-snapshot run, `docs/integration_freeze_candidate.md`, and this branch's pull request when opened.
- **Related proposed patent claim or paper section:** Reproducibility and research-governance evidence only; no inventorship inference.
- **Reviewed by:** Pending teammate review.
- **Notes or disputes:** This entry does not constitute team approval, preregistration, a release tag, authorship allocation or patent inventorship determination.

### 2026-09-21 — Research reporting and evidence preparation

- **Contributor(s):** AI-assisted implementation at Sneha Singh's request; human conception/attribution remains for team confirmation.
- **Type:** statistical reporting, tests, automated technical review and drafting.
- **Implementation performed:** planned-primary-endpoint reporter, missing-matrix/workload checks, defined-metric handling, vector plotting script, preliminary prior-art screen, technical disclosure and paper drafts; initiated the specified full-scale exploratory run on `d6d1884`.
- **Evidence:** `sentinel/novelty_report.py`, `sentinel/novelty_figures.py`, `tests/test_novelty_report.py`, September 21 documents, run `protocol.json`; 175 tests passed locally. The full-scale attempt failed; the focused unchanged-settings diagnostic passed. Both are retained.
- **Reviewed by:** Pending human review. No approvals, external registration, full-scale outcome, inventorship or patentability claim is implied.

### 2026-09-25 — Execution diagnostics and external-data eligibility

- **Contributor(s):** AI-assisted implementation at Sneha Singh's request.
- **Work:** attempted an unchanged-settings full-scale rerun; preserved its failure;
  added phase/request failure records and progress messages without runtime policy
  changes; inspected the pinned MCPSecBench license and JSON schema without running
  third-party code; updated project status and README.
- **Verification:** 177 tests passed in 71.541 seconds, dependency check passed,
  retained-research verification passed for 43 files. An initial targeted test
  exposed source-line content in traceback output; diagnostic stack records were
  narrowed to file/line/function and the complete suite then passed.
- **Diagnostic:** baseline / seed 42 / two TEST scenarios completed at unchanged
  training, validation, scenario sizes and timeouts; this is not full-scale evidence.
- **Final verification:** after moving progress messages to stderr and adding a
  stdout-preservation assertion, all 177 tests passed again in 57.248 seconds.
- **Boundary:** no detector tuning, fabricated external traces, human sign-off,
  inventorship determination or successful full-scale result is claimed.

### 2026-10-03 — Local visual dashboard

- **Contributor(s):** AI-assisted implementation at Sneha Singh's request.
- **Work:** local-only dashboard, five safe scenario controls, actual HTTP gateway
  evidence, checkpoint reset, bounded event history, Host/Origin/token checks,
  packaged frontend assets, seven regression tests and user instructions.
- **Verification:** all 184 tests passed in 91.357 seconds; browser flow verified
  normal calls, blocked mock deletion and reset; console errors/warnings absent;
  wheel built and assets checked; dependencies and 43 retained evidence files passed.
- **Boundary:** no detector tuning, production connection, research completion,
  human sign-off, or patent inventorship claim. Review remains pending.
### 2026-10-03 — Dataset expansion

AI-assisted implementation requested by Sneha: reproducible synthetic corpus
exporter, additional fixed seeds and larger input volumes, dataset card and tests.
See `docs/dataset_expansion.md`. This records implementation assistance, not team
review, inventorship, new experimental findings or approval of research claims.
# October 3 — Scoped read permissions and trust update policy

AI-assisted implementation at Sneha's request: scoped, expiring, revocable
application read permissions; historical-restriction trust hold; six regression
tests; paired grant/no-grant live diagnostics. All 201 tests passed. Results and
limitations are recorded in `docs/flow_policy.md`; no novelty or patentability
determination is asserted.
