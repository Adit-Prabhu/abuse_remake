"""Summary statistics for the repeated comparison. Resampling uses a fixed seed, so a report is
reproducible from its results file.

- ``mean_ci``: the mean with a percentile-bootstrap 95% interval over episodes; no interval for
  fewer than 2 episodes. A deterministic player can give the same value for every seed, and
  then the interval has zero width; the report says so rather than hiding it.
- ``wilson``: the Wilson score 95% interval for a success rate, which stays honest at 0/n and n/n.
- ``paired_diff``: the mean of per-pair differences over the same (scenario, seed) pairs.
- ``cluster_paired_diff``: the same, pooled over scenarios, resampling scenarios and then seeds
  within them, because seeds of one scenario are not independent of each other.
"""

from __future__ import annotations

import math

import numpy as np

RESAMPLES = 10_000
BOOT_SEED = 20261013
NAN = float("nan")


def mean_ci(values: list[float], resamples: int = RESAMPLES, seed: int = BOOT_SEED) -> tuple[float, float, float]:
    """(mean, low, high). Low and high are NaN for fewer than 2 values."""
    if not values:
        return NAN, NAN, NAN
    a = np.asarray(values, dtype=float)
    if len(a) < 2:
        return float(a[0]), NAN, NAN
    rng = np.random.default_rng(seed)
    means = a[rng.integers(0, len(a), size=(resamples, len(a)))].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(a.mean()), float(lo), float(hi)


def wilson(successes: int, n: int, z: float = 1.959964) -> tuple[float, float, float]:
    """(rate, low, high) with the Wilson score interval."""
    if n == 0:
        return NAN, NAN, NAN
    p = successes / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return p, max(0.0, centre - half), min(1.0, centre + half)


def paired_diff(a: dict, b: dict) -> tuple[int, float, float, float]:
    """Mean of a[k] - b[k] over the keys both have, with its bootstrap CI: (n, mean, low, high)."""
    keys = sorted(set(a) & set(b))
    m, lo, hi = mean_ci([a[k] - b[k] for k in keys])
    return len(keys), m, lo, hi


def cluster_paired_diff(a: dict, b: dict, resamples: int = RESAMPLES,
                        seed: int = BOOT_SEED) -> tuple[int, int, float, float, float]:
    """Keys are (scenario, seed). Returns (pairs, scenarios, mean, low, high); the interval comes
    from resampling scenarios with replacement, then seeds within each chosen scenario."""
    keys = sorted(set(a) & set(b))
    groups: dict = {}
    for k in keys:
        groups.setdefault(k[0], []).append(a[k] - b[k])
    if not keys:
        return 0, 0, NAN, NAN, NAN
    mean = float(np.mean([a[k] - b[k] for k in keys]))
    names = sorted(groups)
    if len(names) < 2:
        _, lo, hi = mean_ci(groups[names[0]], resamples, seed)
        return len(keys), 1, mean, lo, hi
    rng = np.random.default_rng(seed)
    arrays = [np.asarray(groups[g], dtype=float) for g in names]
    stats = np.empty(resamples)
    for i in range(resamples):
        picked = rng.integers(0, len(arrays), size=len(arrays))
        parts = [arrays[j][rng.integers(0, len(arrays[j]), size=len(arrays[j]))] for j in picked]
        stats[i] = np.concatenate(parts).mean()
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return len(keys), len(names), mean, float(lo), float(hi)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=float), q))
