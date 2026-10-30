# Local visual demonstration

Run from the project directory using the installed Python environment:

```powershell
.\.venv-repro\Scripts\python.exe -m sentinel.cli dashboard
```

Alternatively, after installing the project into your own environment:

```powershell
python -m sentinel.cli dashboard --port 8765
```

Open **http://127.0.0.1:8765**. Keep the terminal running; Ctrl+C stops the
dashboard and its owned mock/gateway servers. An occupied port can be replaced
with `--port 8766`; use that same port in the browser.

## What the dashboard does

1. Starts two safe local mock MCP servers and their actual HTTP gateways.
2. Enrolls on 100 benign fixture calls using the existing approval-required variant.
3. Runs a selected fixed fixture through real HTTP calls, with online learning enabled.
4. Displays actual decisions, risk/trust, upstream dispatch, model updates,
   capability trust, trace IDs, attestation and memory evidence.
5. Reset restores the post-enrollment checkpoint and clears only in-memory demo history.

Start with Normal reads, then Intent mismatch. The latter calls `simulated_delete`
with a read intent; it cannot delete real files. Inspect the event to distinguish
pre-dispatch blocking (`forwarded=false`) from withholding a response after an
upstream call (`forwarded=true`). Capability misuse, Response injection, and
Learning protection exercise existing synthetic fixtures. No arbitrary server URL,
shell command, file operation, operator approval, or production connection is exposed.

Sessions accumulate state until reset. Repeated runs therefore need not produce
identical outcomes. A reset is recommended when comparing demonstration scenarios.
Initial capability trust is measured after enrollment, not forced to a perfect score.

## Interpretation and boundaries

- Fixture labels describe generated cases, not successful detections.
- Risk is the existing runner's decision score; N/A is preserved for unevaluated trust.
- Interventions include confirm, sandbox and isolate; they are not all pre-dispatch denials.
- Model-update counts are distinct from attack blocking. Candidate/quarantine-related
  learning evidence is visible in the selected event's memory disposition.
- Only the latest 200 events are retained; event totals count since reset. Other
  metric cards summarize retained events, and latency is not direct-server overhead.
- There is no operator approval UI. Required approvals are not silently granted.
- Bind is fixed to 127.0.0.1. Exact Host, Origin, and a per-process demo token protect
  mutation routes against cross-site requests. These are not multi-user authentication.
  Anyone with local machine access remains inside the trust boundary. Do not expose
  the dashboard or its underlying mock/gateway ports publicly.
- No research result files are read or overwritten. This demo does not resolve the
  publication-scale timeout or establish research significance/production readiness.

## Verification

`tests/test_dashboard.py` covers real gateway evidence for all five fixtures,
pre-dispatch blocking, checkpoint reset, asset routes, Host/Origin/token rejection,
input allowlisting, concurrent-action rejection and partial-failure retention without
automatic retries. Browser verification is documented in `dashboard_verification.md`.
