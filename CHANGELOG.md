# Changelog & Historical Research Log: MCP Runtime Sentinel

## [0.2.0] - 2026-10-29
- Hardened gateway state persistence, pending-action retention, and optional state HMAC integrity.
- Added Streamable HTTP/SSE response handling, downstream MCP session mapping, environment-backed upstream credentials, and explicitly gated resource/prompt methods.
- Added structured logs, rotating hash-chained audit output, metrics, readiness/liveness endpoints, rate limits, and pending-action persistence.
- Added TLS/mTLS options, multi-client hashed credentials with SIGHUP reload, client-identity-bound sessions, and a bounded shutdown drain.
- Added optional pre-execution JSON policies and clarified that post-execution response withholding is not tool sandboxing.
- Added container examples, production documentation, and CI security, coverage, and Docker smoke checks.

This log chronicles the developmental iterations, bug fixes, protocol refinements, and pilot runs of the MCP Runtime Sentinel prototype leading up to the final publication release.

## [Phase 7 - Publication Readiness & Pre-Submission Audit] - 2026-10-27
- Audited test suite: reconciled test counts to 304 passing tests across 52 test modules.
- Reconciled project title across `CITATION.cff`, `README.md`, `paper/CHECKLIST.md`, and `paper/main.tex`.
- Audited external bibliography against arXiv and Technical Disclosure Commons publisher records; resolved MindGuard author list from `arXiv:2508.20412` and corrected ShieldMCP to open-source software citation.
- Added explicit Data and Code Availability statement in `paper/main.tex` and flagged pending Zenodo archival DOI placeholders.
- Verified all 480 dataset shards by SHA-256 and confirmed reproducibility via `scripts/reproduce_all.py --verify-only`.
- Corrected the unverified workshop-specific submission deadline and marked the AI-SEC @ AINA-2027 listing and call for papers as pending official confirmation.
- Revised the manuscript availability statement to describe the repository contents and pending archive deposit without promising a future DOI.

## [Phase 6 - Reproducibility Package] - 2026-10-25
- Implemented unified reproduction orchestrator `scripts/reproduce_all.py` (with `Makefile` and `scripts/reproduce_all.ps1`).
- Verified 480 synthetic dataset gzip shards against `datasets/synthetic-expanded-v1/manifest.json` by SHA-256.
- Verified 43 legacy artifacts and 574 20-seed primary artifacts.
- Created `docs/paper_numbers.md` containing cell-by-cell traceability index for all publication tables.
- Pinned reference environment to CPython 3.14.3 (AMD64) and NumPy 2.5.2 in `requirements-repro.txt`.
- Added unit tests in `tests/test_reproducibility.py` (281 tests passing).

## [Phase 5 - Enforcement and Security Gaps] - 2026-10-25
- Added human-in-the-loop pending action confirmation queue (`PendingAction`) and HTTP endpoints (`/v1/pending`, `/v1/pending/{id}/approve`, `/v1/pending/{id}/deny`).
- Added explicit sandbox containment header (`X-Sentinel-Sandbox: true`, `X-Sentinel-Sandbox-Containment: isolated`).
- Implemented fail-closed bearer token authentication for management and audit endpoints (`auth_token` in `GatewayConfig`).
- Implemented atomic state persistence (`save_state`, `load_state`, `export_state`, `import_state`).
- Documented upstream irreversibility and unsupported protocol boundaries in `docs/enforcement_architecture.md` and `docs/final_limitations.md`.

## [Phase 4 - Poisoning and Learning Admission] - 2026-10-25
- Evaluated full 20-seed matched poisoning study across 700 cells (5 streams × 7 policies × 20 seeds).
- Resolved Windows socket timeout bottlenecks with in-process evaluation runner.
- Documented colluding identities limitation (12.0 malicious updates under gated), mixed-traffic promotion leakage (4.0 updates), and post-promotion drift (3.0 updates) in `docs/poisoning_edge_cases.md`.
- Rewrote learning-admission claims in `docs/learning_admission_prototype.md`, documenting exact parity with transactional baseline.

## [Phase 3 - Detector Weaknesses & Hardening] - 2026-10-25
- Added SHA-256 seed expansion in `sentinel/engine.py` for deterministic autoencoder weight initialization.
- Documented calibration tie-handling analysis in `docs/calibration_tie_handling.md`.
- Implemented synthetic intent benchmark and word-overlap semantic matcher (`sentinel/intent_benchmark.py`).
- Conducted mathematical zero-recall analysis for the 4 blind-spot attack families in `docs/zero_recall_analysis.md`.

## [Phase 2 - Publication-Scale Novelty Matrix] - 2026-10-25
- Completed all 330 novelty matrix cells (22 scenarios × 5 variants × 2 phases × 5 legacy seeds) in `results/novelty/publication_scale_complete/`.
- Generated statistical report in `results/novelty/publication_scale_report/REPORT.md`.

## [Phase 1 - Statistical Evidence Expansion] - 2026-10-25
- Expanded main model comparison and Sentinel ablation matrix from 5 to 20 seeds (20001–20020).
- Generated exact Wilcoxon signed-rank tests, exact sign-flip tests, Holm adjustments, and 95% bootstrap confidence intervals in `results/statistical_analysis_20seed/`.

## [Phase 0 - Baseline Snapshot] - 2026-10-25
- Audited baseline repository snapshot (261 tests passing).
- Recorded initial headline metrics, zero-recall failure modes, and claims audit in `docs/baseline_snapshot.md`.

## [Pre-Conference Historical Pilots] - September - October 2026
- Bounded state, request deadlines, connection limits, and capability recovery.
- Scoped read permissions and event-level learning attribution.
- Verification-budget adaptation pilot across 480 cells.
- Application-verified learning with trusted calculator fixtures.
