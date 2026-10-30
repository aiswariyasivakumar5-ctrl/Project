from __future__ import annotations

import csv
import json
from pathlib import Path


def generate_research_tables(
    baseline_root: str, ablation_root: str, statistics_root: str, output: str
) -> list[str]:
    baseline = json.loads(
        (Path(baseline_root) / "aggregate" / "metrics.json").read_text(encoding="utf-8")
    )
    ablation = json.loads(
        (Path(ablation_root) / "aggregate" / "metrics.json").read_text(encoding="utf-8")
    )
    ablation_stats = json.loads(
        (Path(ablation_root) / "aggregate" / "statistics.json").read_text(encoding="utf-8")
    )
    adaptive_stats = json.loads(
        (Path(ablation_root) / "aggregate" / "adaptive_statistics.json").read_text(encoding="utf-8")
    )
    baseline_stats = json.loads(
        (Path(statistics_root) / "baseline_statistics.json").read_text(encoding="utf-8")
    )
    target = Path(output)
    target.mkdir(parents=True, exist_ok=True)

    # 1. Baseline comparison table
    md_lines = [
        "| Model | F1 mean | F1 std | F1 95% bootstrap CI | Precision | Recall | FPR | AUROC | AUPRC | Wilcoxon p | Effect size r | Wilcoxon Holm p | Sign-flip p |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    baseline_rows = []
    for model, metrics in baseline.items():
        ci = baseline_stats.get("confidence_intervals", {}).get(model, {}).get("f1", {})
        ci_str = f"[{ci.get('lower', 0):.4f}, {ci.get('upper', 0):.4f}]" if ci else "[-, -]"
        comp = baseline_stats.get("paired_sentinel_minus_baseline", {}).get(model, {}).get("f1", {})
        wilc = comp.get("wilcoxon") or {}
        sign_flip = comp.get("test") or {}
        w_p = f"{wilc.get('p_value_two_sided'):.6f}" if "p_value_two_sided" in wilc else "-"
        w_r = f"{wilc.get('effect_size_r'):.4f}" if "effect_size_r" in wilc else "-"
        w_holm = f"{comp.get('wilcoxon_holm_p'):.6f}" if "wilcoxon_holm_p" in comp else "-"
        sf_p = (
            f"{sign_flip.get('p_value_two_sided'):.6f}" if "p_value_two_sided" in sign_flip else "-"
        )

        f1_mean = metrics["f1"]["mean"]
        f1_std = metrics["f1"]["std"]
        prec_mean = metrics["precision"]["mean"]
        rec_mean = metrics["recall"]["mean"]
        fpr_mean = metrics["false_positive_rate"]["mean"]
        auroc_mean = metrics["auroc"]["mean"]
        auprc_mean = metrics["auprc"]["mean"]

        md_lines.append(
            f"| {model} | {f1_mean:.4f} | {f1_std:.4f} | {ci_str} | "
            f"{prec_mean:.4f} | {rec_mean:.4f} | {fpr_mean:.4f} | "
            f"{auroc_mean:.4f} | {auprc_mean:.4f} | {w_p} | {w_r} | {w_holm} | {sf_p} |"
        )
        baseline_rows.append(
            {
                "model": model,
                "f1_mean": f1_mean,
                "f1_std": f1_std,
                "f1_ci_lower": ci.get("lower") if ci else None,
                "f1_ci_upper": ci.get("upper") if ci else None,
                "precision_mean": prec_mean,
                "precision_std": metrics["precision"]["std"],
                "recall_mean": rec_mean,
                "recall_std": metrics["recall"]["std"],
                "fpr_mean": fpr_mean,
                "fpr_std": metrics["false_positive_rate"]["std"],
                "auroc_mean": auroc_mean,
                "auprc_mean": auprc_mean,
                "wilcoxon_p_value": wilc.get("p_value_two_sided"),
                "wilcoxon_effect_size_r": wilc.get("effect_size_r"),
                "wilcoxon_holm_p": comp.get("wilcoxon_holm_p"),
                "sign_flip_p_value": sign_flip.get("p_value_two_sided"),
            }
        )

    (target / "baseline_comparison.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    with (target / "baseline_comparison.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(baseline_rows[0].keys()))
        writer.writeheader()
        writer.writerows(baseline_rows)
    (target / "baseline_comparison.json").write_text(
        json.dumps(baseline_rows, indent=2), encoding="utf-8"
    )

    # 2. Ablation matrix table
    abl_lines = [
        "| Sentinel variant | F1 mean | F1 std | F1 95% bootstrap CI | Recall | Precision | FPR | Wilcoxon p | Effect size r | Wilcoxon Holm p | Sign-flip p |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    ablation_rows = []
    for variant, metrics in ablation.items():
        ci = ablation_stats.get("confidence_intervals", {}).get(variant, {}).get("f1", {})
        ci_str = f"[{ci.get('lower', 0):.4f}, {ci.get('upper', 0):.4f}]" if ci else "[-, -]"
        comp = ablation_stats.get("paired_full_minus_ablation", {}).get(variant, {}).get("f1", {})
        wilc = comp.get("wilcoxon") or {}
        sign_flip = comp.get("test") or {}
        w_p = f"{wilc.get('p_value_two_sided'):.6f}" if "p_value_two_sided" in wilc else "-"
        w_r = f"{wilc.get('effect_size_r'):.4f}" if "effect_size_r" in wilc else "-"
        w_holm = f"{comp.get('wilcoxon_holm_p'):.6f}" if "wilcoxon_holm_p" in comp else "-"
        sf_p = (
            f"{sign_flip.get('p_value_two_sided'):.6f}" if "p_value_two_sided" in sign_flip else "-"
        )

        f1_mean = metrics["f1"]["mean"]
        f1_std = metrics["f1"]["std"]
        rec_mean = metrics["recall"]["mean"]
        prec_mean = metrics["precision"]["mean"]
        fpr_mean = metrics["false_positive_rate"]["mean"]

        abl_lines.append(
            f"| {variant} | {f1_mean:.4f} | {f1_std:.4f} | {ci_str} | "
            f"{rec_mean:.4f} | {prec_mean:.4f} | {fpr_mean:.4f} | {w_p} | {w_r} | {w_holm} | {sf_p} |"
        )
        ablation_rows.append(
            {
                "variant": variant,
                "f1_mean": f1_mean,
                "f1_std": f1_std,
                "f1_ci_lower": ci.get("lower") if ci else None,
                "f1_ci_upper": ci.get("upper") if ci else None,
                "recall_mean": rec_mean,
                "recall_std": metrics["recall"]["std"],
                "precision_mean": prec_mean,
                "precision_std": metrics["precision"]["std"],
                "fpr_mean": fpr_mean,
                "fpr_std": metrics["false_positive_rate"]["std"],
                "wilcoxon_p_value": wilc.get("p_value_two_sided"),
                "wilcoxon_effect_size_r": wilc.get("effect_size_r"),
                "wilcoxon_holm_p": comp.get("wilcoxon_holm_p"),
                "sign_flip_p_value": sign_flip.get("p_value_two_sided"),
            }
        )

    (target / "ablation_matrix.md").write_text("\n".join(abl_lines) + "\n", encoding="utf-8")
    with (target / "ablation_matrix.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(ablation_rows[0].keys()))
        writer.writeheader()
        writer.writerows(ablation_rows)
    (target / "ablation_matrix.json").write_text(
        json.dumps(ablation_rows, indent=2), encoding="utf-8"
    )

    # 3. Adaptive analysis table
    adp_lines = [
        "| Adaptive comparison | Mean difference | 95% bootstrap CI | Exact paired p |",
        "|---|---:|---:|---:|",
    ]
    adp_rows = []
    for name, value in adaptive_stats.get("comparisons", {}).items():
        ci, test = value.get("difference_ci", {}), value.get("test", {})
        lower = ci.get("lower", 0.0) if ci else 0.0
        upper = ci.get("upper", 0.0) if ci else 0.0
        diff = test.get("mean_difference", 0.0) if test else 0.0
        p_val = test.get("p_value_two_sided", 1.0) if test else 1.0
        adp_lines.append(f"| {name} | {diff:.4f} | [{lower:.4f}, {upper:.4f}] | {p_val:.6f} |")
        adp_rows.append(
            {
                "comparison": name,
                "mean_difference": diff,
                "ci_lower": lower,
                "ci_upper": upper,
                "p_value_two_sided": p_val,
            }
        )
    (target / "adaptive_analysis.md").write_text("\n".join(adp_lines) + "\n", encoding="utf-8")
    if adp_rows:
        with (target / "adaptive_analysis.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(adp_rows[0].keys()))
            writer.writeheader()
            writer.writerows(adp_rows)
        (target / "adaptive_analysis.json").write_text(
            json.dumps(adp_rows, indent=2), encoding="utf-8"
        )

    # 4. Per attack recall table
    variant_results = {}
    for variant_dir in Path(ablation_root).iterdir():
        seed_files = (
            sorted((variant_dir / "per_seed").glob("seed-*.json")) if variant_dir.is_dir() else []
        )
        if seed_files:
            variant_results[variant_dir.name] = [
                json.loads(path.read_text(encoding="utf-8")) for path in seed_files
            ]
    scenarios = sorted(
        {
            scenario
            for results in variant_results.values()
            for scenario in results[0]["per_scenario"]
            if scenario != "normal"
        }
    )
    variants = list(variant_results)
    per_attack_lines = [
        "| Attack scenario | " + " | ".join(variants) + " |",
        "|---|" + "---:|" * len(variants),
    ]
    per_attack_rows = []
    for scenario in scenarios:
        row_dict = {"scenario": scenario}
        cells = []
        for variant in variants:
            values = [
                result["per_scenario"][scenario]["recall"] for result in variant_results[variant]
            ]
            mean_val = sum(values) / len(values) if values else 0.0
            row_dict[variant] = mean_val
            cells.append(f"{mean_val:.4f}")
        per_attack_lines.append("| " + scenario + " | " + " | ".join(cells) + " |")
        per_attack_rows.append(row_dict)

    (target / "per_attack_recall.md").write_text(
        "\n".join(per_attack_lines) + "\n", encoding="utf-8"
    )
    if per_attack_rows:
        with (target / "per_attack_recall.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(per_attack_rows[0].keys()))
            writer.writeheader()
            writer.writerows(per_attack_rows)
        (target / "per_attack_recall.json").write_text(
            json.dumps(per_attack_rows, indent=2), encoding="utf-8"
        )

    return [
        str(target / name)
        for name in (
            "baseline_comparison.md",
            "baseline_comparison.csv",
            "baseline_comparison.json",
            "ablation_matrix.md",
            "ablation_matrix.csv",
            "ablation_matrix.json",
            "adaptive_analysis.md",
            "adaptive_analysis.csv",
            "adaptive_analysis.json",
            "per_attack_recall.md",
            "per_attack_recall.csv",
            "per_attack_recall.json",
        )
    ]
