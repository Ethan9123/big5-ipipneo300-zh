# -*- coding: utf-8 -*-
"""Part F-H: careless-responding flag rate, norm fidelity, sample composition."""
import io, json, os, sys, collections
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip

OUT = ipip.OUT
Z = ipip.load()
items = Z["items"].astype(np.int8)
facet_raw = Z["facet_raw"].astype(np.float64)
domain_raw = Z["domain_raw"].astype(np.float64)
sex = Z["sex"]; age = Z["age"]; case = Z["case"]; year = Z["year"]
N = len(items)
D = ipip.site_data()
NORMS = {k: np.array(v["ns"], dtype=np.float64) for k, v in D["norms"].items()}
masks = ipip.group_masks(sex, age)
R = {"n": int(N)}

# ============================== F. CARELESS RESPONDING (site rule, raw keypresses)
RUN_CUT = [0, 6, 9, 10, 14, 9]
rev0 = np.array(sorted(D["reversed"]), dtype=int) - 1        # 0-based columns
raw = items.astype(np.int8).copy()
raw[:, rev0] = 6 - raw[:, rev0]                              # undo Johnson's recoding

def longest_runs(a):
    """Vectorised port of the site's longestRuns(): best[v] = longest run of value v."""
    n, k = a.shape
    best = np.zeros((n, 6), dtype=np.int32)
    cur = np.zeros(n, dtype=np.int32)
    prev = np.zeros(n, dtype=np.int8)
    for i in range(k):
        same = a[:, i] == prev
        cur = np.where(same, cur + 1, 1)
        prev = a[:, i]
        for v in range(1, 6):
            sel = prev == v
            best[sel, v] = np.maximum(best[sel, v], cur[sel])
    return best

runs_raw = longest_runs(raw)
runs_rec = longest_runs(items.astype(np.int8))

def flag_report(runs, tag):
    per = {}
    fl = np.zeros(N, dtype=bool)
    for v in range(1, 6):
        f = runs[:, v] > RUN_CUT[v]
        per[f"opt{v}"] = {"n": int(f.sum()), "pct": round(100 * f.mean(), 4)}
        fl |= f
    return {"any": {"n": int(fl.sum()), "pct": round(100 * fl.mean(), 4)}, "per_option": per,
            "caps": [int(runs[:, v].max()) for v in range(1, 6)],
            "at_cap": [int((runs[:, v] == runs[:, v].max()).sum()) for v in range(1, 6)],
            "one_past_cap": [int((runs[:, v] == runs[:, v].max() + 1).sum()) for v in range(1, 6)]}

R["careless_raw"] = flag_report(runs_raw, "raw")
R["careless_recoded"] = flag_report(runs_rec, "recoded")
# run-length histograms in raw space near the cap
hist = {}
for v in range(1, 6):
    h = collections.Counter(runs_raw[:, v].tolist())
    cap = runs_raw[:, v].max()
    hist[f"opt{v}"] = {str(L): int(h.get(L, 0)) for L in range(max(1, cap - 6), cap + 3)}
R["careless_raw_tail_hist"] = hist
# flag rate if RUN_CUT were the data's own caps
caps = R["careless_raw"]["caps"]
f2 = np.zeros(N, dtype=bool)
for v in range(1, 6):
    f2 |= runs_raw[:, v] > caps[v - 1]
R["careless_flag_at_data_caps"] = {"n": int(f2.sum()), "pct": round(100 * f2.mean(), 6)}

# ============================== G. NORM FIDELITY
def ns_from_sample(mask):
    """Build a 71-long ns vector from the sample, same layout as the site."""
    v = np.zeros(71)
    for d, k in enumerate(ipip.DOMAIN_ORDER):
        col = domain_raw[mask, d]
        v[ipip.DOMAIN_INDEX[k]] = col.mean()
        v[ipip.DOMAIN_INDEX[k] + 5] = col.std(ddof=1)
    for k in ipip.DOMAIN_ORDER:
        m0, s0 = ipip.FACET_OFFSET[k]
        for f in range(1, 7):
            col = facet_raw[mask, ipip.facet_slot(k, f)]
            v[m0 + f] = col.mean(); v[s0 + f] = col.std(ddof=1)
    return v

def label(i):
    if 1 <= i <= 5: return ipip.DOMAIN_ORDER[i - 1] + " mean"
    if 6 <= i <= 10: return ipip.DOMAIN_ORDER[i - 6] + " sd"
    for k, (m0, s0) in ipip.FACET_OFFSET.items():
        if m0 + 1 <= i <= m0 + 6: return f"{k}{i - m0} mean"
        if s0 + 1 <= i <= s0 + 6: return f"{k}{i - s0} sd"
    return f"idx{i}"

fid = {}
sample_ns = {}
for g in ipip.GROUPS:
    s = ns_from_sample(masks[g]); sample_ns[g] = s
    shipped = NORMS[g]
    gaps = shipped[1:71] - s[1:71]
    fid[g] = {
        "n": int(masks[g].sum()),
        "exact_match_of_70": int((np.abs(gaps) < 5e-9).sum()),
        "match_at_1dp_of_70": int((np.abs(gaps) < 0.05).sum()),
        "off_by_ge_0.05_of_70": int((np.abs(gaps) >= 0.05).sum()),
        "mean_abs_gap": round(float(np.abs(gaps).mean()), 4),
        "max_abs_gap": round(float(np.abs(gaps).max()), 4),
        "max_abs_gap_element": label(int(np.argmax(np.abs(gaps))) + 1),
        "top5_gaps": [(label(int(i) + 1), round(float(shipped[i + 1]), 4),
                       round(float(s[i + 1]), 4), round(float(gaps[i]), 4))
                      for i in np.argsort(-np.abs(gaps))[:5]],
    }
R["norm_fidelity"] = fid

# N5 copy-paste claim: is F/N N5 mean equal to the MALE N5 mean?
m0, s0 = ipip.FACET_OFFSET["N"]
R["N5_check"] = {
    g: {"shipped_mean": float(NORMS[g][m0 + 5]), "shipped_sd": float(NORMS[g][s0 + 5]),
        "sample_mean": round(float(sample_ns[g][m0 + 5]), 4),
        "sample_sd": round(float(sample_ns[g][s0 + 5]), 4)}
    for g in ipip.GROUPS}
# and every other N facet for context (lt21 cohorts)
R["N_facets_lt21_shipped"] = {
    g: {f"N{f}": [float(NORMS[g][m0 + f]), float(NORMS[g][s0 + f])] for f in range(1, 7)}
    for g in ["M_lt21", "F_lt21", "N_lt21"]}
# how many of the 70 elements are IDENTICAL between M and F shipped vectors?
for pair in [("M_lt21", "F_lt21"), ("M_gte21", "F_gte21")]:
    a, b = NORMS[pair[0]][1:71], NORMS[pair[1]][1:71]
    same = np.where(a == b)[0]
    R.setdefault("MF_identical_elements", {})[f"{pair[0]}_vs_{pair[1]}"] = {
        "n_identical": int(len(same)), "which": [label(int(i) + 1) for i in same]}
# is the N vector the arithmetic mean of M and F shipped vectors?
for suf in ["lt21", "gte21"]:
    a, b, n = NORMS["M_" + suf][1:71], NORMS["F_" + suf][1:71], NORMS["N_" + suf][1:71]
    R.setdefault("N_is_MF_average", {})[suf] = {
        "max_abs_dev_from_mean": round(float(np.abs(n - (a + b) / 2).max()), 6),
        "n_elements_off_by_gt_0.051": int((np.abs(n - (a + b) / 2) > 0.051).sum()),
    }

# percentile impact of the N5 defect for F_lt21
mF = masks["F_lt21"]
slot = ipip.facet_slot("N", 5)
rawv = facet_raw[mF, slot]
t_ship = 50 + 10 * (rawv - NORMS["F_lt21"][m0 + 5]) / NORMS["F_lt21"][s0 + 5]
t_samp = 50 + 10 * (rawv - sample_ns["F_lt21"][m0 + 5]) / sample_ns["F_lt21"][s0 + 5]
p_ship = ipip.pct_from_t(t_ship); p_samp = ipip.pct_from_t(t_samp)
d = np.abs(p_ship - p_samp)
def lvl(p):
    v = np.trunc(p)
    return np.where(v < 45, 0, np.where(v <= 55, 1, 2))
R["N5_F_lt21_impact"] = {
    "mean_abs_pct_shift": round(float(d.mean()), 4),
    "max_abs_pct_shift": round(float(d.max()), 4),
    "share_ge1": round(100 * float((np.abs(np.round(p_ship) - np.round(p_samp)) >= 1).mean()), 4),
    "share_ge5": round(100 * float((d >= 5).mean()), 4),
    "share_ge10": round(100 * float((d >= 10).mean()), 4),
    "level_flip_pct": round(100 * float((lvl(p_ship) != lvl(p_samp)).mean()), 4),
    "median_pct_shipped": round(float(np.median(p_ship)), 4),
    "median_pct_sample": round(float(np.median(p_samp)), 4),
    "mean_T_shipped": round(float(t_ship.mean()), 4),
    "mean_T_sample": round(float(t_samp.mean()), 4),
}

# ============================== H. COMPOSITION
R["sex"] = {"male": int((sex == 1).sum()), "female": int((sex == 2).sum()),
            "other": int(((sex != 1) & (sex != 2)).sum()),
            "pct_female": round(100 * float((sex == 2).mean()), 4)}
R["age"] = {"min": int(age.min()), "max": int(age.max()),
            "mean": round(float(age.mean()), 4), "median": float(np.median(age)),
            "sd": round(float(age.std(ddof=1)), 4),
            "p5_25_50_75_95": [float(np.percentile(age, q)) for q in (5, 25, 50, 75, 95)],
            "modal": int(np.bincount(age.astype(int)).argmax()),
            "modal_n": int(np.bincount(age.astype(int)).max()),
            "n_16_25": int(((age >= 16) & (age <= 25)).sum()),
            "n_lt21": int((age < 21).sum()), "pct_lt21": round(100 * float((age < 21).mean()), 4),
            "n_lt13": int((age < 13).sum()), "n_gt90": int((age > 90).sum()),
            "n_eq10": int((age == 10).sum()), "n_eq99": int((age == 99).sum())}
yv = year.astype(int)
yv = np.where(yv < 1900, yv + 1900, yv)
R["year"] = {"min": int(yv.min()), "max": int(yv.max()),
             "counts": {int(k): int(v) for k, v in sorted(collections.Counter(yv.tolist()).items())},
             "median": float(np.median(yv))}
R["cohort_n"] = {g: [int(masks[g].sum()), round(100 * float(masks[g].mean()), 4)] for g in ipip.GROUPS}
R["dup_case_ids"] = int(N - len(np.unique(case)))
_b = np.ascontiguousarray(items.astype(np.uint8))
_v = _b.view(np.dtype((np.void, 300))).ravel()
uniq, cnts = np.unique(_v, return_counts=True)
R["dup_response_vectors"] = {"n_distinct": int(len(uniq)),
                             "n_groups_with_dupes": int((cnts > 1).sum()),
                             "n_rows_in_dupe_groups": int(cnts[cnts > 1].sum())}

json.dump(R, io.open(os.path.join(OUT, "verify_stats_partF.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1, default=str)
print(json.dumps(R, ensure_ascii=False, indent=1, default=str))
