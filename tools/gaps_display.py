# -*- coding: utf-8 -*-
"""Completeness-critic pass 1: things the SITE DISPLAYS that nobody has audited.

  1. level() band widths -- the site applies Johnson's T-score cutoffs (45/55) to a
     PERCENTILE.  How many of a user's 35 printed scales land in "中等"?
  2. Measurement error -- per-facet alpha -> SEM -> the 95% CI of the printed
     percentile.  The site says "30 和 70 附近是模糊边界" without a number.
  3. The site's central advice ("更值得看的是你 30 个子面向之间的相对高低"):
     how many of the 435 facet pairs are actually reliably ordered?
  4. "同一个维度的总分可以由很不一样的子面向组合而成" -- quantify.
  5. Hint-mode inflation: percentile cost of a given effect size.

Writes tools/out/gaps_display.json.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

FNAMES = None


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

    # ---------- per-respondent shipped-norm T and percentile, exactly as the site ----------
    # cohort assignment: real sex is known for everyone in this file
    fT = np.full((n, 30), np.nan)
    dT = np.full((n, 5), np.nan)
    for g in ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]:
        m = masks[g]
        ns = np.asarray(data["norms"][g]["ns"], dtype=np.float64)
        for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
            di = ipip.DOMAIN_INDEX[dom]
            dT[m, d_i] = 50 + 10 * (domain_raw[m, d_i] - ns[di]) / ns[di + 5]
            mo, so = ipip.FACET_OFFSET[dom]
            for fno in range(1, 7):
                slot = ipip.facet_slot(dom, fno)
                fT[m, slot] = 50 + 10 * (facet_raw[m, slot] - ns[fno + mo]) / ns[fno + so]
    assert not np.isnan(fT).any() and not np.isnan(dT).any()

    fP = ipip.pct_from_t(fT)
    dP = ipip.pct_from_t(dT)

    out = {"n": int(n)}

    # ================= 1. level() bands =================
    def band(p):
        v = np.trunc(p)
        return np.where(v < 45, 0, np.where(v <= 55, 1, 2))   # 0 低 1 中等 2 高

    allP = np.concatenate([dP, fP], axis=1)                   # (n, 35)
    b = band(allP)
    counts = [int((b == k).sum()) for k in range(3)]
    tot = b.size
    per_person_mid = (b == 1).sum(axis=1)
    out["level_bands"] = {
        "rule": "level(p): p<45 低, 45<=p<=55 中等, p>55 高  -- applied to the PERCENTILE",
        "share_low": counts[0] / tot,
        "share_mid": counts[1] / tot,
        "share_high": counts[2] / tot,
        "mean_mid_scales_of_35": float(per_person_mid.mean()),
        "median_mid_scales_of_35": float(np.median(per_person_mid)),
        "share_people_with_zero_mid_of_35": float((per_person_mid == 0).mean()),
        "share_people_with_le2_mid_of_35": float((per_person_mid <= 2).mean()),
    }
    # what the same cutoffs give if read as T-scores (their original units)
    bT = np.where(np.concatenate([dT, fT], axis=1) < 45, 0,
                  np.where(np.concatenate([dT, fT], axis=1) <= 55, 1, 2))
    out["level_bands"]["if_cutoffs_applied_to_T"] = {
        "share_low": float((bT == 0).mean()), "share_mid": float((bT == 1).mean()),
        "share_high": float((bT == 2).mean()),
        "mean_mid_scales_of_35": float((bT == 1).sum(axis=1).mean()),
    }
    # tendencyTag bands (domains only): <=30, <45, <55, <70, >=70
    tt = dP
    out["tendency_tag_bands_domains"] = {
        "p_le30": float((tt <= 30).mean()), "p_30_45": float(((tt > 30) & (tt < 45)).mean()),
        "p_45_55": float(((tt >= 45) & (tt < 55)).mean()),
        "p_55_70": float(((tt >= 55) & (tt < 70)).mean()), "p_ge70": float((tt >= 70).mean()),
    }
    # hero chips: |pct-50|>=25 for facets, >=15 for domains
    dev_f = np.abs(fP - 50)
    out["hero_selection"] = {
        "mean_facets_with_dev_ge25_of_30": float((dev_f >= 25).sum(axis=1).mean()),
        "share_people_with_ge6_such_facets": float(((dev_f >= 25).sum(axis=1) >= 6).mean()),
        "mean_domains_with_dev_ge15_of_5": float((np.abs(dP - 50) >= 15).sum(axis=1).mean()),
        "share_people_with_zero_strong_domain": float(((np.abs(dP - 50) >= 15).sum(axis=1) == 0).mean()),
    }

    # ================= 2. reliability -> printed-percentile CI =================
    k_items = 10
    alpha = np.zeros(30)
    sd_tot = np.zeros(30)
    for slot in range(30):
        cols = ipip.facet_items(slot)
        iv = items[:, cols].var(axis=0, ddof=1).sum()
        tv = facet_raw[:, slot].var(ddof=1)
        alpha[slot] = k_items / (k_items - 1) * (1 - iv / tv)
        sd_tot[slot] = np.sqrt(tv)
    sem_raw = sd_tot * np.sqrt(1 - alpha)                     # raw points

    alpha_d = np.zeros(5)
    sd_d = np.zeros(5)
    for d_i in range(5):
        cols = [c for slot in range(30) if slot % 5 == d_i for c in ipip.facet_items(slot)]
        iv = items[:, cols].var(axis=0, ddof=1).sum()
        tv = domain_raw[:, d_i].var(ddof=1)
        alpha_d[d_i] = 60 / 59 * (1 - iv / tv)
        sd_d[d_i] = np.sqrt(tv)
    sem_raw_d = sd_d * np.sqrt(1 - alpha_d)

    # CI of the PRINTED percentile, per respondent, using their own cohort norms
    def pct_shift(raw_mat, shift, which):
        """which='facet' or 'domain'; recompute printed pct with raw+shift."""
        T = np.full(raw_mat.shape, np.nan)
        for g in ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]:
            m = masks[g]
            ns = np.asarray(data["norms"][g]["ns"], dtype=np.float64)
            if which == "domain":
                for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
                    di = ipip.DOMAIN_INDEX[dom]
                    T[m, d_i] = 50 + 10 * (raw_mat[m, d_i] + shift[d_i] - ns[di]) / ns[di + 5]
            else:
                for dom in ipip.DOMAIN_ORDER:
                    mo, so = ipip.FACET_OFFSET[dom]
                    for fno in range(1, 7):
                        slot = ipip.facet_slot(dom, fno)
                        T[m, slot] = 50 + 10 * (raw_mat[m, slot] + shift[slot] - ns[fno + mo]) / ns[fno + so]
        return ipip.pct_from_t(T)

    hi = pct_shift(facet_raw, 1.96 * sem_raw, "facet")
    lo = pct_shift(facet_raw, -1.96 * sem_raw, "facet")
    ciw = hi - lo
    hi_d = pct_shift(domain_raw, 1.96 * sem_raw_d, "domain")
    lo_d = pct_shift(domain_raw, -1.96 * sem_raw_d, "domain")
    ciw_d = hi_d - lo_d

    facets_tbl = []
    for slot in range(30):
        dom = ipip.DOMAIN_ORDER[slot % 5]
        fno = slot // 5 + 1
        facets_tbl.append({
            "slot": slot, "domain": dom, "facet_no": fno,
            "name": facet_names[dom][fno - 1],
            "alpha": round(float(alpha[slot]), 4),
            "sd_raw": round(float(sd_tot[slot]), 3),
            "sem_raw": round(float(sem_raw[slot]), 3),
            "ci95_pct_width_median": round(float(np.median(ciw[:, slot])), 2),
            "ci95_pct_width_at_p50": None,
        })
    # CI width for someone sitting exactly at the cohort median (T=50), per facet
    for slot in range(30):
        dom = ipip.DOMAIN_ORDER[slot % 5]
        fno = slot // 5 + 1
        # average over the four real cohorts
        ws = []
        for g in ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]:
            ns = np.asarray(data["norms"][g]["ns"], dtype=np.float64)
            mo, so = ipip.FACET_OFFSET[dom]
            sd = ns[fno + so]
            t_hi = 50 + 10 * 1.96 * sem_raw[slot] / sd
            t_lo = 50 - 10 * 1.96 * sem_raw[slot] / sd
            ws.append(float(ipip.pct_from_t(t_hi) - ipip.pct_from_t(t_lo)))
        facets_tbl[slot]["ci95_pct_width_at_p50"] = round(float(np.mean(ws)), 2)
    out["reliability_ci"] = {
        "definition": "SEM = sd_raw*sqrt(1-alpha); CI = printed percentile at raw +/- 1.96*SEM",
        "facet_alpha_min": round(float(alpha.min()), 4),
        "facet_alpha_median": round(float(np.median(alpha)), 4),
        "facet_alpha_max": round(float(alpha.max()), 4),
        "domain_alpha": {ipip.DOMAIN_ORDER[i]: round(float(alpha_d[i]), 4) for i in range(5)},
        "facet_ci95_width_median_over_all_cells": round(float(np.median(ciw)), 2),
        "facet_ci95_width_mean_over_all_cells": round(float(ciw.mean()), 2),
        "domain_ci95_width_median_over_all_cells": round(float(np.median(ciw_d)), 2),
        "facets": facets_tbl,
        "domains": [{
            "domain": ipip.DOMAIN_ORDER[i], "alpha": round(float(alpha_d[i]), 4),
            "sd_raw": round(float(sd_d[i]), 3), "sem_raw": round(float(sem_raw_d[i]), 3),
            "ci95_pct_width_median": round(float(np.median(ciw_d[:, i])), 2),
        } for i in range(5)],
    }
    # how often does the 95% CI straddle a level() boundary?
    straddle45 = ((lo < 45) & (hi >= 45)).mean()
    straddle55 = ((lo <= 55) & (hi > 55)).mean()
    out["reliability_ci"]["facet_cells_whose_CI_straddles_45"] = float(straddle45)
    out["reliability_ci"]["facet_cells_whose_CI_straddles_55"] = float(straddle55)
    out["reliability_ci"]["facet_cells_whose_CI_straddles_a_band_edge"] = float(
        (((lo < 45) & (hi >= 45)) | ((lo <= 55) & (hi > 55))).mean())

    # ================= 3. are the 30 facets reliably ordered within a person? =====
    # reliable difference in T units: |T_i - T_j| > 1.96 * 10 * sqrt((1-a_i)+(1-a_j))
    # (SEM in T units = 10*sqrt(1-alpha) because T is standardised by the cohort SD;
    #  we use the cohort SD implied by sem_raw/sd_tot so this is exact to that approx.)
    semT = 10.0 * np.sqrt(1 - alpha)
    crit = 1.96 * np.sqrt(semT[:, None] ** 2 + semT[None, :] ** 2)      # (30,30)
    iu = np.triu_indices(30, 1)
    critv = crit[iu]
    # subsample for the pairwise count (435 pairs x 145k is fine but keep it honest+fast)
    rng = np.random.default_rng(20260802)
    idx = rng.choice(n, size=20000, replace=False)
    dT_pairs = np.abs(fT[idx][:, iu[0]] - fT[idx][:, iu[1]])
    reliable = dT_pairs > critv
    out["facet_pair_ordering"] = {
        "n_pairs": int(len(critv)),
        "n_respondents_sampled": int(len(idx)),
        "critical_T_gap_median": round(float(np.median(critv)), 3),
        "critical_T_gap_min": round(float(critv.min()), 3),
        "critical_T_gap_max": round(float(critv.max()), 3),
        "mean_reliable_pairs": round(float(reliable.sum(axis=1).mean()), 1),
        "median_reliable_pairs": float(np.median(reliable.sum(axis=1))),
        "share_of_all_pairs_reliable": round(float(reliable.mean()), 4),
    }
    # same thing for adjacent facets inside one domain (what the bars invite you to compare)
    within = [(a, b_) for a in range(30) for b_ in range(30) if a < b_ and a % 5 == b_ % 5]
    wa = np.array([p[0] for p in within]); wb = np.array([p[1] for p in within])
    wcrit = 1.96 * np.sqrt(semT[wa] ** 2 + semT[wb] ** 2)
    wd = np.abs(fT[idx][:, wa] - fT[idx][:, wb])
    out["facet_pair_ordering"]["within_domain_pairs"] = int(len(within))
    out["facet_pair_ordering"]["within_domain_share_reliable"] = round(float((wd > wcrit).mean()), 4)
    out["facet_pair_ordering"]["within_domain_mean_reliable_of_75"] = round(
        float((wd > wcrit).sum(axis=1).mean()), 2)

    # ================= 4. facet spread given a mid domain =================
    spread = []
    for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
        slots = [ipip.facet_slot(dom, f) for f in range(1, 7)]
        mid = (dP[:, d_i] >= 45) & (dP[:, d_i] <= 55)
        sub = fP[mid][:, slots]
        rng_ = sub.max(axis=1) - sub.min(axis=1)
        spread.append({
            "domain": dom, "n_mid": int(mid.sum()),
            "median_facet_pct_range": round(float(np.median(rng_)), 1),
            "p90_facet_pct_range": round(float(np.percentile(rng_, 90)), 1),
            "share_with_range_ge40": round(float((rng_ >= 40).mean()), 4),
            "share_with_one_facet_ge70_and_one_le30": round(
                float(((sub.max(axis=1) >= 70) & (sub.min(axis=1) <= 30)).mean()), 4),
        })
    allrng = np.zeros(n)
    for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
        slots = [ipip.facet_slot(dom, f) for f in range(1, 7)]
        allrng = np.maximum(allrng, fP[:, slots].max(axis=1) - fP[:, slots].min(axis=1))
    out["facet_spread_within_domain"] = {
        "per_domain_given_domain_pct_45_55": spread,
        "whole_sample_max_within_domain_facet_range_median": round(float(np.median(allrng)), 1),
    }

    # ================= 5. hint-mode inflation sensitivity =================
    infl = []
    for d in [0.05, 0.1, 0.2, 0.3, 0.5]:
        # d = effect size in facet-SD units -> T shifts by 10*d
        rows = []
        for slot in range(30):
            dom = ipip.DOMAIN_ORDER[slot % 5]
            fno = slot // 5 + 1
            p0 = ipip.pct_from_t(fT[:, slot])
            p1 = ipip.pct_from_t(fT[:, slot] + 10 * d)
            rows.append(float(np.mean(p1 - p0)))
        # also in per-item terms: how many raw points per item does d cost?
        per_item = float(np.mean(d * sd_tot / 10.0))
        infl.append({
            "effect_size_d_sd": d,
            "mean_percentile_shift_facets": round(float(np.mean(rows)), 2),
            "max_percentile_shift_facet": round(float(np.max(rows)), 2),
            "shift_at_p50_person": round(float(ipip.pct_from_t(np.array([50 + 10 * d]))[0] - 50), 2),
            "shift_at_p80_person": round(float(
                ipip.pct_from_t(np.array([np.percentile(fT, 80) + 10 * d]))[0]
                - ipip.pct_from_t(np.array([np.percentile(fT, 80)]))[0]), 2),
            "implied_mean_raw_points_per_item": round(per_item, 4),
        })
    # inverse: how big a per-item drift is needed to move the median person 5 / 10 pct points
    inv = []
    for target in [5, 10, 20]:
        # solve pct(50+x) - 50 = target
        xs = np.linspace(0, 25, 25001)
        p = ipip.pct_from_t(50 + xs)
        j = int(np.argmin(np.abs(p - 50 - target)))
        dT_needed = float(xs[j])
        inv.append({
            "target_percentile_shift_from_50": target,
            "T_shift_needed": round(dT_needed, 3),
            "effect_size_d_needed": round(dT_needed / 10, 3),
            "mean_raw_points_per_item_needed": round(float(np.mean(dT_needed / 10 * sd_tot / 10.0)), 4),
        })
    out["hint_inflation_sensitivity"] = {"forward": infl, "inverse": inv,
                                         "facet_sd_raw_mean": round(float(sd_tot.mean()), 3)}

    with open(os.path.join(ipip.OUT, "gaps_display.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # ---- console summary ----
    lb = out["level_bands"]
    print("LEVEL BANDS  low %.4f mid %.4f high %.4f | mean 中等 scales of 35 = %.2f | %.2f%% get ZERO 中等"
          % (lb["share_low"], lb["share_mid"], lb["share_high"], lb["mean_mid_scales_of_35"],
             100 * lb["share_people_with_zero_mid_of_35"]))
    print("  if the same 45/55 cutoffs were read as T: low %.4f mid %.4f high %.4f (mean mid %.2f)"
          % (lb["if_cutoffs_applied_to_T"]["share_low"], lb["if_cutoffs_applied_to_T"]["share_mid"],
             lb["if_cutoffs_applied_to_T"]["share_high"], lb["if_cutoffs_applied_to_T"]["mean_mid_scales_of_35"]))
    rc = out["reliability_ci"]
    print("ALPHA facets %.3f..%.3f (med %.3f)  domain alphas %s"
          % (rc["facet_alpha_min"], rc["facet_alpha_max"], rc["facet_alpha_median"], rc["domain_alpha"]))
    print("CI95 width of printed facet percentile: median %.1f pts (domains %.1f)"
          % (rc["facet_ci95_width_median_over_all_cells"], rc["domain_ci95_width_median_over_all_cells"]))
    print("  facet cells whose CI straddles a 低/中/高 edge: %.1f%%"
          % (100 * rc["facet_cells_whose_CI_straddles_a_band_edge"]))
    fpo = out["facet_pair_ordering"]
    print("FACET PAIRS reliably ordered: %.1f of %d (%.1f%%); within-domain %.2f of 75 (%.1f%%)"
          % (fpo["mean_reliable_pairs"], fpo["n_pairs"], 100 * fpo["share_of_all_pairs_reliable"],
             fpo["within_domain_mean_reliable_of_75"], 100 * fpo["within_domain_share_reliable"]))
    print("SPREAD given mid domain:", [(s["domain"], s["median_facet_pct_range"],
                                        s["share_with_one_facet_ge70_and_one_le30"]) for s in spread])
    for r in infl:
        print("  d=%.2f -> mean facet pct shift %+.2f (at p50 person %+.2f), %.3f raw pts/item"
              % (r["effect_size_d_sd"], r["mean_percentile_shift_facets"],
                 r["shift_at_p50_person"], r["implied_mean_raw_points_per_item"]))
    for r in inv:
        print("  to move p50 by %d pts: d=%.3f, %.3f raw points per item"
              % (r["target_percentile_shift_from_50"], r["effect_size_d_needed"],
                 r["mean_raw_points_per_item_needed"]))


if __name__ == "__main__":
    main()
