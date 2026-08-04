# -*- coding: utf-8 -*-
"""Part D-H of the independent adversarial re-computation."""
import io, json, os, sys, collections, csv
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip

OUT = ipip.OUT
Z = ipip.load()
items = Z["items"]
facet_raw = Z["facet_raw"].astype(np.int64)
domain_raw = Z["domain_raw"].astype(np.int64)
sex = Z["sex"]; age = Z["age"]; case = Z["case"]; year = Z["year"]
N = len(items)
D = ipip.site_data()
NORMS = {k: np.array(v["ns"], dtype=np.float64) for k, v in D["norms"].items()}
masks = ipip.group_masks(sex, age)
R = {"n": int(N)}

# ================================================== D. RAIL PINNING
# 35 scales per respondent: 5 domains + 30 facets, using the respondent's M/F cohort.
scales = []          # (kind, domain, facet_no)
for k in ipip.DOMAIN_ORDER:
    scales.append(("domain", k, None))
for k in ipip.DOMAIN_ORDER:
    for f in range(1, 7):
        scales.append(("facet", k, f))

T = np.zeros((N, 35)); P = np.zeros((N, 35))
for g in ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]:
    m = masks[g]; ns = NORMS[g]
    for si, (kind, dom, fno) in enumerate(scales):
        if kind == "domain":
            raw = domain_raw[m, ipip.DOMAIN_ORDER.index(dom)]
            mu, sd = ns[ipip.DOMAIN_INDEX[dom]], ns[ipip.DOMAIN_INDEX[dom] + 5]
        else:
            raw = facet_raw[m, ipip.facet_slot(dom, fno)]
            m0, s0 = ipip.FACET_OFFSET[dom]
            mu, sd = ns[m0 + fno], ns[s0 + fno]
        t = 50 + 10 * (raw - mu) / sd
        T[m, si] = t; P[m, si] = ipip.pct_from_t(t)

cells = N * 35
low = T < 32; high = T > 73
R["rail"] = {
    "cells_respondent_x_scale": cells,
    "n_low_rail_T_lt32": int(low.sum()),
    "n_high_rail_T_gt73": int(high.sum()),
    "n_any_rail": int((low | high).sum()),
    "pct_low": round(100 * low.sum() / cells, 4),
    "pct_high": round(100 * high.sum() / cells, 4),
    "pct_any": round(100 * (low | high).sum() / cells, 4),
}
# how many RESPONDENTS have >=1 railed scale
anyr = (low | high).any(axis=1)
R["rail"]["respondents_with_ge1_railed"] = int(anyr.sum())
R["rail"]["pct_respondents_with_ge1_railed"] = round(100 * anyr.mean(), 4)
R["rail"]["mean_railed_scales_per_respondent"] = round(float((low | high).sum(axis=1).mean()), 4)
# domains only / facets only
R["rail"]["domains_only_pct"] = round(100 * (low[:, :5] | high[:, :5]).mean(), 4)
R["rail"]["facets_only_pct"] = round(100 * (low[:, 5:] | high[:, 5:]).mean(), 4)
# displayed value == 1 or 99 (site rounds for display); check both trunc and round
disp = np.round(P)
R["rail"]["displayed_round_eq1_or_99_pct"] = round(100 * ((disp <= 1) | (disp >= 99)).mean(), 4)
# what the cubic would give WITHOUT the rail, at the rail boundary
R["rail"]["cubic_at_T32"] = float(ipip.cubic(32.0))
R["rail"]["cubic_at_T73"] = float(ipip.cubic(73.0))
R["rail"]["cubic_min_over_data"] = float(ipip.cubic(T).min())
R["rail"]["cubic_max_over_data"] = float(ipip.cubic(T).max())
# per-scale rail rates, worst 8
per = [(f"{d}{f if f else ''}", round(100 * (low[:, i] | high[:, i]).mean(), 4),
        round(100 * low[:, i].mean(), 4), round(100 * high[:, i].mean(), 4))
       for i, (k, d, f) in enumerate(scales)]
R["rail"]["per_scale_worst8"] = sorted(per, key=lambda x: -x[1])[:8]
R["rail"]["per_scale_best5"] = sorted(per, key=lambda x: x[1])[:5]
# rail using pooled N_* norms instead (the site uses these only when sex not M/F)
Tn = np.zeros((N, 35))
for g, gm in (("N_lt21", masks["N_lt21"]), ("N_gte21", masks["N_gte21"])):
    ns = NORMS[g]
    for si, (kind, dom, fno) in enumerate(scales):
        if kind == "domain":
            raw = domain_raw[gm, ipip.DOMAIN_ORDER.index(dom)]
            mu, sd = ns[ipip.DOMAIN_INDEX[dom]], ns[ipip.DOMAIN_INDEX[dom] + 5]
        else:
            raw = facet_raw[gm, ipip.facet_slot(dom, fno)]
            m0, s0 = ipip.FACET_OFFSET[dom]
            mu, sd = ns[m0 + fno], ns[s0 + fno]
        Tn[gm, si] = 50 + 10 * (raw - mu) / sd
R["rail"]["pooled_N_norms_pct_any"] = round(
    100 * ((Tn < 32) | (Tn > 73)).mean(), 4)

# ================================================== E. COUNTRY
meta = {}
with io.open(os.path.join(OUT, "meta.csv"), encoding="utf-8", newline="") as fh:
    rd = csv.DictReader(fh)
    cols = rd.fieldnames
    countries = []
    for row in rd:
        countries.append(row["country"])
R["meta_columns"] = cols
cnt = collections.Counter(countries)
R["country"] = {
    "n_rows": len(countries),
    "n_distinct_labels": len(cnt),
    "blank": cnt.get("", 0),
    "top25": [(c, n, round(100 * n / len(countries), 4)) for c, n in cnt.most_common(25)],
}
ANGLO = ["USA", "CAN", "GBR", "AUS", "NZL", "IRL"]
# figure out the actual label spelling
R["country"]["label_probe"] = {c: cnt.get(c, 0) for c in
    ["USA", "US", "United States", "CAN", "Canada", "GBR", "UK", "United Kingdom",
     "AUS", "Australia", "NZL", "New Zealand", "IRL", "Ireland",
     "CN", "CHN", "China", "HK", "HKG", "Hong Kong", "TW", "TWN", "Taiwan",
     "SG", "SGP", "Singapore", "NL", "NLD", "Netherlands", "IN", "IND", "India"]}

json.dump(R, io.open(os.path.join(OUT, "verify_stats_partD.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1, default=str)
print(json.dumps(R["rail"], ensure_ascii=False, indent=1))
print("meta cols:", cols)
print("distinct labels:", R["country"]["n_distinct_labels"], "blank:", R["country"]["blank"])
print("top25:")
for c, n, p in R["country"]["top25"]:
    print("   %-24s %7d  %.4f%%" % (repr(c), n, p))
print("label probe:", R["country"]["label_probe"])
