# Preliminary prior-art screening — September 21, 2026

This is a documented technical search, not a patentability opinion or an exhaustive
patent search. Publication dates below are from the source pages. Legal relevance
depends on the eventual claims, jurisdiction and verified priority/conception dates.

Searches: `site.arxiv.org MCP security runtime guard tool poisoning intent provenance`
and `site.patents.google.com runtime trust provenance anomaly detection quarantine machine learning`.
The public queries disclosed no project source code or private documents.

| Source | Relevant overlap | Distinction to investigate |
|---|---|---|
| [MindGuard, arXiv:2508.20412](https://arxiv.org/abs/2508.20412), submitted August 28, 2025; revised January 15, 2026 | Decision provenance, dependency graphs and graph anomaly analysis for tool poisoning | Sentinel's gateway consumes context-bound single-use claims before dispatch; it does not inspect model attention. This is a technical difference, not proof of novelty. |
| [MCP Guardian, arXiv:2504.12757](https://arxiv.org/abs/2504.12757), 2025 | Security layer for MCP systems | A generic MCP gateway/security layer is not a defensible sole novelty claim. Full architectural comparison is still needed. |
| [Provenance-Bound Capability-Envelope Pinning](https://www.tdcommons.org/dpubs_series/10604/), Tiago Rosado, June 29, 2026 | MCP gateway, identity-bound manifest pinning, operator reapproval and structural changes | Sentinel currently lacks cryptographic workload identity and structural-diff authority. Its per-call consumption and adaptive-memory lifecycle need an element-level comparison. |
| [US20220407889A1](https://patents.google.com/patent/US20220407889A1/en), published December 22, 2022 | Provenance-based identification of cloud policy deviations | Combining provenance and anomaly detection is established subject matter; analyze actual claims and family members before proposing protection. |

The screening found substantial overlap with broad descriptions of runtime trust,
provenance, gateway enforcement and quarantine. Do not claim that those ingredients
or their MCP application are automatically new. The next professional search should
examine capability authorization, replay-resistant tokens, adaptive-model poisoning,
review revocation and provenance-bound learning, including citation chains and patent
families. No freedom-to-operate conclusion has been made.

The two arXiv papers and the disclosure were reviewed at abstract/landing-page level;
the patent landing page was inspected. Full claim construction and full-text paper
comparison remain outstanding. This document does not certify a formal prior-art review.
