# -*- coding: utf-8 -*-
"""Completeness-critic pass 2: is there an honest short form?

Held-out design
---------------
Respondents are split 50/50 (seed 20260802).  EVERYTHING -- item selection, the
short-form norms, and the reference full-form norms -- is estimated on TRAIN only.
All reported numbers are TEST-only.

Reference target = the printed percentile the 300-item form would show, computed
with TRAIN-derived norms so that the only thing being measured is short-form loss
(not norm drift, which another agent already covered).

Two short forms are tried:
  (a) unit-weighted: the k items per facet with the highest item-rest correlation
      on TRAIN.  k=3/4/5 -> 90/120/150 items.  k=4 is the length of Johnson's own
      IPIP-NEO-120.
  (b) ridge: the SAME administered items, but all 30 facet raws predicted by ridge
      regression from the whole administered subset (cross-facet borrowing).

Honesty controls
----------------
  * part-whole overlap is reported explicitly: r(short, full) shares k of 10 items.
    The overlap-free number r(short, remaining 10-k items) is reported alongside,
    plus the Spearman-Brown / attenuation-corrected true-score estimate.
  * short-form alpha on TEST.
  * the metric that actually matters for shipping: |Δ printed percentile|.

Writes tools/out/gaps_shortform.json.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

SEED = 20260802


def alpha_of(mat):
    k = mat.shape[1]
    if k < 2:
        return float("nan")
    return k / (k - 1) * (1 - mat.var(axis=0, ddof=1).sum() / mat.sum(axis=1).var(ddof=1))


def main():
    data = ipip.site_data()
    z = ipip.load()
    items = z["items"].astype(np.float64)
    facet_raw = z["facet_raw"].astype(np.float64)
    sex, age = z["sex"], z["age"]
    n = len(sex)
    facet_names = {k: [f[0] for f in data["facets"][k]] for k in ipip.DOMAIN_ORDER}

    rng = np.random.default_rng(SEED)
    perm = rng.permutation(n)
    tr, te = perm[: n // 2], perm[n // 2:]
    masks = ipip.group_masks(sex, age)
    cohort = np.full(n, -1)
    for gi, g in enumerate(["M_lt21", "M_gte21", "F_lt21", "F_gte21"]):
        cohort[masks[g]] = gi

    out = {"n_train": int(len(tr)), "n_test": int(len(te)), "seed": SEED}

    # ---------- TRAIN-derived full-form norms (per cohort, per facet) ----------
    full_mu = np.zeros((4, 30))
    full_sd = np.zeros((4, 30))
    for gi in range(4):
        m = tr[cohort[tr] == gi]
        full_mu[gi] = facet_raw[m].mean(axis=0)
        full_sd[gi] = facet_raw[m].std(axis=0, ddof=1)
    ref_T = (facet_raw[te] - full_mu[cohort[te]]) / full_sd[cohort[te]] * 10 + 50
    ref_P = ipip.pct_from_t(ref_T)

    # ---------- item-rest correlations on TRAIN ----------
    sel_rank = {}
    for slot in range(30):
        cols = ipip.facet_items(slot)
        sub = items[np.ix_(tr, cols)]
        tot = sub.sum(axis=1)
        r = np.array([np.corrcoef(sub[:, j], tot - sub[:, j])[0, 1] for j in range(10)])
        sel_rank[slot] = (np.argsort(-r), r)

    results = {}
    for k in [3, 4, 5, 6]:
        chosen = {slot: sorted(sel_rank[slot][0][:k].tolist()) for slot in range(30)}
        admin_cols = sorted(ipip.facet_items(slot)[j] for slot in range(30) for j in chosen[slot])
        # ---- (a) unit-weighted ----
        srawT = np.zeros((len(tr), 30))
        srawE = np.zeros((len(te), 30))
        restE = np.zeros((len(te), 30))
        for slot in range(30):
            cols = np.array(ipip.facet_items(slot))
            take = cols[chosen[slot]]
            rest = np.array([c for c in cols if c not in set(take.tolist())])
            srawT[:, slot] = items[np.ix_(tr, take)].sum(axis=1)
            srawE[:, slot] = items[np.ix_(te, take)].sum(axis=1)
            restE[:, slot] = items[np.ix_(te, rest)].sum(axis=1)
        s_mu = np.zeros((4, 30)); s_sd = np.zeros((4, 30))
        for gi in range(4):
            m = cohort[tr] == gi
            s_mu[gi] = srawT[m].mean(axis=0)
            s_sd[gi] = srawT[m].std(axis=0, ddof=1)
        sT = (srawE - s_mu[cohort[te]]) / s_sd[cohort[te]] * 10 + 50
        sP = ipip.pct_from_t(sT)

        per = []
        for slot in range(30):
            dom = ipip.DOMAIN_ORDER[slot % 5]; fno = slot // 5 + 1
            full = facet_raw[te, slot]
            r_full = float(np.corrcoef(srawE[:, slot], full)[0, 1])
            r_rest = float(np.corrcoef(srawE[:, slot], restE[:, slot])[0, 1])
            a_short = float(alpha_of(items[np.ix_(te, np.array(ipip.facet_items(slot))[chosen[slot]])]))
            a_full = float(alpha_of(items[np.ix_(te, ipip.facet_items(slot))]))
            # attenuation-corrected correlation with the FULL scale's true score
            r_true = r_full / np.sqrt(max(a_short, 1e-9) * max(a_full, 1e-9))
            dP = sP[:, slot] - ref_P[:, slot]
            per.append({
                "domain": dom, "facet_no": fno, "name": facet_names[dom][fno - 1],
                "r_with_full300": round(r_full, 4),
                "r2_with_full300": round(r_full ** 2, 4),
                "r_with_nonoverlapping_rest": round(r_rest, 4),
                "alpha_short": round(a_short, 4), "alpha_full": round(a_full, 4),
                "r_true_score_corrected": round(float(min(r_true, 1.0)), 4),
                "median_abs_pct_error": round(float(np.median(np.abs(dP))), 2),
                "p90_abs_pct_error": round(float(np.percentile(np.abs(dP), 90)), 2),
                "share_abs_pct_error_gt10": round(float((np.abs(dP) > 10).mean()), 4),
                "share_abs_pct_error_gt20": round(float((np.abs(dP) > 20).mean()), 4),
            })
        dPall = sP - ref_P
        # level-band flips under the site's own 45/55-on-percentile rule
        def band(p):
            v = np.trunc(p)
            return np.where(v < 45, 0, np.where(v <= 55, 1, 2))
        flip = (band(sP) != band(ref_P)).mean()

        # domain level: sum the 6 short facet raws
        dom_short_T = np.zeros((len(te), 5)); dom_ref_T = np.zeros((len(te), 5))
        dshortT = np.zeros((len(tr), 5)); dfullT = np.zeros((len(tr), 5))
        for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
            slots = [ipip.facet_slot(dom, f) for f in range(1, 7)]
            dshortT[:, d_i] = srawT[:, slots].sum(axis=1)
            dfullT[:, d_i] = facet_raw[np.ix_(tr, slots)].sum(axis=1)
        dmu_s = np.zeros((4, 5)); dsd_s = np.zeros((4, 5))
        dmu_f = np.zeros((4, 5)); dsd_f = np.zeros((4, 5))
        for gi in range(4):
            m = cohort[tr] == gi
            dmu_s[gi] = dshortT[m].mean(axis=0); dsd_s[gi] = dshortT[m].std(axis=0, ddof=1)
            dmu_f[gi] = dfullT[m].mean(axis=0); dsd_f[gi] = dfullT[m].std(axis=0, ddof=1)
        dsE = np.zeros((len(te), 5)); dfE = np.zeros((len(te), 5))
        for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
            slots = [ipip.facet_slot(dom, f) for f in range(1, 7)]
            dsE[:, d_i] = srawE[:, slots].sum(axis=1)
            dfE[:, d_i] = facet_raw[np.ix_(te, slots)].sum(axis=1)
        dom_short_T = (dsE - dmu_s[cohort[te]]) / dsd_s[cohort[te]] * 10 + 50
        dom_ref_T = (dfE - dmu_f[cohort[te]]) / dsd_f[cohort[te]] * 10 + 50
        dsP = ipip.pct_from_t(dom_short_T); dfP = ipip.pct_from_t(dom_ref_T)
        dom_rows = []
        for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
            r = float(np.corrcoef(dsE[:, d_i], dfE[:, d_i])[0, 1])
            e = dsP[:, d_i] - dfP[:, d_i]
            dom_rows.append({"domain": dom, "r": round(r, 4), "r2": round(r * r, 4),
                             "median_abs_pct_error": round(float(np.median(np.abs(e))), 2),
                             "p90_abs_pct_error": round(float(np.percentile(np.abs(e), 90)), 2),
                             "share_abs_pct_error_gt10": round(float((np.abs(e) > 10).mean()), 4)})

        # ---- (b) ridge from the administered subset to all 30 facet raws ----
        X = items[np.ix_(tr, admin_cols)]
        Xm = X.mean(axis=0); Xs = X.std(axis=0, ddof=1)
        Xz = (X - Xm) / Xs
        Y = facet_raw[np.ix_(tr, np.arange(30))]
        Ym = Y.mean(axis=0)
        G = Xz.T @ Xz
        lam = 1.0 * len(tr) / 1000.0
        W = np.linalg.solve(G + lam * np.eye(G.shape[0]), Xz.T @ (Y - Ym))
        Xe = (items[np.ix_(te, admin_cols)] - Xm) / Xs
        Yhat = Xe @ W + Ym
        ridge_r = np.array([float(np.corrcoef(Yhat[:, s], facet_raw[te, s])[0, 1]) for s in range(30)])
        # ridge predictions renormed on train
        Yhat_tr = Xz @ W + Ym
        rmu = np.zeros((4, 30)); rsd = np.zeros((4, 30))
        for gi in range(4):
            m = cohort[tr] == gi
            rmu[gi] = Yhat_tr[m].mean(axis=0); rsd[gi] = Yhat_tr[m].std(axis=0, ddof=1)
        rP = ipip.pct_from_t((Yhat - rmu[cohort[te]]) / rsd[cohort[te]] * 10 + 50)
        rdP = rP - ref_P

        results[str(k)] = {
            "items_administered": len(admin_cols),
            "minutes_saved_at_6s_per_item": round((300 - len(admin_cols)) * 6 / 60.0, 1),
            "unit_weighted": {
                "r_with_full300_min": round(float(min(p["r_with_full300"] for p in per)), 4),
                "r_with_full300_median": round(float(np.median([p["r_with_full300"] for p in per])), 4),
                "r2_median": round(float(np.median([p["r2_with_full300"] for p in per])), 4),
                "r_nonoverlap_median": round(float(np.median([p["r_with_nonoverlapping_rest"] for p in per])), 4),
                "r_true_corrected_median": round(float(np.median([p["r_true_score_corrected"] for p in per])), 4),
                "alpha_short_median": round(float(np.median([p["alpha_short"] for p in per])), 4),
                "alpha_short_min": round(float(min(p["alpha_short"] for p in per)), 4),
                "median_abs_pct_error_over_all_cells": round(float(np.median(np.abs(dPall))), 2),
                "mean_abs_pct_error_over_all_cells": round(float(np.abs(dPall).mean()), 2),
                "p90_abs_pct_error_over_all_cells": round(float(np.percentile(np.abs(dPall), 90)), 2),
                "share_cells_gt10": round(float((np.abs(dPall) > 10).mean()), 4),
                "share_cells_gt20": round(float((np.abs(dPall) > 20).mean()), 4),
                "level_band_flip_rate": round(float(flip), 4),
                "mean_facets_moving_gt10_of_30": round(float((np.abs(dPall) > 10).sum(axis=1).mean()), 2),
                "per_facet": per,
                "domains": dom_rows,
            },
            "ridge_same_items": {
                "r_median": round(float(np.median(ridge_r)), 4),
                "r_min": round(float(ridge_r.min()), 4),
                "median_abs_pct_error_over_all_cells": round(float(np.median(np.abs(rdP))), 2),
                "share_cells_gt10": round(float((np.abs(rdP) > 10).mean()), 4),
                "gain_over_unit_weighted_r_median": round(
                    float(np.median(ridge_r) - np.median([p["r_with_full300"] for p in per])), 4),
            },
        }
        print("k=%d (%d items, saves ~%.0f min): unit-weighted r med %.3f (min %.3f), "
              "nonoverlap r med %.3f, |dPct| med %.1f p90 %.1f, >10pts %.1f%%, band flip %.1f%%"
              % (k, len(admin_cols), results[str(k)]["minutes_saved_at_6s_per_item"],
                 results[str(k)]["unit_weighted"]["r_with_full300_median"],
                 results[str(k)]["unit_weighted"]["r_with_full300_min"],
                 results[str(k)]["unit_weighted"]["r_nonoverlap_median"],
                 results[str(k)]["unit_weighted"]["median_abs_pct_error_over_all_cells"],
                 results[str(k)]["unit_weighted"]["p90_abs_pct_error_over_all_cells"],
                 100 * results[str(k)]["unit_weighted"]["share_cells_gt10"],
                 100 * results[str(k)]["unit_weighted"]["level_band_flip_rate"]))
        print("      domains: " + ", ".join("%s r=%.3f |dP|med=%.1f" % (d["domain"], d["r"],
                                                                        d["median_abs_pct_error"])
                                             for d in dom_rows))
        print("      ridge on same items: r med %.3f (min %.3f), |dPct| med %.1f, gain %+.4f"
              % (results[str(k)]["ridge_same_items"]["r_median"],
                 results[str(k)]["ridge_same_items"]["r_min"],
                 results[str(k)]["ridge_same_items"]["median_abs_pct_error_over_all_cells"],
                 results[str(k)]["ridge_same_items"]["gain_over_unit_weighted_r_median"]))

    # ---------- reference: what does the FULL form's own unreliability cost? ----------
    # split-half of the 300-item form: odd vs even items within each facet, 5+5.
    half_a = np.zeros((len(te), 30)); half_b = np.zeros((len(te), 30))
    for slot in range(30):
        cols = np.array(ipip.facet_items(slot))
        half_a[:, slot] = items[np.ix_(te, cols[0::2])].sum(axis=1)
        half_b[:, slot] = items[np.ix_(te, cols[1::2])].sum(axis=1)
    hr = np.array([float(np.corrcoef(half_a[:, s], half_b[:, s])[0, 1]) for s in range(30)])
    out["full_form_split_half_r_median"] = round(float(np.median(hr)), 4)
    out["full_form_split_half_spearman_brown_median"] = round(
        float(np.median(2 * hr / (1 + hr))), 4)

    out["results"] = results
    with open(os.path.join(ipip.OUT, "gaps_shortform.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("full-form split-half r median %.3f (Spearman-Brown %.3f)"
          % (out["full_form_split_half_r_median"], out["full_form_split_half_spearman_brown_median"]))


if __name__ == "__main__":
    main()
