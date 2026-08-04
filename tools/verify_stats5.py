# -*- coding: utf-8 -*-
"""Part J: chase the specific discrepancies."""
import io, json, os, sys, collections, csv
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip

OUT = ipip.OUT
Z = ipip.load()
facet_raw = Z["facet_raw"].astype(np.float64)
domain_raw = Z["domain_raw"].astype(np.float64)
sex = Z["sex"]; age = Z["age"]
N = len(sex)
D = ipip.site_data()
NORMS = {k: np.array(v["ns"], dtype=np.float64) for k, v in D["norms"].items()}
masks = ipip.group_masks(sex, age)

def label(i):
    if 1 <= i <= 5: return ipip.DOMAIN_ORDER[i - 1] + " mean"
    if 6 <= i <= 10: return ipip.DOMAIN_ORDER[i - 6] + " sd"
    for k, (m0, s0) in ipip.FACET_OFFSET.items():
        if m0 + 1 <= i <= m0 + 6: return f"{k}{i - m0} mean"
        if s0 + 1 <= i <= s0 + 6: return f"{k}{i - s0} sd"

def sample_ns(mask, ddof=1):
    s = np.zeros(71)
    for d, k in enumerate(ipip.DOMAIN_ORDER):
        c = domain_raw[mask, d]; s[ipip.DOMAIN_INDEX[k]] = c.mean(); s[ipip.DOMAIN_INDEX[k] + 5] = c.std(ddof=ddof)
    for k in ipip.DOMAIN_ORDER:
        m0, s0 = ipip.FACET_OFFSET[k]
        for f in range(1, 7):
            c = facet_raw[mask, ipip.facet_slot(k, f)]
            s[m0 + f] = c.mean(); s[s0 + f] = c.std(ddof=ddof)
    return s

print("=== A. borderline elements near the 0.05 cut (claimed 64/60/64/64/68/60) ===")
for g in ipip.GROUPS:
    for ddof in (1, 0):
        s = sample_ns(masks[g], ddof)
        gaps = np.abs(NORMS[g][1:71] - s[1:71])
        n_ge = int((gaps >= 0.05).sum())
        near = [(label(int(i) + 1), round(float(gaps[i]), 6)) for i in np.argsort(np.abs(gaps - 0.05))[:3]]
        print(f"  {g:9s} ddof={ddof}  n(|gap|>=0.05)={n_ge}   nearest-to-0.05: {near}")

print()
print("=== B. mean-vs-SD drift (claim: 0.60 vs 0.42 avg) ===")
mi = [i for i in range(1, 71) if label(i).endswith("mean")]
si = [i for i in range(1, 71) if label(i).endswith("sd")]
mall, sall = [], []
for g in ipip.GROUPS:
    s = sample_ns(masks[g])
    gm = np.abs(NORMS[g][mi] - s[mi]).mean()
    gs = np.abs(NORMS[g][si] - s[si]).mean()
    mall.append(gm); sall.append(gs)
    print(f"  {g:9s} mean-elements {gm:.4f}   sd-elements {gs:.4f}")
print(f"  AVERAGE over cohorts: means {np.mean(mall):.4f}   sds {np.mean(sall):.4f}")

print()
print("=== C. does rounding the refreshed norms to 1dp reproduce their impact figures? ===")
def lvl(p):
    v = np.trunc(p); return np.where(v < 45, 0, np.where(v <= 55, 1, 2))
m = masks["F_lt21"]; ns = NORMS["F_lt21"]
m0, s0 = ipip.FACET_OFFSET["N"]
rv = facet_raw[m, ipip.facet_slot("N", 5)]
p1 = ipip.pct_from_t(50 + 10 * (rv - ns[m0 + 5]) / ns[s0 + 5])
for tag, mu, sd in [("unrounded", rv.mean(), rv.std(ddof=1)),
                    ("1dp",  round(rv.mean(), 1), round(rv.std(ddof=1), 1)),
                    ("ddof0", rv.mean(), rv.std(ddof=0))]:
    p2 = ipip.pct_from_t(50 + 10 * (rv - mu) / sd)
    d = np.abs(p1 - p2); dr = np.abs(np.round(p1) - np.round(p2))
    print("  %-10s mu=%.4f sd=%.4f | meanabs=%.4f max=%.4f ge1=%.4f ge5=%.4f ge10(round)=%.4f ge10(raw)=%.4f flip=%.4f"
          % (tag, mu, sd, d.mean(), d.max(), 100*(dr>=1).mean(), 100*(dr>=5).mean(),
             100*(dr>=10).mean(), 100*(d>=10).mean(), 100*(lvl(p1)!=lvl(p2)).mean()))

print()
print("=== D. full ranked cell list, top 12 (claim's runner-ups) ===")
scales = [("domain", k, None) for k in ipip.DOMAIN_ORDER]
for k in ipip.DOMAIN_ORDER:
    for f in range(1, 7): scales.append(("facet", k, f))
rows = []
for g in ipip.GROUPS:
    mk = masks[g]; ns = NORMS[g]
    for kind, dom, fno in scales:
        if kind == "domain":
            r = domain_raw[mk, ipip.DOMAIN_ORDER.index(dom)]
            i = ipip.DOMAIN_INDEX[dom]; mu_s, sd_s = ns[i], ns[i + 5]; nm = dom
        else:
            r = facet_raw[mk, ipip.facet_slot(dom, fno)]
            a, b = ipip.FACET_OFFSET[dom]; mu_s, sd_s = ns[a + fno], ns[b + fno]; nm = f"{dom}{fno}"
        pa = ipip.pct_from_t(50 + 10 * (r - mu_s) / sd_s)
        pb = ipip.pct_from_t(50 + 10 * (r - r.mean()) / r.std(ddof=1))
        rows.append((g, nm, float(np.abs(pa - pb).mean())))
for g, nm, v in sorted(rows, key=lambda x: -x[2])[:12]:
    print("  %-9s %-4s %.4f" % (g, nm, v))

print()
print("=== E. country: continental Europe with the ACTUAL truncated labels ===")
recs = list(csv.DictReader(io.open(os.path.join(OUT, "meta.csv"), encoding="utf-8", newline="")))
cn = collections.Counter(r["country"] for r in recs)
ANGLO = ["USA", "Canada", "UK", "Australia", "New Zealand", "Ireland"]
EU = ["Netherlands","Finland","Sweden","Germany","Norway","France","Denmark","Belgium","Greece",
      "Italy","Spain","Poland","Portugal","Switzerland","Austria","Czech Repub","Hungary",
      "Romania","Russian Fed","Croatia","Slovenia","Iceland","Estonia","Latvia","Lithuania",
      "Bulgaria","Slovakia","Serbia","Ukraine","Luxembourg","Malta","Cyprus","Belarus",
      "Bosnia Herz","Albania","Macedonia","Moldova","Monaco","Andorra","Liechtenst","San Marino",
      "Yugoslavia","Faeroe Isla","Greenland","Gibraltar","Isle of Ma","Jersey","Guernsey",
      "Vatican Cit","Svalbard a","Holy See","Slovak Rep","Czechoslov"]
present = {c: cn[c] for c in EU if cn.get(c, 0) > 0}
tot = sum(present.values())
print("  EUROPE n=%d (%.4f%%) across %d labels" % (tot, 100*tot/len(recs), len(present)))
print("  ", sorted(present.items(), key=lambda x: -x[1]))
a = sum(cn.get(c, 0) for c in ANGLO)
print("  ANGLO n=%d (%.4f%%)" % (a, 100*a/len(recs)))
print("  ROW  n=%d (%.4f%%)  [includes %d blank-country rows]" % (len(recs)-a-tot, 100*(len(recs)-a-tot)/len(recs), cn.get("", 0)))
print("  Turkey=%d  Russian Fed=%d  Czech Repub=%d  Bosnia Herz=%d  Faeroe Isla=%d"
      % (cn.get("Turkey",0), cn.get("Russian Fed",0), cn.get("Czech Repub",0),
         cn.get("Bosnia Herz",0), cn.get("Faeroe Isla",0)))
print("  ambiguous truncations:", {c: cn[c] for c in ["Republic of","Virgin Isla","Korea, Repu"] if c in cn})
print("  labels with count, len==11, that could hide a merge:",
      [(c, cn[c]) for c in cn if len(c) == 11 and cn[c] > 100])
