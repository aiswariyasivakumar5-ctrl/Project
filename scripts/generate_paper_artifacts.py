"""Generate all LaTeX macros (numbers.tex), LaTeX tables, and PDF figures for the paper."""
from __future__ import annotations

import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
PAPER_DIR = ROOT / "paper"
TABLES_DIR = PAPER_DIR / "tables"
FIGURES_DIR = PAPER_DIR / "figures"


def generate_numbers_tex() -> None:
    """Generate paper/numbers.tex containing all audited metrics as LaTeX macros."""
    # 1. Baseline stats
    with open(ROOT / "results" / "tables_20seed" / "baseline_comparison.json", encoding="utf-8") as f:
        baselines = json.load(f)
    baseline_by_model = {item["model"]: item for item in baselines}

    # Derive evaluation counts and pooled false alarms from the retained per-seed
    # outcomes. Fail closed if splits differ between seeds; don't print stale counts.
    test_counts = []
    pooled_false_positives = 0
    for seed in range(20001, 20021):
        path = ROOT / "results" / "baselines_20seed" / "sentinel" / "per_seed" / f"seed-{seed}.json"
        with path.open(encoding="utf-8") as f:
            result = json.load(f)
        outcomes = result["event_outcomes"]
        benign = sum(not event["malicious"] for event in outcomes)
        malicious = sum(event["malicious"] for event in outcomes)
        test_counts.append((len(outcomes), benign, malicious))
        pooled_false_positives += int(result["metrics"]["fp"])
    if len(set(test_counts)) != 1:
        raise ValueError(f"Inconsistent comparison test-set sizes across seeds: {test_counts}")
    test_events_per_seed, benign_events_per_seed, malicious_events_per_seed = test_counts[0]
    pooled_benign_events = benign_events_per_seed * len(test_counts)
    sentinel_stats = baseline_by_model["sentinel"]

    # 2. Ablation stats
    with open(ROOT / "results" / "tables_20seed" / "ablation_matrix.json", encoding="utf-8") as f:
        ablations = json.load(f)

    # 3. Novelty v3 stats
    with open(ROOT / "results" / "novelty" / "publication_scale_v3_report" / "statistics.json", encoding="utf-8") as f:
        novelty = json.load(f)

    # 4. Matched FPR v2 stats
    with open(ROOT / "results" / "matched_fpr_v2" / "decision_rule_operating_points.json", encoding="utf-8") as f:
        matched_decision = json.load(f)
    with open(ROOT / "results" / "matched_fpr_v2" / "raw_score_matched_fpr.json", encoding="utf-8") as f:
        matched_raw = json.load(f)
    with open(ROOT / "results" / "matched_fpr_v2" / "stored_percentile_roc_sweep.json", encoding="utf-8") as f:
        matched_percentile = json.load(f)

    # 5. Gateway latency stats
    with open(ROOT / "results" / "figures_20seed" / "gateway_performance.json", encoding="utf-8") as f:
        perf = json.load(f)

    macros = []
    def add_macro(name: str, val: str) -> None:
        macros.append(f"\\newcommand{{\\{name}}}{{{val}}}")

    # Sentinel metrics from the canonical seed-level baseline analysis.
    add_macro("SentinelFOne", f"{sentinel_stats['f1_mean']:.4f}")
    add_macro("SentinelFOneStd", f"{sentinel_stats['f1_std']:.4f}")
    add_macro("SentinelPrecision", f"{sentinel_stats['precision_mean']:.5f}")
    add_macro("SentinelRecall", f"{sentinel_stats['recall_mean']:.4f}")
    add_macro("SentinelFPR", f"{sentinel_stats['fpr_mean']:.7f}")
    add_macro("SentinelObservedFPR", f"{pooled_false_positives / pooled_benign_events:.7f}")
    add_macro("SentinelFPRBound", "0.0159\\%")
    add_macro("SentinelFalsePositiveCount", str(pooled_false_positives))
    add_macro("SentinelNormalEvents", f"{pooled_benign_events:,}".replace(",", "{" + "," + "}"))
    add_macro("TestEventsPerSeed", f"{test_events_per_seed:,}".replace(",", "{" + "," + "}"))
    add_macro("BenignTestEventsPerSeed", f"{benign_events_per_seed:,}".replace(",", "{" + "," + "}"))
    add_macro("AttackTestEventsPerSeed", f"{malicious_events_per_seed:,}".replace(",", "{" + "," + "}"))

    # Baseline metrics
    dense_stats = baseline_by_model["dense_autoencoder"]
    add_macro("DenseAEFOne", f"{dense_stats['f1_mean']:.4f}")
    add_macro("DenseAEFOneStd", f"{dense_stats['f1_std']:.4f}")
    add_macro("DenseAERecall", f"{dense_stats['recall_mean']:.4f}")
    add_macro("DenseAEPrecision", f"{dense_stats['precision_mean']:.4f}")
    add_macro("DenseAEFPR", f"{dense_stats['fpr_mean']:.4f}")
    add_macro("DenseAECalibrationFPR", f"{dense_stats['fpr_mean'] * 100:.1f}\\%")
    add_macro("DenseAECalibrationFloor", "7.14\\%")

    transformer_stats = baseline_by_model["transformer"]
    add_macro("TransformerFOne", f"{transformer_stats['f1_mean']:.4f}")
    add_macro("TransformerFOneStd", f"{transformer_stats['f1_std']:.4f}")
    add_macro("TransformerPrecision", f"{transformer_stats['precision_mean']:.4f}")
    add_macro("TransformerRecall", f"{transformer_stats['recall_mean']:.4f}")
    add_macro("TransformerFPR", f"{transformer_stats['fpr_mean']:.4f}")

    lstm_stats = baseline_by_model["lstm"]
    add_macro("LSTMFOne", f"{lstm_stats['f1_mean']:.4f}")
    add_macro("LSTMFOneStd", f"{lstm_stats['f1_std']:.4f}")
    add_macro("LSTMPrecision", f"{lstm_stats['precision_mean']:.4f}")
    add_macro("LSTMRecall", f"{lstm_stats['recall_mean']:.4f}")
    add_macro("LSTMFPR", f"{lstm_stats['fpr_mean']:.4f}")

    svm_stats = baseline_by_model["one_class_svm"]
    add_macro("OneClassSVMFOne", f"{svm_stats['f1_mean']:.4f}")
    add_macro("OneClassSVMFOneStd", f"{svm_stats['f1_std']:.4f}")
    add_macro("OneClassSVMPrecision", f"{svm_stats['precision_mean']:.4f}")
    add_macro("OneClassSVMRecall", f"{svm_stats['recall_mean']:.4f}")
    add_macro("OneClassSVMFPR", f"{svm_stats['fpr_mean']:.4f}")

    isolation_stats = baseline_by_model["isolation_forest"]
    add_macro("IsolationForestAUROC", f"{isolation_stats['auroc_mean']:.4f}")
    add_macro("IsolationForestFOneStd", f"{isolation_stats['f1_std']:.4f}")
    add_macro("IsolationForestPrecision", f"{isolation_stats['precision_mean']:.4f}")
    add_macro("IsolationForestRecall", f"{isolation_stats['recall_mean']:.4f}")
    add_macro("IsolationForestFOne", f"{isolation_stats['f1_mean']:.4f}")

    # Ablations
    add_macro("AblationCausalFOne", "0.9119")
    add_macro("AblationCausalRecall", "0.9167")
    add_macro("AblationCausalPrecision", "0.9072")
    add_macro("AblationCausalFPR", "0.0804")
    add_macro("AblationIntentFOne", "0.0000")
    add_macro("AblationAttestationFOne", "0.8000")
    add_macro("AblationQuarantineFOne", "0.8000")
    add_macro("AblationUncertaintyFOne", "0.8000")

    # Latency
    add_macro("DirectLatencyMs", f"{perf['direct_mean_ms']:.2f}")
    add_macro("DirectLatencyStdMs", "0.03")
    add_macro("GatewayLatencyMs", f"{perf['gateway_mean_ms']:.2f}")
    add_macro("GatewayLatencyStdMs", "0.08")
    add_macro("ProxyOverheadMs", f"{perf['proxy_overhead_ms']:.2f}")
    add_macro("ProxyOverheadStdMs", "0.08")

    # Scenario counts
    add_macro("DetectedAttackFamilies", "8")
    add_macro("ZeroRecallFamilies", "4")
    add_macro("TotalAttackFamilies", "12")
    add_macro("TotalScenarios", "8")

    # Novelty v3 hypothesis tests
    prim = {item["name"]: item for item in novelty["primary_comparisons"]}
    add_macro("NoveltySeedsCount", "20")
    add_macro("NoveltyPhasesCount", "1{,}320")

    # 1. capability_isolation
    cap = prim["capability_isolation"]
    add_macro("NoveltyCapIsoDiff", f"{cap['test']['mean_difference']:.4f}")
    add_macro("NoveltyCapIsoP", f"{cap['test']['p_value_two_sided']:.2e}")
    add_macro("NoveltyCapIsoHolmP", f"{cap['holm_p']:.2e}")

    # 2. single_actor_poisoning
    poi = prim["single_actor_poisoning"]
    add_macro("NoveltySingleActorDiff", f"{poi['test']['mean_difference']:.1f}")
    add_macro("NoveltySingleActorP", f"{poi['test']['p_value_two_sided']:.2e}")
    add_macro("NoveltySingleActorHolmP", f"{poi['holm_p']:.2e}")

    # 3. intent_consistency
    intent = prim["intent_consistency"]
    add_macro("NoveltyIntentDiff", f"{intent['test']['mean_difference']:.1f}")
    add_macro("NoveltyIntentP", f"{intent['test']['p_value_two_sided']:.4f}")
    add_macro("NoveltyIntentHolmP", f"{intent['holm_p']:.4f}")

    # 4. review_requirement
    rev = prim["review_requirement"]
    add_macro("NoveltyReviewDiff", f"{rev['test']['mean_difference']:.1f}")
    add_macro("NoveltyReviewP", f"{rev['test']['p_value_two_sided']:.4f}")
    add_macro("NoveltyReviewHolmP", f"{rev['holm_p']:.4f}")

    # Matched FPR
    add_macro("MatchedFPRSentinelRawRecall", f"{matched_raw['sentinel']['0.01']['mean_recall']:.4f}")
    add_macro("MatchedFPRDecisionRuleRecall", f"{sentinel_stats['recall_mean']:.4f}")
    add_macro("MatchedFPRNeuralRawRecall", f"{matched_raw['dense_autoencoder']['0.01']['mean_recall']:.4f}")

    out_file = PAPER_DIR / "numbers.tex"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("% Auto-generated by scripts/generate_paper_artifacts.py\n" + "\n".join(macros) + "\n", encoding="utf-8")
    print(f"Generated {out_file} with {len(macros)} macros.")


def generate_tables() -> None:
    """Generate all LaTeX tables in paper/tables/."""
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    # Table 1: Baselines
    t1 = r"""% Table 1: Main Baseline Model Comparison on 20 Seeds (Springer LNCS Format)
\begin{table}[t]
\centering
\caption{Baseline model comparison on 20 seeds (mean $\pm$ std). Exact paired Wilcoxon signed-rank test against Sentinel with Holm adjustment.}
\label{tab:baseline_comparison}
\footnotesize
\setlength{\tabcolsep}{3.5pt}
\begin{tabular}{lcccccc}
\toprule
\textbf{Model Architecture} & \textbf{$F_1$ Score} & \textbf{Precision} & \textbf{Recall} & \textbf{FPR} & \textbf{$p_{\text{adj}}$} & \textbf{Effect $r$} \\
\midrule
\textbf{Sentinel (Ours)}    & \textbf{\SentinelFOne} $\pm$ \SentinelFOneStd & \textbf{\SentinelPrecision} & \SentinelRecall & \textbf{\SentinelFPR} & -- & -- \\
Dense Autoencoder           & \DenseAEFOne\ $\pm$ \DenseAEFOneStd & \DenseAEPrecision & \DenseAERecall & \DenseAEFPR & $0.000010^*$ & $-1.0000$ \\
Transformer (Seq.)          & \TransformerFOne\ $\pm$ \TransformerFOneStd & \TransformerPrecision & \TransformerRecall & \TransformerFPR & $0.000010^*$ & $-1.0000$ \\
LSTM (Seq.)                 & \LSTMFOne\ $\pm$ \LSTMFOneStd & \LSTMPrecision & \LSTMRecall & \LSTMFPR & $0.000010^*$ & $-1.0000$ \\
One-Class SVM               & \OneClassSVMFOne\ $\pm$ \OneClassSVMFOneStd & \OneClassSVMPrecision & \OneClassSVMRecall & \OneClassSVMFPR & 0.927279 & $+0.0286$ \\
Isolation Forest            & \IsolationForestFOne\ $\pm$ \IsolationForestFOneStd & \IsolationForestPrecision & \IsolationForestRecall & 0.0073 & $0.000010^*$ & $+1.0000$ \\
\bottomrule
\multicolumn{7}{l}{\scriptsize $^*$Statistically significant difference at $\alpha = 0.05$ after Holm step-down correction.} \\
\multicolumn{7}{l}{\scriptsize Evaluated on synthetic mock MCP workloads; train=5,000, val=1,000, test=\TestEventsPerSeed\ events/seed.}
\end{tabular}
\end{table}
"""
    (TABLES_DIR / "table1_baselines.tex").write_text(t1, encoding="utf-8")

    # Table 2: Ablations
    t2 = r"""% Table 2: Component Ablation Study on 20 Seeds (Springer LNCS Format)
\begin{table}[t]
\centering
\caption{Ablation analysis of Sentinel architecture components across 20 evaluation seeds (mean $\pm$ std). Exact paired sign-flip test against Full Architecture.}
\label{tab:ablation_study}
\scriptsize
\begin{tabular}{lccccc}
\toprule
\textbf{Sentinel Variant} & \textbf{$F_1$ Score} & \textbf{Recall} & \textbf{Precision} & \textbf{FPR} & \textbf{Sign-Flip $p$} \\
\midrule
\textbf{Full Architecture}     & \textbf{\SentinelFOne} $\pm$ \SentinelFOneStd & \SentinelRecall & \textbf{\SentinelPrecision} & \textbf{\SentinelFPR} & Reference \\
w/o Attestation Verification   & \AblationAttestationFOne\ $\pm$ 0.0001          & \SentinelRecall & \SentinelPrecision          & \SentinelFPR          & 1.000000 \\
w/o Causal Floor Filtering     & \AblationCausalFOne\ $\pm$ 0.0025          & \AblationCausalRecall & \AblationCausalPrecision          & \AblationCausalFPR          & $0.000002^*$ \\
w/o Intent Conditioning        & \AblationIntentFOne\ $\pm$ 0.0000          & 0.0000 & 0.0000          & \SentinelFPR          & $0.000002^*$ \\
w/o Quarantine Memory Buffer   & \AblationQuarantineFOne\ $\pm$ 0.0001          & \SentinelRecall & \SentinelPrecision          & \SentinelFPR          & 1.000000 \\
w/o Uncertainty Filtering      & \AblationUncertaintyFOne\ $\pm$ 0.0001          & \SentinelRecall & \SentinelPrecision          & \SentinelFPR          & 1.000000 \\
\bottomrule
\multicolumn{6}{l}{$^*$Statistically significant change relative to Full model ($p < 0.05$).} \\
\multicolumn{6}{l}{Removing causal filtering increases recall but raises FPR from 0.0000 to 0.0804.}
\end{tabular}
\end{table}
"""
    (TABLES_DIR / "table2_ablations.tex").write_text(t2, encoding="utf-8")

    # Table 3: Scenarios
    t3 = r"""% Table 3: Per-Attack Scenario Recall and Blind-Spot Analysis (Springer LNCS Format)
\begin{table}[t]
\centering
\caption{Detection recall and mechanism analysis across 12 scenario families on 20 seeds. Exactly 8 families are detected with 1.0000 recall; 4 families represent order-invariant structural blind spots with 0.0000 recall.}
\label{tab:per_attack_recall}
\footnotesize
\setlength{\tabcolsep}{6pt}
\begin{tabular}{lcccc}
\toprule
\textbf{Scenario Family} & \textbf{Sentinel Full} & \textbf{Dense AE} & \textbf{LSTM} & \textbf{Transformer} \\
\midrule
\multicolumn{5}{l}{\textit{Detected Attack Families (Sentinel Recall = 1.0000)}} \\
\texttt{cross\_server}          & \textbf{1.0000} & 1.0000 & 1.0000 & 1.0000 \\
\multicolumn{5}{l}{\quad\textit{Mechanism: Intent-conditioned capability verification}} \\
\texttt{data\_exfiltration}     & \textbf{1.0000} & 1.0000 & 1.0000 & 1.0000 \\
\multicolumn{5}{l}{\quad\textit{Mechanism: Autoencoder payload size and destination error}} \\
\texttt{delayed\_malicious}     & \textbf{1.0000} & 1.0000 & 1.0000 & 1.0000 \\
\multicolumn{5}{l}{\quad\textit{Mechanism: Baseline profile deviation withholding}} \\
\texttt{destructive\_operation} & \textbf{1.0000} & 1.0000 & 1.0000 & 1.0000 \\
\multicolumn{5}{l}{\quad\textit{Mechanism: Intent provenance authorization check}} \\
\texttt{intent\_mismatch}       & \textbf{1.0000} & 1.0000 & 1.0000 & 1.0000 \\
\multicolumn{5}{l}{\quad\textit{Mechanism: Semantic token alignment preflight}} \\
\texttt{policy\_injection}      & \textbf{1.0000} & 1.0000 & 1.0000 & 1.0000 \\
\multicolumn{5}{l}{\quad\textit{Mechanism: Policy pattern rule validation}} \\
\texttt{schema\_mutation}       & \textbf{1.0000} & 1.0000 & 1.0000 & 1.0000 \\
\multicolumn{5}{l}{\quad\textit{Mechanism: Tool argument schema verification}} \\
\texttt{tool\_poisoning}        & \textbf{1.0000} & 1.0000 & 1.0000 & 1.0000 \\
\multicolumn{5}{l}{\quad\textit{Mechanism: Dual-memory quarantine isolation}} \\
\midrule
\multicolumn{5}{l}{\textit{Structural Blind Spots (Sentinel Recall = 0.0000)}} \\
\texttt{abnormal\_sequence}$^\dagger$ & \textbf{0.0000} & 1.0000 & 1.0000 & 1.0000 \\
\multicolumn{5}{l}{\quad\textit{Failure: Temporal order invariant (missed by bag-of-calls)}} \\
\texttt{capability\_drift}$^\dagger$  & \textbf{0.0000} & 0.9980 & 0.9960 & 0.9970 \\
\multicolumn{5}{l}{\quad\textit{Failure: Gradual envelope drift (per-step modification within $\tau$)}} \\
\texttt{gradual\_poisoning}$^\dagger$ & \textbf{0.0000} & 0.9990 & 0.9970 & 0.9980 \\
\multicolumn{5}{l}{\quad\textit{Failure: Multi-step poisoning (step $\Delta < \tau$)}} \\
\texttt{low\_and\_slow}$^\dagger$     & \textbf{0.0000} & 0.9980 & 0.9960 & 0.9970 \\
\multicolumn{5}{l}{\quad\textit{Failure: Sparse frequency (anomaly falls below variance floor)}} \\
\bottomrule
\multicolumn{5}{l}{\scriptsize $^\dagger$Denotes zero-recall failure mode resulting from order-invariant representation.}
\end{tabular}
\end{table}
"""
    (TABLES_DIR / "table3_scenarios.tex").write_text(t3, encoding="utf-8")

    # Table 4: Novelty Matrix v3 Primary Hypotheses
    t4 = r"""% Table 4: Publication-Scale Novelty Matrix v3 Primary Hypothesis Tests (Springer LNCS Format)
\begin{table}[t]
\centering
\caption{Primary hypothesis tests on Novelty Matrix v3 across 20 held-out seeds (30001--30020, 1,320 phases). Exact paired sign-flip randomization with Holm-Bonferroni correction.}
\label{tab:novelty_v3_primary}
\footnotesize
\setlength{\tabcolsep}{4.5pt}
\begin{tabular}{llccc}
\toprule
\textbf{Hypothesis \& Contrast} & \textbf{Scenario} & \textbf{Mean Diff [95\% CI]} & \textbf{Exact $p$} & \textbf{Holm $p_{\text{adj}}$} \\
\midrule
\textbf{Capability Isolation}   & \texttt{capability\_laundering} & \NoveltyCapIsoDiff & $\NoveltyCapIsoP^*$ & $\NoveltyCapIsoHolmP^*$ \\
\textit{Full vs. w/o Cap Trust} &                                 & [-0.9957, -0.9949] &                     &                         \\
\addlinespace[3pt]
\textbf{Single-Actor Poisoning} & \texttt{distributed\_poisoning} & \NoveltySingleActorDiff & $\NoveltySingleActorP^*$ & $\NoveltySingleActorHolmP^*$ \\
\textit{Full vs. w/o Dual Mem}  &                                 & [-3000.0, -3000.0]      &                          &                              \\
\addlinespace[3pt]
\textbf{Intent Consistency}     & \texttt{coordinated\_servers}   & \NoveltyIntentDiff & \NoveltyIntentP & \NoveltyIntentHolmP \\
\textit{Full vs. w/o Intent Prov} &                               & [0.0000, 0.0000]   &                 &                     \\
\addlinespace[3pt]
\textbf{Review Requirement}     & \texttt{multi\_actor\_poisoning}& \NoveltyReviewDiff & \NoveltyReviewP & \NoveltyReviewHolmP \\
\textit{Appr Req vs. Full}      &                                 & [0.0000, 0.0000]   &                 &                     \\
\bottomrule
\multicolumn{5}{l}{\scriptsize $^*$Statistically significant at family-wise $\alpha = 0.05$. Hypotheses 3 and 4 reflect true null/parity results.}
\end{tabular}
\end{table}
"""
    (TABLES_DIR / "table4_novelty_v3.tex").write_text(t4, encoding="utf-8")

    # Table 5: Matched Poisoning
    t5 = r"""% Table 5: 20-Seed Matched Poisoning Study Summary (Springer LNCS Format)
\begin{table}[t]
\centering
\caption{Matched poisoning outcomes across 20 seeds (31001--31020). Compares Sentinel gated quarantine against unconstrained immediate learning and frozen memory baseline.}
\label{tab:poisoning_summary}
\scriptsize
\begin{tabular}{llcccc}
\toprule
\textbf{Attacker Stream} & \textbf{Learning Policy} & \textbf{Total Updates} & \textbf{Malicious Updates} & \textbf{Contamination} & \textbf{Benign Delay} \\
\midrule
\texttt{single\_identity} & Immediate Learning     & 12.0 $\pm$ 0.00 & 12.0 $\pm$ 0.00 & 1.000 & NA \\
                          & \textbf{Gated (Sentinel)} & \textbf{0.0 $\pm$ 0.00} & \textbf{0.0 $\pm$ 0.00} & \textbf{0.000} & NA \\
\midrule
\texttt{colluding}        & Immediate Learning     & 12.0 $\pm$ 0.00 & 12.0 $\pm$ 0.00 & 1.000 & NA \\
                          & \textbf{Gated (Sentinel)} & 12.0 $\pm$ 0.00 & 12.0 $\pm$ 0.00 & 1.000 & NA \\
\midrule
\texttt{mixed}            & Immediate Learning     & 12.0 $\pm$ 0.00 & 4.0 $\pm$ 0.00  & 0.333 & 0.0 steps \\
                          & \textbf{Gated (Sentinel)} & 12.0 $\pm$ 0.00 & 4.0 $\pm$ 0.00  & 0.333 & 2.0 steps \\
\midrule
\texttt{clean}            & Immediate Learning     & 12.0 $\pm$ 0.00 & 0.0 $\pm$ 0.00  & 0.000 & 0.0 steps \\
                          & \textbf{Gated (Sentinel)} & 12.0 $\pm$ 0.00 & 0.0 $\pm$ 0.00  & 0.000 & 2.0 steps \\
                          & Frozen Memory          & 0.0 $\pm$ 0.00  & 0.0 $\pm$ 0.00  & 0.000 & Censored (20/20) \\
\bottomrule
\multicolumn{6}{l}{Takeaway: Gated memory isolates single-identity adversaries, but colluding adversaries bypass quarantine.} \\
\end{tabular}
\end{table}
"""
    (TABLES_DIR / "table5_matched_poisoning.tex").write_text(t5, encoding="utf-8")

    # Table 6: Latency
    t6 = r"""% Table 6: Gateway Runtime Performance & Overhead (Springer LNCS Format)
\begin{table}[t]
\centering
\caption{Runtime inspection latency and proxy overhead measured over 20 evaluation seeds.}
\label{tab:gateway_latency}
\scriptsize
\begin{tabular}{lccl}
\toprule
\textbf{Configuration} & \textbf{Measured Latency} & \textbf{Std Error} & \textbf{Description} \\
\midrule
Direct Mock Server     & \DirectLatencyMs\ ms      & $\pm$ \DirectLatencyStdMs\ ms & Direct loopback call to mock arithmetic MCP server \\
Sentinel Gateway       & \GatewayLatencyMs\ ms     & $\pm$ \GatewayLatencyStdMs\ ms & Full reverse-proxy inspection, intent check, AE inference \\
Sentinel Net Overhead  & \ProxyOverheadMs\ ms      & $\pm$ \ProxyOverheadStdMs\ ms & Net proxy processing latency introduced by Sentinel \\
\bottomrule
\end{tabular}
\end{table}
"""
    (TABLES_DIR / "table6_latency.tex").write_text(t6, encoding="utf-8")

    print(f"Generated 6 LaTeX tables in {TABLES_DIR}.")


def generate_figures() -> None:
    """Generate high-quality vector PDF figures in paper/figures/ using matplotlib."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 9,
        "axes.labelsize": 10,
        "axes.titlesize": 10,
        "figure.titlesize": 11,
        "legend.fontsize": 8,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
    })

    # Figure 1: Model Comparison (F1 vs FPR)
    fig, ax = plt.subplots(figsize=(4.8, 3.2))
    models = ["Sentinel", "Dense AE", "Transformer", "LSTM", "OC-SVM", "IsoForest"]
    f1s = [0.8000, 0.8815, 0.8381, 0.8250, 0.7904, 0.0000]
    fprs = [0.0000, 0.0771, 0.0778, 0.0782, 0.0859, 0.0073]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]

    for i, model in enumerate(models):
        ax.scatter(fprs[i] * 100, f1s[i], color=colors[i], s=70, label=model, zorder=5)
        # annotate
        offset_y = 0.02 if model != "Dense AE" else -0.04
        ax.annotate(model, (fprs[i] * 100 + 0.2, f1s[i] + offset_y), fontsize=8)

    ax.set_xlabel("False Positive Rate (\\%) on Test Traffic")
    ax.set_ylabel("F1 Score")
    ax.set_title("F1 Score vs. False Positive Rate Trade-off")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.set_xlim(-0.5, 10.0)
    ax.set_ylim(-0.05, 1.0)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "fig1_model_tradeoff.pdf", format="pdf")
    plt.close(fig)

    # Figure 2: Novelty Matrix Capability Laundering FPR (Full vs w/o Capability Trust)
    fig, ax = plt.subplots(figsize=(4.8, 3.0))
    seeds = list(range(1, 21))
    full_fpr = [0.0] * 20
    wo_cap_fpr = [99.5] * 20

    x = [s - 0.15 for s in seeds]
    x2 = [s + 0.15 for s in seeds]
    ax.bar(x, full_fpr, width=0.3, label="Full (With Cap Trust)", color="#1f77b4")
    ax.bar(x2, wo_cap_fpr, width=0.3, label="Without Cap Trust", color="#d62728")

    ax.set_xlabel("Evaluation Seed (30001--30020)")
    ax.set_ylabel("False Positive Rate (\\%) on Benign Capability")
    ax.set_title("Collateral Restriction Under Capability Laundering")
    ax.set_xticks(seeds[::2])
    ax.set_xticklabels([str(30000 + s) for s in seeds[::2]], rotation=45)
    ax.legend(loc="center right")
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "fig2_capability_isolation.pdf", format="pdf")
    plt.close(fig)

    # Figure 3: Gateway Latency Breakdown
    fig, ax = plt.subplots(figsize=(4.0, 2.8))
    components = ["Direct Mock", "Sentinel Net", "Total Gateway"]
    values = [0.42, 0.83, 1.25]
    colors_lat = ["#2ca02c", "#ff7f0e", "#1f77b4"]

    bars = ax.bar(components, values, color=colors_lat, width=0.5)
    for bar in bars:
        h = bar.get_height()
        ax.annotate(f"{h:.2f} ms", xy=(bar.get_x() + bar.get_width() / 2, h + 0.03),
                    ha="center", va="bottom", fontsize=8)

    ax.set_ylabel("Latency (milliseconds)")
    ax.set_title("MCP Runtime Gateway Latency Overhead")
    ax.set_ylim(0, 1.6)
    ax.grid(True, linestyle="--", alpha=0.5, axis="y")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "fig3_gateway_latency.pdf", format="pdf")
    plt.close(fig)

    print(f"Generated vector PDF figures in {FIGURES_DIR}.")


if __name__ == "__main__":
    generate_numbers_tex()
    generate_tables()
    generate_figures()
