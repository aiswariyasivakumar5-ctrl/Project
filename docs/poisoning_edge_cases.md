# Adversarial Poisoning Edge Cases in MCP Runtime Sentinel

**Publication Analysis for AI-SEC @ AINA-2027**  
**Evidence Source**: 20-seed matched evaluation (`results/adaptation/matched_poisoning_20seed/`, seeds 31001–31020, 700 cells total)

---

## Executive Summary

MCP Runtime Sentinel incorporates a dual-memory adaptation gate (`DualMemoryAdapter` / `gated` policy) designed to mitigate online model poisoning. Under this mechanism, newly observed interactions from unseen or unverified tools are buffered in an isolated quarantine memory (`quarantine_memory`) rather than being immediately incorporated into the production baseline (`production_memory`). Promotion to the production baseline requires sustained observation across a minimum threshold of distinct, authenticated caller identities (`promotion_threshold` independent principals).

While this mechanism successfully insulates the baseline against simple, single-source injection attacks (**0.0 malicious updates under `gated` vs. 12.0 under `immediate`**), systematic empirical evaluation across 20 randomized seeds demonstrates that poisoning **still succeeds completely or partially in three critical operational regimes**:

1. **Colluding identities (distributed/Sybil attackers)**: 12.0 / 12.0 malicious updates ingested (100% contamination).
2. **Mixed traffic (co-occurring benign and malicious workloads)**: 4.0 / 4.0 malicious updates ingested (33.3% contamination of total updates).
3. **Post-promotion drift / shape-equivalent payload manipulation**: 3.0 / 3.0 malicious updates ingested (25.0% contamination of total updates).

These findings represent structural identifiability and quorum-based architectural boundaries that must be explicitly acknowledged as limitations in the submitted paper.

---

## Failure Mode 1: Colluding Identities (Quorum Spoofing)

### Mechanism
Sentinel's dual-memory promotion gate enforces identity diversity: a candidate interaction pattern is quarantined until requests exhibiting that pattern are observed from $K \ge 3$ distinct `independent_identity` principals. The core assumption is that an attacker controls only a single principal context, making it impossible to satisfy the multi-principal quorum without triggering anomaly detection.

In the `colluding` stream, the adversary distributes identical malicious payload requests across distinct synthetic principals (`principal-0`, `principal-1`, ..., `principal-11`). 

### Empirical Outcome (20/20 Seeds)
| Policy | Total Updates (mean ± std) | Malicious Updates (mean ± std) | Contamination Rate | Benign Learning Delay |
|---|---|---|---|---|
| **immediate** | 12.0 ± 0.00 | 12.0 ± 0.00 | 1.000 [1.000, 1.000] | NA |
| **gated (Sentinel)** | **12.0 ± 0.00** | **12.0 ± 0.00** | **1.000 [1.000, 1.000]** | NA |
| **mistaken_review** | 12.0 ± 0.00 | 12.0 ± 0.00 | 1.000 [1.000, 1.000] | NA |
| **frozen / withheld** | 0.0 ± 0.00 | 0.0 ± 0.00 | 0.000 [0.000, 0.000] | NA |

### Root Cause & Vulnerability Analysis
Instead of blocking the attack, the identity diversity requirement acts as an enabler: by rotating distinct caller identities, the adversary satisfies the multi-principal promotion condition. At index 2, the third distinct caller is observed; the gateway marks the quarantined candidate as eligible and flushes all buffered interactions directly into `production_memory`. 

**Takeaway for Paper**: Identity counting without cryptographic sybil-resistance (e.g., proof-of-work, verifiable organizational credentials, or hardware attestation) provides no defense against distributed or multi-session poisoning. Distinct authenticated tokens do not prove independent adversarial intent.

---

## Failure Mode 2: Mixed Traffic (Quorum Hijacking / Tailgating)

### Mechanism
In real-world deployment, malicious requests rarely arrive in isolation; they are interleaved with legitimate user traffic. In the `mixed` stream, malicious arithmetic requests (e.g., returning $3.1$ instead of $3.0$) are injected every third step (indices 2, 5, 8, 11), while intervening steps (indices 0, 1, 3, 4, 6, 7, 9, 10) consist of benign calls from legitimate independent users.

### Empirical Outcome (20/20 Seeds)
| Policy | Total Updates (mean ± std) | Malicious Updates (mean ± std) | Contamination Rate | Benign Delay | Benign FPR |
|---|---|---|---|---|---|
| **immediate** | 12.0 ± 0.00 | 4.0 ± 0.00 | 0.333 [0.333, 0.333] | 0.0 steps | 0.000 |
| **gated (Sentinel)** | **12.0 ± 0.00** | **4.0 ± 0.00** | **0.333 [0.333, 0.333]** | 2.0 steps | 0.000 |
| **mistaken_review** | 12.0 ± 0.00 | 4.0 ± 0.00 | 0.333 [0.333, 0.333] | 2.0 steps | 0.000 |
| **oracle_review** | 0.0 ± 0.00 | 0.0 ± 0.00 | 0.000 [0.000, 0.000] | Censored (20/20) | 0.000 |

### Root Cause & Vulnerability Analysis
In mixed traffic:
1. Benign users supply legitimate calls from distinct identities (`benign-0`, `benign-1`, etc.).
2. The dual-memory buffer maintains a sliding window of recent interactions for the tool.
3. Because the tool name and schema match (`calculate`), benign calls and malicious calls are aggregated into the same tool-level quarantine candidate buffer.
4. The legitimate users satisfy the multi-identity threshold.
5. When promotion triggers at index 2, the entire candidate buffer—including the interleaved malicious interactions—is flushed into the production baseline.
6. The oracle reviewer, by contrast, withholds approval due to detecting the mixed stream, but as a result **learns zero benign events**, completely forfeiting adaptive utility.

**Takeaway for Paper**: Co-tenancy and shared tool namespace allow stealthy poisoning payloads to "tailgate" behind legitimate users' reputation and promotion quorum.

---

## Failure Mode 3: Post-Promotion Drift & Shape-Equivalent Payloads

### Mechanism
In the `late_sparse` scenario, the MCP server initially behaves completely honestly during an enrollment or probationary period (steps 0 to 5), allowing the tool to legitimately graduate from quarantine to the production baseline. Once promoted, the server begins returning sparse, incorrect arithmetic values ($3.1, 3.2, 3.3$) at steps 6, 8, and 10.

Crucially, the attacker crafts responses that preserve identical JSON schema and structural shapes:
- Expected response: `{"content": [{"type": "text", "text": "3.0"}]}` (length = 3)
- Poisoned response: `{"content": [{"type": "text", "text": "3.1"}]}` (length = 3)

### Empirical Outcome (20/20 Seeds)
| Policy | Total Updates (mean ± std) | Malicious Updates (mean ± std) | Contamination Rate | Post-Onset Malicious Admitted |
|---|---|---|---|---|
| **immediate** | 12.0 ± 0.00 | 3.0 ± 0.00 | 0.250 [0.250, 0.250] | 3 / 3 (100%) |
| **gated (Sentinel)** | **12.0 ± 0.00** | **3.0 ± 0.00** | **0.250 [0.250, 0.250]** | **3 / 3 (100%)** |
| **mistaken_review** | 12.0 ± 0.00 | 3.0 ± 0.00 | 0.250 [0.250, 0.250] | 3 / 3 (100%) |
| **oracle_review** | 0.0 ± 0.00 | 0.0 ± 0.00 | 0.000 [0.000, 0.000] | 0 / 3 (Censored) |

### Root Cause & Vulnerability Analysis
1. **Quarantine Bypass**: Dual-memory quarantine only intercepts *unpromoted* capabilities. Once a capability is promoted to the production baseline, subsequent calls are routed through the standard online update path.
2. **Feature Invariance**: The extractor `extract_features(interaction)` extracts response length, schema depth, and string character counts. Because `"3.1"` has identical length (3 chars), string type, and JSON key structure to `"3.0"`, `extract_features(correct) == extract_features(wrong)`.
3. The reconstruction error and behavioral risk score remain below the anomaly threshold ($\text{risk} < 0.50$). Consequently, the gateway cannot detect the arithmetic inaccuracy without an external arithmetic verifier or semantic oracle.

**Takeaway for Paper**: Schema and structural anomaly detectors are blind to semantic correctness within valid schemas. Once trust is established or approved, post-promotion semantic drift is ingested directly into online baseline memory.

---

## Comparison Summary Across Threat Scenarios

| Attack Vector | Baseline Memory Contaminated? | Why Sentinel Fails to Prevent Ingestion |
|---|---|---|
| **Single-Identity Attack** | **No** (0/12 updates admitted) | Adversary cannot provide multiple caller identities; remains quarantined indefinitely. |
| **Colluding Identities** | **Yes** (12/12 updates admitted) | Rotating identities satisfy the multi-principal quorum requirement, triggering automatic promotion. |
| **Mixed Benign/Malicious Traffic** | **Yes** (4/4 attacks admitted) | Interleaved benign users satisfy the quorum, causing co-buffered attack calls to be promoted. |
| **Post-Promotion Semantic Drift** | **Yes** (3/3 attacks admitted) | Capability is already in production memory; shape-equivalent wrong answers produce zero feature deviation. |

---

## Honest Narrative & Submission Guidelines

To adhere strictly to the Springer LNCS submission standards and non-negotiable research rules:
1. **Never claim generic "poisoning resistance"**: Sentinel's dual memory provides defense **only** against uncoordinated, single-identity injection.
2. **Explicitly disclose identity limits**: Distinct authenticated MCP identities cannot be assumed to represent independent, non-colluding entities.
3. **Acknowledge semantic blind spots**: Sentinel models structural and behavioral protocol features, not application-level arithmetic or logical correctness. An attacker operating within valid schemas can poison models undetected once promoted.
4. **Report negative results**: All numbers above reflect raw, reproducible 20-seed runs without hyperparameter tuning or selective reporting.
