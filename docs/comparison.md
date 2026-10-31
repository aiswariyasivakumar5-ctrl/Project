# Comparative ML evaluation

## Models

The offline comparison implements six executable models:

- MCP Runtime Sentinel using its native interaction, intent, sequence, causal,
  attestation, uncertainty, and protected-learning architecture;
- Isolation Forest with deterministic randomized isolation trees;
- One-Class SVM trained on the primal one-class hinge objective using a deterministic
  random-Fourier approximation to an RBF kernel;
- a NumPy dense autoencoder with one tanh bottleneck and reconstruction-error score.
- a constrained NumPy LSTM sequence encoder with a trained reconstruction head;
- a constrained NumPy causal Transformer encoder with a trained reconstruction head.

The OCSVM is an explicit finite-dimensional RBF approximation, not scikit-learn's
dual kernel solver. This distinction must be retained in publications.
The sequence encoders are deterministically initialized and fixed because the runtime
does not include PyTorch/TensorFlow; only their heads are optimized. This distinction
must also be retained.

## Common representation

The ML baselines receive 31 past-only features:

- twelve structural features: latency, argument count/size/types, response size,
  shape/nesting, success, side-effect, and sensitive input/output indicators;
- intent mismatch, session position, server position, and repeated-tool state;
- server transition, previous-response/current-argument overlap, and embedded
  policy-instruction indicators;
- stable four-bin one-hot hashes for current tool, server, and previous tool.

Features use only the current interaction and earlier session state. Attack labels
and future events are never features. Scalers are fit only on TRAIN.

LSTM/Transformer inputs are length-eight, left-zero-padded same-session windows with
an explicit validity mask. History resets at session and split boundaries.

Sentinel receives the equivalent raw interaction and performs its native graph and
trust processing. Its full-history causal graph is an explicit architecture-specific
advantage under evaluation; the baseline overlap and transition features ensure the
underlying current/previous information is not withheld from comparison models.

## Split and calibration

Default sizes are at least 5,000 normal TRAIN interactions, 1,000 normal VALIDATION
interactions, and 3,000 requested TEST interactions. Cross-server attacks add benign
source context, so the realized test size can be slightly larger. TEST contains a
normal half and equally allocated malicious samples from twelve attack families.

All detectors fit only normal TRAIN data. A single model-wide threshold is fixed at
the 99th percentile of that model's normal VALIDATION anomaly scores, corresponding
to a predeclared 1% validation false-positive target. The same threshold applies to
every attack family, server, and test sample. Test labels and scores never affect it.

Raw scores are mapped to their empirical validation percentile for comparable
curves and risk-distribution output; decisions still use the raw validation threshold.

## Commands

Publication-size five-seed comparison:

```powershell
python -m sentinel_research.cli compare --seeds 42,123,456,789,1001 `
  --train-size 5000 --validation-size 1000 --test-size 3000 `
  --output results/baselines
```

Small smoke run:

```powershell
python -m sentinel_research.cli compare --seeds 42 --train-size 200 `
  --validation-size 80 --test-size 240 --output results/baselines_smoke
```

Generate the Markdown table:

```powershell
python -m sentinel_research.cli report --results results/baselines
```

Offline inference timing belongs to this comparison. Real transport and gateway
overhead remain separately measured with:

```powershell
python -m sentinel_research.cli gateway-benchmark --requests 100
```

## Stored results

Each model/seed JSON contains configuration, software versions, split sizes,
calibration rule and raw threshold, overall metrics, per-scenario metrics, per-server
metrics, fit time, and offline inference latency. Outputs include:

- `<root>/<model>/per_seed/seed-<seed>.json`;
- `<root>/per_seed.csv`;
- `<root>/per_scenario/metrics.csv`;
- `<root>/aggregate/metrics.json`;
- `<root>/aggregate/conference-table.md`.

Aggregate values report mean, sample standard deviation, minimum, and maximum. No
statistical significance claim is made.

## Integrity and limitations

- Scenario generation is fixed independently of model output.
- No per-attack threshold tuning occurs.
- Dense-autoencoder or OCSVM performance may exceed Sentinel and is reported as-is.
- Synthetic diversity is not a substitute for production MCP traces.
- Stable hash buckets can collide.
- RFF OCSVM performance depends on its finite approximation.
- Offline latency excludes JSON parsing, HTTP, policy enforcement, and audit overhead.
- The implemented dense autoencoder is a lightweight baseline, not the same as the
  Sentinel engine's online autoencoder component.
- Confidence intervals and significance tests are not yet implemented.
