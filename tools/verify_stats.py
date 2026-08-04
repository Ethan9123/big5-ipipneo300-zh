# -*- coding: utf-8 -*-
"""Independent adversarial re-computation. Written from scratch against scored.npz.
Deliberately does NOT import any other agent's module except ipip.py helpers."""
import io, json, os, sys, collections
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip

OUT = ipip.OUT
Z = ipip.load()
items = Z["items"].astype(np.int16)
facet_raw = Z["facet_raw"].astype(np.int64)
domain_raw = Z["domain_raw"].astype(np.int64)
sex = Z["sex"]; age = Z["age"]; case = Z["case"]
ref_dom = Z["ref_domain_pct"]; ref_fac = Z["ref_facet_pct"]
year = Z["year"]
N = len(items)
D = ipip.site_data()
NORMS = {k: np.array(v["ns"], dtype=np.float64) for k, v in D["norms"].items()}
REV = sorted(D["reversed"])

R = {}   # results
R["n"] = int(N)

# ---------------------------------------------------------------- A. sanity
fr, dr = ipip.facet_and_domain_raw(items)
R["facet_raw_matches_cache"] = bool(np.array_equal(fr, facet_raw))
R["domain_raw_matches_cache"] = bool(np.array_equal(dr, domain_raw))

masks = ipip.group_masks(sex, age)

def domain_pct_matrix():
    """percentile for the 5 domains, per respondent, using their M/F cohort norms."""
    P = np.zeros((N, 5)); T = np.zeros((N, 5))
    for g in ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]:
        m = masks[g]; ns = NORMS[g]
        for d, k in enumerate(ipip.DOMAIN_ORDER):
            i = ipip.DOMAIN_INDEX[k]
            t = 50 + 10 * (domain_raw[m, d] - ns[i]) / ns[i + 5]
            T[m, d] = t; P[m, d] = ipip.pct_from_t(t)
    return T, P

Tdom, Pdom = domain_pct_matrix()
R["sanity_max_abs_err_vs_csv_domain_pct"] = float(np.abs(Pdom - ref_dom).max())

# ---------------------------------------------------------- B. Cronbach alpha
def alpha(cols):
    X = items[:, cols].astype(np.float64)
    k = X.shape[1]
    iv = X.var(axis=0, ddof=1).sum()
    tv = X.sum(axis=1).var(ddof=1)
    return k / (k - 1.0) * (1 - iv / tv)

facet_alpha = {}
for j in range(30):
    dom = ipip.DOMAIN_ORDER[j % 5]; fno = j // 5 + 1
    facet_alpha[f"{dom}{fno}"] = float(alpha(ipip.facet_items(j)))
R["facet_alpha"] = facet_alpha
R["facet_alpha_min"] = min(facet_alpha.items(), key=lambda kv: kv[1])
R["facet_alpha_max"] = max(facet_alpha.items(), key=lambda kv: kv[1])
R["facet_alpha_mean"] = float(np.mean(list(facet_alpha.values())))
R["facet_alpha_median"] = float(np.median(list(facet_alpha.values())))

domain_alpha = {}
for d, k in enumerate(ipip.DOMAIN_ORDER):
    cols = []
    for j in range(30):
        if j % 5 == d:
            cols += ipip.facet_items(j)
    domain_alpha[k] = float(alpha(sorted(cols)))
R["domain_alpha"] = domain_alpha

# alpha with ddof=0 too, to see whether an estimator choice could explain gaps
def alpha0(cols):
    X = items[:, cols].astype(np.float64)
    k = X.shape[1]
    return k / (k - 1.0) * (1 - X.var(axis=0).sum() / X.sum(axis=1).var())
R["facet_alpha_ddof0_spotcheck"] = {
    f"{ipip.DOMAIN_ORDER[j%5]}{j//5+1}": float(alpha0(ipip.facet_items(j))) for j in (0, 1, 2, 3, 4)
}

# ------------------------------------- C. corrected item-total correlations
def corr(a, b):
    a = a - a.mean(); b = b - b.mean()
    return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum()))

cit_corrected = {}   # item number (1..300) -> r
cit_uncorrected = {}
cit_domain_corrected = {}
for j in range(30):
    dom = ipip.DOMAIN_ORDER[j % 5]; fno = j // 5 + 1
    cols = ipip.facet_items(j)
    X = items[:, cols].astype(np.float64)
    tot = X.sum(axis=1)
    for c, col in enumerate(cols):
        rest = tot - X[:, c]
        cit_corrected[col + 1] = (f"{dom}{fno}", corr(X[:, c], rest))
        cit_uncorrected[col + 1] = corr(X[:, c], tot)

lowest = sorted(cit_corrected.items(), key=lambda kv: kv[1][1])[:12]
R["cit_lowest12"] = [
    {"item": it, "facet": v[0], "r_corrected": round(v[1], 6),
     "r_uncorrected": round(cit_uncorrected[it], 6),
     "reversed": it in D["reversed"],
     "text": D["items"][it - 1]}
    for it, v in lowest
]
allr = np.array([v[1] for v in cit_corrected.values()])
R["cit_min"] = float(allr.min()); R["cit_max"] = float(allr.max())
R["cit_mean"] = float(allr.mean()); R["cit_median"] = float(np.median(allr))
R["cit_n_negative"] = int((allr < 0).sum())
R["cit_n_below_0.20"] = int((allr < 0.20).sum())
R["cit_n_below_0.30"] = int((allr < 0.30).sum())
R["cit_correction_gap_mean"] = float(np.mean(
    [cit_uncorrected[k] - v[1] for k, v in cit_corrected.items()]))
R["cit_min_uncorrected"] = float(min(cit_uncorrected.values()))

# domain-level corrected item-total (item vs its 60-item domain minus itself)
for d, k in enumerate(ipip.DOMAIN_ORDER):
    cols = sorted(c for j in range(30) if j % 5 == d for c in ipip.facet_items(j))
    X = items[:, cols].astype(np.float64)
    tot = X.sum(axis=1)
    for c, col in enumerate(cols):
        cit_domain_corrected[col + 1] = corr(X[:, c], tot - X[:, c])
dv = np.array(list(cit_domain_corrected.values()))
R["cit_domain_min"] = float(dv.min()); R["cit_domain_n_negative"] = int((dv < 0).sum())
R["cit_domain_lowest8"] = sorted(
    ({"item": k, "r": round(v, 6)} for k, v in cit_domain_corrected.items()),
    key=lambda x: x["r"])[:8]

json.dump(R, io.open(os.path.join(OUT, "verify_stats_partA.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1, default=str)
print("PART A/B/C done")
for k in ["sanity_max_abs_err_vs_csv_domain_pct", "facet_alpha_min", "facet_alpha_max",
          "facet_alpha_mean", "facet_alpha_median", "domain_alpha", "cit_min", "cit_max",
          "cit_mean", "cit_n_negative", "cit_n_below_0.20", "cit_n_below_0.30",
          "cit_correction_gap_mean", "cit_min_uncorrected", "cit_domain_min",
          "cit_domain_n_negative", "facet_alpha_ddof0_spotcheck"]:
    print(" ", k, "=", R[k])
print(" facet_alpha sorted:", sorted(facet_alpha.items(), key=lambda kv: kv[1]))
print(" cit_lowest12:")
for e in R["cit_lowest12"]:
    print("   ", e["item"], e["facet"], "corr=%.4f" % e["r_corrected"],
          "uncorr=%.4f" % e["r_uncorrected"], "rev=", e["reversed"])
print(" cit_domain_lowest8:", R["cit_domain_lowest8"])
