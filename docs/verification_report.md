# Production-readiness verification report

## Scope and conclusion

This report summarizes Steps 1–7 recorded in [`verification_log.md`](verification_log.md). The changes improve runtime safety and verification coverage, but the project is **not fully verified as production-ready**. Linux mutation CI and Docker image/smoke execution have not run from this workstation. The last full test run passed, but it preceded one final focused JSON depth-boundary test. The run result for that added test is recorded separately below; the full suite should be rerun in CI after these edits are pushed.

## Step results

| Step | Result | Evidence / remaining work |
| --- | --- | --- |
| 1. Baseline | Completed for local checks. | Earlier baseline: 377 passed, 10 skipped; runtime-file coverage 88%; package build passed; pip-audit reported no known vulnerabilities after pip upgrade. See log for exact commands and output. |
| 2. Test assertions and skips | Completed for requested gaps. | `EnforcementFlowsTests::test_sandbox_containment_response` asserts `contained-withheld` and both legacy aliases. `StreamableHttpGatewayTests::test_gated_resource_method_is_unavailable_by_default` asserts zero upstream sessions/requests before initialize. Both focused tests: exit 0, `2 passed in 2.33s`. |
| 3. Concurrency | Completed for local stress evidence. | Lock-order recorder regression passed (`1 passed in 0.28s`). Stress suite passed (`5 passed in 49.93s`), including exactly-once provenance consumption: 17 races at each of 2, 4, and 8 workers. |
| 4. Mutation testing | Partial; target not met or refreshed. | Original 1,041-mutant run: 740 killed, 297 survived, 4 timed out; 71.1% overall. Module scores: audit log 71.6%, HTTP limits 62.7%, policy 81.3%, provenance 66.6%. All 297 survivor IDs and generated source changes are inventoried in [`mutant_triage.md`](mutant_triage.md), including behavior-specific source locations for the 21 helper-function rows that were previously generic. Additional boundary/rate/depth/hash canonicalization regressions are added; no updated mutant-kill scores are claimed. Linux CI mutation job is prepared, not executed. |
| 5. Runtime typing and checks | Completed for the runtime package target; broader research package remains untyped. | `mypy` is configured for the 10 runtime modules (`gateway`, `cli`, `service`, `http_limits`, `audit_log`, `policy`, `provenance`, `engine`, `models`, `jsonrpc`) and passes: `Success: no issues found in 10 source files`. The broader `mypy sentinel` exploratory run failed with 546 errors in 51 files; research/experimental code is not part of the runtime target. Ruff and coverage checks pass. |
| 6. Docker and CI | Configuration updated; execution pending. | All 9 workflow action references are full-SHA pinned; workflow and compose YAML parse. Dockerfile healthcheck now verifies TLS using `/certs/server.crt`; compose disables it for one-shot enrollment and uses a TCP healthcheck for the mock upstream. Docker build was attempted but the Docker Desktop Linux daemon was unavailable. Docker build/smoke and hosted CI are NOT VERIFIED HERE. |
| 7. Documentation and final report | Completed with known limitations documented. | Runtime docs now describe separate caller/operator credentials, Streamable HTTP session mapping, bounded upstream SSE responses, and unsupported downstream SSE. Ignore/type-ignore/noqa diff review is recorded in the verification log. |

## Latest local test evidence

- Full suite command: `.venv-clean-verify\Scripts\coverage erase; .venv-clean-verify\Scripts\coverage run -m pytest -q` — with loopback access, exit 0; `389 passed, 10 skipped, 108 subtests passed in 139.37s (0:02:19)`. Without loopback permission, the same command exited 1 with `44 failed, 338 passed, 10 skipped, 7 errors`; failures were socket permission denials (`WinError 10013`).
- Latest focused security suite: `.venv-clean-verify\Scripts\python -m pytest -q tests/test_preexecution_policy.py tests/test_provenance.py tests/test_http_limits.py tests/test_audit_log.py tests/test_gateway_state.py` — exit 0; `72 passed, 2 skipped, 55 subtests passed in 11.97s`.
- Additional focused regressions: `.venv-clean-verify\Scripts\python -m pytest -q tests/test_http_hardening.py::BoundaryHardeningTests::test_json_depth_limit_accepts_boundary_and_rejects_one_level_over` — exit 0; `1 passed in 0.48s`. `.venv-clean-verify\Scripts\python -m pytest -q tests/test_audit_log.py::AuditLogTests::test_verifier_canonicalizes_keys_and_rejects_missing_hash_and_nan` — exit 0; `1 passed in 0.93s`.
- Configured `mypy` — exit 0; `Success: no issues found in 10 source files`.
- `.venv-clean-verify\Scripts\ruff check sentinel tests/test_http_limits.py tests/test_preexecution_policy.py tests/test_concurrency_stress.py tests/test_http_hardening.py tests/test_audit_log.py` — exit 0; `All checks passed!`.
- `.venv-clean-verify\Scripts\coverage report --include='sentinel/gateway.py,sentinel/http_limits.py,sentinel/audit_log.py,sentinel/policy.py' --show-missing --fail-under=85` — exit 0; selected total coverage 89%, gateway 86%, other selected modules fully covered.
- Build: `.venv-clean-verify\Scripts\python -m build` — exit 0; sdist and wheel created. The first offline attempt failed resolving setuptools; network-enabled retry passed.
- Dependency audit: `.venv-clean-verify\Scripts\pip-audit` — exit 0; `No known vulnerabilities found`. The local unpublished project itself is skipped by PyPI lookup.
- `git diff --check` — exit 0; no whitespace errors (Git emitted only line-ending normalization warnings).

## NOT VERIFIED HERE

1. **Linux mutation run**: WSL returns `E_ACCESSDENIED`, and native Windows mutmut exits with its WSL requirement. Push the branch, then run:

   ```powershell
   gh workflow run tests.yml --ref master
   gh run watch
   gh run download --name gateway-security-mutmut-results
   ```

   The workflow runs mutations for audit log, HTTP limits, policy, provenance, gateway authentication/credential checks, Host/Origin, body parsing, state HMAC, and atomic save. Review updated per-module results and survivor triage; the existing score is below 80% for three modules.

2. **Docker image and compose smoke**: Docker CLI is installed, but `dockerDesktopLinuxEngine` is not running. On a Docker-enabled host run:

   ```powershell
   docker build -t mcp-runtime-sentinel:ci .
   docker compose -f docker-compose.example.yml up --build -d
   python scripts/docker_smoke.py
   docker compose -f docker-compose.example.yml restart gateway
   python scripts/docker_smoke.py
   docker compose -f docker-compose.example.yml exec -T gateway python -m sentinel_research.cli verify-audit /data/audit.jsonl
   docker compose -f docker-compose.example.yml down -v
   ```

3. **Hosted CI full run**: local full suite passes with loopback access. GitHub hosted Linux execution remains pending; after push, run `gh workflow run tests.yml --ref master` and `gh run watch`.

4. **Mutation score after new tests**: no updated mutation results exist. Do not interpret the added tests as killed mutants until Linux mutmut confirms it.

## Production-readiness assessment

The reviewed work addresses several concrete hardening issues, adds reproducible local test evidence, documents residual shared-state access paths, and corrects the Docker healthcheck certificate handling. Production readiness remains **conditional** on a passing hosted Linux workflow, Docker build and restart smoke, and refreshed mutation results. The app has no demonstrated multi-host deployment, durable distributed state, signed audit chain, or production workload validation; these remain documented product limits rather than checks performed by this verification pass.

## Phase 0 package separation update (2026-10-30)

Phase 0 package and repository hygiene changes were implemented and verified at that stage. Runtime and research code are separate installable distributions; runtime package discovery is restricted to `sentinel`, research discovery to `sentinel_research`, and the Phase 0 runtime wheel contained 20 modules with no research imports. This is a historical result; the latest rebuilt runtime wheel verification is recorded in the Phase 1 section below. Runtime Ruff, configured strict mypy, the number consistency check, archive tests, YAML parsing, wheel-isolation check, and `git diff --check` passed. Exact commands and output are in [`verification_log.md`](verification_log.md).

The fresh full-suite rerun is **NOT VERIFIED HERE**: it exited 1 with 45 failed, 337 passed, 10 skipped, and 7 errors; the integration failures/errors are caused by denied loopback socket access (`WinError 10013`) in this environment. The Docker build is **NOT VERIFIED HERE** because the Docker Buildx lock access was denied. Research Ruff reports 128 pre-existing style/import-order findings and is not a configured runtime CI gate. These unresolved checks must be run in an environment with loopback access and Docker before claiming complete verification.

## Phase 1 safe-by-default enforcement update (2026-10-30)

The current WSL/Linux full suite supersedes the earlier loopback-blocked result for Linux verification: coverage-instrumented `python -m pytest -q --tb=short -p no:cacheprovider` exited 0 with `399 passed, 8 skipped, 110 subtests passed`. This is +8 passed and +2 subtests compared with the 391 passed / 8 skipped preflight.

The latest rebuilt runtime wheel isolation check passed: it contains 21 runtime modules and has no research package or research imports. Runtime Ruff and strict mypy pass. The coverage-instrumented full suite passed with 87% statement/branch coverage for `sentinel/*.py`, over the 85% target. After updating the isolated verification venv's pip, `pip-audit` reported no known vulnerabilities among resolvable third-party dependencies. The local targeted mutmut command was interrupted before completion; mutation results are not verified here. The GitHub workflow includes a dedicated security mutation job. Docker was not run locally; the operator reports its smoke gate green in CI, which this report does not independently verify. Hosted CI and fresh mutation artifacts remain pending, so readiness is still conditional on those external results.
