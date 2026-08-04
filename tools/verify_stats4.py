# -*- coding: utf-8 -*-
"""Part I: full 210-cell shipped-vs-sample impact matrix + country grouping."""
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
R = {}

scales = [("domain", k, None) for k in ipip.DOMAIN_ORDER]
for k in ipip.DOMAIN_ORDER:
    for f in range(1, 7):
        scales.append(("facet", k, f))
NAMES = [d if f is None else f"{d}{f}" for (kd, d, f) in scales]

def raw_for(mask, kind, dom, fno):
    if kind == "domain":
        return domain_raw[mask, ipip.DOMAIN_ORDER.index(dom)]
    return facet_raw[mask, ipip.facet_slot(dom, fno)]

def musd_shipped(ns, kind, dom, fno):
    if kind == "domain":
        i = ipip.DOMAIN_INDEX[dom]; return ns[i], ns[i + 5]
    m0, s0 = ipip.FACET_OFFSET[dom]; return ns[m0 + fno], ns[s0 + fno]

def lvl(p):
    v = np.trunc(p)
    return np.where(v < 45, 0, np.where(v <= 55, 1, 2))

cells = []
for g in ipip.GROUPS:
    m = masks[g]; ns = NORMS[g]
    for si, (kind, dom, fno) in enumerate(scales):
        rv = raw_for(m, kind, dom, fno)
        mu_s, sd_s = musd_shipped(ns, kind, dom, fno)
        mu_e, sd_e = rv.mean(), rv.std(ddof=1)
        t1 = 50 + 10 * (rv - mu_s) / sd_s
        t2 = 50 + 10 * (rv - mu_e) / sd_e
        p1, p2 = ipip.pct_from_t(t1), ipip.pct_from_t(t2)
        d = np.abs(p1 - p2)
        dr = np.abs(np.round(p1) - np.round(p2))          # JS Math.round display
        cells.append({
            "cohort": g, "scale": NAMES[si], "n": int(m.sum()),
            "mean_abs": float(d.mean()), "max_abs": float(d.max()),
            "share_ge1_round": float((dr >= 1).mean()), "share_ge5_round": float((dr >= 5).mean()),
            "share_ge10_round": float((dr >= 10).mean()),
            "share_ge1_raw": float((d >= 1).mean()), "share_ge5_raw": float((d >= 5).mean()),
            "share_ge10_raw": float((d >= 10).mean()),
            "level_flip": float((lvl(p1) != lvl(p2)).mean()),
            "mu_shipped": float(mu_s), "mu_sample": float(mu_e),
            "sd_shipped": float(sd_s), "sd_sample": float(sd_e),
        })

ma = np.array([c["mean_abs"] for c in cells])
R["n_cells"] = len(cells)
R["overall_mean_abs_pct_shift"] = round(float(ma.mean()), 4)
R["overall_median"] = round(float(np.median(ma)), 4)
R["overall_p90"] = round(float(np.percentile(ma, 90)), 4)
R["overall_max"] = round(float(ma.max()), 4)
noN5 = np.array([c["mean_abs"] for c in cells if c["scale"] != "N5"])
R["overall_mean_abs_excl_N5"] = round(float(noN5.mean()), 4)
for key in ["share_ge1_round", "share_ge5_round", "share_ge10_round",
            "share_ge1_raw", "share_ge5_raw", "share_ge10_raw", "level_flip"]:
    R["mean_" + key] = round(100 * float(np.mean([c[key] for c in cells])), 4)
R["worst_cells_top8"] = [
    {k: (round(v, 4) if isinstance(v, float) else v) for k, v in c.items()}
    for c in sorted(cells, key=lambda c: -c["mean_abs"])[:8]]

# per-respondent, using only the M/F cohorts (each respondent scored once)
cnt1 = np.zeros(N); cnt5 = np.zeros(N); cnt10 = np.zeros(N); cntl = np.zeros(N)
for g in ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]:
    m = masks[g]; ns = NORMS[g]
    for si, (kind, dom, fno) in enumerate(scales):
        rv = raw_for(m, kind, dom, fno)
        mu_s, sd_s = musd_shipped(ns, kind, dom, fno)
        mu_e, sd_e = rv.mean(), rv.std(ddof=1)
        p1 = ipip.pct_from_t(50 + 10 * (rv - mu_s) / sd_s)
        p2 = ipip.pct_from_t(50 + 10 * (rv - mu_e) / sd_e)
        dr = np.abs(np.round(p1) - np.round(p2))
        cnt1[m] += (dr >= 1); cnt5[m] += (dr >= 5); cnt10[m] += (dr >= 10)
        cntl[m] += (lvl(p1) != lvl(p2))
R["per_respondent"] = {
    "mean_scales_moving_ge1": round(float(cnt1.mean()), 4),
    "mean_scales_moving_ge5": round(float(cnt5.mean()), 4),
    "mean_scales_moving_ge10": round(float(cnt10.mean()), 4),
    "mean_scales_level_flip": round(float(cntl.mean()), 4),
    "pct_respondents_any_ge1": round(100 * float((cnt1 > 0).mean()), 4),
    "pct_respondents_any_ge5": round(100 * float((cnt5 > 0).mean()), 4),
    "pct_respondents_any_ge10": round(100 * float((cnt10 > 0).mean()), 4),
    "pct_respondents_any_level_flip": round(100 * float((cntl > 0).mean()), 4),
}

# ---- exact-match accounting for the shipped 1dp norms
def label(i):
    if 1 <= i <= 5: return ipip.DOMAIN_ORDER[i - 1] + " mean"
    if 6 <= i <= 10: return ipip.DOMAIN_ORDER[i - 6] + " sd"
    for k, (m0, s0) in ipip.FACET_OFFSET.items():
        if m0 + 1 <= i <= m0 + 6: return f"{k}{i - m0} mean"
        if s0 + 1 <= i <= s0 + 6: return f"{k}{i - s0} sd"
em = {}
for g in ipip.GROUPS:
    mk = masks[g]; s = np.zeros(71)
    for d, k in enumerate(ipip.DOMAIN_ORDER):
        c = domain_raw[mk, d]; s[ipip.DOMAIN_INDEX[k]] = c.mean(); s[ipip.DOMAIN_INDEX[k] + 5] = c.std(ddof=1)
    for k in ipip.DOMAIN_ORDER:
        m0, s0 = ipip.FACET_OFFSET[k]
        for f in range(1, 7):
            c = facet_raw[mk, ipip.facet_slot(k, f)]
            s[m0 + f] = c.mean(); s[s0 + f] = c.std(ddof=1)
    sh = NORMS[g]
    gaps = sh[1:71] - s[1:71]
    # shipped values are published to 1dp (N_* to 2dp because they average M/F)
    dp = 2 if g.startswith("N_") else 1
    em[g] = {"identical_after_rounding_sample_to_shipped_dp":
                 int((np.round(s[1:71], dp) == np.round(sh[1:71], dp)).sum()),
             "abs_gap_lt_0.05": int((np.abs(gaps) < 0.05).sum()),
             "abs_gap_lt_0.005": int((np.abs(gaps) < 0.005).sum()),
             "abs_gap_eq_0": int((gaps == 0).sum())}
R["exact_match_accounting"] = em

# ================= COUNTRY grouping
rows = list(csv.DictReader(io.open(os.path.join(OUT, "meta.csv"), encoding="utf-8", newline="")))
cn = collections.Counter(r["country"] for r in rows)
ANGLO = ["USA", "Canada", "UK", "Australia", "New Zealand", "Ireland"]
EUROPE = ["Netherlands", "Finland", "Sweden", "Germany", "Norway", "France", "Denmark",
          "Belgium", "Greece", "Italy", "Spain", "Poland", "Portugal", "Switzerland",
          "Austria", "Czech Repu", "Hungary", "Romania", "Russia", "Croatia", "Slovenia",
          "Iceland", "Estonia", "Latvia", "Lithuania", "Bulgaria", "Slovakia", "Serbia",
          "Ukraine", "Luxembourg", "Malta", "Cyprus", "Belarus", "Bosnia and", "Albania",
          "Macedonia", "Moldova", "Monaco", "Andorra", "Liechtenst", "San Marino",
          "Yugoslavia", "Faroe Isla", "Greenland", "Gibraltar", "Isle of Ma", "Jersey",
          "Guernsey", "Svalbard a", "Vatican Ci", "Holy See"]
R["country_groups"] = {
    "total": len(rows),
    "blank": cn.get("", 0),
    "blank_pct": round(100 * cn.get("", 0) / len(rows), 4),
    "anglo_n": sum(cn.get(c, 0) for c in ANGLO),
    "anglo_pct": round(100 * sum(cn.get(c, 0) for c in ANGLO) / len(rows), 4),
    "europe_n": sum(cn.get(c, 0) for c in EUROPE),
    "europe_countries_present": sorted([c for c in EUROPE if cn.get(c, 0) > 0]),
    "europe_pct": round(100 * sum(cn.get(c, 0) for c in EUROPE) / len(rows), 4),
    "greater_china_plus_sg": {c: cn.get(c, 0) for c in ["China", "Hong Kong", "Taiwan", "Singapore"]},
    "cn_hk_tw_sg_total": sum(cn.get(c, 0) for c in ["China", "Hong Kong", "Taiwan", "Singapore"]),
    "cn_hk_tw_total": sum(cn.get(c, 0) for c in ["China", "Hong Kong", "Taiwan"]),
}
g = R["country_groups"]
g["cn_hk_tw_sg_pct"] = round(100 * g["cn_hk_tw_sg_total"] / len(rows), 4)
g["cn_hk_tw_pct"] = round(100 * g["cn_hk_tw_total"] / len(rows), 4)
g["rest_of_world_n"] = len(rows) - g["anglo_n"] - g["europe_n"]
g["rest_of_world_pct"] = round(100 * g["rest_of_world_n"] / len(rows), 4)
# labels truncated at 11 chars -> check for collisions that merge distinct countries
g["labels_at_11_chars"] = sorted([c for c in cn if len(c) == 11])

json.dump(R, io.open(os.path.join(OUT, "verify_stats_partI.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1, default=str)
print(json.dumps({k: v for k, v in R.items() if k != "worst_cells_top8"},
                 ensure_ascii=False, indent=1, default=str))
print("WORST CELLS:")
for c in R["worst_cells_top8"]:
    print("  %-8s %-4s n=%-6d meanabs=%6.3f max=%6.3f ge1=%5.1f%% ge5=%5.1f%% ge10=%5.1f%% flip=%5.1f%% mu %.2f->%.2f sd %.2f->%.2f"
          % (c["cohort"], c["scale"], c["n"], c["mean_abs"], c["max_abs"],
             100*c["share_ge1_round"], 100*c["share_ge5_round"], 100*c["share_ge10_round"],
             100*c["level_flip"], c["mu_shipped"], c["mu_sample"], c["sd_shipped"], c["sd_sample"]))
