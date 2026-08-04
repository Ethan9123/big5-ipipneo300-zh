# -*- coding: utf-8 -*-
"""How well does a 3^5 = 243-cell personality typology actually behave?

Two questions that decide how the feature has to be written:
  1. Occupancy -- which of the 243 cells real people actually land in, and how often.
  2. Stability -- if the same person took the test again, would they get the same cell?

Percentiles come from the empirical lookup tables built earlier (the shipped ones now),
bands are the site's new 低 <=30 / 中等 / 高 >=70 cuts.
"""
import io
import json
import os
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

OCEAN = ["O", "C", "E", "A", "N"]
LO, HI = 30.0, 70.0
BAND = ["低", "中", "高"]
rng = np.random.default_rng(20260803)

tables = json.load(io.open(os.path.join(ipip.OUT, "pct_tables.json"), encoding="utf-8"))
psy = json.load(io.open(os.path.join(ipip.OUT, "psychometrics.json"), encoding="utf-8"))
alpha = {d["domain"]: d["alpha"] for d in psy["reliability"]["domains"]}
print("domain alphas:", {k: round(v, 4) for k, v in alpha.items()})

z = ipip.load()
domain_raw, sex, age = z["domain_raw"], z["sex"], z["age"]
masks = ipip.group_masks(sex, age)

# cohort key per respondent (M/F cohorts partition the sample)
cohort = np.where(sex == 1, "M", "F")
cohort = np.char.add(cohort, np.where(age < 21, "_lt21", "_gte21"))


def pct_of(raw_col, key, cohort_names):
    """Look the raw scores up in the shipped empirical tables."""
    out = np.empty(len(raw_col), dtype=np.float64)
    for g in ("M_lt21", "M_gte21", "F_lt21", "F_gte21"):
        m = cohort_names == g
        tab = tables["tables"][g][key]
        arr = np.asarray(tab["pct_quantised"], dtype=np.float64)
        idx = np.clip(raw_col[m] - tab["raw_min"], 0, len(arr) - 1)
        out[m] = arr[idx]
    return out


def band(p):
    return np.where(p <= LO, 0, np.where(p < HI, 1, 2))


pcts = {k: pct_of(domain_raw[:, ipip.DOMAIN_ORDER.index(k)], k, cohort) for k in OCEAN}
bands = {k: band(pcts[k]) for k in OCEAN}
cell = np.zeros(len(sex), dtype=np.int32)
for k in OCEAN:
    cell = cell * 3 + bands[k]

n = len(sex)
counts = Counter(cell.tolist())
print("\n=== OCCUPANCY (n=%d) ===" % n)
print("cells with at least one person : %d / 243" % len(counts))
print("cells with >= 100 people       : %d" % sum(1 for v in counts.values() if v >= 100))
print("cells with >= 1000 people      : %d" % sum(1 for v in counts.values() if v >= 1000))
print("cells with < 10 people         : %d" % sum(1 for v in counts.values() if v < 10))


def name(c):
    out = []
    for k in OCEAN:
        out.append(k + BAND[(c // (3 ** (4 - OCEAN.index(k)))) % 3])
    return "".join(out)


top = counts.most_common(10)
print("\nmost common 10 cells:")
for c, v in top:
    print("   %-14s %6d  %5.2f%%" % (name(c), v, 100.0 * v / n))
rare = sorted(counts.items(), key=lambda kv: kv[1])[:8]
print("rarest occupied cells:")
for c, v in rare:
    print("   %-14s %6d  %.4f%%" % (name(c), v, 100.0 * v / n))
empty = [c for c in range(243) if c not in counts]
print("empty cells (%d): %s" % (len(empty), ", ".join(name(c) for c in empty[:12])))
print("\nshare of people covered by the top 20 cells: %.1f%%"
      % (100.0 * sum(v for _, v in counts.most_common(20)) / n))

# ---------------------------------------------------------------- boundary proximity
print("\n=== BOUNDARY PROXIMITY ===")
for margin in (2, 5, 10):
    near = np.zeros(n, dtype=bool)
    for k in OCEAN:
        p = pcts[k]
        near |= (np.abs(p - LO) < margin) | (np.abs(p - HI) < margin)
    print("  at least one dimension within %2d percentile points of a 30/70 cut: %.1f%%"
          % (margin, 100.0 * near.mean()))

# ---------------------------------------------------------------- retest stability
# Classical model: observed = true + error, SEM_raw = SD * sqrt(1 - alpha).
# A parallel form draws a fresh error term, so simulate raw' = true + e' where
# true = observed - e. Standard approach: raw' = observed*alpha + mean*(1-alpha) + N(0, SD*sqrt(alpha*(1-alpha)))
# is regression-to-the-mean; the simpler and more conservative parallel-form draw is
# raw' = true_est + N(0, SEM) with true_est = observed (i.e. one SEM of fresh noise).
print("\n=== RETEST STABILITY (parallel-form simulation) ===")
REPS = 20
same_cell = np.zeros(n, dtype=np.float64)
same_per_dim = {k: np.zeros(n) for k in OCEAN}
for _ in range(REPS):
    cell2 = np.zeros(n, dtype=np.int32)
    for k in OCEAN:
        d = ipip.DOMAIN_ORDER.index(k)
        col = domain_raw[:, d].astype(np.float64)
        sd = col.std(ddof=1)
        sem = sd * np.sqrt(1.0 - alpha[k])
        noisy = np.rint(col + rng.normal(0, sem, n)).astype(np.int32)
        noisy = np.clip(noisy, ipip.DOMAIN_RAW_MIN, ipip.DOMAIN_RAW_MAX)
        b2 = band(pct_of(noisy, k, cohort))
        same_per_dim[k] += (b2 == bands[k])
        cell2 = cell2 * 3 + b2
    same_cell += (cell2 == cell)
same_cell /= REPS
print("  SEM in raw points per domain:",
      {k: round(domain_raw[:, ipip.DOMAIN_ORDER.index(k)].std(ddof=1) * np.sqrt(1 - alpha[k]), 1) for k in OCEAN})
print("  P(identical 243-cell on a parallel form) : %.1f%%" % (100.0 * same_cell.mean()))
for k in OCEAN:
    print("     %s band reproduces: %.1f%%" % (k, 100.0 * (same_per_dim[k] / REPS).mean()))
print("  people whose cell reproduces >90%% of the time: %.1f%%" % (100.0 * (same_cell > 0.9).mean()))
print("  people whose cell reproduces <50%% of the time: %.1f%%" % (100.0 * (same_cell < 0.5).mean()))

json.dump({
    "n": int(n),
    "bands": {"low_max": LO, "high_min": HI},
    "occupancy": {"occupied": len(counts), "empty": len(empty),
                  "ge100": sum(1 for v in counts.values() if v >= 100),
                  "ge1000": sum(1 for v in counts.values() if v >= 1000),
                  "lt10": sum(1 for v in counts.values() if v < 10),
                  "top20_share_pct": 100.0 * sum(v for _, v in counts.most_common(20)) / n,
                  "counts": {name(c): int(v) for c, v in counts.items()}},
    "stability": {"cell_reproduce_pct": float(100.0 * same_cell.mean()),
                  "per_dim_pct": {k: float(100.0 * (same_per_dim[k] / REPS).mean()) for k in OCEAN}},
}, io.open(os.path.join(ipip.OUT, "cells_243.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("\nwrote out/cells_243.json")
