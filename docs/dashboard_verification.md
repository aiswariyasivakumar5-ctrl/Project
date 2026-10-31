# Dashboard verification — October 3, 2026

Story: selecting a safe fixture sends a protected browser request to the local
API, which executes real HTTP MCP calls and renders actual gateway evidence.

| Boundary | Status | Evidence |
|---|---|---|
| Browser | Passed | Dashboard rendered; console error/warning query returned an empty list. |
| Browser to API | Passed | Run scenario completed; six benign calls appeared. |
| API to gateway/mock | Passed | Live tests exercise all five scenarios; mock deletion was not forwarded. |
| Response rendering | Passed | Six allow rows, then one isolate row with forwarded=false and error -32041 appeared. |
| Reset | Passed | Browser showed zero calls and restored enrolled capability trust; tests compare learning-state hashes. |
| Packaging | Passed historically | The dashboard module and HTML, CSS and JavaScript assets are now shipped by the separate research wheel; the runtime wheel intentionally excludes them. Re-run package isolation checks for the current layout. |

Full suite: **184 tests passed in 91.357 seconds**, including seven new dashboard
tests. Dependency consistency passed; retained-research verification passed for
43 files. No historical results or detector thresholds changed.

The computer-use skill supported browser verification and the verification skill
structured the full-flow checks. Screenshot: ignored local artifact
`artifacts/dashboard/dashboard.jpg`; it is demonstration evidence, not a research
performance figure. Latency is environment-dependent.

Periodic refresh now avoids rebuilding unchanged controls. Startup failures are
not presented as a ready connection. Desktop flow is verified; comprehensive
mobile and assistive-technology testing is not claimed.

Still open: large-run transport timeout, complete 330-record novelty matrix,
final novelty inference/figures, independent runtime traces, owner approvals and
final manuscript/invention review. This dashboard does not resolve those items.

Read-only execution-environment checks found only `docker-desktop` registered
with WSL. Docker CLI reported its engine pipe unavailable. No Docker daemon,
additional distribution, cloud job, or new full-scale study was started here.
