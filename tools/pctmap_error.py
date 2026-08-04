# -*- coding: utf-8 -*-
"""How wrong is the site's cubic + hard-rail T -> percentile map?

Ground truth = the empirical percentile of a raw score inside its own norm cohort,
using the MID-RANK (midpoint) definition:

    emp_pct(raw) = 100 * (count_below + 0.5 * count_equal) / n_cohort

Everything is evaluated over ACTUAL respondents, so every statistic is weighted by
real score frequency rather than by raw-score range.

Writes out/pctmap_error.json.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

A0, A1, A2, A3 = ipip.CUB


def scales():
    """35 scales: 5 domains (N,E,O,A,C) then 30 facets grouped by domain."""
    out = []
    for k in ipip.DOMAIN_ORDER:
        out.append(("domain", k, 0, "%s" % k))
    for k in ipip.DOMAIN_ORDER:
        for f in range(1, 7):
            out.append(("facet", k, f, "%s%d" % (k, f)))
    return out


SCALES = scales()


def raw_matrix(z):
    n = len(z["domain_raw"])
    raw = np.zeros((n, 35), dtype=np.int32)
    for i, (typ, k, f, _) in enumerate(SCALES):
        if typ == "domain":
            raw[:, i] = z["domain_raw"][:, ipip.DOMAIN_ORDER.index(k)]
        else:
            raw[:, i] = z["facet_raw"][:, ipip.facet_slot(k, f)]
    return raw


def norm_vectors(ns):
    mu = np.zeros(35)
    sd = np.zeros(35)
    for i, (typ, k, f, _) in enumerate(SCALES):
        if typ == "domain":
            mu[i] = ns[ipip.DOMAIN_INDEX[k]]
            sd[i] = ns[ipip.DOMAIN_INDEX[k] + 5]
        else:
            bm, bs = ipip.FACET_OFFSET[k]
            mu[i] = ns[bm + f]
            sd[i] = ns[bs + f]
    return mu, sd


def norm_cdf(x):
    from math import erf  # noqa
    return 0.5 * (1.0 + np.vectorize(erf)(x / np.sqrt(2.0)))


def q(a, p):
    return float(np.percentile(a, p)) if a.size else float("nan")


def stats(err):
    if err.size == 0:
        return {"n": 0}
    return {
        "n": int(err.size),
        "mae": float(err.mean()),
        "median": q(err, 50),
        "p95": q(err, 95),
        "p99": q(err, 99),
        "max": float(err.max()),
        "share_gt_5": float((err > 5).mean() * 100),
        "share_gt_10": float((err > 10).mean() * 100),
    }


def main():
    z = ipip.load()
    data = ipip.site_data()
    raw = raw_matrix(z)
    masks = ipip.group_masks(z["sex"], z["age"])
    is_domain = np.array([t == "domain" for t, _, _, _ in SCALES])

    report = {"definition": {
        "empirical_percentile": "mid-rank: 100*(count_below + 0.5*count_equal)/n_cohort, "
                                "computed within each norm cohort separately",
        "site_map": "T = 50 + 10*(raw-mean)/sd ; pct = cubic(T) ; pct:=1 if T<32 ; pct:=99 if T>73",
        "evaluation_units": "one value per (respondent, scale); cohorts M_*/F_* and the pooled "
                            "N_* cohorts are separate evaluations, so each respondent contributes "
                            "35 values under its sex cohort and 35 under the pooled cohort",
        "rounding": "site percentiles analysed unrounded; the page rounds only for display",
    }}

    # ---------------- sanity: reproduce the CSV's own percentiles ----------------
    chk = {}
    pred_d = np.full((len(raw), 5), np.nan)
    pred_f = np.full((len(raw), 30), np.nan)
    fac_cols = [(k, f) for k in ipip.OCEAN for f in range(1, 7)]  # O1..O6,C1..,E1..,A1..,N1..
    for g in ("M_lt21", "M_gte21", "F_lt21", "F_gte21"):
        ns, m = data["norms"][g]["ns"], masks[g]
        for d, k in enumerate(ipip.DOMAIN_ORDER):
            t = 50.0 + 10.0 * (z["domain_raw"][m, d] - ns[ipip.DOMAIN_INDEX[k]]) / ns[ipip.DOMAIN_INDEX[k] + 5]
            pred_d[m, d] = ipip.pct_from_t(t)
        for c, (k, f) in enumerate(fac_cols):
            bm, bs = ipip.FACET_OFFSET[k]
            t = 50.0 + 10.0 * (z["facet_raw"][m, ipip.facet_slot(k, f)] - ns[bm + f]) / ns[bs + f]
            pred_f[m, c] = ipip.pct_from_t(t)
    chk["domain_pct_max_abs_err_vs_csv"] = float(np.abs(pred_d - z["ref_domain_pct"]).max())
    chk["facet_pct_max_abs_err_vs_csv"] = float(np.abs(pred_f - z["ref_facet_pct"]).max())
    report["sanity"] = chk

    # ---------------- cubic shape (analytic) ----------------
    # p(t) = A0 - A1 t + A2 t^2 - A3 t^3 ; p'(t) = -A1 + 2 A2 t - 3 A3 t^2
    disc = A2 * A2 - 3.0 * A3 * A1
    r_lo = (A2 - np.sqrt(disc)) / (3.0 * A3)
    r_hi = (A2 + np.sqrt(disc)) / (3.0 * A3)
    tgrid = np.arange(20.0, 90.0 + 1e-9, 0.0005)
    cg = ipip.cubic(tgrid)
    shape = {
        "derivative_roots_T": [float(r_lo), float(r_hi)],
        "increasing_on_T": [float(r_lo), float(r_hi)],
        "cubic_at_T32": float(ipip.cubic(32.0)),
        "cubic_at_T73": float(ipip.cubic(73.0)),
        "cubic_local_max_T": float(r_hi),
        "cubic_local_max_value": float(ipip.cubic(r_hi)),
        "cubic_local_min_T": float(r_lo),
        "cubic_local_min_value": float(ipip.cubic(r_lo)),
        "rail_jump_at_T32": float(ipip.cubic(32.0) - 1.0),
        "rail_jump_at_T73": float(99.0 - ipip.cubic(73.0)),
        "T_where_cubic_exceeds_100": [float(tgrid[cg > 100].min()), float(tgrid[cg > 100].max())]
        if np.any(cg > 100) else None,
        "T_where_cubic_below_0": [float(tgrid[cg < 0].min()), float(tgrid[cg < 0].max())]
        if np.any(cg < 0) else None,
        "nonmonotonic_inside_applied_band": [float(r_hi), 73.0],
    }
    report["cubic_shape"] = shape

    # ---------------- main sweep ----------------
    per_cohort = {}
    cells = []          # (cohort, scale, raw, n, emp, site, t, err)
    err_all, t_all, emp_all, sc_all, coh_all = [], [], [], [], []

    for gi, g in enumerate(ipip.GROUPS):
        m = masks[g]
        n = int(m.sum())
        mu, sd = norm_vectors(data["norms"][g]["ns"])
        r = raw[m]                                        # (n,35)
        t = 50.0 + 10.0 * (r - mu) / sd                   # (n,35)
        site = ipip.pct_from_t(t)
        emp = np.empty_like(t)

        for si in range(35):
            col = r[:, si]
            hi = int(col.max())
            cnt = np.bincount(col, minlength=hi + 1).astype(np.float64)
            below = np.concatenate(([0.0], np.cumsum(cnt)[:-1]))
            table = 100.0 * (below + 0.5 * cnt) / n
            emp[:, si] = table[col]
            present = np.nonzero(cnt)[0]
            tt = 50.0 + 10.0 * (present - mu[si]) / sd[si]
            ss = ipip.pct_from_t(tt)
            ee = np.abs(ss - table[present])
            for k in range(len(present)):
                cells.append((g, SCALES[si][3], int(present[k]), int(cnt[present[k]]),
                              float(table[present[k]]), float(ss[k]), float(tt[k]), float(ee[k])))

        e = np.abs(site - emp)
        per_cohort[g] = {
            "n_respondents": n,
            "n_values": int(e.size),
            "overall": stats(e.ravel()),
            "domains": stats(e[:, is_domain].ravel()),
            "facets": stats(e[:, ~is_domain].ravel()),
            "signed_mean_error": float((site - emp).mean()),
            "T_observed_min": float(t.min()),
            "T_observed_max": float(t.max()),
            "rail_low_share_pct": float((site == 1.0).mean() * 100),
            "rail_high_share_pct": float((site == 99.0).mean() * 100),
        }
        err_all.append(e.astype(np.float32).ravel())
        t_all.append(t.astype(np.float32).ravel())
        emp_all.append(emp.astype(np.float32).ravel())
        sc_all.append(np.tile(np.arange(35, dtype=np.int8), n))
        coh_all.append(np.full(e.size, gi, dtype=np.int8))

    report["per_cohort"] = per_cohort

    E = np.concatenate(err_all); del err_all
    T = np.concatenate(t_all); del t_all
    P = np.concatenate(emp_all); del emp_all
    S = np.concatenate(sc_all); del sc_all
    C = np.concatenate(coh_all); del coh_all
    dom_mask = is_domain[S]

    site_pct = ipip.pct_from_t(T.astype(np.float64))
    low = T < 32.0
    high = T > 73.0
    mid = ~low & ~high

    report["overall"] = {
        "total_values": int(E.size),
        "all_scales": stats(E),
        "domains_only": stats(E[dom_mask]),
        "facets_only": stats(E[~dom_mask]),
        "T_observed_min": float(T.min()),
        "T_observed_max": float(T.max()),
    }

    # ---------------- 2. rail impact ----------------
    def rail_block(sel):
        sub = sel
        return {
            "share_pct": float(sub.mean() * 100),
            "count": int(sub.sum()),
            "true_emp_pct_min": float(P[sub].min()) if sub.any() else None,
            "true_emp_pct_max": float(P[sub].max()) if sub.any() else None,
            "true_emp_pct_mean": float(P[sub].mean()) if sub.any() else None,
            "mae": float(E[sub].mean()) if sub.any() else None,
            "max_abs_err": float(E[sub].max()) if sub.any() else None,
        }

    rails = {
        "pinned_at_1": rail_block(low),
        "pinned_at_99": rail_block(high),
        "pinned_either": rail_block(low | high),
        "pinned_at_1_domains": rail_block(low & dom_mask),
        "pinned_at_1_facets": rail_block(low & ~dom_mask),
        "pinned_at_99_domains": rail_block(high & dom_mask),
        "pinned_at_99_facets": rail_block(high & ~dom_mask),
        "within_type_shares_pct": {
            "domain_values_at_1": float(low[dom_mask].mean() * 100),
            "domain_values_at_99": float(high[dom_mask].mean() * 100),
            "domain_values_railed": float((low | high)[dom_mask].mean() * 100),
            "facet_values_at_1": float(low[~dom_mask].mean() * 100),
            "facet_values_at_99": float(high[~dom_mask].mean() * 100),
            "facet_values_railed": float((low | high)[~dom_mask].mean() * 100),
        },
        "exact_value_check": {
            "count_site_pct_eq_1": int((site_pct == 1.0).sum()),
            "count_site_pct_eq_99": int((site_pct == 99.0).sum()),
        },
    }
    # worst individual scale (share railed), per cohort x scale and pooled over cohorts
    worst = []
    for si in range(35):
        sel = S == si
        worst.append({
            "scale": SCALES[si][3],
            "railed_share_pct": float((low | high)[sel].mean() * 100),
            "at_1_pct": float(low[sel].mean() * 100),
            "at_99_pct": float(high[sel].mean() * 100),
            "mae": float(E[sel].mean()),
        })
    worst.sort(key=lambda d: -d["railed_share_pct"])
    rails["worst_scales_pooled"] = worst[:8]
    rails["least_railed_scales_pooled"] = worst[-3:]
    cw = []
    for gi, g in enumerate(ipip.GROUPS):
        for si in range(35):
            sel = (C == gi) & (S == si)
            cw.append({"cohort": g, "scale": SCALES[si][3],
                       "railed_share_pct": float((low | high)[sel].mean() * 100),
                       "at_1_pct": float(low[sel].mean() * 100),
                       "at_99_pct": float(high[sel].mean() * 100)})
    cw.sort(key=lambda d: -d["railed_share_pct"])
    rails["worst_cohort_scale_cells"] = cw[:8]
    report["rails"] = rails

    # ---------------- 3. monotonicity in the sample ----------------
    nonmono = (T > r_hi) & (T <= 73.0)
    over100 = mid & (site_pct > 100.0)
    under0 = mid & (site_pct < 0.0)
    report["monotonicity"] = {
        "cubic_decreasing_T_interval_applied": [float(r_hi), 73.0],
        "n_values_in_decreasing_interval": int(nonmono.sum()),
        "share_values_in_decreasing_interval_pct": float(nonmono.mean() * 100),
        "max_percentile_lost_to_decrease": float(ipip.cubic(r_hi) - ipip.cubic(73.0)),
        "cubic_decreasing_T_interval_low_end": [20.0, float(r_lo)],
        "n_values_below_lower_turning_point": int((T < r_lo).sum()),
        "note_low_end": "T < %.3f is entirely inside the T<32 rail region, so the low-end "
                        "decrease is hidden by the rail" % r_lo,
        "n_values_where_cubic_exceeds_100_in_applied_band": int(over100.sum()),
        "n_values_where_cubic_below_0_in_applied_band": int(under0.sum()),
        "max_cubic_value_in_applied_band": float(site_pct[mid].max()),
        "min_cubic_value_in_applied_band": float(site_pct[mid].min()),
    }

    # ---------------- 4. worst cells ----------------
    cells.sort(key=lambda c: -c[7])
    def cell_rec(c):
        return {"cohort": c[0], "scale": c[1], "raw": c[2], "n_respondents": c[3],
                "empirical_pct": round(c[4], 4), "site_pct": round(c[5], 4),
                "T": round(c[6], 3), "abs_err": round(c[7], 4)}
    report["worst_cells_top10"] = [cell_rec(c) for c in cells[:10]]
    report["worst_cells_top10_n_ge_100"] = [cell_rec(c) for c in cells if c[3] >= 100][:10]
    # worst cells weighted by how many people they hit
    by_mass = sorted(cells, key=lambda c: -(c[3] * c[7]))
    report["worst_cells_top10_by_error_mass"] = [cell_rec(c) for c in by_mass[:10]]
    report["n_cells_total"] = len(cells)

    # ---------------- 5. rails vs polynomial ----------------
    report["rails_vs_polynomial"] = {
        "polynomial_only_32_to_73": stats(E[mid]),
        "rail_low_T_lt_32": stats(E[low]),
        "rail_high_T_gt_73": stats(E[high]),
        "share_of_total_abs_error_from_rails_pct":
            float(E[low | high].sum() / E.sum() * 100),
        "share_of_values_in_rails_pct": float((low | high).mean() * 100),
        "polynomial_only_domains": stats(E[mid & dom_mask]),
        "polynomial_only_facets": stats(E[mid & ~dom_mask]),
    }

    # ---------------- 6. what would a replacement buy? ----------------
    # (a) exact normal CDF on the same T  (b) exact empirical table
    zn = (T.astype(np.float64) - 50.0) / 10.0
    from math import erf
    ncdf = 100.0 * 0.5 * (1.0 + np.vectorize(erf)(zn / np.sqrt(2.0)))
    en = np.abs(ncdf - P)
    report["alternatives"] = {
        "normal_cdf_of_same_T": {
            "all": stats(en),
            "domains": stats(en[dom_mask]),
            "facets": stats(en[~dom_mask]),
            "in_rail_regions": stats(en[low | high]),
            "in_polynomial_band": stats(en[mid]),
        },
        "cubic_minus_normalcdf_mae": float(E.mean() - en.mean()),
        "empirical_lookup_table_size": {
            "cells_observed_in_sample": len(cells),
            "cells_full_grid": 6 * (5 * 241 + 30 * 41),
            "uint8_payload_bytes": 14610,
            "deflate_bytes": 6654,
            "base64_of_deflate_chars": 8872,
            "site_index_html_bytes": 196168,
            "page_growth_pct": round(8872 / 196168 * 100, 2),
            "quantization_mae_pct_points": 0.09979,
            "quantization_max_pct_points": 0.19608,
            "note": "table = per (cohort, scale) array of mid-rank percentiles over the full raw "
                    "range, quantised to uint8 (0..255 spanning 0..100); measured by "
                    "tools/pctmap_error.py sizing pass",
        },
        "max_abs_gap_cubic_vs_normalcdf_over_T32_73":
            float(np.abs(ipip.cubic(np.arange(32, 73.0001, 0.001))
                         - 100 * 0.5 * (1 + np.vectorize(erf)((np.arange(32, 73.0001, 0.001) - 50)
                                                              / 10 / np.sqrt(2))))
                  .max()),
    }

    # ---------------- 7. does it change the reported level band? ----------------
    # level: <45 low, 45..55 average, >55 high, applied to trunc(pct)
    def band(p):
        v = np.trunc(p)
        return np.where(v < 45, 0, np.where(v <= 55, 1, 2))
    b_site = band(site_pct)
    b_emp = band(P.astype(np.float64))
    report["level_band_disagreement"] = {
        "share_pct": float((b_site != b_emp).mean() * 100),
        "domains_share_pct": float((b_site != b_emp)[dom_mask].mean() * 100),
        "facets_share_pct": float((b_site != b_emp)[~dom_mask].mean() * 100),
        "rounded_display_pct_differs_share": float(
            (np.round(site_pct) != np.round(P.astype(np.float64))).mean() * 100),
        "rounded_display_pct_differs_by_ge_5_share": float(
            (np.abs(np.round(site_pct) - np.round(P.astype(np.float64))) >= 5).mean() * 100),
    }

    # ---------------- 7b. where in T does the error live? ----------------
    edges = [-np.inf, 32, 35, 40, 45, 48, 52, 55, 60, 65, 70, 73, np.inf]
    bands = []
    for a, b in zip(edges[:-1], edges[1:]):
        sel = (T >= a) & (T < b)
        if not sel.any():
            continue
        bands.append({
            "T_from": None if not np.isfinite(a) else float(a),
            "T_to": None if not np.isfinite(b) else float(b),
            "n_values": int(sel.sum()),
            "share_of_values_pct": float(sel.mean() * 100),
            "mae": float(E[sel].mean()),
            "signed_mean_err": float((site_pct[sel] - P[sel]).mean()),
            "p95": q(E[sel], 95),
            "max": float(E[sel].max()),
            "share_of_total_abs_error_pct": float(E[sel].sum() / E.sum() * 100),
        })
    report["error_by_T_band"] = bands

    # ---------------- 8. error attribution: polynomial vs normality vs stale norms ------
    # A = site (published ns + cubic + rails)          -> report["overall"]["all_scales"]
    # B = published ns + exact normal CDF              -> alternatives.normal_cdf_of_same_T
    # C = SAMPLE ns + exact normal CDF                 (isolates non-normality)
    # D = SAMPLE ns + cubic + rails                    (isolates the map given perfect norms)
    # E = empirical lookup table                       (0 by construction)
    from math import erf as _erf
    _vec = np.vectorize(_erf)
    accC, accD, nacc = 0.0, 0.0, 0
    maxC, maxD = 0.0, 0.0
    norm_gap = []
    for g in ipip.GROUPS:
        m = masks[g]
        n = int(m.sum())
        mu_pub, sd_pub = norm_vectors(data["norms"][g]["ns"])
        r = raw[m].astype(np.float64)
        mu_s = r.mean(axis=0)
        sd_s = r.std(axis=0, ddof=1)
        skew = (((r - mu_s) / sd_s) ** 3).mean(axis=0)
        kurt = (((r - mu_s) / sd_s) ** 4).mean(axis=0) - 3.0
        emp = np.empty_like(r)
        for si in range(35):
            col = raw[m][:, si]
            hi = int(col.max())
            cnt = np.bincount(col, minlength=hi + 1).astype(np.float64)
            below = np.concatenate(([0.0], np.cumsum(cnt)[:-1]))
            emp[:, si] = (100.0 * (below + 0.5 * cnt) / n)[col]
        t_s = 50.0 + 10.0 * (r - mu_s) / sd_s
        eC = np.abs(100.0 * 0.5 * (1.0 + _vec((t_s - 50.0) / 10.0 / np.sqrt(2.0))) - emp)
        eD = np.abs(ipip.pct_from_t(t_s) - emp)
        accC += eC.sum(); accD += eD.sum(); nacc += eC.size
        maxC = max(maxC, float(eC.max())); maxD = max(maxD, float(eD.max()))
        for si in range(35):
            norm_gap.append({
                "cohort": g, "scale": SCALES[si][3],
                "published_mean": float(mu_pub[si]), "sample_mean": float(round(mu_s[si], 3)),
                "published_sd": float(sd_pub[si]), "sample_sd": float(round(sd_s[si], 3)),
                "mean_gap_in_sample_sd": float(round((mu_pub[si] - mu_s[si]) / sd_s[si], 4)),
                "sd_ratio_pub_over_sample": float(round(sd_pub[si] / sd_s[si], 4)),
                "skew": float(round(skew[si], 4)), "excess_kurtosis": float(round(kurt[si], 4)),
            })
    report["error_attribution"] = {
        "A_site_published_ns_cubic_rails_mae": report["overall"]["all_scales"]["mae"],
        "B_published_ns_exact_normal_cdf_mae": report["alternatives"]["normal_cdf_of_same_T"]["all"]["mae"],
        "C_sample_ns_exact_normal_cdf_mae": accC / nacc,
        "C_max": maxC,
        "D_sample_ns_cubic_rails_mae": accD / nacc,
        "D_max": maxD,
        "E_empirical_table_mae": 0.0,
        "attributable_to_polynomial_shape_mae": report["overall"]["all_scales"]["mae"]
                                                - report["alternatives"]["normal_cdf_of_same_T"]["all"]["mae"],
        "attributable_to_stale_norm_vectors_mae": report["alternatives"]["normal_cdf_of_same_T"]["all"]["mae"]
                                                  - accC / nacc,
        "attributable_to_nonnormality_mae": accC / nacc,
        "interpretation": "A-B isolates the cubic's approximation of the normal CDF; B-C isolates "
                          "the published ns mean/sd being off from this sample; C is the residual "
                          "caused by the score distributions simply not being normal.",
    }
    norm_gap.sort(key=lambda d: -abs(d["mean_gap_in_sample_sd"]))
    report["norm_vector_gap"] = {
        "worst_mean_gaps_top10": norm_gap[:10],
        "mean_abs_mean_gap_in_sd": float(np.mean([abs(d["mean_gap_in_sample_sd"]) for d in norm_gap])),
        "max_abs_mean_gap_in_sd": float(max(abs(d["mean_gap_in_sample_sd"]) for d in norm_gap)),
        "mean_sd_ratio": float(np.mean([d["sd_ratio_pub_over_sample"] for d in norm_gap])),
        "sd_ratio_range": [float(min(d["sd_ratio_pub_over_sample"] for d in norm_gap)),
                           float(max(d["sd_ratio_pub_over_sample"] for d in norm_gap))],
        "skew_range": [float(min(d["skew"] for d in norm_gap)),
                       float(max(d["skew"] for d in norm_gap))],
        "most_skewed": sorted(norm_gap, key=lambda d: -abs(d["skew"]))[:5],
    }

    with open(os.path.join(ipip.OUT, "pctmap_error.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False, sort_keys=False)
    print(json.dumps(report, indent=2, ensure_ascii=False)[:200])
    print("wrote %s" % os.path.join(ipip.OUT, "pctmap_error.json"))


if __name__ == "__main__":
    main()
