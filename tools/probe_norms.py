# -*- coding: utf-8 -*-
"""Encoding options for the mean/sd companion section."""
import os, sys, gzip
import brotli
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip, build_tables as B

z = ipip.load()
masks = ipip.group_masks(z["sex"], z["age"])
scales = ipip.scale_index()
names = [d if k == "domain" else "%s%d" % (d, f) for k, d, f in scales]
norms = {}
for g in ipip.GROUPS:
    m = masks[g]
    for (kind, dom, fno), nm in zip(scales, names):
        v = (z["domain_raw"][m, ipip.DOMAIN_ORDER.index(dom)] if kind == "domain"
             else z["facet_raw"][m, ipip.facet_slot(dom, fno)])
        norms[(g, nm)] = (float(v.mean()), float(v.std(ddof=1)))

def sizes(s):
    b = s.encode()
    return len(b), len(brotli.compress(b, quality=11)), len(gzip.compress(b, 9))

def fixed(order):
    buf = []
    for k in order:
        B.enc_u18(int(round(norms[k][0] * 100)), buf)
        B.enc_u18(int(round(norms[k][1] * 100)), buf)
    return "".join(buf)

def zig(v):
    return (v << 1) ^ (v >> 31) if v >= 0 else ((-v) << 1) - 1

def zzdelta(order):
    """separate mean and sd streams, zigzag delta varint (2-char code)."""
    buf = []
    for which in (0, 1):
        prev = 0
        for k in order:
            cur = int(round(norms[k][which] * 100))
            B.enc_val(min(zig(cur - prev), 1071), buf)
            prev = cur
    return "".join(buf)

cm = [(g, nm) for g in ipip.GROUPS for nm in names]
sm = [(g, nm) for nm in names for g in ipip.GROUPS]
print("%-34s %6s %7s %6s" % ("norms encoding", "raw", "brotli", "gzip"))
for nm_, s in [("fixed u18, cohort-major", fixed(cm)),
               ("fixed u18, scale-major", fixed(sm)),
               ("zigzag-delta, cohort-major", zzdelta(cm)),
               ("zigzag-delta, scale-major", zzdelta(sm))]:
    print("%-34s %6d %7d %6d" % ((nm_,) + sizes(s)))

# check the zigzag deltas actually fit the 2-char code in scale-major order
for which, lab in ((0, "mean"), (1, "sd")):
    prev, mx = 0, 0
    for k in sm:
        cur = int(round(norms[k][which] * 100)); mx = max(mx, zig(cur - prev)); prev = cur
    print("max zigzag %s delta (scale-major): %d  (2-char code holds 1071)" % (lab, mx))
