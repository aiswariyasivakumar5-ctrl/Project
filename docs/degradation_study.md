# Feature-changing poisoning and fixed probes

Results retained in `results/adaptation/degradation-20261006`; completion audited
October 16, 2026. All 45 runs completed: three training-order seeds, five policies,
and three streams. No production thresholds or historical results were changed.

Verification on October 16: all 226 tests passed in 100.800 seconds, retained
research verification passed for 43 files, and the evidence report audit passed.
These are local checks; no remote CI result is claimed for this milestone.

## Design

Each policy starts from 100 shuffled balanced integer-addition calls. The clean
stream contains 12 correct decimal-addition responses. The abrupt stream substitutes
12 wrong 64-digit answers. The gradual stream starts with three correct responses,
then substitutes nine wrong answers growing from 4 to 20 digits. Arguments, intent,
identities, and latency inputs remain matched. Blanket review is issued at index 0;
it has no oracle filtering. All response changes occur only in the local mock server.

Six probes were fixed before execution: two benign additions and four incorrect
answers of lengths 4, 12, 32 and 64. Each probe restores the enrolled checkpoint.
Only fitted scaler/autoencoder/error-moment state is transferred from the adapted
model; capability trust, quarantine counts and runtime history are not transferred.
Probes use `learn=False`, with model-digest invariance checked at every invocation.
This isolates fitted-model effects, not the complete live post-incident experience.

Compare both pre/post adaptation and poisoned-versus-clean adaptation at the same
seed/policy. Probes are development diagnostics, not a new held-out benchmark.
Three seeds change training order, not the underlying task inventory. Four attack
probes provide coarse recall resolution; two benign probes provide very limited
false-positive coverage.

```powershell
python -m sentinel.degradation_study --output results/adaptation/new-degradation
python -m sentinel.degradation_report --output results/adaptation/new-degradation
```

The report rejects incomplete matrices, event-attribution mismatches, inconsistent
probe digests/metrics, and incorrect paired clean comparisons. It renders all 45
rows without overwriting an existing report. The retained evidence audit checked
540 adaptive event records and 540 stored probe records. Pre-adaptation probes are
reused across streams within each seed/policy; these are not 540 independent probes.

## Findings

Exact rows: [audited tables](../results/adaptation/degradation-20261006/tables.md).

- Clean adaptation: immediate, gated and blanket-review policies each learned all
  12 events. Frozen and withheld policies learned none.
- Abrupt poisoning: no policy learned any of the 12 malicious events.
- Gradual poisoning: immediate, gated and blanket-review each learned six events,
  three benign and three malicious, in every seed. Their fitted model digests changed.
  Frozen and withheld learned none, including no benign adaptation.
- Fixed-probe attack recall was **0.75 before and after in every cell**; benign FPR
  was **0.00**. Thus this experiment did not demonstrate deterioration in those
  operating-point metrics, nor perfect detection.
- Gradual-poisoned models had lower mean attack risk than clean-adapted models by
  0.005612, 0.005034 and 0.004922 for seeds 31001, 31002 and 31003 respectively.
  These score changes were identical across immediate, gated and blanket-review.
  They did not cause a threshold crossing on the fixed probes.

There is no demonstrated advantage of gating over immediate learning for this
post-promotion gradual attack. Zero malicious updates under frozen/withheld policies
must be considered alongside their zero adaptation. A small score change is not a
statistically significant degradation claim, and unchanged probe recall is not proof
of general resistance. No confidence intervals or p-values are asserted here.

## Novelty evidence boundary

Completed: live trained-model promotion, matched poisoning ingestion, and isolated
feature-changing model-effect diagnostics with reproducible artifacts and tests.

Not established: robust poisoning resistance after promotion, semantic correctness
of same-shape responses, superiority across real MCP workloads, or patentable novelty.
The next substantive mechanism decision is what independent evidence can authorize
continued learning after a server changes behavior. Any proposed fix needs a separately
specified comparison and fresh evaluation data; do not tune against these probes.
