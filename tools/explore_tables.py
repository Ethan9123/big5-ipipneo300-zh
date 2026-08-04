# -*- coding: utf-8 -*-
"""Exploration for the empirical percentile lookup tables (task: build_tables)."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip

z = ipip.load()
sex, age = z["sex"], z["age"]
masks = ipip.group_masks(sex, age)
facet_raw, domain_raw = z["facet_raw"], z["domain_raw"]

print("total rows", len(sex))
for g in ipip.GROUPS:
    print(g, int(masks[g].sum()))

# gap / sparsity stats
scales = ipip.scale_index()
print("n scales", len(scales))
tot_cells = 0
empty_cells = 0
per_kind = {"domain": [0, 0], "facet": [0, 0]}
worst = []
for g in ipip.GROUPS:
    m = masks[g]
    for kind, dom, fno in scales:
        if kind == "domain":
            v = domain_raw[m, ipip.DOMAIN_ORDER.index(dom)]
            lo, hi = ipip.DOMAIN_RAW_MIN, ipip.DOMAIN_RAW_MAX
        else:
            v = facet_raw[m, ipip.facet_slot(dom, fno)]
            lo, hi = ipip.FACET_RAW_MIN, ipip.FACET_RAW_MAX
        cnt = np.bincount(v - lo, minlength=hi - lo + 1)
        assert cnt.sum() == len(v)
        tot_cells += len(cnt)
        e = int((cnt == 0).sum())
        empty_cells += e
        per_kind[kind][0] += len(cnt)
        per_kind[kind][1] += e
        occ = np.nonzero(cnt)[0]
        # interior empty
        interior = int(((cnt[occ[0]:occ[-1] + 1]) == 0).sum())
        worst.append((e, interior, int(occ[0]) + lo, int(occ[-1]) + lo, g, kind, dom, fno))
print("total cells", tot_cells, "empty", empty_cells, "%.2f%%" % (100 * empty_cells / tot_cells))
for k, (t, e) in per_kind.items():
    print(k, "cells", t, "empty", e, "%.2f%%" % (100 * e / t))
worst.sort(reverse=True)
print("worst 8 by empty count (empty, interiorEmpty, minObs, maxObs, cohort, kind, dom, facet):")
for w in worst[:8]:
    print("  ", w)
inter_tot = sum(w[1] for w in worst)
print("interior empty cells total:", inter_tot)

# smallest cohort counts per cell
print()
print("min n over cohorts:", min(int(masks[g].sum()) for g in ipip.GROUPS))
