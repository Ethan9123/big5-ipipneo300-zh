# -*- coding: utf-8 -*-
"""Supplementary probes for the norm-fidelity audit (console only, no artifacts)."""
import csv
import json
import os
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

z = ipip.load()
fr, dr, sex, age, yr = z["facet_raw"], z["domain_raw"], z["sex"], z["age"], z["year"]
masks = ipip.group_masks(sex, age)
site = ipip.site_data()
sh = {g: [float(v) for v in site["norms"][g]["ns"]] for g in ipip.GROUPS}

J = json.load(open(os.path.join(ipip.OUT, "norm_fidelity.json"), encoding="utf-8"))

print("== overall impact summary ==")
print(json.dumps({k: v for k, v in J["impact_summary"].items()
                  if not isinstance(v, (list,))}, indent=1)[:2500])

print("\n== top 12 drifting ns elements, all cohorts ==")
rows = []
for g in ipip.GROUPS:
    for e in J["cohorts"][g]["elements"]:
        rows.append((g, e))
rows.sort(key=lambda r: -abs(r[1]["diff"]))
for g, e in rows[:12]:
    print("%-9s %-16s shipped=%8.2f sample=%8.2f diff=%+6.2f (%+6.1f%% of SD)" %
          (g, e["label"], e["shipped"], e["sample"], e["diff"], e["pct_of_shipped_sd"]))

print("\n== top 15 scale x cohort by mean |percentile shift| ==")
prim = [r for r in J["impact_rows"] if r["variant"] == "sample"]
for r in sorted(prim, key=lambda r: -r["mean_abs_pct_shift"])[:15]:
    print("%-9s %-4s mean=%6.2f max=%6.2f  >=1:%5.1f%% >=5:%5.1f%% >=10:%5.1f%% flip:%5.1f%%" %
          (r["cohort"], r["scale"], r["mean_abs_pct_shift"], r["max_abs_pct_shift"],
           100 * r["share_disp_ge1"], 100 * r["share_disp_ge5"],
           100 * r["share_disp_ge10"], 100 * r["share_level_flip"]))

print("\n== distribution of the 210 (cohort x scale) mean shifts ==")
ms = np.array([r["mean_abs_pct_shift"] for r in prim])
print("min %.3f  median %.3f  mean %.3f  p90 %.3f  max %.3f" %
      (ms.min(), np.median(ms), ms.mean(), np.percentile(ms, 90), ms.max()))
print("rows with mean shift <1 pct pt:", int((ms < 1).sum()), "of", len(ms))
print("rows with mean shift >=3:", int((ms >= 3).sum()), " >=5:", int((ms >= 5).sum()))
lf = np.array([r["share_level_flip"] for r in prim])
print("level-flip share: median %.4f max %.4f" % (np.median(lf), lf.max()))
g1 = np.array([r["share_disp_ge1"] for r in prim])
g10 = np.array([r["share_disp_ge10"] for r in prim])
print("share>=1 displayed pt: median %.4f min %.4f max %.4f" % (np.median(g1), g1.min(), g1.max()))
print("share>=10 displayed pt: rows nonzero %d, max %.4f" % (int((g10 > 0).sum()), g10.max()))

print("\n== worst cell detail: F_lt21 / N5 (immoderation) ==")
d, f = "N", 5
j = ipip.facet_slot(d, f)
m = masks["F_lt21"]
x = fr[m][:, j].astype(float)
mo, so = ipip.FACET_OFFSET[d]
print("shipped mean/sd = %.2f / %.2f ; sample mean/sd = %.3f / %.3f ; n=%d" %
      (sh["F_lt21"][mo + f], sh["F_lt21"][so + f], x.mean(), x.std(ddof=1), m.sum()))
t0 = 50 + 10 * (x - sh["F_lt21"][mo + f]) / sh["F_lt21"][so + f]
ns_s = J["cohorts"]["F_lt21"]["elements"]
sm = [e for e in ns_s if e["label"] == "N5_mean"][0]["sample"]
ssd = [e for e in ns_s if e["label"] == "N5_sd"][0]["sample"]
t1 = 50 + 10 * (x - sm) / ssd
print("mean T shipped %.2f -> sample %.2f ; median pct %.1f -> %.1f" %
      (t0.mean(), t1.mean(), np.median(ipip.pct_from_t(t0)), np.median(ipip.pct_from_t(t1))))

print("\n== is the drift a vintage effect?  domain means by year, F_lt21 ==")
print("year counts:", sorted(Counter(yr.tolist()).items()))
for d in ipip.DOMAIN_ORDER:
    col = ipip.DOMAIN_ORDER.index(d)
    line = []
    for y in sorted(set(yr.tolist())):
        mm = m & (yr == y)
        if mm.sum() > 300:
            line.append("%d:%.1f(n=%d)" % (y, dr[mm][:, col].mean(), mm.sum()))
    print(d, "shipped=%.1f" % sh["F_lt21"][ipip.DOMAIN_INDEX[d]], " ".join(line))

print("\n== country mix (meta.csv) ==")
cnt = Counter()
with open(os.path.join(ipip.OUT, "meta.csv"), encoding="utf-8", newline="") as fh:
    for row in csv.DictReader(fh):
        cnt[row["country"]] += 1
tot = sum(cnt.values())
for k, v in cnt.most_common(8):
    print("%-6s %7d %5.1f%%" % (k, v, 100.0 * v / tot))
print("distinct countries:", len(cnt), "total", tot)

print("\n== how big is the M/F averaging error vs the shipped drift? ==")
for band in ("lt21", "gte21"):
    g = "N_" + band
    print(g,
          "shipped vs pooled mean|d| = %.4f max %.4f" %
          (J["neutral_check"][g]["shipped_vs_pooled_sample_stats"]["mean_abs"],
           J["neutral_check"][g]["shipped_vs_pooled_sample_stats"]["max_abs"]),
          "| avg-of-sample vs pooled mean|d| = %.4f max %.4f" %
          (J["neutral_check"][g]["elementwise_avg_of_sample_MF_vs_pooled_sample"]["mean_abs"],
           J["neutral_check"][g]["elementwise_avg_of_sample_MF_vs_pooled_sample"]["max_abs"]))

print("\n== stability: n and SE of domain means ==")
for g in ipip.GROUPS:
    s = J["stability"][g]
    ses = [s["domains"][d]["se_mean_analytic"] for d in ipip.DOMAIN_ORDER]
    bts = [s["domains"][d]["se_mean_bootstrap"] for d in ipip.DOMAIN_ORDER]
    gaps = [s["domains"][d]["gap_in_SE_units"] for d in ipip.DOMAIN_ORDER]
    pcts = [s["domains"][d]["pct_shift_per_SE_at_T50"] for d in ipip.DOMAIN_ORDER]
    print("%-9s n=%6d  SE(mean) %.3f-%.3f  boot %.3f-%.3f  pctshift/SE %.3f-%.3f  gap %.1f-%.1f SE" %
          (g, s["n"], min(ses), max(ses), min(bts), max(bts),
           min(pcts), max(pcts), min(gaps), max(gaps)))
