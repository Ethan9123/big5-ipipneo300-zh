# -*- coding: utf-8 -*-
"""Pick the quantisation ladder on displayed-integer fidelity vs bytes."""
import gzip, os, sys
import brotli
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip
import build_tables as B

z = ipip.load()
masks = ipip.group_masks(z["sex"], z["age"])
facet_raw, domain_raw = z["facet_raw"], z["domain_raw"]
scales = ipip.scale_index()
names = [d if k == "domain" else "%s%d" % (d, f) for k, d, f in scales]

exact, norms, rawv = {}, {}, {}
for g in ipip.GROUPS:
    m = masks[g]
    for (kind, dom, fno), nm in zip(scales, names):
        if kind == "domain":
            v = domain_raw[m, ipip.DOMAIN_ORDER.index(dom)]; lo, hi = 60, 300
        else:
            v = facet_raw[m, ipip.facet_slot(dom, fno)]; lo, hi = 10, 50
        mu, sd = float(v.mean()), float(v.std(ddof=1))
        p, _, _ = B.build_cell(v, lo, hi, mu, sd)
        exact[(g, nm)] = p; norms[(g, nm)] = (mu, sd); rawv[(g, nm)] = v

EXTRA = {
    "c015": [(0, .01), (0.5, .05), (2, .1), (5, .15), (95, .1), (98, .05), (99.5, .01)],
    "c03":  [(0, .01), (0.5, .05), (2, .1), (5, .3), (95, .1), (98, .05), (99.5, .01)],
    "c04":  [(0, .01), (0.5, .05), (2, .1), (5, .4), (95, .1), (98, .05), (99.5, .01)],
    "c05t": [(0, .01), (0.5, .05), (2, .1), (5, .5), (95, .1), (98, .05), (99.5, .01)],
    "c10t": [(0, .01), (0.5, .05), (2, .2), (5, 1.0), (95, .2), (98, .05), (99.5, .01)],
}
CAND = dict(B.LADDERS); CAND.update(EXTRA)

print("%-8s %6s %9s %9s %8s %8s %8s %8s" % (
    "ladder", "levels", "maxqerr", "meanqerr", "raw", "brotli", "gzip", "dispdiff%"))
rows = []
for name, spec in CAND.items():
    levels = B.ladder_levels(spec)
    if len(levels) > 1072:
        print("%-8s %6d  skipped (too many levels)" % (name, len(levels))); continue
    q = {k: B.quantise(exact[k], levels) for k in exact}
    qv = {k: levels[q[k]] for k in exact}
    maxq = max(float(np.abs(qv[k] - exact[k]).max()) for k in exact)
    meanq = float(np.mean([np.abs(qv[k] - exact[k]).mean() for k in exact]))
    # displayed-integer disagreement over real respondents
    diff = tot = 0
    for k in exact:
        lo = 60 if len(k[1]) == 1 else 10
        idx = rawv[k] - lo
        diff += int((np.round(qv[k][idx]) != np.round(exact[k][idx])).sum())
        tot += len(idx)
    pay = B.encode(names, levels, spec, q, norms).encode()
    rows.append((name, len(levels), maxq, meanq, len(pay), len(brotli.compress(pay, quality=11)),
                 len(gzip.compress(pay, 9)), 100.0 * diff / tot))
for r in sorted(rows, key=lambda r: r[5]):
    print("%-8s %6d %9.5f %9.5f %8d %8d %8d %9.4f" % r)
