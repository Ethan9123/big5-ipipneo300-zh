# -*- coding: utf-8 -*-
"""(1) locate the single dense-scan trunc artifact, (2) test stream orderings."""
import os, sys, gzip
import brotli
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip, build_tables as B

spec = B.LADDERS["safe025"]
levels = B.ladder_levels(spec)

scan = np.arange(0, 100.0000001, 0.0005)
sc = np.clip(scan, levels[0], levels[-1])
sq = levels[B.quantise(scan, levels)]
bad = np.nonzero(np.trunc(sc) != np.trunc(sq))[0]
print("dense trunc mismatches:", len(bad))
for i in bad:
    print("   p=%.10f clipped=%.10f quantised=%.10f  trunc %d vs %d"
          % (scan[i], sc[i], sq[i], np.trunc(sc[i]), np.trunc(sq[i])))
badr = np.nonzero(np.floor(sc + 0.5) != np.floor(sq + 0.5))[0]
print("dense round mismatches:", len(badr))
print("levels: n=%d min=%.6f max=%.6f" % (len(levels), levels[0], levels[-1]))

# ---- stream ordering experiment ----
z = ipip.load()
masks = ipip.group_masks(z["sex"], z["age"])
scales = ipip.scale_index()
names = [d if k == "domain" else "%s%d" % (d, f) for k, d, f in scales]
exact, norms = {}, {}
for g in ipip.GROUPS:
    m = masks[g]
    for (kind, dom, fno), nm in zip(scales, names):
        if kind == "domain":
            v = z["domain_raw"][m, ipip.DOMAIN_ORDER.index(dom)]; lo, hi = 60, 300
        else:
            v = z["facet_raw"][m, ipip.facet_slot(dom, fno)]; lo, hi = 10, 50
        mu, sd = float(v.mean()), float(v.std(ddof=1))
        exact[(g, nm)], _, _ = B.build_cell(v, lo, hi, mu, sd)
        norms[(g, nm)] = (mu, sd)
q = {k: B.quantise(exact[k], levels) for k in exact}

def stream(order):
    buf = []
    for k in order:
        B.enc_val(int(q[k][0]), buf)
        for d in np.diff(q[k]):
            B.enc_val(int(d), buf)
    return "".join(buf)

orders = {
    "cohort-major (current)": [(g, nm) for g in ipip.GROUPS for nm in names],
    "scale-major": [(g, nm) for nm in names for g in ipip.GROUPS],
    "kind-split, cohort-major": ([(g, nm) for g in ipip.GROUPS for nm in names if len(nm) == 1] +
                                 [(g, nm) for g in ipip.GROUPS for nm in names if len(nm) > 1]),
    "kind-split, scale-major": ([(g, nm) for nm in names if len(nm) == 1 for g in ipip.GROUPS] +
                                [(g, nm) for nm in names if len(nm) > 1 for g in ipip.GROUPS]),
}
print()
print("%-26s %8s %8s %8s" % ("stream order", "raw", "brotli", "gzip"))
for name, order in orders.items():
    s = stream(order).encode()
    print("%-26s %8d %8d %8d" % (name, len(s), len(brotli.compress(s, quality=11)),
                                 len(gzip.compress(s, 9))))

# how many cells need 2 chars?
two = sum(1 for k in q for d in ([int(q[k][0])] + list(np.diff(q[k]))) if d >= 48)
print("\ncells needing the 2-char code: %d / 14610 (%.2f%%)" % (two, 100 * two / 14610))
alld = np.concatenate([np.diff(q[k]) for k in q])
print("delta stats: max %d  mean %.2f  zero %.1f%%" % (alld.max(), alld.mean(), 100 * (alld == 0).mean()))
