# Verification-budget prior-art screening — October 16, 2026

Targeted question: are limited-budget uncertainty selection, delayed verification
and poisoning-aware active learning already studied? Include original research
and publisher/repository records; exclude secondary summaries as evidence of
originality. This screening uses abstracts, not a completed full-text review.

Searches: `budgeted online active learning concept drift uncertainty sampling
Zliobaite 2014` and `verification delayed labels online learning poisoning active
learning budget`. No private project source was submitted to search services.

| Source | Located overlap | Consequence for Sentinel |
|---|---|---|
| [Ienco, Žliobaitė and Pfahringer, 2014, High density-focused uncertainty sampling for active learning over evolving stream data](https://proceedings.mlr.press/v36/ienco14.html) | Online sliding-window selection combining density and predictive uncertainty to reduce labeling effort | Neither uncertainty ranking nor budgeted stream selection is new by itself. Our scheduler is simpler, not a reimplementation of DBALStream. |
| [Castellani, Schmitt and Hammer, 2022, Stream-based Active Learning with Verification Latency in Non-stationary Environments](https://arxiv.org/abs/2204.06822) | Delayed labels, concept drift, utility estimation and time-varying budgets; repository links an ICANN publication | Limited verification, delay and drift are already a research combination. We do not implement PRopagate or claim superiority against it. |
| [Active Learning Under Malicious Mislabeling and Poisoning Attacks, arXiv:2101.00157](https://arxiv.org/abs/2101.00157) | Active learning under malicious feedback and poisoning | Faulty-verifier stress tests are relevant but do not originate poisoning-aware active learning. Full method and assumption comparison remains pending. |

These are different tasks and evaluations; their results cannot be ranked against
Sentinel's arithmetic ingestion counts. Authors' claims are not independently
reproduced here. This is not an exhaustive patent search or legal opinion.

The implemented pilot's scope is narrower: study bounded result-verification
admission into a runtime anomaly model, with evidence TTL, capability binding,
and at-most-once delayed learning. Those safeguards also require prior-art review;
combining known safeguards is not automatically non-obvious. A defensible research
contribution requires measurable benefit over the simple budget-matched controls,
then stronger established active-learning baselines and independent workloads.

The frozen pilot is exploratory. Do not adjust selectors, thresholds or stream
composition after seeing its outcomes merely to obtain a favorable result.
