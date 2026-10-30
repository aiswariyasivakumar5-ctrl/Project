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
