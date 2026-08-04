# -*- coding: utf-8 -*-
"""Audit: do the 6 shipped norm vectors in site/index.html match this sample?

Writes tools/out/norm_fidelity.json.  Run:  python tools/norm_fidelity.py
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

RNG = np.random.default_rng(20260802)
BOOT = 400


# ---------------------------------------------------------------- ns helpers
def ns_labels():
    """Human label for each of the 71 ns slots ('' for the pad)."""
    lab = [""] * 71
    for d, i in ipip.DOMAIN_INDEX.items():
        lab[i] = "%s_domain_mean" % d
        lab[i + 5] = "%s_domain_sd" % d
    for d, (mo, so) in ipip.FACET_OFFSET.items():
        for f in range(1, 7):
            lab[mo + f] = "%s%d_mean" % (d, f)
            lab[so + f] = "%s%d_sd" % (d, f)
    return lab


LAB = ns_labels()
# element index -> ("domain"|"facet", domain key, facet no or None, "mean"|"sd")
SLOT = {}
for _d, _i in ipip.DOMAIN_INDEX.items():
    SLOT[_i] = ("domain", _d, None, "mean")
    SLOT[_i + 5] = ("domain", _d, None, "sd")
for _d, (_mo, _so) in ipip.FACET_OFFSET.items():
    for _f in range(1, 7):
        SLOT[_mo + _f] = ("facet", _d, _f, "mean")
        SLOT[_so + _f] = ("facet", _d, _f, "sd")


def sample_ns(facet_raw, domain_raw, mask, ddof, nd=2):
    """Recompute the full 71-element ns vector from the masked sample."""
    ns = [0.0] * 71
    fr = facet_raw[mask]
    dr = domain_raw[mask]
    for d, i in ipip.DOMAIN_INDEX.items():
        col = ipip.DOMAIN_ORDER.index(d)          # domain_raw is ordered N,E,O,A,C
        ns[i] = round(float(dr[:, col].mean()), nd)
        ns[i + 5] = round(float(dr[:, col].std(ddof=ddof)), nd)
    for d, (mo, so) in ipip.FACET_OFFSET.items():
        for f in range(1, 7):
            j = ipip.facet_slot(d, f)
            ns[mo + f] = round(float(fr[:, j].mean()), nd)
            ns[so + f] = round(float(fr[:, j].std(ddof=ddof)), nd)
    return ns


def scale_raw(facet_raw, domain_raw, kind, d, f):
    if kind == "domain":
        return domain_raw[:, ipip.DOMAIN_ORDER.index(d)].astype(np.float64)
    return facet_raw[:, ipip.facet_slot(d, f)].astype(np.float64)


def ns_slot_for(kind, d, f, what):
    if kind == "domain":
        return ipip.DOMAIN_INDEX[d] + (0 if what == "mean" else 5)
    mo, so = ipip.FACET_OFFSET[d]
    return (mo if what == "mean" else so) + f


def jsround(x):
    """JS Math.round: half away from zero toward +inf (percentiles are positive)."""
    return np.floor(np.asarray(x, dtype=np.float64) + 0.5)


def level_of(p):
    """Site: const v = Math.trunc(p); v<45 low, v<=55 average, else high. 0/1/2."""
    v = np.trunc(np.asarray(p, dtype=np.float64))
    return np.where(v < 45, 0, np.where(v <= 55, 1, 2))


def main():
    z = ipip.load()
    facet_raw, domain_raw = z["facet_raw"], z["domain_raw"]
    sex, age = z["sex"], z["age"]
    masks = ipip.group_masks(sex, age)
    site = ipip.site_data()
    shipped = {g: [float(v) for v in site["norms"][g]["ns"]] for g in ipip.GROUPS}

    out = {
        "generated_for": "site/index.html DATA.norms",
        "n_total": int(len(age)),
        "cohort_n": {g: int(masks[g].sum()) for g in ipip.GROUPS},
    }

    # ---- 0. sanity: shipped norms reproduce the CSV's own percentile columns -----
    ref = z["ref_domain_pct"]
    err = np.zeros(len(age))
    for g in ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]:
        m = masks[g]
        ns = shipped[g]
        for d in ipip.DOMAIN_ORDER:
            col = ipip.DOMAIN_ORDER.index(d)
            i = ipip.DOMAIN_INDEX[d]
            t = 50 + 10 * (domain_raw[m][:, col] - ns[i]) / ns[i + 5]
            p = ipip.pct_from_t(t)
            err[np.flatnonzero(m)] = np.maximum(
                err[np.flatnonzero(m)], np.abs(p - ref[m][:, col]))
    out["sanity_max_abs_pct_vs_csv_reference"] = float(err.max())

    # ---- 1. which SD convention does the shipping vector use? -------------------
    conv = {}
    for ddof in (0, 1):
        tot = 0.0
        for g in ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]:
            s = sample_ns(facet_raw, domain_raw, masks[g], ddof)
            tot += sum(abs(s[i] - shipped[g][i]) for i in SLOT if SLOT[i][3] == "sd")
        conv["ddof%d_total_abs_sd_gap" % ddof] = round(tot, 4)
    out["sd_convention_probe"] = conv
    DDOF = 1  # sample SD; the two differ by <0.001 at these n (see probe)

    # ---- 2. element-by-element comparison, all 6 cohorts ------------------------
    recomputed = {g: sample_ns(facet_raw, domain_raw, masks[g], DDOF) for g in ipip.GROUPS}
    # site-style neutral: elementwise average of the SHIPPED M and F vectors, 2dp
    for band in ("lt21", "gte21"):
        m, f = shipped["M_" + band], shipped["F_" + band]
        out.setdefault("neutral_from_shipped_MF_avg", {})["N_" + band] = [
            round((m[i] + f[i]) / 2, 2) for i in range(71)]
    # neutral built the five-factor-e way but from RECOMPUTED M/F sample vectors
    neutral_avg_of_sample = {}
    for band in ("lt21", "gte21"):
        m, f = recomputed["M_" + band], recomputed["F_" + band]
        neutral_avg_of_sample["N_" + band] = [round((m[i] + f[i]) / 2, 2) for i in range(71)]

    cohorts = {}
    for g in ipip.GROUPS:
        sh, rc = shipped[g], recomputed[g]
        rows = []
        for i in sorted(SLOT):
            kind, d, f, what = SLOT[i]
            rows.append({
                "idx": i, "label": LAB[i], "kind": kind, "domain": d, "facet": f,
                "stat": what, "shipped": sh[i], "sample": rc[i],
                "diff": round(rc[i] - sh[i], 4),
                "pct_of_shipped_sd": round(
                    (rc[i] - sh[i]) / sh[ns_slot_for(kind, d, f, "sd")] * 100, 3),
            })
        ad = [abs(r["diff"]) for r in rows]
        adm = [abs(r["diff"]) for r in rows if r["stat"] == "mean"]
        ads = [abs(r["diff"]) for r in rows if r["stat"] == "sd"]
        worst = max(rows, key=lambda r: abs(r["diff"]))
        worst_sd = max(rows, key=lambda r: abs(r["pct_of_shipped_sd"]))
        cohorts[g] = {
            "n": int(masks[g].sum()),
            "n_elements_exactly_equal": int(sum(1 for a in ad if a == 0)),
            "n_elements_gap_ge_0p05": int(sum(1 for a in ad if a >= 0.05)),
            "mean_abs_diff_all70": round(float(np.mean(ad)), 4),
            "max_abs_diff_all70": round(float(np.max(ad)), 4),
            "mean_abs_diff_means": round(float(np.mean(adm)), 4),
            "mean_abs_diff_sds": round(float(np.mean(ads)), 4),
            "max_abs_diff_in_sd_units_pct": round(worst_sd["pct_of_shipped_sd"], 3),
            "worst_element": {k: worst[k] for k in
                              ("label", "shipped", "sample", "diff", "pct_of_shipped_sd")},
            "worst_element_in_sd_units": {k: worst_sd[k] for k in
                                          ("label", "shipped", "sample", "diff",
                                           "pct_of_shipped_sd")},
            "elements": rows,
        }
    out["cohorts"] = cohorts

    # ---- 3. the neutral question ------------------------------------------------
    neu = {}
    for band in ("lt21", "gte21"):
        g = "N_" + band
        sh = shipped[g]
        avg_ship = out["neutral_from_shipped_MF_avg"][g]
        pooled = recomputed[g]
        avg_samp = neutral_avg_of_sample[g]
        da = [abs(sh[i] - avg_ship[i]) for i in sorted(SLOT)]
        dp = [abs(sh[i] - pooled[i]) for i in sorted(SLOT)]
        dap = [abs(avg_samp[i] - pooled[i]) for i in sorted(SLOT)]
        neu[g] = {
            "shipped_vs_elementwise_avg_of_shipped_MF": {
                "n_exact": int(sum(1 for a in da if a == 0)),
                "max_abs": round(float(np.max(da)), 4),
                "mean_abs": round(float(np.mean(da)), 4),
            },
            "shipped_vs_pooled_sample_stats": {
                "max_abs": round(float(np.max(dp)), 4),
                "mean_abs": round(float(np.mean(dp)), 4),
            },
            "elementwise_avg_of_sample_MF_vs_pooled_sample": {
                "max_abs": round(float(np.max(dap)), 4),
                "mean_abs": round(float(np.mean(dap)), 4),
            },
        }
        # why avg != pooled: the sex mix
        m = masks["M_" + band].sum()
        f = masks["F_" + band].sum()
        neu[g]["sex_mix"] = {"male": int(m), "female": int(f),
                             "male_share": round(float(m) / float(m + f), 4)}
    out["neutral_check"] = neu

    # ---- 4. user-visible impact --------------------------------------------------
    scales = ipip.scale_index()
    impact_rows = []
    for g in ipip.GROUPS:
        m = masks[g]
        fr, dr = facet_raw[m], domain_raw[m]
        sh = shipped[g]
        variants = {"sample": recomputed[g]}
        if g.startswith("N_"):
            variants["sample_avgMF"] = neutral_avg_of_sample[g]
        for vname, rc in variants.items():
            for kind, d, f in scales:
                raw = scale_raw(fr, dr, kind, d, f)
                im, isd = ns_slot_for(kind, d, f, "mean"), ns_slot_for(kind, d, f, "sd")
                t0 = 50 + 10 * (raw - sh[im]) / sh[isd]
                t1 = 50 + 10 * (raw - rc[im]) / rc[isd]
                p0, p1 = ipip.pct_from_t(t0), ipip.pct_from_t(t1)
                dp = np.abs(p1 - p0)
                dr_disp = np.abs(jsround(p1) - jsround(p0))
                lv = level_of(p0) != level_of(p1)
                impact_rows.append({
                    "cohort": g, "variant": vname,
                    "scale": d if kind == "domain" else "%s%d" % (d, f),
                    "kind": kind, "n": int(m.sum()),
                    "mean_abs_pct_shift": round(float(dp.mean()), 4),
                    "max_abs_pct_shift": round(float(dp.max()), 4),
                    "p99_abs_pct_shift": round(float(np.percentile(dp, 99)), 4),
                    "share_disp_ge1": round(float((dr_disp >= 1).mean()), 6),
                    "share_disp_ge5": round(float((dr_disp >= 5).mean()), 6),
                    "share_disp_ge10": round(float((dr_disp >= 10).mean()), 6),
                    "share_level_flip": round(float(lv.mean()), 6),
                    "mean_abs_T_shift": round(float(np.abs(t1 - t0).mean()), 4),
                })
    out["impact_rows"] = impact_rows

    prim = [r for r in impact_rows if r["variant"] == "sample"]
    out["impact_summary"] = {
        "n_rows": len(prim),
        "overall_mean_abs_pct_shift": round(float(np.mean([r["mean_abs_pct_shift"] for r in prim])), 4),
        "overall_max_abs_pct_shift": round(float(np.max([r["max_abs_pct_shift"] for r in prim])), 4),
        "overall_mean_share_disp_ge1": round(float(np.mean([r["share_disp_ge1"] for r in prim])), 6),
        "overall_mean_share_disp_ge5": round(float(np.mean([r["share_disp_ge5"] for r in prim])), 6),
        "overall_mean_share_disp_ge10": round(float(np.mean([r["share_disp_ge10"] for r in prim])), 6),
        "overall_mean_share_level_flip": round(float(np.mean([r["share_level_flip"] for r in prim])), 6),
        "worst_by_mean_shift": max(prim, key=lambda r: r["mean_abs_pct_shift"]),
        "worst_by_max_shift": max(prim, key=lambda r: r["max_abs_pct_shift"]),
        "worst_by_share_ge5": max(prim, key=lambda r: r["share_disp_ge5"]),
        "worst_by_level_flip": max(prim, key=lambda r: r["share_level_flip"]),
        "top10_by_mean_shift": sorted(prim, key=lambda r: -r["mean_abs_pct_shift"])[:10],
    }
    # per-cohort roll-up over the 35 scales (primary variant)
    out["impact_by_cohort"] = {}
    for g in ipip.GROUPS:
        rs = [r for r in prim if r["cohort"] == g]
        out["impact_by_cohort"][g] = {
            "n": rs[0]["n"],
            "mean_abs_pct_shift": round(float(np.mean([r["mean_abs_pct_shift"] for r in rs])), 4),
            "max_abs_pct_shift": round(float(np.max([r["max_abs_pct_shift"] for r in rs])), 4),
            "mean_share_disp_ge1": round(float(np.mean([r["share_disp_ge1"] for r in rs])), 6),
            "mean_share_disp_ge5": round(float(np.mean([r["share_disp_ge5"] for r in rs])), 6),
            "mean_share_disp_ge10": round(float(np.mean([r["share_disp_ge10"] for r in rs])), 6),
            "mean_share_level_flip": round(float(np.mean([r["share_level_flip"] for r in rs])), 6),
            "worst_scale": max(rs, key=lambda r: r["mean_abs_pct_shift"])["scale"],
        }
    # neutral variant comparison roll-up
    out["impact_neutral_variants"] = {}
    for g in ("N_lt21", "N_gte21"):
        for vname in ("sample", "sample_avgMF"):
            rs = [r for r in impact_rows if r["cohort"] == g and r["variant"] == vname]
            out["impact_neutral_variants"]["%s|%s" % (g, vname)] = {
                "mean_abs_pct_shift": round(float(np.mean([r["mean_abs_pct_shift"] for r in rs])), 4),
                "max_abs_pct_shift": round(float(np.max([r["max_abs_pct_shift"] for r in rs])), 4),
                "mean_share_disp_ge1": round(float(np.mean([r["share_disp_ge1"] for r in rs])), 6),
                "mean_share_disp_ge5": round(float(np.mean([r["share_disp_ge5"] for r in rs])), 6),
            }

    out["impact_summary"]["overall_mean_abs_pct_shift_excl_N5"] = round(
        float(np.mean([r["mean_abs_pct_shift"] for r in prim if r["scale"] != "N5"])), 4)

    # ---- 4a2. per-respondent: how many of the 35 printed numbers move? -----------
    # The four sex-specific cohorts partition the whole sample, so this is a
    # "would this person's report look different" figure.
    n_tot = len(age)
    cnt1 = np.zeros(n_tot); cnt5 = np.zeros(n_tot)
    cnt10 = np.zeros(n_tot); cntlv = np.zeros(n_tot)
    for g in ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]:
        m = masks[g]
        idx = np.flatnonzero(m)
        fr, dr = facet_raw[m], domain_raw[m]
        sh, rc = shipped[g], recomputed[g]
        for kind, d, f in scales:
            raw = scale_raw(fr, dr, kind, d, f)
            im, isd = ns_slot_for(kind, d, f, "mean"), ns_slot_for(kind, d, f, "sd")
            p0 = ipip.pct_from_t(50 + 10 * (raw - sh[im]) / sh[isd])
            p1 = ipip.pct_from_t(50 + 10 * (raw - rc[im]) / rc[isd])
            dd = np.abs(jsround(p1) - jsround(p0))
            cnt1[idx] += (dd >= 1); cnt5[idx] += (dd >= 5); cnt10[idx] += (dd >= 10)
            cntlv[idx] += (level_of(p0) != level_of(p1))
    out["per_respondent_report_impact"] = {
        "basis": "M/F cohorts only (they partition the sample); 35 printed percentiles each",
        "n_respondents": int(n_tot),
        "mean_scales_moving_ge1": round(float(cnt1.mean()), 3),
        "mean_scales_moving_ge5": round(float(cnt5.mean()), 3),
        "mean_scales_moving_ge10": round(float(cnt10.mean()), 4),
        "mean_scales_changing_level_band": round(float(cntlv.mean()), 3),
        "share_with_ANY_scale_moving_ge1": round(float((cnt1 >= 1).mean()), 5),
        "share_with_ANY_scale_moving_ge5": round(float((cnt5 >= 1).mean()), 5),
        "share_with_ANY_scale_moving_ge10": round(float((cnt10 >= 1).mean()), 5),
        "share_with_ANY_level_band_change": round(float((cntlv >= 1).mean()), 5),
        "share_with_ge5_scales_changing_level_band": round(float((cntlv >= 5).mean()), 5),
    }

    # ---- 4b. internal consistency of each SHIPPED vector -------------------------
    # In any real sample, domain mean == sum of its 6 facet means, exactly.
    ic = {}
    for g in ipip.GROUPS:
        row = {}
        for d in ipip.DOMAIN_ORDER:
            mo, _so = ipip.FACET_OFFSET[d]
            s6 = sum(shipped[g][mo + f] for f in range(1, 7))
            row[d] = round(s6 - shipped[g][ipip.DOMAIN_INDEX[d]], 4)
        ic[g] = row
    out["shipped_internal_consistency"] = {
        "note": "sum(6 facet means) - domain mean; must be 0 (+-0.05 rounding) in a real sample",
        "shipped": ic,
        "sample_control": {g: {d: round(
            sum(recomputed[g][ipip.FACET_OFFSET[d][0] + f] for f in range(1, 7))
            - recomputed[g][ipip.DOMAIN_INDEX[d]], 4) for d in ipip.DOMAIN_ORDER}
            for g in ipip.GROUPS},
    }

    # ---- 4c. the N5 defect -------------------------------------------------------
    mo, so = ipip.FACET_OFFSET["N"]
    identical = {}
    for band in ("lt21", "gte21"):
        m_, f_ = shipped["M_" + band], shipped["F_" + band]
        identical[band] = [LAB[i] for i in sorted(SLOT) if m_[i] == f_[i]]
    bug = {"finding": "shipped F_* and N_* vectors carry the MALE N5 (immoderation) "
                      "mean and SD; only N5 breaks the domain=sum(facets) identity",
           "identical_M_vs_F_elements": identical,
           "n5_mean_index": mo + 5, "n5_sd_index": so + 5, "cohorts": {}}
    for band in ("lt21", "gte21"):
        fg = "F_" + band
        s6 = sum(shipped[fg][mo + f] for f in range(1, 7))
        implied = round(shipped[fg][ipip.DOMAIN_INDEX["N"]] - (s6 - shipped[fg][mo + 5]), 2)
        for pre in ("F", "N"):
            g = pre + "_" + band
            fixed = implied if pre == "F" else round(
                (shipped["M_" + band][mo + 5] + implied) / 2, 2)
            x = facet_raw[masks[g]][:, ipip.facet_slot("N", 5)].astype(np.float64)
            sd = shipped[g][so + 5]
            t0 = 50 + 10 * (x - shipped[g][mo + 5]) / sd
            t1 = 50 + 10 * (x - fixed) / sd
            p0, p1 = ipip.pct_from_t(t0), ipip.pct_from_t(t1)
            dp = np.abs(p1 - p0)
            rd = np.abs(jsround(p1) - jsround(p0))
            bug["cohorts"][g] = {
                "shipped_n5_mean": shipped[g][mo + 5],
                "male_n5_mean": shipped["M_" + band][mo + 5],
                "identity_implied_n5_mean": fixed,
                "sample_n5_mean": round(float(x.mean()), 3),
                "residual_after_fix": round(float(x.mean() - fixed), 3),
                "shipped_n5_sd": sd,
                "sample_n5_sd": round(float(x.std(ddof=1)), 3),
                "fix_mean_abs_pct_shift": round(float(dp.mean()), 3),
                "fix_max_abs_pct_shift": round(float(dp.max()), 3),
                "fix_share_disp_ge1": round(float((rd >= 1).mean()), 6),
                "fix_share_disp_ge5": round(float((rd >= 5).mean()), 6),
                "fix_share_disp_ge10": round(float((rd >= 10).mean()), 6),
                "fix_share_level_flip": round(
                    float((level_of(p0) != level_of(p1)).mean()), 6),
                "median_pct_before": round(float(np.median(p0)), 2),
                "median_pct_after": round(float(np.median(p1)), 2),
            }
    bug["patch"] = {g: {"index": mo + 5, "from": bug["cohorts"][g]["shipped_n5_mean"],
                        "to": bug["cohorts"][g]["identity_implied_n5_mean"]}
                    for g in bug["cohorts"]}
    out["n5_defect"] = bug

    # ---- 4d. vintage drift within the sample -------------------------------------
    yr = z["year"]
    early, late = yr <= 103, yr >= 109
    vint = {"year_coding": "year-1900; 101..111 == 2001..2011",
            "year_counts": {int(y): int((yr == y).sum()) for y in np.unique(yr)},
            "cohorts": {}}
    for g in ipip.GROUPS:
        row = {"n_early_2001_2003": int((masks[g] & early).sum()),
               "n_late_2009_2011": int((masks[g] & late).sum()), "domains": {}}
        for d in ipip.DOMAIN_ORDER:
            col = ipip.DOMAIN_ORDER.index(d)
            a = domain_raw[masks[g] & early][:, col].astype(np.float64)
            b = domain_raw[masks[g] & late][:, col].astype(np.float64)
            sd = shipped[g][ipip.DOMAIN_INDEX[d] + 5]
            dT = 10 * (b.mean() - a.mean()) / sd
            row["domains"][d] = {
                "mean_early": round(float(a.mean()), 2), "mean_late": round(float(b.mean()), 2),
                "raw_delta": round(float(b.mean() - a.mean()), 2),
                "T_delta": round(float(dT), 3),
                "pct_delta_at_median": round(float(ipip.cubic(50 + dT) - ipip.cubic(50)), 2),
            }
        vint["cohorts"][g] = row
    out["vintage_drift"] = vint

    # ---- 4e. what a recent-only refresh would cost --------------------------------
    rec_only = {}
    for g in ipip.GROUPS:
        m = masks[g]
        row = {}
        for d in ipip.DOMAIN_ORDER:
            col = ipip.DOMAIN_ORDER.index(d)
            xf = domain_raw[m][:, col].astype(np.float64)
            xl = domain_raw[m & late][:, col].astype(np.float64)
            t0 = 50 + 10 * (xf - xf.mean()) / xf.std(ddof=1)
            t1 = 50 + 10 * (xf - xl.mean()) / xl.std(ddof=1)
            p = np.abs(ipip.pct_from_t(t1) - ipip.pct_from_t(t0))
            row[d] = {"mean_abs_pct": round(float(p.mean()), 3),
                      "max_abs_pct": round(float(p.max()), 3)}
        rec_only[g] = row
    out["refresh_recent_only_vs_full_sample"] = rec_only

    # how much percentile does one T point buy, near the middle?
    out["pct_per_T_point"] = {
        "at_T45": round(float(ipip.cubic(46) - ipip.cubic(45)), 4),
        "at_T50": round(float(ipip.cubic(51) - ipip.cubic(50)), 4),
        "at_T55": round(float(ipip.cubic(56) - ipip.cubic(55)), 4),
    }

    # ---- 5. stability: n, analytic SE, bootstrap SE ------------------------------
    stab = {}
    for g in ipip.GROUPS:
        m = masks[g]
        n = int(m.sum())
        dr = domain_raw[m]
        rec = {"n": n, "domains": {}}
        for d in ipip.DOMAIN_ORDER:
            col = ipip.DOMAIN_ORDER.index(d)
            x = dr[:, col].astype(np.float64)
            sd = float(x.std(ddof=1))
            se_mean = sd / np.sqrt(n)
            se_sd = sd / np.sqrt(2.0 * (n - 1))
            boot = np.empty(BOOT)
            for b in range(BOOT):
                boot[b] = x[RNG.integers(0, n, n)].mean()
            rec["domains"][d] = {
                "mean": round(float(x.mean()), 3),
                "sd": round(sd, 3),
                "se_mean_analytic": round(float(se_mean), 4),
                "se_mean_bootstrap": round(float(boot.std(ddof=1)), 4),
                "se_sd_analytic": round(float(se_sd), 4),
                # a 1-SE error in the mean moves T by 10*se/sd, i.e. 10/sqrt(n)
                "T_shift_per_SE_of_mean": round(float(10 * se_mean / sd), 4),
                "pct_shift_per_SE_at_T50": round(
                    float(abs(ipip.cubic(50 + 10 * se_mean / sd) - ipip.cubic(50))), 4),
                # what the ACTUAL shipped-vs-sample mean gap is, in SE units
                "shipped_minus_sample_mean": round(
                    float(shipped[g][ipip.DOMAIN_INDEX[d]] - x.mean()), 3),
                "gap_in_SE_units": round(
                    float(abs(shipped[g][ipip.DOMAIN_INDEX[d]] - x.mean()) / se_mean), 2),
            }
        stab[g] = rec
    out["stability"] = stab
    out["bootstrap_reps"] = BOOT

    # ---- 6. sample provenance ------------------------------------------------------
    cnt = {}
    meta = os.path.join(ipip.OUT, "meta.csv")
    if os.path.exists(meta):
        import csv as _csv
        with open(meta, encoding="utf-8", newline="") as fh:
            for row in _csv.DictReader(fh):
                cnt[row["country"]] = cnt.get(row["country"], 0) + 1
        tot = sum(cnt.values())
        out["country_mix"] = {
            "distinct_countries": len(cnt), "total": tot,
            "top": [{"country": k, "n": v, "share": round(v / tot, 4)}
                    for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])[:8]],
        }

    out["verdict"] = {
        "n5_defect": "REPLACE the four female/neutral N5 mean entries now: provable copy-paste "
                     "of the male value, breaks the internal identity, worst single "
                     "user-visible error in the file.",
        "general_drift": "REFRESH the remaining 66 elements per vector from this sample when "
                         "convenient; the drift is real but sub-3-percentile on average.",
        "sample_size": "LEAVE sample size alone: every cohort has n>=25,042, SE(domain mean) "
                       "<=0.23 raw points, i.e. <=0.23 T*0.1 -> <0.09 percentile points. "
                       "Sampling noise is 1-2 orders of magnitude below the observed drift.",
    }

    path = os.path.join(ipip.OUT, "norm_fidelity.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print("wrote", path)

    # ---- console digest ----------------------------------------------------------
    print("\nsanity max|pct - csv ref| =", out["sanity_max_abs_pct_vs_csv_reference"])
    print("sd convention:", conv)
    print("\ncohort   n      exact  >=0.05  mean|d|  max|d|   worst")
    for g in ipip.GROUPS:
        c = cohorts[g]
        print("%-9s %-6d %-5d %-6d %-8.3f %-7.3f %s %.2f->%.2f" % (
            g, c["n"], c["n_elements_exactly_equal"], c["n_elements_gap_ge_0p05"],
            c["mean_abs_diff_all70"], c["max_abs_diff_all70"],
            c["worst_element"]["label"], c["worst_element"]["shipped"],
            c["worst_element"]["sample"]))
    print("\nneutral:", json.dumps(neu, indent=1))
    print("\nimpact by cohort:", json.dumps(out["impact_by_cohort"], indent=1))
    print("\noverall:", json.dumps(out["impact_summary"]["worst_by_mean_shift"], indent=1))
    print("worst by max:", json.dumps(out["impact_summary"]["worst_by_max_shift"], indent=1))
    print("neutral variants:", json.dumps(out["impact_neutral_variants"], indent=1))
    print("pct per T point:", out["pct_per_T_point"])
    print("\nshipped internal consistency (sum facet means - domain mean):")
    print(json.dumps(out["shipped_internal_consistency"]["shipped"], indent=1))
    print("N5 defect:", json.dumps(out["n5_defect"]["cohorts"], indent=1))
    print("patch:", json.dumps(out["n5_defect"]["patch"], indent=1))
    print("overall mean shift excl N5:",
          out["impact_summary"]["overall_mean_abs_pct_shift_excl_N5"])
    print("per-respondent:", json.dumps(out["per_respondent_report_impact"], indent=1))
    print("vintage (C domain, raw early->late):",
          {g: out["vintage_drift"]["cohorts"][g]["domains"]["C"]["pct_delta_at_median"]
           for g in ipip.GROUPS})
    for g in ipip.GROUPS:
        print(g, "n=", stab[g]["n"],
              {d: (stab[g]["domains"][d]["se_mean_analytic"],
                   stab[g]["domains"][d]["gap_in_SE_units"]) for d in ipip.DOMAIN_ORDER})


if __name__ == "__main__":
    main()
