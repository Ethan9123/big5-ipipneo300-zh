# -*- coding: utf-8 -*-
"""Probe 3: the N5 (immoderation) anomaly in the shipped female norm vectors."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

z = ipip.load()
fr, dr, sex, age = z["facet_raw"], z["domain_raw"], z["sex"], z["age"]
masks = ipip.group_masks(sex, age)
site = ipip.site_data()
sh = {g: [float(v) for v in site["norms"][g]["ns"]] for g in ipip.GROUPS}
J = json.load(open(os.path.join(ipip.OUT, "norm_fidelity.json"), encoding="utf-8"))

print("== are ANY shipped facet values byte-identical between the M and F vectors? ==")
for band in ("lt21", "gte21"):
    m, f = sh["M_" + band], sh["F_" + band]
    same = [(i, J["cohorts"]["M_" + band]["elements"][0] and None) for i in []]
    lab = {e["idx"]: e["label"] for e in J["cohorts"]["M_" + band]["elements"]}
    hits = [(lab[i], m[i]) for i in sorted(lab) if m[i] == f[i]]
    print(band, "identical elements:", hits)

print("\n== shipped N-facet SDs, M vs F ==")
mo, so = ipip.FACET_OFFSET["N"]
for band in ("lt21", "gte21"):
    print(band, "M sd:", [sh["M_" + band][so + f] for f in range(1, 7)],
          " F sd:", [sh["F_" + band][so + f] for f in range(1, 7)])
    print(band, "sample sd M:",
          [round(float(fr[masks["M_" + band]][:, ipip.facet_slot("N", f)].std(ddof=1)), 2)
           for f in range(1, 7)],
          " F:",
          [round(float(fr[masks["F_" + band]][:, ipip.facet_slot("N", f)].std(ddof=1)), 2)
           for f in range(1, 7)])

print("\n== identity-implied correct value for the female N5 mean ==")
for band in ("lt21", "gte21"):
    g = "F_" + band
    s6 = sum(sh[g][mo + f] for f in range(1, 7))
    implied = sh[g][ipip.DOMAIN_INDEX["N"]] - (s6 - sh[g][mo + 5])
    samp = float(fr[masks[g]][:, ipip.facet_slot("N", 5)].mean())
    print("%-9s shipped N5 mean=%.2f (== male value %.2f)  identity-implied=%.2f  sample=%.3f"
          % (g, sh[g][mo + 5], sh["M_" + band][mo + 5], implied, samp))
    print("          residual after the implied fix = %+.3f "
          "(other F N-facets drift %s)" %
          (samp - implied,
           [round(float(fr[masks[g]][:, ipip.facet_slot("N", f)].mean()) - sh[g][mo + f], 2)
            for f in (1, 2, 3, 4, 6)]))

print("\n== user-visible impact of the N5 mean bug ALONE (fix mean only, keep shipped SD) ==")
for band in ("lt21", "gte21"):
    for pre in ("F", "N"):
        g = pre + "_" + band
        m = masks[g]
        x = fr[m][:, ipip.facet_slot("N", 5)].astype(float)
        sd = sh[g][so + 5]
        fg = "F_" + band
        s6 = sum(sh[fg][mo + f] for f in range(1, 7))
        implied_F = sh[fg][ipip.DOMAIN_INDEX["N"]] - (s6 - sh[fg][mo + 5])
        fixed = implied_F if pre == "F" else round((sh["M_" + band][mo + 5] + implied_F) / 2, 2)
        t0 = 50 + 10 * (x - sh[g][mo + 5]) / sd
        t1 = 50 + 10 * (x - fixed) / sd
        p0, p1 = ipip.pct_from_t(t0), ipip.pct_from_t(t1)
        d = np.abs(p1 - p0)
        rd = np.abs(np.floor(p1 + .5) - np.floor(p0 + .5))
        lv0 = np.trunc(p0); lv1 = np.trunc(p1)
        L = lambda v: np.where(v < 45, 0, np.where(v <= 55, 1, 2))  # noqa: E731
        print("%-9s shipped %.2f -> fixed %.2f | mean|dpct| %.2f max %.2f | "
              ">=1 %.1f%% >=5 %.1f%% >=10 %.1f%% | level flip %.1f%% | "
              "median pct %.1f -> %.1f" %
              (g, sh[g][mo + 5], fixed, d.mean(), d.max(), 100 * (rd >= 1).mean(),
               100 * (rd >= 5).mean(), 100 * (rd >= 10).mean(),
               100 * (L(lv0) != L(lv1)).mean(), np.median(p0), np.median(p1)))

print("\n== residual drift once the N5 bug is excluded: mean |percentile shift| per cohort ==")
prim = [r for r in J["impact_rows"] if r["variant"] == "sample"]
for g in ipip.GROUPS:
    rs = [r for r in prim if r["cohort"] == g]
    a = np.mean([r["mean_abs_pct_shift"] for r in rs])
    b = np.mean([r["mean_abs_pct_shift"] for r in rs if r["scale"] != "N5"])
    print("%-9s all-35 %.3f  excl-N5 %.3f" % (g, a, b))
allr = np.mean([r["mean_abs_pct_shift"] for r in prim])
excl = np.mean([r["mean_abs_pct_shift"] for r in prim if r["scale"] != "N5"])
print("overall all-35 %.3f  excl-N5 %.3f" % (allr, excl))
