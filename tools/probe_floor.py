# -*- coding: utf-8 -*-
"""What does each candidate ladder actually crush at the extremes?"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip, build_tables as B

z = ipip.load()
masks = ipip.group_masks(z["sex"], z["age"])
sc = ipip.scale_index()
names = [d if k == "domain" else "%s%d" % (d, f) for k, d, f in sc]
exact, rawv = {}, {}
for g in ipip.GROUPS:
    m = masks[g]
    for (kind, dom, fno), nm in zip(sc, names):
        v = (z["domain_raw"][m, ipip.DOMAIN_ORDER.index(dom)] if kind == "domain"
             else z["facet_raw"][m, ipip.facet_slot(dom, fno)])
        lo, hi = (60, 300) if kind == "domain" else (10, 50)
        exact[(g, nm)], _, _ = B.build_cell(v, lo, hi, float(v.mean()), float(v.std(ddof=1)))
        rawv[(g, nm)] = v

for lname in ("safe025", "safe025x"):
    lv = B.ladder_levels(B.LADDERS[lname])
    q = {k: lv[B.quantise(exact[k], lv)] for k in exact}
    nfloor = nceil = tot = 0
    coll = pairs = 0
    fspan_lo, fspan_hi = [], []
    for k in exact:
        base = 60 if len(k[1]) == 1 else 10
        i = rawv[k] - base
        p, e = q[k][i], exact[k][i]
        tot += len(i)
        fm = p <= lv[0] + 1e-12
        cm = p >= lv[-1] - 1e-12
        nfloor += int(fm.sum()); nceil += int(cm.sum())
        if fm.any(): fspan_lo.append((float(e[fm].min()), float(e[fm].max())))
        if cm.any(): fspan_hi.append((float(e[cm].min()), float(e[cm].max())))
        occ = np.unique(i)
        d = np.diff(q[k][occ])
        coll += int((d == 0).sum()); pairs += len(d)
    print("%s  levels=%d  min=%.4f max=%.4f" % (lname, len(lv), lv[0], lv[-1]))
    print("   at floor   : %6d (%.5f%%)" % (nfloor, 100.0 * nfloor / tot))
    print("   at ceiling : %6d (%.5f%%)" % (nceil, 100.0 * nceil / tot))
    if fspan_lo:
        print("   true pct range crushed into the floor  : %.6f - %.6f"
              % (min(a for a, b in fspan_lo), max(b for a, b in fspan_lo)))
    if fspan_hi:
        print("   true pct range crushed into the ceiling: %.6f - %.6f"
              % (min(a for a, b in fspan_hi), max(b for a, b in fspan_hi)))
    print("   adjacent occupied raw scores sharing a percentile: %d / %d (%.3f%%)"
          % (coll, pairs, 100.0 * coll / pairs))
