# -*- coding: utf-8 -*-
"""Diagnostic: full longest-run histograms per option, keypress vs stored space.

Purpose: decide whether Johnson's published file is ALREADY screened for straightlining
(a hard cliff in the run-length histogram) or whether the tail decays naturally.
"""
import collections
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402
from profile_sample import RUN_CUT, longest_runs  # noqa: E402


def main():
    z = ipip.load()
    items = z["items"].astype(np.int16)
    n = len(items)
    data = ipip.site_data()
    rev = np.array(sorted(data["reversed"]), dtype=np.int64)
    print("reversed items: %d  (min %d max %d)" % (len(rev), rev.min(), rev.max()))
    key = items.copy()
    key[:, rev - 1] = 6 - key[:, rev - 1]

    for label, X in (("RAW KEYPRESS (site-equivalent)", key), ("AS STORED (recoded)", items)):
        runs = longest_runs(X)
        print("\n=== %s" % label)
        for v in range(1, 6):
            c = collections.Counter(runs[:, v].tolist())
            top = sorted(c)[-14:]
            print(" option %d (site cut %2d): max=%2d  tail %s"
                  % (v, RUN_CUT[v], runs[:, v].max(),
                     " ".join("%d:%d" % (L, c[L]) for L in top)))
        # what per-option cut would the observed caps imply?
        print(" observed caps per option 1..5:", [int(runs[:, v].max()) for v in range(1, 6)])

    # option-usage sanity: overall response distribution in keypress space
    vals, cnts = np.unique(key, return_counts=True)
    print("\nkeypress option usage:", {int(a): int(b) for a, b in zip(vals, cnts)},
          "total", int(cnts.sum()), "rows", n)
    vals, cnts = np.unique(items, return_counts=True)
    print("stored   option usage:", {int(a): int(b) for a, b in zip(vals, cnts)})

    # how many rows would each candidate cut vector remove (keypress space)?
    runs = longest_runs(key)
    for cut in ([0, 6, 9, 10, 14, 9], [0, 9, 9, 9, 12, 9], [0, 5, 8, 9, 13, 8]):
        f = np.zeros(n, bool)
        for v in range(1, 6):
            f |= runs[:, v] > cut[v]
        print("cut %s -> %d flagged (%.4f%%)" % (cut[1:], int(f.sum()), 100.0 * f.sum() / n))


if __name__ == "__main__":
    main()
