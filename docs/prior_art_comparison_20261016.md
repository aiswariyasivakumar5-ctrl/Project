# Targeted technical prior-art comparison — October 16, 2026

## Scope and method

Question: which implemented Sentinel mechanisms differ technically from published
MCP runtime defenses and adaptive-learning protections, and what evidence supports
those differences? Include original papers, publisher records, technical disclosures,
and relevant patent text published by October 16, 2026. Exclude marketing summaries
as evidence of originality, unrelated federated-learning settings, and unverified
citations. This is a targeted follow-up to `prior_art_screening.md`, not a systematic
review, exhaustive patent search, legal claim construction, or freedom-to-operate opinion.

Sources were selected from the earlier screen and targeted searches for MCP runtime
verification and adaptive online poisoning. We inspected the specific sections below;
we did not reproduce the authors' experiments. Missing descriptions are not evidence
that a feature has never been published. Dates alone do not establish legal priority.

## Evidence and differences

| Primary source and inspected material | Relevant mechanism and evidence | Sentinel comparison and limitation |
| --- | --- | --- |
| [Yergattikar, ShieldMCP, ACL Industry 2026](https://aclanthology.org/2026.acl-industry.58/), [PDF](https://aclanthology.org/2026.acl-industry.58.pdf), sections 3–5 and Limitations | Proxy checks descriptions, parameters and responses; hashes detect changes requiring reauthorization; a session dependency graph flags unexpected follow-on calls. Authors evaluate 40 servers, 487 attacks, 200 benign tasks and five model backends. | Substantial overlap with broad runtime/intent/graph claims. Sentinel's explicit single-use context claim and retained learning-evidence lifecycle are narrower candidate distinctions, not proven novelty. ShieldMCP reports residual chain attacks, English-only classifier training and limited expert review. Its attack-success outcomes cannot be compared numerically with Sentinel's synthetic per-call F1. |
| [Wang et al., MindGuard, arXiv:2508.20412v3](https://arxiv.org/html/2508.20412v3), preprint, sections IV–V and VII | Decision-dependency graphs use attention-derived signals to inspect call provenance. Discussion identifies weaker semantic-parameter signals, inactive poisoned-context noise and attribution ambiguity. | Sentinel's claims are gateway-issued authorization records, not evidence of the LLM's internal causal reasoning; it requires no attention access. Do not equate lexical intent overlap with MindGuard's decision inspection or causal explanation. Neither mechanism's performance is independently replicated here. |
| [Bose et al., AISTATS 2025](https://proceedings.mlr.press/v258/bose25b.html), publisher abstract | Studies dynamic online poisoning with certified impact bounds, illustrated on mean estimation and binary classification. Full PDF retrieval failed in this review. | Protecting online learning is established research. Sentinel currently has empirical ingestion controls, not certified robustness. Different task assumptions prevent direct superiority claims. Further full-text comparison is pending. |
| [Rosado, Technical Disclosure Commons, June 29, 2026](https://www.tdcommons.org/dpubs_series/10604/), landing-page disclosure | Identity-bound surface pins, operator reapproval after structural changes, and import-time intent screening. Linked full-text retrieval failed. | Sentinel does not implement this disclosure's cryptographic workload identity or structural-diff authority. Blocking and review are not novel by themselves; distinguish invocation authorization from tool-surface approval. A defensive disclosure is not an independently evaluated system. |
| [US20220407889A1](https://patents.google.com/patent/US20220407889A1/en), displayed claims 1, 10 and 19 | Describes provenance ledger, actor authorization, trust-weighted bipartite graph, real-time deviation rules and infrastructure rollback. Related grant listed as US11553005B1. | Sentinel does not provide an immutable transaction ledger or infrastructure rollback. Provenance plus trust plus enforcement is not a defensible broad originality claim. This technical comparison does not determine infringement, validity, claim scope or legal status; official prosecution/family review remains necessary. |

The earlier MCP Guardian entry remains abstract-level only: the attempted HTML
full-text URL was unavailable. No stronger architectural conclusion was added.

## Element-level claim discipline

| Candidate element | Local implementation evidence | Defensible statement now | Missing evidence |
| --- | --- | --- | --- |
| Context-bound single-use invocation authority | `sentinel/provenance.py`; replay/concurrency tests | Implemented authorization consumption before dispatch, including failure cases | Dedicated capability/token prior-art search and independent review |
| Capability-scoped isolation | `sentinel/novelty.py`; gateway integration tests | Implemented partial isolation, not a claim to invent least privilege | Complete matched collateral-denial comparison |
| Evidence-gated candidate promotion and revocation | `sentinel/novelty.py`; matched/degradation diagnostics | Observable learning lifecycle with documented collusion and post-promotion weaknesses | General resistance, independent identities and realistic operator evidence |
| Per-event trusted result verification | `sentinel/verified_learning.py`; 100-cell diagnostic | Narrow arithmetic verifier prevents ingestion in the tested fixtures | Coverage on nontrivial tools; verifier cost/errors; benefit beyond simple verified-immediate baseline |

Our synthesis: a precise lifecycle and its failure analysis may be a useful systems
contribution. The current evidence does not establish that the combination is
non-obvious, uniquely new, or superior. In particular, the verified-immediate
ablation matches the combined verifier/gate's ingestion protection and adapts faster.
Do not present that result as a contribution of dual memory.

## Review handoff

Before a paper or patent claim: independently verify source sections and citation
chains; search capability tokens, replay protection, taint/data-flow authorization,
training-data admission and revocable approval together; document the specific
technical effect versus the simplest relevant baseline. Have qualified counsel
assess claims, priority, disclosure history and jurisdiction. Do not publish new
private invention details merely to search for them. No patentability conclusion
or complete closure of the runtime-security gap follows from this comparison.
