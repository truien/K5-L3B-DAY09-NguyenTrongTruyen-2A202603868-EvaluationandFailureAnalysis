"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy import stats as sps

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    _check(human, judge)
    tp = fp = fn = tn = 0
    for h, j in zip(human, judge):
        if j == POS:
            tp, fp = tp + (h == POS), fp + (h != POS)
        else:
            fn, tn = fn + (h == POS), tn + (h != POS)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def _check(human: Sequence[str], judge: Sequence[str]) -> None:
    if len(human) != len(judge):
        raise ValueError("human and judge must have the same length")


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    c = confusion(human, judge)
    p = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else 0.0
    r = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else 0.0
    return p, r


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    c = confusion(human, judge)
    n = sum(c.values())
    if n == 0:
        raise ValueError("kappa undefined for empty input")
    p_o = (c["tp"] + c["tn"]) / n
    p_e = ((c["tp"] + c["fp"]) * (c["tp"] + c["fn"]) + (c["fn"] + c["tn"]) * (c["fp"] + c["tn"])) / (n * n)
    if math.isclose(p_e, 1.0):
        raise ValueError("kappa undefined: chance agreement is 1 (constant labels)")
    return (p_o - p_e) / (1 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denom = sensitivity + specificity - 1
    if denom <= 0:
        raise ValueError("judge no better than chance (sens + spec <= 1): cannot correct")
    return min(1.0, max(0.0, (observed_rate + specificity - 1) / denom))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    if len(a) != len(b):
        raise ValueError("paired samples must have equal length")
    if len(a) == 0:
        raise ValueError("empty samples")
    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if np.array_equal(x, y):
        return 0.0, 0.0, 0.0
    res = sps.bootstrap((x, y), lambda u, v, axis=-1: np.mean(u, axis=axis) - np.mean(v, axis=axis),
                        paired=True, vectorized=True, n_resamples=n_resamples, confidence_level=confidence,
                        method="percentile", rng=np.random.default_rng(rng))
    return float(np.mean(x) - np.mean(y)), float(res.confidence_interval.low), float(res.confidence_interval.high)


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    _check_nck(n, c, k)
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def _check_nck(n: int, c: int, k: int) -> None:
    if not (n >= 1 and 0 <= c <= n and 1 <= k <= n):
        raise ValueError(f"invalid (n={n}, c={c}, k={k}): need n >= 1, 0 <= c <= n, 1 <= k <= n")


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    _check_nck(n, c, k)
    return math.comb(c, k) / math.comb(n, k)
