# -*- coding: utf-8 -*-
"""Probe 2: internal consistency of the shipped ns vectors + vintage drift."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

z = ipip.load()
fr, dr, sex, age, yr = z["facet_raw"], z["domain_raw"], z["sex"], z["age"], z["year"]
masks = ipip.group_masks(sex, age)
site = ipip.site_data()
sh = {g: [float(v) for v in site["norms"][g]["ns"]] for g in ipip.GROUPS}
J = json.load(open(os.path.join(ipip.OUT, "norm_fidelity.json"), encoding="utf-8"))

print("== internal identity: domain mean must equal sum of its 6 facet means ==")
print("(exact in any real sample; violation => the shipped vector is not one coherent sample)")
for g in ipip.GROUPS:
    line = []
    for d in ipip.DOMAIN_ORDER:
        mo, _ = ipip.FACET_OFFSET[d]
        s = sum(sh[g][mo + f] for f in range(1, 7))
        line.append("%s %+6.2f" % (d, s - sh[g][ipip.DOMAIN_INDEX[d]]))
    print("%-9s shipped: %s" % (g, "  ".join(line)))
for g in ipip.GROUPS:
    line = []
    for d in ipip.DOMAIN_ORDER:
        mo, _ = ipip.FACET_OFFSET[d]
        el = {e["label"]: e["sample"] for e in J["cohorts"][g]["elements"]}
        s = sum(el["%s%d_mean" % (d, f)] for f in range(1, 7))
        line.append("%s %+6.2f" % (d, s - el["%s_domain_mean" % d]))
    print("%-9s sample : %s" % (g, "  ".join(line)))

print("\n== N-facet means, shipped vs sample, all cohorts (N5 is the outlier) ==")
for f in range(1, 7):
    row = []
    for g in ipip.GROUPS:
        mo, _ = ipip.FACET_OFFSET["N"]
        el = {e["label"]: e["sample"] for e in J["cohorts"][g]["elements"]}
        row.append("%s %5.2f/%5.2f" % (g.split("_")[0] + g.split("_")[1][:1],
                                       sh[g][mo + f], el["N%d_mean" % f]))
    print("N%d  %s" % (f, "  ".join(row)))

print("\n== vintage drift inside the sample itself ==")
print("year is coded year-1900 (101..111 = 2001..2011)")
early = yr <= 103
late = yr >= 109
for g in ipip.GROUPS:
    outs = []
    for d in ipip.DOMAIN_ORDER:
        col = ipip.DOMAIN_ORDER.index(d)
        a = dr[masks[g] & early][:, col].astype(float)
        b = dr[masks[g] & late][:, col].astype(float)
        sd = sh[g][ipip.DOMAIN_INDEX[d] + 5]
        dT = 10 * (b.mean() - a.mean()) / sd
        dP = ipip.cubic(50 + dT) - ipip.cubic(50)
        outs.append("%s %+5.1f raw %+4.2fT %+5.1fpct" % (d, b.mean() - a.mean(), dT, dP))
    print("%-9s n_early=%6d n_late=%6d  %s" %
          (g, int((masks[g] & early).sum()), int((masks[g] & late).sum()), "  ".join(outs)))

print("\n== if norms were refreshed on 2009-2011 only, vs on the full sample ==")
for g in ipip.GROUPS:
    m_full, m_late = masks[g], masks[g] & late
    dif = []
    for d in ipip.DOMAIN_ORDER:
        col = ipip.DOMAIN_ORDER.index(d)
        xf = dr[m_full][:, col].astype(float)
        xl = dr[m_late][:, col].astype(float)
        mf, sf = xf.mean(), xf.std(ddof=1)
        ml, sl = xl.mean(), xl.std(ddof=1)
        t0 = 50 + 10 * (xf - mf) / sf
        t1 = 50 + 10 * (xf - ml) / sl
        p = np.abs(ipip.pct_from_t(t1) - ipip.pct_from_t(t0))
        dif.append("%s mean|d|=%4.2f max=%4.2f" % (d, p.mean(), p.max()))
    print("%-9s n_late=%6d  %s" % (g, int(m_late.sum()), "  ".join(dif)))

print("\n== how much of the shipped-vs-sample gap is age-band composition? ==")
for g in ("M_gte21", "F_gte21"):
    m = masks[g]
    a = age[m]
    print(g, "age median %d  p25 %d p75 %d p95 %d" %
          (np.median(a), np.percentile(a, 25), np.percentile(a, 75), np.percentile(a, 95)))
