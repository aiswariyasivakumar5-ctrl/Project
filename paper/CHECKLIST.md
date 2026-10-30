# General Publication Preparation Checklist

Paper Title: **MCP Runtime Sentinel: Context-Bound Authorization and Evidence-Gated Runtime Adaptation for Model Context Protocol Gateways**  
Venue: **Not selected**. Check the selected venue's scope, formatting rules, page limits, anonymization policy, and submission deadlines before submission. This checklist is venue-neutral and does not certify compliance with any particular venue.

---

## 1. Page Count and Formatting Compliance
- [ ] **Page Budget**: Check the selected venue's current page limit and whether references count.
- [ ] **Template Compliance**: The source currently uses Springer LNCS; confirm the selected venue accepts this exact template and class files.
- [ ] **Abstract Budget**: Recount and check the selected venue's abstract limit after final edits.
- [ ] **Keywords**: Check the selected venue's keyword requirements and final keyword count.
- [x] **Tables & Figures**: Generated automatically via `scripts/generate_paper_artifacts.py` using standard booktabs and vector PDF formats (`fig1_model_tradeoff.pdf`, `fig2_capability_isolation.pdf`, `fig3_gateway_latency.pdf`).

---

## 2. Anonymization & Double-Blind Integrity
- [x] **Author Identifiers**: Author names, affiliations, and institutions omitted from `main.tex`.
- [x] **Repository Links**: Public/private GitHub URLs removed from submission manuscript.
- [x] **Acknowledgments & Funding**: Omitted from blind review draft.
- [x] **Camera-Ready Authors Template**: Provided in `paper/camera_ready_authors.tex` for post-acceptance preparation.

---

## 3. Scientific Integrity & Data Claims Verification
- [ ] **Numerical Audit**: Headline baseline metrics are generated as macros; audit remaining narrative values and secondary results against their source artifacts before submission.
- [ ] **No False Overstatement**: Sweep all public-facing documents for outdated zero-false-positive or production-performance claims.
- [x] **Transparent Recall Breakdown**: All-or-nothing breakdown disclosed: exactly 8 of 12 attack families detected with 1.0000 recall, 4 families completely missed (0.0000 recall).
- [x] **Null Hypothesis Reporting**: Preserved true null and parity results for `intent_consistency` ($p = 1.0000$) and `review_requirement` ($p = 1.0000$) on the 20-seed novelty matrix v3.
- [ ] **Full-Trace Reproducibility**: Verification and mapping test pass locally; complete test-suite run and public raw-data availability still need confirmation.

---

## 4. Citation and Related Work Verification
- [ ] **Citation Verification**: Independently verify bibliographic metadata, publication status, and technical claims for every cited source:
  - Kumar et al. (MCP Guardian): arXiv:2504.12757 (April 2025).
  - MindGuard: arXiv:2508.20412 (August 2025) (author team resolved from arXiv record).
  - Tiago Rosado (Capability Pinning): TDCommons Paper 10604 (2026).
  - ShieldMCP: Open-source software security package (https://github.com/mcp-security/shieldmcp).
- [x] **Unverified References Audit**: Documented in `paper/UNVERIFIED_REFERENCES.md`.

---

## 5. Ethical Guidelines & AI-Use Disclosure
- [ ] **Originality Review**: Authors should complete the required originality/plagiarism review before submission.
- [x] **AI-Use Disclosure**: The authors utilized the Google DeepMind Antigravity AI agentic coding assistant to assist in script automation, unit test generation, experimental orchestration, and LaTeX formatting. All experimental results, statistical hypothesis tests, and raw traces were deterministically executed and verified on the local testbed.
- [x] **Synthetic Workload Disclosure**: State that evaluations use synthetic mock MCP services and do not establish real-world or production security guarantees.

## 6. Remaining Release Checks
- [ ] Compile the final LaTeX source and inspect the rendered PDF for layout, references, figures, and page count.
- [ ] Complete independent citation and claim verification; the presence of an audit note is not proof that every citation is valid.
- [ ] Decide how to publish the large raw novelty traces and replace pending archive placeholders only after an actual deposit and checksum verification.
- [ ] Run the complete test suite and reproducibility checks on the final commit and archive the resulting logs.
- [ ] Prepare the final author, affiliation, conflict-of-interest, funding, and AI-use disclosures required by the selected venue.
