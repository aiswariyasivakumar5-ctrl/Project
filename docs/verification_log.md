# Verification log

This log records commands run for the production-hardening verification. A
`VERIFIED` result means the command completed successfully in this environment;
checks that depend on unavailable network or Docker services are marked
`NOT VERIFIED HERE`.

## Step 1: Version control and clean environment

| Command/check | Exit | Relevant output | Verdict |
| --- | ---: | --- | --- |
| `git status --short --branch` before initialization | 128 | `fatal: not a git repository` | VERIFIED: no repository existed |
| `python --version` | 0 | Python 3.14.3 | VERIFIED |
| `git grep -nE '(token|secret|password|api[_-]?key)\s*='` after staging | 0 | 66 matching lines across 27 files; reviewed matches are configuration references, generated/demo canaries, or test fixture credentials. No live credential was identified. `certs/` and state/audit files were absent. | VERIFIED: no secrets committed |
| `.gitignore` check | 0 | `.venv/`, `.venv-clean-verify/`, caches, `dist/`, `build/`, `.coverage`, `__pycache__/`, certificates, state, and audit files are excluded | VERIFIED |
| `git commit -m "baseline: pre-verification state"` | 0 | Root commit `5a17f15`; 746 files captured; status clean before verification began | VERIFIED |
| `python -m venv .venv-clean-verify` | 0 | Fresh Python 3.14.3 virtual environment created; ignored by Git | VERIFIED |
| `.venv-clean-verify/Scripts/python -m pip install -e '.[dev]' build` | 0 after network-capable retry | Installed editable project and dev tools. First sandbox attempt failed downloading isolated setuptools. Added `pytest>=8,<10` to the dev extra because the prescribed fresh-env command otherwise did not install the runner needed by CI's `coverage run -m pytest`. | VERIFIED |
| `.venv-clean-verify/Scripts/python -m pip check` | 0 | `No broken requirements found.` | VERIFIED |
| `.venv-clean-verify/Scripts/ruff check sentinel` | 0 | `All checks passed!` | VERIFIED |
| `.venv-clean-verify/Scripts/mypy sentinel/gateway.py sentinel/cli.py sentinel/http_limits.py sentinel/audit_log.py sentinel/policy.py` | 0 | `Success: no issues found in 5 source files` | VERIFIED |
| `.venv-clean-verify/Scripts/coverage erase`; `.venv-clean-verify/Scripts/coverage run -m pytest -q` | 0 | `377 passed, 10 skipped, 108 subtests passed in 113.85s` | VERIFIED |
| `.venv-clean-verify/Scripts/coverage report --include='sentinel/gateway.py,sentinel/http_limits.py,sentinel/audit_log.py,sentinel/policy.py' --show-missing --fail-under=85` | 0 | gateway 86%, http_limits 98%, audit_log 98%, policy 94%; selected-file total 88% | VERIFIED |
| `.venv-clean-verify/Scripts/python -m unittest discover -s tests` | 0 | `Ran 387 tests in 89.788s; OK (skipped=10)` | VERIFIED |
| `.venv-clean-verify/Scripts/python -m build` | 0 | built `mcp_runtime_sentinel-0.2.0.tar.gz` and `mcp_runtime_sentinel-0.2.0-py3-none-any.whl` | VERIFIED |
| `.venv-clean-verify/Scripts/pip-audit` before pip upgrade | 1 | 10 known advisories for pip 25.3, with fixes in pip 26.0+; local editable project was not resolvable from PyPI | FAILED (toolchain dependency finding) |
| Upgrade pip to 26.2.2, then `.venv-clean-verify/Scripts/pip-audit` | 0 | `No known vulnerabilities found`; local editable project is explicitly skipped because it is not published on PyPI | VERIFIED for installed dependencies; project source itself is not an advisory database package |
| `.venv-clean-verify/Scripts/pip-audit -r requirements-service.txt` | 0 | `No known vulnerabilities found` for the pinned service dependency | VERIFIED |

## Step 2: Test strictness and skipped-test audit

The initial repository snapshot is the root commit (`5a17f15`), so there is no pre-verification parent revision to diff against. The earlier test edits were reviewed against the requested “before” behavior recorded in the verification task and prior session notes. In all three cases, the test conditions were strengthened or kept equivalent; no assertion was removed or weakened.

| Test | Earlier behavior | Current behavior and assessment |
| --- | --- | --- |
| `tests/test_enforcement_flows.py::EnforcementFlowsTests::test_sandbox_containment_response` | Expected the former `X-Sentinel-Decision: sandbox` value. | Expects the explicit `contained-withheld` decision while retaining checks for `X-Sentinel-Sandbox: true`, `X-Sentinel-Sandbox-Containment: isolated`, and JSON `sandbox_contained: true`. This updates the expected API value and preserves the compatibility aliases and containment assertions. |
| `tests/test_gateway_streamable_http.py::StreamableHttpGatewayTests::test_gated_resource_method_is_unavailable_by_default` | Asserted no upstream session after initialize plus gated RPC, incorrectly conflating legitimate initialize setup with the gated method. | Now asserts upstream starts with zero sessions/requests; initialize creates exactly one session/request; then `resources/list` returns method-not-found and leaves both session set and request count unchanged. The final assertions directly prove the gated call created no session and reached no upstream. |
| `tests/test_preexecution_policy.py::PreExecutionPolicyTests::test_approval_holds_request_until_operator_approves_then_dispatches` | Used a short sleep/poll before indexing pending action and a short join. | Uses an event to synchronize action creation; verifies an action exists, the forwarder has not run before approval, then approves and confirms the worker finishes, dispatches exactly once, and returns a result. This removes timing fragility without weakening the contract. A separate regression test covers approval before waiter registration. |

The streamable HTTP test was strengthened in this step. Its first sandboxed invocation could not bind localhost (`WinError 10013`); with the required localhost permission, the focused test passed: `.venv-clean-verify\\Scripts\\python -m pytest -q tests/test_gateway_streamable_http.py::StreamableHttpGatewayTests::test_gated_resource_method_is_unavailable_by_default` — 1 passed.

### Requested assertion details

- `tests/test_enforcement_flows.py::EnforcementFlowsTests::test_sandbox_containment_response` asserts `X-Sentinel-Decision == "contained-withheld"`, the legacy `X-Sentinel-Sandbox == "true"` and `X-Sentinel-Sandbox-Containment == "isolated"` aliases, and JSON `sandbox_contained == true`. Both aliases and the new decision are asserted.
- `tests/test_gateway_streamable_http.py::StreamableHttpGatewayTests::test_gated_resource_method_is_unavailable_by_default` asserts `upstream_sessions == set()` and `request_count == 0` before sending `initialize`. After initialize, it records the legitimate session/request baseline and proves the gated `resources/list` request adds neither.
- `.venv-clean-verify\\Scripts\\python -m pytest -q tests/test_enforcement_flows.py::EnforcementFlowsTests::test_sandbox_containment_response tests/test_gateway_streamable_http.py::StreamableHttpGatewayTests::test_gated_resource_method_is_unavailable_by_default` | 0 | `2 passed in 2.33s` (with loopback access) | VERIFIED |

### Skipped tests

The ten skips are intentional in this environment. Eight depend on generated research artifacts in `results/`; those are outside this runtime-hardening verification and were not generated. Two check POSIX permission bits and cannot be meaningfully run on Windows.

| Test | Skip reason | Classification / action |
| --- | --- | --- |
| `tests/test_audit_log.py::AuditLogTests::test_file_permissions_on_creation_and_rotation` | POSIX permission mode bits unsupported on Windows | Platform-only; remain skipped on Windows. |
| `tests/test_audit_log.py::AuditLogTests::test_preexisting_looser_permissions_tightened_and_logged` | POSIX permission mode bits unsupported on Windows | Platform-only; remain skipped on Windows. |
| `tests/test_calibration_gap_diagnosis.py::BaselineCalibrationGapTest::test_diagnosis_summary_consistency` | Requires generated `results/baselines_20seed` | Artifact-dependent; not a missing package, Docker, network, or socket dependency. Leave skipped. |
| `tests/test_final_verification.py::FinalVerificationTests::test_retained_package_is_consistent` | Requires generated `results` | Artifact-dependent; leave skipped. |
| `tests/test_matched_fpr_reconciliation.py::TestMatchedFPRReconciliation::test_decision_rule_matches_raw_sweep_for_sentinel` | Requires generated `results/baselines_20seed` | Artifact-dependent; leave skipped. |
| `tests/test_matched_fpr_reconciliation.py::TestMatchedFPRReconciliation::test_sentinel_tie_counts_and_percentile_clamping` | Requires generated `results/baselines_20seed` | Artifact-dependent; leave skipped. |
| `tests/test_matched_fpr_reconciliation.py::TestMatchedFPRReconciliation::test_reconciliation_files_exist_and_contain_valid_cis` | Requires generated `results/matched_fpr_v2` | Artifact-dependent; leave skipped. |
| `tests/test_paper_numbers_mapping.py::PaperNumbersMappingTests::test_all_referenced_artifacts_exist` | Requires generated `results` | Artifact-dependent; leave skipped. |
| `tests/test_reproducibility.py::TestReproducibilityPackage::test_legacy_research_package` | Requires generated `results` | Artifact-dependent; leave skipped. |
| `tests/test_reproducibility.py::TestReproducibilityPackage::test_20seed_artifacts_integrity` | Requires generated `results` | Artifact-dependent; leave skipped. |

No skipped test was found that should be unskipped for a runtime-only verification: the permission checks are OS-specific and the other eight require absent generated artifacts.

### `tests/test_coverage_boost.py` assertion audit

Parsed all 16 test methods with Python AST and counted direct `assert` statements and unittest `assert*`/`fail` calls. Every test has at least one direct assertion (range: 1–14). The tests check observable behavior such as raised errors, response values, files, state, and dispatch effects; no assertion-free test was found. No change was needed.

## Step 3: Concurrency and race review

| Command/check | Exit | Relevant output | Verdict |
| --- | ---: | --- | --- |
| `.venv-clean-verify\\Scripts\\ruff check sentinel tests/test_concurrency_stress.py` | 0 | `All checks passed!` | VERIFIED |
| `.venv-clean-verify\\Scripts\\python -m pytest -q tests/test_concurrency_stress.py -m stress` (with localhost access) | 0 | `5 passed in 46.78s`; four stress scenarios ran 51 rounds each (17 rounds at each of 2, 4, and 8 worker threads), plus lock-order regression | VERIFIED; no flakes observed in these runs |
| `.venv-clean-verify\\Scripts\\mypy sentinel/gateway.py sentinel/cli.py sentinel/http_limits.py sentinel/audit_log.py sentinel/policy.py` | 0 | `Success: no issues found in 5 source files` | VERIFIED |
| `.venv-clean-verify\\Scripts\\python -m pytest -q tests/test_preexecution_policy.py tests/test_gateway_streamable_http.py` | 1 | `5 passed, 3 failed, 11 subtests passed`; all three failures were localhost socket permission errors (`WinError 10013`) in the sandbox | NOT VERIFIED HERE for the socket-dependent tests. The focused gated-resource test passed with localhost permission during Step 2; this broader command needs the same permission to provide additional evidence. |
| `.venv-clean-verify\\Scripts\\python -m pytest -q tests/test_preexecution_policy.py tests/test_gateway_streamable_http.py` (with localhost access) | 0 | `8 passed, 11 subtests passed in 3.52s` | VERIFIED after granting the required local socket permission |

### Concurrency findings and fixes

- Found a lock-order inversion in recovery probing: `probe_recovery` held `engine.lock` while acquiring `_lock`, while state save/import/export acquire `_lock` before `engine.lock`. Moved recovery audit append outside the engine-lock scope and added a regression that fails if the gateway lock is acquired while the engine lock is held.
- Credential reload swapped `client_credentials` without synchronization while request handlers read and iterated the mapping. Reload now swaps under `_auth_lock`; request handlers snapshot the mapping under that lock and then iterate the stable snapshot. Concurrent reload/request stress passed.
- Found an unlocked read of `_uses_upstream_sessions`; it now reads under `_session_lock`.
- The complete lock inventory, ordering, and remaining caller-side synchronization requirements are documented in `docs/concurrency_review.md`.
- Updated `tests/test_concurrency_stress.py::GatewayConcurrencyStressTests::test_recovery_probe_does_not_invert_gateway_and_engine_locks` to record nested gateway/engine lock acquisitions per thread and fail if a lower-ranked lock is acquired while a higher-ranked lock is held.
- `tests/test_concurrency_stress.py::GatewayConcurrencyStressTests::test_provenance_single_use_is_atomic_under_contention` runs 17 rounds each at 2, 4, and 8 workers and requires exactly one successful consume for each token in every race (51 races per worker count).
- `.venv-clean-verify\\Scripts\\python -m pytest -q tests/test_concurrency_stress.py -m stress` | 0 | `5 passed in 49.93s` | VERIFIED (with loopback access); the four stress scenarios ran 51 rounds each across 2, 4, and 8 workers.
- `.venv-clean-verify\\Scripts\\python -m pytest -q tests/test_concurrency_stress.py::GatewayConcurrencyStressTests::test_recovery_probe_does_not_invert_gateway_and_engine_locks` | 0 | `1 passed in 0.28s` | VERIFIED |

## Step 4: Mutation testing and assertion quality

Added `mutmut>=3.8,<4` to the `dev` extra only. Mutation scope was limited to the focused production modules and the associated gateway/security regression tests. The full 1,041-mutant run completed under WSL using mutmut 3.8.1. Results from `mutants/results.txt`:

| Module | Killed | Survived | Timed out | Mutation score (killed / all generated) |
| --- | ---: | ---: | ---: | ---: |
| `sentinel.audit_log` | 194 | 77 | 0 | 71.6% |
| `sentinel.http_limits` | 64 | 35 | 3 | 62.7% |
| `sentinel.policy` | 205 | 47 | 0 | 81.3% |
| `sentinel.provenance` | 277 | 138 | 1 | 66.6% |
| **Total** | **740** | **297** | **4** | **71.1%** |

Added policy regressions for the exact maximum serialized-argument size boundary and deterministic forbidden-pattern matching regardless of JSON key insertion order. Focused validation: `.venv-clean-verify/Scripts/python -m pytest -q tests/test_preexecution_policy.py` — `7 passed, 11 subtests passed`.

The mutation run still has survivors and does not meet the 80% target overall. All 297 survivors have a per-mutant source-diff inventory in `docs/mutant_triage.md`; updated static triage classifies 15 as equivalent, 90 as not worth testing, and 192 as test gaps. Added additional policy, audit-log, and HTTP deadline assertions after the mutation run. Their mutation outcomes are **NOT VERIFIED HERE** because WSL currently returns `E_ACCESSDENIED`; do not count these tests as killing mutants until CI reruns them.

**Gateway auth and persisted-state HMAC mutation coverage is incomplete.** `.venv-clean-verify\\Scripts\\mutmut run 'sentinel.gateway*authenticate*'` | 1 | `To run mutmut on Windows, please use the WSL.` `wsl.exe -l -q` | 1 | `Wsl/E_ACCESSDENIED`. Added an Ubuntu CI job for gateway authentication, credential comparison, Host/Origin validation, state-HMAC validation, and atomic `save_state`; it uploads `mutants/`. It has not run here. Trigger after pushing this branch with `gh workflow run tests.yml --ref master`. mutmut's Windows fork/WSL requirement is documented [here](https://mutmut.readthedocs.io/en/latest/). Treat Step 4 as **partially verified**, not as meeting the requested 80% per-module target.

The AST audit of `tests/test_coverage_boost.py` found 16 test methods, each with at least one direct assertion or unittest assertion call (range 1–14); no code-executing assertion-free test was found. This was a structural check and does not prove every assertion is strong enough to detect every behavioral regression.

Additional gap-focused tests added after the 1,041-mutant run:

- Policy per-client token bucket and deterministic refill behavior (`test_rate_limit_is_per_client_and_refills_at_configured_rate`).
- Exact one-second provenance claim expiry boundary (`test_stale_and_exact_expiration_boundary`).
- Empty audit log uses genesis while a nonempty partial record is rejected (`test_empty_log_is_genesis_but_nonempty_partial_record_is_rejected`).
- HTTP handler timeout is applied to accepted sockets and shutdown drain uses the exact configured deadline (`test_bounded_server_validates_and_releases_connection_slots`, `test_drain_uses_the_exact_shutdown_deadline`).
- Audit verification rejects records missing `record_hash`, accepts equivalent JSON key order through canonical hashing, and rejects nonstandard NaN values (`test_verifier_canonicalizes_keys_and_rejects_missing_hash_and_nan`).

Focused security suite: `.venv-clean-verify\\Scripts\\python -m pytest -q tests/test_preexecution_policy.py tests/test_provenance.py tests/test_http_limits.py tests/test_audit_log.py tests/test_gateway_state.py` | 0 | `72 passed, 2 skipped, 55 subtests passed in 11.97s` (with loopback access) | VERIFIED. The added audit canonicalization/missing-hash/NaN test separately passed: `.venv-clean-verify\\Scripts\\python -m pytest -q tests/test_audit_log.py::AuditLogTests::test_verifier_canonicalizes_keys_and_rejects_missing_hash_and_nan` | 0 | `1 passed in 0.93s`. `.venv-clean-verify\\Scripts\\ruff check tests/test_audit_log.py` | 0 | `All checks passed!`. The GitHub Linux mutation job now includes all four prior mutation modules plus gateway authentication, credential comparison, Host/Origin validation, body parsing, state HMAC, and atomic save functions. No updated mutation score is available until that job runs.

## Steps 5–7: Runtime typing, Docker/CI, and documentation reconciliation

| Command/check | Exit | Relevant output | Verdict |
| --- | ---: | --- | --- |
| `.venv-clean-verify\\Scripts\\mypy` (configured files: gateway, CLI, service, HTTP limits, audit log, policy, provenance, engine, models, JSON-RPC) | 0 | `Success: no issues found in 10 source files` | VERIFIED |
| Exploratory `.venv-clean-verify\\Scripts\\mypy sentinel` | 1 | `Found 546 errors in 51 files (checked 68 source files)`; mostly untyped research modules and existing typing defects | NOT VERIFIED as a full-package check; configured runtime check is the required CI check |
| `.venv-clean-verify\\Scripts\\mypy sentinel/attestation.py sentinel/causal.py sentinel/detectors.py sentinel/features.py sentinel/novelty.py sentinel/approvals.py sentinel/retention.py sentinel/validation.py` | 1 | `60 errors in 7 files (checked 8 source files)` | NOT VERIFIED; outside runtime target, errors remain in experimental/research-support code |
| `.venv-clean-verify\\Scripts\\ruff check sentinel tests/test_http_limits.py tests/test_preexecution_policy.py tests/test_concurrency_stress.py` | 0 | `All checks passed!` | VERIFIED |
| `.venv-clean-verify\\Scripts\\python -m build` (network-enabled retry) | 0 | `Successfully built mcp_runtime_sentinel-0.2.0.tar.gz and mcp_runtime_sentinel-0.2.0-py3-none-any.whl` | VERIFIED |
| `.venv-clean-verify\\Scripts\\pip-audit` (network-enabled retry) | 0 | `No known vulnerabilities found`; local project skipped because it is not published on PyPI | VERIFIED for resolvable dependencies |
| `.venv-clean-verify\\Scripts\\python -c "import pathlib,yaml; [yaml.load(pathlib.Path(p).read_text(),Loader=yaml.BaseLoader) for p in ['.github/workflows/tests.yml','docker-compose.example.yml']]; print('workflow and compose YAML parsed successfully')"` | 0 | `workflow and compose YAML parsed successfully` | VERIFIED |
| PowerShell action-SHA scan of `.github/workflows/tests.yml` | 0 | `action references=9; unpinned=0` | VERIFIED |
| Dockerfile healthcheck source assertion | 0 | `Docker healthcheck uses the mounted certificate as a trust anchor; no verification bypass` | VERIFIED; `ssl._create_unverified_context` removed, certificate verification enabled against `/certs/server.crt` |
| `docker build -t mcp-runtime-sentinel:verification .` | 1 | Docker CLI exists but Linux Docker Desktop daemon pipe is absent: `The system cannot find the file specified` | NOT VERIFIED HERE; run `docker build -t mcp-runtime-sentinel:verification .` on a host with Docker daemon |
| `.venv-clean-verify\\Scripts\\python -m build` (offline first attempt) | 1 | isolated build could not resolve `setuptools` from `pypi.org` | FAILED (network unavailable in sandbox); network-enabled retry passed |

GitHub workflow `tests.yml` now pins all nine external action references to full commit SHAs, grants read-only contents permission, adds workflow dispatch, and has Linux jobs for Docker smoke checks and mutation testing. The mutation job is not run on this workstation because WSL returns `E_ACCESSDENIED`; after push use `gh workflow run tests.yml --ref master`. The workflow's GitHub-hosted execution and artifact upload are **NOT VERIFIED HERE**.

The Dockerfile review found the previous liveness command explicitly disabled TLS certificate validation. It now trusts the mounted `/certs/server.crt` with `ssl.create_default_context(cafile=...)` and connects by `localhost`, matching the compose SAN. Compose overrides the healthcheck for mock-upstream and disables it for one-shot enrollment. Docker image execution/smoke remains **NOT VERIFIED HERE** because the daemon is unavailable. CI command to run: `docker build -t mcp-runtime-sentinel:ci .`; full smoke job: `docker compose -f docker-compose.example.yml up --build -d` followed by `python scripts/docker_smoke.py`.

Documentation updates reconcile actual code: `docs/architecture.md`, `docs/enforcement_architecture.md`, `docs/final_architecture.md`, `docs/final_limitations.md`, `docs/troubleshooting.md`, `docs/demo.md`, `docs/gateway_completion.md`, `docs/threats_to_validity.md`, and `docs/research_inventory.md` now describe client/operator credentials and supported Streamable HTTP session mapping/upstream SSE parsing, while distinguishing unsupported downstream SSE subscriptions/resources. The policy, audit-log, and timeout tests added after the previous full run were covered by the latest full run below.

### Added ignore/noqa/type-ignore diff review

| Added item | Justification |
| --- | --- |
| `.gitignore`: `.venv-wsl-mutmut/`, `.venv*/` | Exclude the failed WSL environment and all local virtual environments from repository noise. |
| `.gitignore`: `mutants/` | mutmut generates mutated source copies and CI result artifacts here; CI uploads the directory. |
| `.gitignore`: `.mutmut-cache/` | Exclude generated mutation cache. |
| `.gitignore`: `.coverage*` | Exclude coverage data files, including parallel-process suffixes. |
| New `# noqa` comments | None. |
| New `# type: ignore` comments | None. |

Final full test command in the sandbox: `.venv-clean-verify\\Scripts\\coverage erase; .venv-clean-verify\\Scripts\\coverage run -m pytest -q` | 1 | `44 failed, 338 passed, 10 skipped, 7 errors, 108 subtests passed in 77.54s`; failures were loopback socket denials (`WinError 10013`) | NOT VERIFIED in restricted sandbox. Same command with permitted loopback access, including the final Unicode audit-log regression | 0 | `389 passed, 10 skipped, 108 subtests passed in 139.37s (0:02:19)` | VERIFIED. Coverage: `.venv-clean-verify\\Scripts\\coverage report --include='sentinel/gateway.py,sentinel/http_limits.py,sentinel/audit_log.py,sentinel/policy.py' --show-missing --fail-under=85` | 0 | `TOTAL 1692 statements, 89%`; gateway 86%, other three selected modules fully covered; three files skipped as completely covered | VERIFIED. Latest Ruff: `.venv-clean-verify\\Scripts\\ruff check sentinel tests/test_http_limits.py tests/test_preexecution_policy.py tests/test_concurrency_stress.py tests/test_http_hardening.py tests/test_audit_log.py` | 0 | `All checks passed!`. Latest configured mypy: `.venv-clean-verify\\Scripts\\mypy` | 0 | `Success: no issues found in 10 source files`. `git diff --check` | 0 | no whitespace errors; only line-ending normalization warnings | VERIFIED.

`.venv-clean-verify\\Scripts\\python -c "import pathlib,yaml; [yaml.load(pathlib.Path(p).read_text(),Loader=yaml.BaseLoader) for p in ['.github/workflows/tests.yml','docker-compose.example.yml']]; print('workflow and compose YAML parsed successfully')"` | 0 | `workflow and compose YAML parsed successfully` | VERIFIED after the compose healthcheck override. `git diff --check` | 0 | no whitespace errors (line-ending normalization warnings only) | VERIFIED.

## Phase 0 package separation and hygiene

| Command | Exit | Output | Status |
| --- | ---: | --- | --- |
| `.venv-clean-verify\\Scripts\\ruff check sentinel tests` | 0 | `All checks passed!` | VERIFIED |
| `.venv-clean-verify\\Scripts\\mypy` | 0 | `Success: no issues found in 20 source files` | VERIFIED |
| `.venv-clean-verify\\Scripts\\python scripts/check_doc_numbers.py` | 0 | `documentation number check passed: 24 generated metrics and seed/test-count labels` | VERIFIED |
| `.venv-clean-verify\\Scripts\\python -m pytest -q tests/test_release_archive.py` | 0 | `2 passed in 0.37s` | VERIFIED |
| `.venv-clean-verify\\Scripts\\python -c "import pathlib,yaml; [yaml.load(pathlib.Path(p).read_text(),Loader=yaml.BaseLoader) for p in ['.github/workflows/tests.yml','docker-compose.example.yml']]; print('workflow and compose YAML parsed successfully')"` | 0 | `workflow and compose YAML parsed successfully` | VERIFIED |
| `.venv-clean-verify\\Scripts\\python scripts/check_runtime_wheel.py dist` | 0 | `runtime wheel isolation passed: mcp_runtime_sentinel-0.2.0-py3-none-any.whl; 20 runtime modules; no research package/imports` | VERIFIED for the built wheel |
| `$env:PYTHONPATH='research'; .venv-clean-verify\\Scripts\\python -m pytest -q` | 1 | `45 failed, 337 passed, 10 skipped, 7 errors, 108 subtests passed in 54.66s`; failures/errors include denied loopback sockets (`WinError 10013`) | NOT VERIFIED HERE; sandbox disallows the local sockets needed by gateway/dashboard integration tests. Rerun on a host permitting loopback: `python -m pytest -q` |
| `docker build -t mcp-runtime-sentinel:phase0 .` | 1 | `ERROR: open C:\\Users\\ssiva\\.docker\\buildx\\.lock: Access is denied.` | NOT VERIFIED HERE; Docker Desktop/buildx is inaccessible in this environment. |
| `.venv-clean-verify\\Scripts\\ruff check --config research/pyproject.toml research/sentinel_research` | 1 | 128 legacy research lint findings (mainly import ordering and long lines) | Research Ruff is not a configured runtime CI gate; no findings were suppressed or weakened for runtime. |
| `git diff --check` | 0 | No whitespace errors; Git reported line-ending normalization warnings | VERIFIED |

The runtime distribution now includes only the runtime `sentinel` package. Research modules and dashboard assets live in the separately installable `research/` distribution. The release-archive test passes, and ignores cover virtual environments, coverage outputs, and mutation artifacts. The wheel checker checks both archive contents and import resolution.

## Phase 1 safe-by-default enforcement (2026-10-30)

Commands were run from the repository root in WSL Ubuntu using the fresh `/home/ssiva/sentinel-phase0-classify` venv. The 391 passed / 8 skipped preflight was confirmed before Phase 1 edits. The final full suite was repeated after the last source/test/development-dependency change:

| Command | Exit | Output | Status |
| --- | ---: | --- | --- |
| `/home/ssiva/sentinel-phase0-classify/bin/coverage erase && /home/ssiva/sentinel-phase0-classify/bin/coverage run -m pytest -q --tb=short -p no:cacheprovider` | 0 | `399 passed, 8 skipped, 110 subtests passed in 186.53s (0:03:06)` | VERIFIED in WSL/Linux; +8 passed and +2 subtests vs 391/8 baseline |
| `/home/ssiva/sentinel-phase0-classify/bin/ruff check sentinel` | 0 | `All checks passed!` | VERIFIED |
| `/home/ssiva/sentinel-phase0-classify/bin/mypy --strict sentinel` | 0 | `Success: no issues found in 21 source files` | VERIFIED; full runtime package |
| `python scripts/check_runtime_wheel.py` (rebuilt runtime wheel; isolated runtime-check environment) | 0 | `runtime wheel isolation passed: mcp_runtime_sentinel-0.2.0-py3-none-any.whl; 21 runtime modules; no research package/imports` | VERIFIED in WSL/Linux; latest rebuilt wheel |
| `/home/ssiva/sentinel-phase0-classify/bin/coverage report --include='sentinel/*.py' --fail-under=85` | 0 | `TOTAL 3406 statements, 87%` after the 399-test coverage run | VERIFIED; runtime coverage exceeds 85% |
| `/home/ssiva/sentinel-phase0-classify/bin/python -m pytest -q --tb=short -p no:cacheprovider` (final post-formatting run) | 0 | `399 passed, 8 skipped, 110 subtests passed in 1259.51s (0:20:59)` | VERIFIED in WSL/Linux; +8 passed and +2 subtests vs 391/8 baseline |
| `/home/ssiva/sentinel-phase0-classify/bin/pip-audit` after upgrading the disposable venv pip from 24.0 to 26.2.2 | 0 | `No known vulnerabilities found`; editable local distributions are not listed on PyPI | VERIFIED for resolvable third-party dependencies |
| `/home/ssiva/sentinel-phase0-classify/bin/mutmut run --max-children 4 'sentinel.policy*'` | 1 (interrupted) | The local run remained active after more than five minutes; interrupted before results completed | NOT VERIFIED HERE; use the `gateway-security-mutation` GitHub Actions job |
| `docker build` / `scripts/docker_smoke.py` | not run | Docker was not run locally; operator reports Docker smoke verified in CI | NOT VERIFIED HERE locally; no local Docker success is claimed |

Phase 1 adds operator-assigned per-tool risk classes and closed-by-default JSON Schema validation with argument size/depth bounds; pre-dispatch policy denials and approval decisions are audited. Detector role, decision, execution stage, risk class, and response-withheld status are returned in headers and audit records. `write`/`destructive` detector output is advisory; `read` responses can be withheld after execution. Online learning is opt-in, and baseline approval/export/rollback changes are operator-attributed and audited. Intent metadata does not affect policy or approval. New policy and baseline tests are included in the full suite.

Hosted CI, Docker smoke, and completed mutation results remain separate gates; the local WSL results above do not assert those remote checks.
