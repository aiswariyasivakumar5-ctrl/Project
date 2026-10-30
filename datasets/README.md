# Expanded synthetic workloads v1

This is generated **input data**, not new experimental results or independent
MCP traces. It reuses the project's workload and scenario generators unchanged.
No external dataset was downloaded. All responses/latencies/identities are fixture
inputs; no credentials or real user sessions are collected.

Completed export: **1,050,380 records** in **480 compressed shards**, covering
20 seeds and 22 TEST scenarios. TRAIN: 200,000; VALIDATION: 40,000;
TEST: 810,380. These counts include repeated templates, not unique attack types.

## Reproduce

```powershell
python -m sentinel.dataset --output artifacts/synthetic-expanded-v1-rebuilt
```

The checked-in `synthetic-expanded-v1/manifest.json` lists actual per-shard
counts, class counts, generator source hashes, compressed and uncompressed SHA-256
hashes. Each `.jsonl.gz` holds JSON records readable with Python's `gzip.open`.
The exporter refuses existing directories and marks incomplete exports `building`.
Gzip headers use a fixed timestamp; reproducibility is tested in the same runtime.
Different compression-library versions may produce different gzip bytes; compare
uncompressed hashes as well.

## Configuration and split contract

- Twenty fixed seeds: 20001 through 20020, chosen consecutively before evaluation.
- 10,000 benign TRAIN and 2,000 benign VALIDATION records per seed.
- Every legacy scenario plus every novelty scenario, requested size 3,000.
  Novelty definitions take precedence for shared names. Generators with fixed
  attack counts remain fixed; the manifest reports actual counts, not 3,000 blindly.
- Generator RNG inputs are `seed*10` for TRAIN, `seed*10+1` for VALIDATION,
  and `seed*10+2` for TEST scenario generation.
- Event IDs are unique; session IDs are namespaced by seed/split/scenario while
  preserving within-scenario relationships. TRAIN/VALIDATION/TEST sessions cannot
  overlap. Server IDs and templates intentionally remain shared, so this is NOT
  a held-out-server or held-out-template generalization benchmark.
- Case labels, controls, provenance operations, and optional response overrides
  are retained. These are evaluation-only metadata, never model features or
  client-supplied gateway authority. `scenario` inside a benign prefix may be
  `normal`; the containing shard identifies the evaluation scenario.
- `adaptive_eligible` identifies existing adaptive novelty scenarios. Do not
  append adaptive observations to frozen TEST or learn from TEST. Any adaptive
  evaluation must independently restore its training checkpoint.

## Research limitations and next gate

This expands volume and seed coverage, **not the number of independent real-world
servers or attack templates**. Repeated benign prefixes and fixed attack templates
are correlated, including across seeds. Raw row counts are not statistical sample
sizes. Large gradual-poisoning parameter strings compress heavily and require much
more memory after decompression; stream one shard at a time.

The exporter is not wired into the live experiment runner. Before evaluating this
corpus, review an input adapter and a separate amended analysis protocol, freeze
that configuration, then run all comparison models on matched inputs. Calibrate
only on VALIDATION; never tune on TEST. No model training, new CIs, p-values,
accuracy improvement, or completed publication-scale experiment is claimed here.
The existing five-seed protocol and all retained results remain unchanged.
Independent licensed runtime traces and team review are still needed.
