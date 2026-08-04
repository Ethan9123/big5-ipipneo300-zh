# -*- coding: utf-8 -*-
"""How stable is the LABEL the page prints?

Two independent estimates of the same quantity:

  (1) Model-based parallel-form simulation.  Under classical test theory the score
      on a parallel 300-item administration has
          mean = mu + alpha*(x - mu)          (true-score regression)
          sd   = SEM * sqrt(1 + alpha)
      Draw one parallel administration per respondent per scale and count how often
      the printed 低/中等/高 label and the printed percentile change.

  (2) Assumption-light empirical split-half.  Score each facet from items 1,3,5,7,9
      and again from items 2,4,6,8,10 of its block, renorm each half separately, and
      count label disagreement.  This is a 150-item vs 150-item comparison, so it is
      an upper bound on 300-vs-300 instability -- reported as such.

Also reports the SEE ("regressed true score") version of the confidence interval,
which is the narrower of the two conventions, so the CI claim is not overstated.

Writes tools/out/gaps_retest.json.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402


def band(p):
    v = np.trunc(p)
    return np.where(v < 45, 0, np.where(v <= 55, 1, 2))


def main():
    data = ipip.site_data()
    z = ipip.load()
    items = z["items"].astype(np.float64)
    facet_raw = z["facet_raw"].astype(np.float64)
    domain_raw = z["domain_raw"].astype(np.float64)
    sex, age = z["sex"], z["age"]
    n = len(sex)
    masks = ipip.group_masks(sex, age)
    facet_names = {k: [f[0] for f in data["facets"][k]] for k in ipip.DOMAIN_ORDER}

    # alphas
    af = np.zeros(30); sdf = np.zeros(30)
    for s in range(30):
        cols = ipip.facet_items(s)
        iv = items[:, cols].var(axis=0, ddof=1).sum()
        tv = facet_raw[:, s].var(ddof=1)
        af[s] = 10 / 9 * (1 - iv / tv); sdf[s] = np.sqrt(tv)
    ad = np.zeros(5); sdd = np.zeros(5)
    for d in range(5):
        cols = [c for s in range(30) if s % 5 == d for c in ipip.facet_items(s)]
        iv = items[:, cols].var(axis=0, ddof=1).sum()
        tv = domain_raw[:, d].var(ddof=1)
        ad[d] = 60 / 59 * (1 - iv / tv); sdd[d] = np.sqrt(tv)
    semf = sdf * np.sqrt(1 - af); semd = sdd * np.sqrt(1 - ad)
    seef = sdf * np.sqrt(af * (1 - af)); seed_ = sdd * np.sqrt(ad * (1 - ad))

    # printed percentiles under the shipped norms
    def to_pct(raw, which, shift=None):
        T = np.zeros(raw.shape)
        for g in ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]:
            m = masks[g]
            ns = np.asarray(data["norms"][g]["ns"], dtype=np.float64)
            if which == "d":
                for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
                    di = ipip.DOMAIN_INDEX[dom]
                    T[m, d_i] = 50 + 10 * (raw[m, d_i] - ns[di]) / ns[di + 5]
            else:
                for dom in ipip.DOMAIN_ORDER:
                    mo, so = ipip.FACET_OFFSET[dom]
                    for fno in range(1, 7):
                        s = ipip.facet_slot(dom, fno)
                        T[m, s] = 50 + 10 * (raw[m, s] - ns[fno + mo]) / ns[fno + so]
        return ipip.pct_from_t(T)

    fP = to_pct(facet_raw, "f"); dP = to_pct(domain_raw, "d")

    rng = np.random.default_rng(20260802)
    # cohort mu for the true-score regression: use the shipped norm mean
    mu_f = np.zeros((n, 30)); mu_d = np.zeros((n, 5))
    for g in ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]:
        m = masks[g]
        ns = np.asarray(data["norms"][g]["ns"], dtype=np.float64)
        for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
            mu_d[m, d_i] = ns[ipip.DOMAIN_INDEX[dom]]
            mo, _ = ipip.FACET_OFFSET[dom]
            for fno in range(1, 7):
                mu_f[m, ipip.facet_slot(dom, fno)] = ns[fno + mo]

    par_f = mu_f + af * (facet_raw - mu_f) + rng.normal(size=(n, 30)) * (semf * np.sqrt(1 + af))
    par_d = mu_d + ad * (domain_raw - mu_d) + rng.normal(size=(n, 5)) * (semd * np.sqrt(1 + ad))
    pfP = to_pct(par_f, "f"); pdP = to_pct(par_d, "d")

    out = {}
    out["parallel_form_simulation"] = {
        "facet_label_change_rate": round(float((band(pfP) != band(fP)).mean()), 4),
        "domain_label_change_rate": round(float((band(pdP) != band(dP)).mean()), 4),
        "mean_facet_labels_changing_of_30": round(float((band(pfP) != band(fP)).sum(axis=1).mean()), 2),
        "mean_domain_labels_changing_of_5": round(float((band(pdP) != band(dP)).sum(axis=1).mean()), 2),
        "share_people_with_ge1_domain_narrative_flip": round(
            float(((band(pdP) != band(dP)).sum(axis=1) >= 1).mean()), 4),
        "facet_median_abs_pct_change": round(float(np.median(np.abs(pfP - fP))), 2),
        "facet_share_pct_change_gt10": round(float((np.abs(pfP - fP) > 10).mean()), 4),
        "domain_median_abs_pct_change": round(float(np.median(np.abs(pdP - dP))), 2),
        "hero_chip_top6_mean_overlap": None,
    }
    # would the 6 hero chips be the same people?
    idx = rng.choice(n, 20000, replace=False)
    t1 = np.argsort(-np.abs(fP[idx] - 50), axis=1)[:, :6]
    t2 = np.argsort(-np.abs(pfP[idx] - 50), axis=1)[:, :6]
    ov = np.array([len(set(t1[i].tolist()) & set(t2[i].tolist())) for i in range(len(idx))])
    out["parallel_form_simulation"]["hero_chip_top6_mean_overlap"] = round(float(ov.mean()), 2)
    out["parallel_form_simulation"]["hero_chip_identical_share"] = round(float((ov == 6).mean()), 4)

    # ---- empirical split-half (upper bound) ----
    ha = np.zeros((n, 30)); hb = np.zeros((n, 30))
    for s in range(30):
        cols = np.array(ipip.facet_items(s))
        ha[:, s] = items[:, cols[0::2]].sum(axis=1)
        hb[:, s] = items[:, cols[1::2]].sum(axis=1)
    pa = np.zeros((n, 30)); pb = np.zeros((n, 30))
    for g in ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]:
        m = masks[g]
        pa[m] = ipip.pct_from_t((ha[m] - ha[m].mean(0)) / ha[m].std(0, ddof=1) * 10 + 50)
        pb[m] = ipip.pct_from_t((hb[m] - hb[m].mean(0)) / hb[m].std(0, ddof=1) * 10 + 50)
    out["empirical_split_half_150v150"] = {
        "facet_label_disagreement_rate": round(float((band(pa) != band(pb)).mean()), 4),
        "facet_median_abs_pct_gap": round(float(np.median(np.abs(pa - pb))), 2),
        "note": "150 items vs 150 items -- an upper bound on 300-vs-300 instability",
    }

    # ---- CI conventions ----
    def ciw(sem_vec):
        return float(np.median(ipip.pct_from_t(50 + 1.96 * 10 * sem_vec / sdf)
                               - ipip.pct_from_t(50 - 1.96 * 10 * sem_vec / sdf)))
    out["ci_conventions_at_p50"] = {
        "facet_SEM_convention_median_width": round(ciw(semf), 2),
        "facet_SEE_convention_median_width": round(ciw(seef), 2),
        "domain_SEM_convention_median_width": round(float(np.median(
            ipip.pct_from_t(50 + 1.96 * 10 * semd / sdd) - ipip.pct_from_t(50 - 1.96 * 10 * semd / sdd))), 2),
        "domain_SEE_convention_median_width": round(float(np.median(
            ipip.pct_from_t(50 + 1.96 * 10 * seed_ / sdd) - ipip.pct_from_t(50 - 1.96 * 10 * seed_ / sdd))), 2),
    }
    # per-facet SEM CI at p50, for a shippable table
    tbl = []
    for s in range(30):
        dom = ipip.DOMAIN_ORDER[s % 5]; fno = s // 5 + 1
        w = float(ipip.pct_from_t(50 + 1.96 * 10 * semf[s] / sdf[s])
                  - ipip.pct_from_t(50 - 1.96 * 10 * semf[s] / sdf[s]))
        tbl.append({"scale": "%s%d %s" % (dom, fno, facet_names[dom][fno - 1]),
                    "alpha": round(float(af[s]), 4), "sem_raw": round(float(semf[s]), 3),
                    "ci95_width_at_p50": round(w, 1),
                    "plus_minus_pct_at_p50": round(w / 2, 1)})
    out["per_facet_ci_at_p50"] = sorted(tbl, key=lambda r: -r["ci95_width_at_p50"])

    with open(os.path.join(ipip.OUT, "gaps_retest.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    p = out["parallel_form_simulation"]
    print("PARALLEL FORM: facet label changes %.1f%% of cells (%.2f of 30 per person); "
          "domain %.1f%% (%.2f of 5); %.1f%% of people get >=1 different domain narrative"
          % (100 * p["facet_label_change_rate"], p["mean_facet_labels_changing_of_30"],
             100 * p["domain_label_change_rate"], p["mean_domain_labels_changing_of_5"],
             100 * p["share_people_with_ge1_domain_narrative_flip"]))
    print("  facet printed percentile moves median %.1f pts, >10 pts in %.1f%% of cells; domain median %.1f"
          % (p["facet_median_abs_pct_change"], 100 * p["facet_share_pct_change_gt10"],
             p["domain_median_abs_pct_change"]))
    print("  hero chips: %.2f of 6 survive a re-test; identical set %.1f%%"
          % (p["hero_chip_top6_mean_overlap"], 100 * p["hero_chip_identical_share"]))
    e = out["empirical_split_half_150v150"]
    print("SPLIT-HALF (150v150): label disagreement %.1f%%, median |gap| %.1f pts"
          % (100 * e["facet_label_disagreement_rate"], e["facet_median_abs_pct_gap"]))
    c = out["ci_conventions_at_p50"]
    print("CI at p50: facet SEM %.1f / SEE %.1f pts wide; domain SEM %.1f / SEE %.1f"
          % (c["facet_SEM_convention_median_width"], c["facet_SEE_convention_median_width"],
             c["domain_SEM_convention_median_width"], c["domain_SEE_convention_median_width"]))
    print("widest facets:", [(r["scale"], r["ci95_width_at_p50"]) for r in out["per_facet_ci_at_p50"][:4]])
    print("narrowest facets:", [(r["scale"], r["ci95_width_at_p50"]) for r in out["per_facet_ci_at_p50"][-4:]])


if __name__ == "__main__":
    main()
