# -*- coding: utf-8 -*-
"""How much does the answer depend on WHO the comparison group is?

The biggest known weakness of the deployed page is that its norm sample is 69.2%
American and only 1.46% Greater Chinese. The page discloses that. This script puts a
number on it, using nothing but the norm sample itself: no external data, no new
assumptions, fully reproducible.

Method: rebuild the empirical percentile table (the same mid-rank definition
build_tables.py uses) from the 2,117 Greater-China respondents alone, score those same
2,117 people with it, and compare against the percentile the whole-sample table gives
them. The null is the identical procedure on random subsamples of the same size, matched
on the site's own sex x age cohorts, which separates sampling noise from a real
population difference.

Everything here describes people who answered IN ENGLISH. It is a sensitivity analysis,
not a Chinese norm, and nothing here is applied to a displayed score.

  python tools/norm_sensitivity.py
"""
import io
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

GC_COUNTRIES = ["China", "Hong Kong", "Taiwan", "Singapore"]   # Macau (n=15) excluded
NULL_REPS = 50
SEED = 20260821

z = ipip.load()
facet_raw, domain_raw = z["facet_raw"], z["domain_raw"]
items = z["items"].astype(np.float64)
sex, age = z["sex"], z["age"]
country = pd.read_csv(os.path.join(ipip.OUT, "meta.csv"))["country"].to_numpy()
data = ipip.site_data()
N = len(country)
GC = np.isin(country, GC_COUNTRIES)
US = country == "USA"
ALL = np.ones(N, bool)
masks = ipip.group_masks(sex, age)
cohort = np.char.add(np.where(sex == 1, "M", np.where(sex == 2, "F", "X")),
                     np.where(age < 21, "_lt21", "_gte21"))
COH = ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]

raws, cols = {}, {}
for i, d in enumerate(ipip.DOMAIN_ORDER):
    raws[d] = domain_raw[:, i].astype(np.int32)
for d in ipip.OCEAN:
    for f in range(1, 7):
        s = d + str(f)
        raws[s] = facet_raw[:, ipip.facet_slot(d, f)].astype(np.int32)
        cols[s] = ipip.facet_items(ipip.facet_slot(d, f))
for d in ipip.OCEAN:
    cols[d] = [c for f in range(1, 7) for c in ipip.facet_items(ipip.facet_slot(d, f))]
FACETS = [d + str(f) for d in ipip.OCEAN for f in range(1, 7)]
SCALES = ipip.OCEAN + FACETS
NAME = dict([(d, [x for x in data["domains"] if x["key"] == d][0]["name"]) for d in ipip.OCEAN] +
            [(d + str(f), data["facets"][d][f - 1][0]) for d in ipip.OCEAN for f in range(1, 7)])


def lohi(s):
    return (60, 300) if len(s) == 1 else (10, 50)


def table(v, lo, hi):
    """mid-rank empirical percentile: 100*(count_below + 0.5*count_equal)/n"""
    cnt = np.bincount(v - lo, minlength=hi - lo + 1).astype(np.float64)
    return 100.0 * (np.cumsum(cnt) - cnt + 0.5 * cnt) / len(v)


def shift(sub, s):
    lo, hi = lohi(s)
    r = raws[s][sub] - lo
    return table(raws[s][sub], lo, hi)[r] - table(raws[s][ALL], lo, hi)[r]


def alpha(x):
    k = x.shape[1]
    return float(k / (k - 1.0) * (1 - x.var(axis=0, ddof=1).sum() / x.sum(axis=1).var(ddof=1)))


def rbar(a, k):
    """average inter-item correlation implied by alpha -- comparable across item counts"""
    return a / (k - (k - 1) * a)


def hr(t):
    print("\n" + "=" * 78 + "\n" + t + "\n" + "=" * 78)


out = {}

hr("0  sample")
print("  whole sample %d; Greater China %d = %.2f%% (Macau n=15 not counted)"
      % (N, GC.sum(), 100.0 * GC.sum() / N))
print("  Greater China : female %.1f%%, under 21 %.1f%%, median age %.0f"
      % (100 * (sex[GC] == 2).mean(), 100 * (age[GC] < 21).mean(), np.median(age[GC])))
print("  whole sample  : female %.1f%%, under 21 %.1f%%, median age %.0f"
      % (100 * (sex == 2).mean(), 100 * (age < 21).mean(), np.median(age)))
print("  -> demographically near-identical, so what follows is not an age/sex artefact.")
out["n_gc"] = int(GC.sum())
out["n_total"] = int(N)

hr("1  swap the reference population: how far does the percentile move?")
pool = np.concatenate([np.abs(shift(GC, s)) for s in FACETS])
print("  n = %d (person x facet) values: median %.2f  mean %.2f  p90 %.2f  %%>10 = %.1f%%"
      % (len(pool), np.median(pool), pool.mean(), np.percentile(pool, 90), 100 * (pool > 10).mean()))
per = {s: float(np.median(np.abs(shift(GC, s)))) for s in SCALES}
print("  domains: " + "   ".join("%s %.2f" % (NAME[d], per[d]) for d in ipip.OCEAN))
print("  largest six facets:")
for s in sorted(FACETS, key=lambda x: -per[x])[:6]:
    print("     %-3s %-6s %5.2f" % (s, NAME[s], per[s]))
out["pooled"] = dict(median=float(np.median(pool)), mean=float(pool.mean()),
                     p90=float(np.percentile(pool, 90)),
                     pct_gt10=float(100 * (pool > 10).mean()))
out["per_scale_median"] = per

hr("2  null: same size, matched on the site's own sex x age cohorts")
rng = np.random.default_rng(SEED)
null = []
for _ in range(NULL_REPS):
    m = np.zeros(N, bool)
    for g in COH:
        want = int((cohort[GC] == g).sum())
        cand = np.where(masks[g] & ~GC)[0]
        m[rng.choice(cand, size=want, replace=False)] = True
    null.append(float(np.median(np.concatenate([np.abs(shift(m, s)) for s in FACETS]))))
print("  %d draws: median shift  mean %.3f  max %.3f" % (NULL_REPS, np.mean(null), np.max(null)))
print("  Greater China / null = %.2f / %.3f = %.1fx"
      % (np.median(pool), np.mean(null), np.median(pool) / np.mean(null)))
out["null_median_mean"] = float(np.mean(null))
out["null_median_max"] = float(np.max(null))
out["ratio"] = float(np.median(pool) / np.mean(null))

hr("3  direction: a raw score at self-percentile q is displayed as ...")
qs = [10, 25, 50, 75, 84, 90]
shown = {}
for s in SCALES:
    lo, hi = lohi(s)
    tg, ta = table(raws[s][GC], lo, hi), table(raws[s][ALL], lo, hi)
    shown[s] = [float(ta[min(int(np.searchsorted(tg, q)), len(tg) - 1)]) for q in qs]
fm = [float(np.mean([shown[s][j] for s in FACETS])) for j in range(len(qs))]
dm = [float(np.mean([shown[s][j] for s in ipip.OCEAN])) for j in range(len(qs))]
print("  self-percentile " + "".join("%7d" % q for q in qs))
print("  facet mean shown" + "".join("%7.1f" % x for x in fm))
print("  domain mean shown" + "".join("%6.1f" % x for x in dm))
print("  -> the distribution is narrower; both tails are pushed toward the middle.")
out["qs"] = qs
out["shown_facet_mean"] = fm
out["shown_domain_mean"] = dm
out["shown"] = shown

hr("4  reliability: Greater China vs USA, same English items, 10-item scales")
print("  scale        a_GC   a_US   mean inter-item r (GC/US)   true-var ratio   SEM ratio")
al = {}
for s in SCALES:
    k = len(cols[s])
    ag, au = alpha(items[GC][:, cols[s]]), alpha(items[US][:, cols[s]])
    sg = items[GC][:, cols[s]].sum(1).std(ddof=1)
    su = items[US][:, cols[s]].sum(1).std(ddof=1)
    al[s] = dict(gc=ag, us=au, rbar_gc=rbar(ag, k), rbar_us=rbar(au, k),
                 truevar=(sg ** 2 * ag) / (su ** 2 * au),
                 sem=(sg * np.sqrt(1 - ag)) / (su * np.sqrt(1 - au)))
for s in sorted(FACETS, key=lambda x: al[x]["gc"])[:6]:
    a = al[s]
    print("  %-3s %-6s  %.3f  %.3f       %.3f / %.3f            %.3f          %.2f"
          % (s, NAME[s], a["gc"], a["us"], a["rbar_gc"], a["rbar_us"], a["truevar"], a["sem"]))
fv = [al[s] for s in FACETS]
print("  30 facets: median true-variance ratio %.3f ; median SEM ratio %.2f"
      % (np.median([x["truevar"] for x in fv]), np.median([x["sem"] for x in fv])))
print("  -> alpha falls but SD falls with it, so SEM barely moves. What changes is")
print("     discrimination between people, not measurement error.")
out["alpha"] = al

hr("5  O6 Liberalism: corrected item-rest correlations, item by item")
o6 = ipip.facet_items(ipip.facet_slot("O", 6))
itc = []
for c in o6:
    rest = [x for x in o6 if x != c]
    rg = float(np.corrcoef(items[GC][:, c], items[GC][:, rest].sum(1))[0, 1])
    ru = float(np.corrcoef(items[US][:, c], items[US][:, rest].sum(1))[0, 1])
    itc.append({"q": c + 1, "gc": rg, "us": ru, "zh": data["items"][c]["zh"]})
    print("  #%3d  GC %+.3f   US %+.3f   %s" % (c + 1, rg, ru, data["items"][c]["zh"]))
print("  GC max %.3f ; US min %.3f -- the two ranges do not overlap."
      % (max(x["gc"] for x in itc), min(x["us"] for x in itc)))
out["o6_item_rest"] = itc

p = os.path.join(ipip.OUT, "norm_sensitivity.json")
io.open(p, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
print("\nwrote out/norm_sensitivity.json")
