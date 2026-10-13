"""Summary statistics for the repeated comparison: means with bootstrap 95% CIs and paired
differences over the same (scenario, seed) pairs. Resampling uses a fixed seed, so a report is
reproducible from its results file."""

from __future__ import annotations

import numpy as np

RESAMPLES = 10_000
BOOT_SEED = 20261013


def mean_ci(values: list[float], resamples: int = RESAMPLES, seed: int = BOOT_SEED) -> tuple[float, float, float]:
    """(mean, low, high): the percentile bootstrap 95% interval of the mean."""
    if not values:
        return float("nan"), float("nan"), float("nan")
    a = np.asarray(values, dtype=float)
    if len(a) == 1:
        return float(a[0]), float(a[0]), float(a[0])
    rng = np.random.default_rng(seed)
    means = a[rng.integers(0, len(a), size=(resamples, len(a)))].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(a.mean()), float(lo), float(hi)


def paired_diff(a: dict, b: dict) -> tuple[int, float, float, float]:
    """Mean of a[k] - b[k] over the keys both have, with its bootstrap CI: (n, mean, low, high)."""
    keys = sorted(set(a) & set(b))
    d = [a[k] - b[k] for k in keys]
    m, lo, hi = mean_ci(d)
    return len(keys), m, lo, hi


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=float), q))
