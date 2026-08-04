# -*- coding: utf-8 -*-
"""Completeness-critic pass 3.

A. AGE COHORTS.  The site uses only <21 / >=21.  All norms below are derived from
   THIS sample so the comparison isolates the banding choice (norm drift is another
   agent's job).  Question: what does an older adult pay for being pooled with 21-
   year-olds, and would a third band recover it?

B. FACET INFORMATIVENESS.  The 30 bars are drawn identically.  How much does each
   facet add beyond its own domain score?  Residual after regressing facet T on
   domain T, within cohort.  Also: does the hero-chip rule (|pct-50| >= 25) pick the
   facets that carry the most unique information, or just the ones with the fattest
   marginal distribution?

Writes tools/out/gaps_structure.json.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402


def norm_pct(raw, mu, sd):
    return ipip.pct_from_t((raw - mu) / sd * 10 + 50)


def main():
    data = ipip.site_data()
    z = ipip.load()
    facet_raw = z["facet_raw"].astype(np.float64)
    domain_raw = z["domain_raw"].astype(np.float64)
    sex, age = z["sex"], z["age"].astype(np.int32)
    n = len(sex)
    facet_names = {k: [f[0] for f in data["facets"][k]] for k in ipip.DOMAIN_ORDER}
    names35 = [d for d in ipip.DOMAIN_ORDER] + \
        ["%s%d %s" % (d, f, facet_names[d][f - 1]) for d in ipip.DOMAIN_ORDER for f in range(1, 7)]
    scales = np.concatenate([domain_raw, facet_raw[:, [ipip.facet_slot(d, f)
                                                       for d in ipip.DOMAIN_ORDER
                                                       for f in range(1, 7)]]], axis=1)  # (n,35)
    out = {"n": int(n)}

    # ================= A. age bands =================
    valid = (age >= 13) & (age <= 90)
    out["age_n_by_band"] = {}
    for lab, m in [("13-20", (age >= 13) & (age < 21)), ("21-29", (age >= 21) & (age < 30)),
                   ("30-39", (age >= 30) & (age < 40)), ("40-49", (age >= 40) & (age < 50)),
                   ("50-59", (age >= 50) & (age < 60)), ("60+", (age >= 60) & (age <= 90))]:
        out["age_n_by_band"][lab] = {"n": int(m.sum()), "n_male": int((m & (sex == 1)).sum()),
                                     "n_female": int((m & (sex == 2)).sum())}

    def band_of(a, edges):
        b = np.zeros(len(a), dtype=np.int64)
        for e in edges:
            b += (a >= e)
        return b

    schemes = {
        "site_2band_lt21_gte21": [21],
        "3band_lt21_21to29_30plus": [21, 30],
        "3band_lt21_21to34_35plus": [21, 35],
        "4band_lt21_21to29_30to44_45plus": [21, 30, 45],
        "5band_lt21_21to25_26to34_35to49_50plus": [21, 26, 35, 50],
    }
    base = "site_2band_lt21_gte21"
    pct = {}
    for name, edges in schemes.items():
        b = band_of(age, edges)
        P = np.zeros((n, 35))
        for s in (1, 2):
            for bb in range(len(edges) + 1):
                m = (sex == s) & (b == bb) & valid
                if m.sum() < 2:
                    continue
                mu = scales[m].mean(axis=0)
                sd = scales[m].std(axis=0, ddof=1)
                P[m] = norm_pct(scales[m], mu, sd)
        pct[name] = P

    ok = valid
    rows = []
    for name in schemes:
        if name == base:
            continue
        d = np.abs(pct[name][ok] - pct[base][ok])
        rows.append({"scheme": name,
                     "mean_abs_pct_shift_all_35": round(float(d.mean()), 3),
                     "median_abs_pct_shift": round(float(np.median(d)), 3),
                     "share_cells_gt5": round(float((d > 5).mean()), 4),
                     "mean_scales_moving_gt5_of_35": round(float((d > 5).sum(axis=1).mean()), 2)})
    out["age_scheme_vs_site_2band"] = rows

    # who pays?  mean |dPct| by current age, under the best 3-band scheme
    best = "3band_lt21_21to29_30plus"
    by_age = []
    for lo, hi, lab in [(13, 20, "13-20"), (21, 24, "21-24"), (25, 29, "25-29"), (30, 34, "30-34"),
                        (35, 39, "35-39"), (40, 49, "40-49"), (50, 59, "50-59"), (60, 90, "60+")]:
        m = (age >= lo) & (age <= hi)
        if m.sum() == 0:
            continue
        d = np.abs(pct[best][m] - pct[base][m])
        d4 = np.abs(pct["4band_lt21_21to29_30to44_45plus"][m] - pct[base][m])
        by_age.append({"age": lab, "n": int(m.sum()),
                       "mean_abs_pct_shift_3band": round(float(d.mean()), 2),
                       "max_scale_mean_shift_3band": round(float(d.mean(axis=0).max()), 2),
                       "worst_scale_3band": names35[int(np.argmax(d.mean(axis=0)))],
                       "mean_abs_pct_shift_4band": round(float(d4.mean()), 2)})
    out["age_cost_by_age_group"] = by_age

    # which scales drift most with age (within the >=21 pool)?
    adults = (age >= 21) & valid
    drift = []
    for i in range(35):
        a1 = scales[adults & (age < 30), i].mean()
        a2 = scales[adults & (age >= 30) & (age < 45), i].mean()
        a3 = scales[adults & (age >= 45), i].mean()
        sd = scales[adults, i].std(ddof=1)
        drift.append({"scale": names35[i], "mean_21_29": round(float(a1), 2),
                      "mean_30_44": round(float(a2), 2), "mean_45plus": round(float(a3), 2),
                      "d_45plus_minus_21_29": round(float((a3 - a1) / sd), 3),
                      "pct_shift_for_45plus_person_at_median": round(
                          float(ipip.pct_from_t(np.array([50 - 10 * (a3 - a1) / sd]))[0] - 50), 2)})
    drift.sort(key=lambda r: -abs(r["d_45plus_minus_21_29"]))
    out["age_drift_within_adults_top12"] = drift[:12]
    out["age_drift_within_adults_all"] = drift

    # is 21 the right cut?  single-year means for the 5 domains, z vs whole sample
    yr = []
    for a in range(14, 61):
        m = age == a
        if m.sum() < 200:
            continue
        yr.append({"age": a, "n": int(m.sum()),
                   "z": [round(float((scales[m, i].mean() - scales[valid, i].mean())
                                     / scales[valid, i].std(ddof=1)), 3) for i in range(5)]})
    out["single_year_domain_z_NEOAC"] = yr

    # ================= B. facet informativeness =================
    masks = ipip.group_masks(sex, age)
    cohort = np.full(n, -1)
    for gi, g in enumerate(["M_lt21", "M_gte21", "F_lt21", "F_gte21"]):
        cohort[masks[g]] = gi
    # cohort-standardised T from the sample (isolates structure, not norm error)
    fT = np.zeros((n, 30)); dT = np.zeros((n, 5))
    for gi in range(4):
        m = cohort == gi
        fT[m] = (facet_raw[m] - facet_raw[m].mean(axis=0)) / facet_raw[m].std(axis=0, ddof=1) * 10 + 50
        dT[m] = (domain_raw[m] - domain_raw[m].mean(axis=0)) / domain_raw[m].std(axis=0, ddof=1) * 10 + 50

    fP = ipip.pct_from_t(fT); dP = ipip.pct_from_t(dT)
    info = []
    for dom in ipip.DOMAIN_ORDER:
        d_i = ipip.DOMAIN_ORDER.index(dom)
        for fno in range(1, 7):
            slot = ipip.facet_slot(dom, fno)
            r = float(np.corrcoef(fT[:, slot], dT[:, d_i])[0, 1])
            resid = fT[:, slot] - (50 + r * (dT[:, d_i] - 50))
            # displayed disagreement between facet and its own domain
            gap = np.abs(fP[:, slot] - dP[:, d_i])
            info.append({
                "domain": dom, "facet_no": fno, "name": facet_names[dom][fno - 1],
                "r_with_own_domain": round(r, 4),
                "pct_variance_unique": round(float(1 - r * r), 4),
                "residual_T_sd": round(float(resid.std(ddof=1)), 3),
                "median_abs_pct_gap_to_own_domain": round(float(np.median(gap)), 2),
                "share_gap_ge25": round(float((gap >= 25).mean()), 4),
            })
    out["facet_informativeness"] = sorted(info, key=lambda r: r["pct_variance_unique"], reverse=True)

    # hero chips: current rule vs "most surprising given the domain"
    rng = np.random.default_rng(SEED := 20260802)
    idx = rng.choice(n, 20000, replace=False)
    dev = np.abs(fP[idx] - 50)
    # surprise = |facet T - domain-predicted facet T| in T units
    predT = np.zeros((len(idx), 30))
    for dom in ipip.DOMAIN_ORDER:
        d_i = ipip.DOMAIN_ORDER.index(dom)
        for fno in range(1, 7):
            slot = ipip.facet_slot(dom, fno)
            r = float(np.corrcoef(fT[:, slot], dT[:, d_i])[0, 1])
            predT[:, slot] = 50 + r * (dT[idx, d_i] - 50)
    surprise = np.abs(fT[idx] - predT)
    top_dev = np.argsort(-dev, axis=1)[:, :6]
    top_sur = np.argsort(-surprise, axis=1)[:, :6]
    ov = np.array([len(set(top_dev[i].tolist()) & set(top_sur[i].tolist())) for i in range(len(idx))])
    out["hero_chip_rule"] = {
        "n_sampled": int(len(idx)),
        "mean_overlap_of_top6": round(float(ov.mean()), 3),
        "share_with_identical_top6": round(float((ov == 6).mean()), 4),
        "share_with_le3_overlap": round(float((ov <= 3).mean()), 4),
    }

    with open(os.path.join(ipip.OUT, "gaps_structure.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("AGE n:", {k: v["n"] for k, v in out["age_n_by_band"].items()})
    for r in rows:
        print("  %-42s mean|dP| %.2f  median %.2f  cells>5pts %.1f%%  scales>5 of 35: %.2f"
              % (r["scheme"], r["mean_abs_pct_shift_all_35"], r["median_abs_pct_shift"],
                 100 * r["share_cells_gt5"], r["mean_scales_moving_gt5_of_35"]))
    print("  cost by age (3band vs site 2band):")
    for r in by_age:
        print("    %-6s n=%6d mean|dP| %.2f (4band %.2f)  worst scale %s %.2f"
              % (r["age"], r["n"], r["mean_abs_pct_shift_3band"], r["mean_abs_pct_shift_4band"],
                 r["worst_scale_3band"], r["max_scale_mean_shift_3band"]))
    print("  biggest adult age drift (d, 45+ vs 21-29):")
    for r in drift[:10]:
        print("    %-18s d=%+.3f -> %+.1f pct pts for a 45+ median person"
              % (r["scale"], r["d_45plus_minus_21_29"], r["pct_shift_for_45plus_person_at_median"]))
    print("FACET UNIQUE VARIANCE (1-r^2 vs own domain):")
    for r in out["facet_informativeness"][:6]:
        print("    most unique  %s%d %-8s r=%.3f unique=%.3f  median |gap to domain| %.1f pts"
              % (r["domain"], r["facet_no"], r["name"], r["r_with_own_domain"],
                 r["pct_variance_unique"], r["median_abs_pct_gap_to_own_domain"]))
    for r in out["facet_informativeness"][-6:]:
        print("    least unique %s%d %-8s r=%.3f unique=%.3f  median |gap to domain| %.1f pts"
              % (r["domain"], r["facet_no"], r["name"], r["r_with_own_domain"],
                 r["pct_variance_unique"], r["median_abs_pct_gap_to_own_domain"]))
    print("HERO CHIPS: top6 by |pct-50| vs top6 by surprise-given-domain overlap %.2f/6; identical %.1f%%"
          % (out["hero_chip_rule"]["mean_overlap_of_top6"],
             100 * out["hero_chip_rule"]["share_with_identical_top6"]))


if __name__ == "__main__":
    main()
