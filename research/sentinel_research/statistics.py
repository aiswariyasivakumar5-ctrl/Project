from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ConfidenceInterval:
    estimate: float
    lower: float
    upper: float
    confidence: float
    method: str
    resamples: int

    def to_dict(self) -> dict[str, float | int | str]:
        return self.__dict__.copy()


def bootstrap_mean_ci(
    values: list[float], seed: int = 2026, resamples: int = 20_000, confidence: float = 0.95
) -> ConfidenceInterval | None:
    if not values:
        return None
    data = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(data), size=(resamples, len(data)))
    estimates = data[indices].mean(axis=1)
    alpha = (1 - confidence) / 2
    return ConfidenceInterval(
        float(data.mean()),
        float(np.quantile(estimates, alpha)),
        float(np.quantile(estimates, 1 - alpha)),
        confidence,
        "seed-cluster percentile bootstrap of mean",
        resamples,
    )


def paired_bootstrap_difference(
    a: list[float],
    b: list[float],
    seed: int = 2026,
    resamples: int = 20_000,
    confidence: float = 0.95,
) -> ConfidenceInterval | None:
    if len(a) != len(b) or not a:
        return None
    differences = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    return bootstrap_mean_ci(differences.tolist(), seed, resamples, confidence)


def exact_paired_sign_flip(a: list[float], b: list[float]) -> dict[str, float | int | str] | None:
    if len(a) != len(b) or not a:
        return None
    differences = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    nonzero = differences[np.abs(differences) > 1e-15]
    n = len(nonzero)
    if n == 0:
        return {
            "mean_difference": 0.0,
            "p_value_two_sided": 1.0,
            "pairs": len(a),
            "nonzero_pairs": 0,
            "method": "exact paired sign-flip randomization",
        }
    if np.all(nonzero > 0) or np.all(nonzero < 0):
        p_value = float(2.0 ** (1 - n))
        return {
            "mean_difference": float(differences.mean()),
            "p_value_two_sided": p_value,
            "pairs": len(a),
            "nonzero_pairs": n,
            "method": "exact paired sign-flip randomization",
        }
    vals = [round(float(x), 6) for x in nonzero]
    sums = {0.0: 1}
    for v in vals:
        new_sums: dict[float, int] = {}
        for s, count in sums.items():
            s1 = round(s + v, 6)
            s2 = round(s - v, 6)
            new_sums[s1] = new_sums.get(s1, 0) + count
            new_sums[s2] = new_sums.get(s2, 0) + count
        sums = new_sums
    cutoff = abs(round(sum(vals), 6)) - 1e-7
    extreme = sum(count for s, count in sums.items() if abs(s) >= cutoff)
    p_value = float(extreme / (2.0**n))
    return {
        "mean_difference": float(differences.mean()),
        "p_value_two_sided": p_value,
        "pairs": len(a),
        "nonzero_pairs": n,
        "method": "exact paired sign-flip randomization",
    }


def wilcoxon_signed_rank(a: list[float], b: list[float]) -> dict[str, float | int | str] | None:
    """Exact paired Wilcoxon signed-rank test with mid-rank tie handling,

    exact dynamic programming permutation distribution for two-sided p-value,
    and matched-pairs rank-biserial correlation effect size r = (W_+ - W_-) / S.
    """
    if len(a) != len(b) or not a:
        return None
    differences = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    nonzero = differences[np.abs(differences) > 1e-15]
    n = len(nonzero)
    if n == 0:
        return {
            "statistic": 0.0,
            "w_plus": 0.0,
            "w_minus": 0.0,
            "total_rank_sum": 0.0,
            "p_value_two_sided": 1.0,
            "effect_size_r": 0.0,
            "pairs": len(a),
            "nonzero_pairs": 0,
            "method": "exact paired Wilcoxon signed-rank test",
        }
    abs_d = np.abs(nonzero)
    signs = np.sign(nonzero)
    order = np.argsort(abs_d)
    ranks = np.zeros(n, dtype=float)
    i = 0
    while i < n:
        j = i
        while j < n and abs(abs_d[order[j]] - abs_d[order[i]]) <= 1e-15:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[order[k]] = avg_rank
        i = j

    w_plus = float(np.sum(ranks[signs > 0]))
    w_minus = float(np.sum(ranks[signs < 0]))
    total_s = float(np.sum(ranks))
    statistic = min(w_plus, w_minus)
    effect_size_r = float((w_plus - w_minus) / total_s) if total_s > 0 else 0.0

    # Dynamic programming for exact null distribution of 2 * W_+
    # Scaling ranks by 2 ensures integer weights even with average ranks.
    int_ranks = np.round(ranks * 2).astype(int)
    max_sum = int(np.sum(int_ranks))
    dp = np.zeros(max_sum + 1, dtype=np.int64)
    dp[0] = 1
    for r in int_ranks:
        dp[r:] += dp[:-r].copy()

    w_plus_doubled = int(round(w_plus * 2))
    center = max_sum / 2.0
    dev = abs(w_plus_doubled - center)

    tails = 0
    for s in range(max_sum + 1):
        if abs(s - center) >= dev - 1e-7:
            tails += dp[s]
    p_value = float(min(1.0, tails / (2.0**n)))

    return {
        "statistic": statistic,
        "w_plus": w_plus,
        "w_minus": w_minus,
        "total_rank_sum": total_s,
        "p_value_two_sided": p_value,
        "effect_size_r": effect_size_r,
        "pairs": len(a),
        "nonzero_pairs": n,
        "method": "exact paired Wilcoxon signed-rank test",
    }


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values, key=p_values.get)
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for rank, name in enumerate(ordered):
        value = min(1.0, (total - rank) * p_values[name])
        running = max(running, value)
        adjusted[name] = running
    return adjusted
