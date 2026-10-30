# Novelty development experiments

The `novelty-study` command runs the real HTTP gateway and two safe mock servers.
It compares baseline Sentinel with full novelty and three independent ablations.
This is a development evaluation harness. Team review, protocol preregistration
and an approved release commit are still required before final research runs.

## Run

From the repository with its virtual environment active:

```powershell
python -m sentinel.cli novelty-study --seeds 42,123 `
  --training-events 40 --validation-events 8 --test-events 6 `
  --output results/novelty/my-new-smoke
```

The output directory must not already exist. The runner refuses to overwrite even
an empty existing directory. Interrupted runs keep their protocol and completed
rows; choose a new output path for a retry.

Use `--variants full,without_dual_memory` or
`--scenarios distributed_poisoning,legitimate_upgrade` to select a smaller study.
Seeds, variants and scenarios must be nonempty and unique. Training/validation
counts must be positive; scenario size must be at least three. Counts are inputs
to scenario generation; the actual event counts are recorded for each scenario.

## Variants

The five original variants keep the historical promotion policy for comparison.
An optional sixth variant, `approval_required`, uses the new reviewed-promotion
default. No operator approvals are injected by this runner: this variant is an
unapproved-change control for both benign and adversarial candidates. See
`runtime_controls.md` for reviewed positive controls and operational use.

| Variant | Changed mechanism |
|---|---|
| `baseline` | Base Sentinel gateway without the novelty wrapper |
| `full` | Counterfactual intent scoring, capability trust and dual memory |
| `without_intent_provenance` | Disables counterfactual score contribution; mandatory claim integrity validation remains active |
| `without_capability_trust` | Disables capability trust and restores server-wide preflight isolation |
| `without_dual_memory` | Low-risk allowed events can update directly without multi-session promotion |

The intent-provenance variant is a score ablation, not an authorization bypass.
Each variant runs the same seeded TRAIN, VALIDATION and scenario inputs. No new
model family or tuning of retained research thresholds is introduced.

## Scenario catalog

| Scenario | Purpose | Separate adaptive phase |
|---|---|---|
| `capability_laundering` | Alternating export misuse and benign reads measures collateral capability blocking | No |
| `coordinated_servers` | Same-session data passes from one server's response to another server's argument | No |
| `distributed_poisoning` | A single authenticated attacker rotates raw sessions to promote a new argument shape | Yes |
| `multi_actor_poisoning` | Distinct compromised identities coordinate the same low-risk candidate | Yes |
| `legitimate_upgrade` | Independent approved sessions adopt a benign argument-shape extension | Yes |
| `schema_stable_response` | Policy injection preserves the normal content/type/text JSON shape | No |
| `delayed_causal_misuse` | Unused authorization expires before a destructive call | No |
| `provenance_replay` | Reuse of a consumed claim before expiry | No |

The legitimate-upgrade fixture is a behavior/argument extension supported by the
mock server's existing manifest. It does not implement software deployment,
signed manifest replacement or trusted upgrade approval. Coordinated-server cases
test observable data flow, not arbitrary collusion learning.

## Phase isolation and measurements

### Optional validation-only score calibration

Add `--validation-fpr 0.01` to fit the existing offline comparison's normal-
validation quantile rule, once per variant/seed, before any scenario execution.
The threshold uses `method="higher"` and a strict `score > threshold` comparison.
Calibration files under `calibration/<variant>/seed-<seed>-calibration.json` record
scores, score/workload hashes, empirical FPR, target and threshold. They are written
before TEST and reused unchanged across all scenario TEST/ADAPTIVE phases.

This optional workflow adds `score_metrics`, `score_threshold` and
`calibration_reference` to per-phase results plus a separate score table in the
report. Existing `metrics`, aggregate comparisons and event decisions still refer
to actual gateway interventions. It does not tune gateway action bands, alter
learning or replace authorization decisions. Without the option, the earlier
fixed-policy workflow is unchanged. See [the draft protocol](novelty_protocol.md)
for proposed primary/secondary outcomes and outstanding approval gates.

1. TRAIN explicitly enrolls synthetic trusted traffic.
2. The runner checkpoints the shared base engine, both novelty wrappers, candidate
   and trusted memories, capability trust, tool metadata and mock state together.
3. VALIDATION runs without learning. With the optional flag, its benign scores fit
   the secondary score threshold; otherwise no threshold is fit.
4. Each scenario's TEST starts from the post-TRAIN checkpoint with learning disabled.
5. Declared ADAPTIVE phases independently start from the same post-TRAIN checkpoint
   with learning enabled. TEST never supplies training evidence to ADAPTIVE.

Learning-state hashes include model arrays, normalizer/error statistics, sequence
learning state, enrolled manifests and novelty memories. The runner raises if
VALIDATION or TEST changes those hashes. Causal history, audit records and dynamic
enforcement trust still advance during a phase, as they do at runtime.

Primary metrics use actual gateway intervention decisions and the existing fixed action
bands; they are distinct from the offline comparison's validation-p99 threshold.
Event rows include forwarding, provenance validation, memory disposition,
attestation verification and number of model updates during the call. An update
count can include previously buffered events promoted during that call, so it must
not be described as a count of malicious events learned without tracing provenance.

Recall/F1 are not informative in benign-only scenarios. FPR is not informative in
attack-only scenarios; the generic metric schema uses zero for empty denominators.
Interpret each row alongside its confusion counts and scenario labels.

The study reports means per variant/scenario/phase and exploratory paired F1 tests
matched by seed ID. These comparisons are not preregistered, adjusted confirmatory
tests. One or two seeds are smoke evidence only, not statistical superiority.

## Threat assumptions

An in-process sequential research fixture supplies independent identities to the
gateway resolver. A malicious client cannot create these identities by editing
`X-Sentinel-Session`. The same-attacker scenario deliberately maps all raw sessions
to one identity; the multi-actor scenario maps them to different compromised ones.
That second case exposes a real limit: independent sessions plus a valid manifest
do not guarantee benevolent behavior.

Mock response overrides are set only by the fixture and have no HTTP control route.
Labels and expected outcomes are used by metrics, never passed into the detector.
The attestation mechanism remains the existing experimental manifest hash echo.

## Output and provenance

- `protocol.json`: config, fixed policy, identity assumptions, Python/NumPy/platform,
  Git revision/dirty status and hashes of the implementation's Python source files.
- `<variant>/<scenario>/seed-<seed>-<phase>.json`: phase metrics, event evidence,
  workload hashes, actual sizes and before/after learning-state hashes.
- `summary.json`: aggregate metrics and exploratory paired comparisons.
- `REPORT.md`: readable comparison table.

Wall-clock transport timings, random challenge IDs and authorization claim IDs may
differ across runs. Seeded workloads and detection/learning decisions are covered
by deterministic regression checks. Retained historical results are not overwritten.

## Remaining work

Review the threat model and fixture coverage with the team, address the remaining
runtime controls now implemented (retention, deadlines, reviewed promotion and
recovery), preregister the final comparisons, and freeze a release commit.
Independent MCP traces and publication-scale evidence remain outstanding.
