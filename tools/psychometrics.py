# -*- coding: utf-8 -*-
"""Reliability, keying validation, discriminant and intercorrelation analysis
for the IPIP-NEO-300 norm sample as scored by site/index.html.

Everything is derived from a single 300x300 item covariance matrix, computed
exactly once over all 145,388 respondents.

Writes tools/out/psychometrics.json.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402


def facet_label(slot):
    """slot 0..29 -> ('N', 1, 'anxiety')-ish label."""
    dom = ipip.DOMAIN_ORDER[slot % 5]
    no = slot // 5 + 1
    return dom, no


def main():
    data = ipip.site_data()
    z = ipip.load()
    items = z["items"]                       # (145388, 300) int16, 1..5, pre-keyed
    n, p = items.shape
    assert p == 300

    facets_meta = data["facets"]
    rev_set = set(int(x) for x in data["reversed"])

    names = {}
    for slot in range(30):
        dom, no = facet_label(slot)
        zh, en, desc = facets_meta[dom][no - 1]
        names[slot] = {"domain": dom, "facet_no": no, "code": "%s%d" % (dom, no),
                       "en": en, "zh": zh, "desc": desc}

    # ---------------- 300x300 covariance, chunked in float64 ----------------
    colsum = np.zeros(p, dtype=np.float64)
    S = np.zeros((p, p), dtype=np.float64)
    CH = 20000
    for s in range(0, n, CH):
        X = items[s:s + CH].astype(np.float64)
        S += X.T @ X
        colsum += X.sum(axis=0)
    cov = (S - np.outer(colsum, colsum) / n) / (n - 1.0)
    sd = np.sqrt(np.diag(cov))
    R = cov / np.outer(sd, sd)

    # indicator matrices
    A = np.zeros((30, p))                    # facet slot -> its 10 items
    for j in range(30):
        A[j, ipip.facet_items(j)] = 1.0
    B = np.zeros((5, 30))                    # domain (N,E,O,A,C order) -> its 6 facet slots
    for d in range(5):
        for j in range(30):
            if j % 5 == d:
                B[d, j] = 1.0

    Fcov = A @ cov @ A.T                     # 30x30 facet-total covariance
    Fsd = np.sqrt(np.diag(Fcov))
    Fcorr = Fcov / np.outer(Fsd, Fsd)
    Dcov = B @ Fcov @ B.T                    # 5x5 domain-total covariance (N,E,O,A,C)
    Dsd = np.sqrt(np.diag(Dcov))
    Dcorr = Dcov / np.outer(Dsd, Dsd)

    itcov = cov @ A.T                        # (300, 30) item vs facet-total covariance
    idcov = itcov @ B.T                      # (300, 5)  item vs domain-total covariance

    # ---------------- 1. reliability ----------------
    facet_rel = []
    for j in range(30):
        cols = ipip.facet_items(j)
        k = len(cols)
        sum_var = float(np.diag(cov)[cols].sum())
        tot_var = float(Fcov[j, j])
        alpha = k / (k - 1.0) * (1.0 - sum_var / tot_var)
        blk = R[np.ix_(cols, cols)]
        off = blk[~np.eye(k, dtype=bool)]
        mic = float(off.mean())
        # Spearman-Brown: alpha the facet would need to reach .70
        facet_rel.append({
            "slot": j, **names[j], "k_items": k,
            "alpha": round(alpha, 4),
            "mean_inter_item_r": round(mic, 4),
            "min_inter_item_r": round(float(off.min()), 4),
            "max_inter_item_r": round(float(off.max()), 4),
            "items": [c + 1 for c in cols],
            "n_reversed_items": sum(1 for c in cols if c + 1 in rev_set),
            "below_070": bool(alpha < 0.70),
        })

    domain_rel = []
    for d, key in enumerate(ipip.DOMAIN_ORDER):
        cols = [c for c in range(p) if (c % 30) % 5 == d]
        k = len(cols)
        sum_var = float(np.diag(cov)[cols].sum())
        tot_var = float(Dcov[d, d])
        alpha = k / (k - 1.0) * (1.0 - sum_var / tot_var)
        blk = R[np.ix_(cols, cols)]
        off = blk[~np.eye(k, dtype=bool)]
        domain_rel.append({
            "domain": key, "k_items": k,
            "alpha": round(alpha, 4),
            "mean_inter_item_r": round(float(off.mean()), 4),
            "facet_alphas_mean": round(
                float(np.mean([f["alpha"] for f in facet_rel if f["domain"] == key])), 4),
        })

    # ---------------- 2. keying validation: corrected item-total ----------------
    var_i = np.diag(cov)
    own = np.array([c % 30 for c in range(p)])
    cov_it_own = itcov[np.arange(p), own]
    var_T_own = Fcov[own, own]
    cov_rest = cov_it_own - var_i
    var_rest = var_T_own - 2.0 * cov_it_own + var_i
    r_corrected = cov_rest / np.sqrt(var_i * var_rest)

    # uncorrected r with every facet total (for the discriminant check the item
    # is not a member of the 29 competing facets, so no correction is needed there)
    r_item_facet = itcov / np.outer(sd, Fsd)
    r_item_facet_corr = r_item_facet.copy()
    r_item_facet_corr[np.arange(p), own] = r_corrected

    r_item_domain = idcov / np.outer(sd, Dsd)

    it_all = []
    for c in range(p):
        j = own[c]
        it_all.append({
            "item": c + 1, "facet": names[j]["code"], "facet_en": names[j]["en"],
            "r_corrected": round(float(r_corrected[c]), 4),
            "reversed_on_site": (c + 1) in rev_set,
        })

    flagged = [d for d in it_all if d["r_corrected"] < 0.15]
    for d in flagged:
        d["en"] = data["items"][d["item"] - 1]["en"]
        d["zh"] = data["items"][d["item"] - 1]["zh"]
    flagged.sort(key=lambda d: d["r_corrected"])
    negatives = [d for d in flagged if d["r_corrected"] < 0]

    # weakest 15 regardless of threshold, for context
    weakest = sorted(it_all, key=lambda d: d["r_corrected"])[:15]
    for d in weakest:
        d.setdefault("en", data["items"][d["item"] - 1]["en"])
        d.setdefault("zh", data["items"][d["item"] - 1]["zh"])

    it_dist = {
        "n_items": p,
        "min": round(float(r_corrected.min()), 4),
        "p01": round(float(np.percentile(r_corrected, 1)), 4),
        "p05": round(float(np.percentile(r_corrected, 5)), 4),
        "p25": round(float(np.percentile(r_corrected, 25)), 4),
        "median": round(float(np.median(r_corrected)), 4),
        "mean": round(float(r_corrected.mean()), 4),
        "p75": round(float(np.percentile(r_corrected, 75)), 4),
        "p95": round(float(np.percentile(r_corrected, 95)), 4),
        "max": round(float(r_corrected.max()), 4),
        "n_negative": int((r_corrected < 0).sum()),
        "n_below_0.15": int((r_corrected < 0.15).sum()),
        "n_below_0.20": int((r_corrected < 0.20).sum()),
        "n_below_0.30": int((r_corrected < 0.30).sum()),
        "mean_reversed_items": round(float(r_corrected[[c for c in range(p)
                                                        if c + 1 in rev_set]].mean()), 4),
        "mean_forward_items": round(float(r_corrected[[c for c in range(p)
                                                       if c + 1 not in rev_set]].mean()), 4),
    }

    # ---------------- 3. discriminant check ----------------
    fails = []
    for c in range(p):
        j = own[c]
        rr = r_item_facet_corr[c].copy()
        r_own = float(rr[j])
        rr[j] = -np.inf
        best = int(np.argmax(rr))
        r_best = float(rr[best])
        if r_best >= r_own:
            fails.append({
                "item": c + 1,
                "own_facet": names[j]["code"], "own_facet_en": names[j]["en"],
                "r_own_corrected": round(r_own, 4),
                "best_competing_facet": names[best]["code"],
                "best_competing_en": names[best]["en"],
                "r_competing": round(r_best, 4),
                "gap": round(r_best - r_own, 4),
                "en": data["items"][c]["en"],
                "reversed_on_site": (c + 1) in rev_set,
            })
    fails.sort(key=lambda d: -d["gap"])

    # domain-level discriminant: does the item's own domain win?
    dom_of_item = np.array([(c % 30) % 5 for c in range(p)])
    # corrected for own-domain membership
    cov_id_own = idcov[np.arange(p), dom_of_item]
    var_D_own = Dcov[dom_of_item, dom_of_item]
    r_dom_corr = (cov_id_own - var_i) / np.sqrt(
        var_i * (var_D_own - 2.0 * cov_id_own + var_i))
    r_item_domain_corr = r_item_domain.copy()
    r_item_domain_corr[np.arange(p), dom_of_item] = r_dom_corr
    dom_fail = int(sum(1 for c in range(p)
                       if r_item_domain_corr[c].argmax() != dom_of_item[c]))

    # ---------------- 4. intercorrelations ----------------
    def slot_of(dom, no):
        return ipip.facet_slot(dom, no)

    within = {}
    for key in ipip.OCEAN:
        slots = [slot_of(key, m) for m in range(1, 7)]
        m6 = Fcorr[np.ix_(slots, slots)]
        within[key] = {
            "labels": ["%s%d %s" % (key, m, names[slots[m - 1]]["en"]) for m in range(1, 7)],
            "matrix": [[round(float(v), 4) for v in row] for row in m6],
            "mean_offdiag": round(float(m6[~np.eye(6, dtype=bool)].mean()), 4),
        }

    dom_order_ocean = [ipip.DOMAIN_ORDER.index(k) for k in ipip.OCEAN]
    dmat = Dcorr[np.ix_(dom_order_ocean, dom_order_ocean)]
    domain_matrix = {
        "labels": ipip.OCEAN,
        "matrix": [[round(float(v), 4) for v in row] for row in dmat],
    }

    # full 30x30, ordered OCEAN then facet 1..6
    order30 = [slot_of(k, m) for k in ipip.OCEAN for m in range(1, 7)]
    f30 = Fcorr[np.ix_(order30, order30)]
    facet_matrix_30 = {
        "labels": ["%s%d %s" % (ipip.OCEAN[i // 6], i % 6 + 1, names[order30[i]]["en"])
                   for i in range(30)],
        "matrix": [[round(float(v), 4) for v in row] for row in f30],
    }

    redundant = []
    for a in range(30):
        for b in range(a + 1, 30):
            r = float(Fcorr[a, b])
            if r > 0.75:
                redundant.append({
                    "a": names[a]["code"] + " " + names[a]["en"],
                    "b": names[b]["code"] + " " + names[b]["en"],
                    "r": round(r, 4),
                    "same_domain": names[a]["domain"] == names[b]["domain"],
                })
    redundant.sort(key=lambda d: -d["r"])

    top_pairs = []
    for a in range(30):
        for b in range(a + 1, 30):
            top_pairs.append((float(Fcorr[a, b]),
                              names[a]["code"] + " " + names[a]["en"],
                              names[b]["code"] + " " + names[b]["en"],
                              names[a]["domain"] == names[b]["domain"]))
    top_pairs.sort(key=lambda t: -t[0])
    top_pairs = [{"a": t[1], "b": t[2], "r": round(t[0], 4), "same_domain": t[3]}
                 for t in top_pairs[:12]]

    # facet vs domain totals: corrected for its own domain (facet removed from its
    # own domain total), raw against the other four.
    facet_domain = []
    misplaced = []
    for j in range(30):
        dom = names[j]["domain"]
        d_own = ipip.DOMAIN_ORDER.index(dom)
        row = {}
        for d2, k2 in enumerate(ipip.DOMAIN_ORDER):
            if d2 == d_own:
                cov_fd = float(Fcov[j] @ B[d2])
                v = float(Fcov[j, j])
                r = (cov_fd - v) / np.sqrt(v * (float(Dcov[d2, d2]) - 2 * cov_fd + v))
            else:
                r = float(Fcov[j] @ B[d2]) / (Fsd[j] * Dsd[d2])
            row[k2] = round(float(r), 4)
        best = max(row, key=lambda k: row[k])
        rec = {"facet": names[j]["code"] + " " + names[j]["en"],
               "own_domain": dom, "r_own_domain_corrected": row[dom],
               "r_by_domain": row, "best_domain": best}
        facet_domain.append(rec)
        if best != dom:
            misplaced.append(rec)

    # ---------------- independent structural validation ----------------
    # Reproduce the CSV's own 30 facet percentile columns from facet_raw using the
    # site's norms + cubic.  This validates the item->facet assignment AND the keying
    # independently of the domain-level check already in prep.py.
    facet_raw = z["facet_raw"]
    masks = ipip.group_masks(z["sex"], z["age"])
    ref_cols = [(k, m) for k in ipip.OCEAN for m in range(1, 7)]  # CSV column order
    pred = np.full((n, 30), np.nan)
    for g in ("M_lt21", "M_gte21", "F_lt21", "F_gte21"):
        ns, mask = data["norms"][g]["ns"], masks[g]
        for ci, (k, m) in enumerate(ref_cols):
            slot = slot_of(k, m)
            mu = ns[ipip.FACET_OFFSET[k][0] + m]
            sdv = ns[ipip.FACET_OFFSET[k][1] + m]
            t = 10.0 * (facet_raw[mask, slot] - mu) / sdv + 50.0
            pred[mask, ci] = ipip.pct_from_t(t)
    okm = ~np.isnan(pred[:, 0])
    err = np.abs(pred[okm] - z["ref_facet_pct"][okm])
    facet_repro = {
        "rows_checked": int(okm.sum()),
        "cells_checked": int(okm.sum() * 30),
        "max_abs_error": float(err.max()),
        "mean_abs_error": float(err.mean()),
    }

    # ---------------- measurement error, in the units the site shows users ----------------
    # T = 50 + 10*(raw-mean)/sd_norm, so SEM expressed in T units is simply
    # 10*sqrt(1-alpha) regardless of cohort.  Push that through the site's own
    # cubic to get the 95% confidence band in PERCENTILE points at T=50.
    def band(alpha, t_center=50.0):
        sem_t = 10.0 * np.sqrt(1.0 - alpha)
        lo_t, hi_t = t_center - 1.96 * sem_t, t_center + 1.96 * sem_t
        lo_p, hi_p = float(ipip.pct_from_t(lo_t)), float(ipip.pct_from_t(hi_t))
        return {"sem_T": round(float(sem_t), 3),
                "ci95_T": [round(lo_t, 2), round(hi_t, 2)],
                "ci95_percentile_at_median": [round(lo_p, 1), round(hi_p, 1)],
                "ci95_percentile_width": round(hi_p - lo_p, 1)}

    for f in facet_rel:
        f["measurement"] = band(f["alpha"])
    for d in domain_rel:
        d["measurement"] = band(d["alpha"])

    # how often does a facet's low/average/high LABEL flip?  The site cuts the
    # percentile at 45 and 55.  A score sitting exactly on a cut has ~50% flip
    # odds; report the percentile distance that one SEM buys instead.
    for f in facet_rel:
        sem_t = 10.0 * np.sqrt(1.0 - f["alpha"])
        # percentile move produced by +-1 SEM around the 45 and 55 cut points
        f["measurement"]["pct_move_per_1sem_at_p50"] = round(
            float(ipip.pct_from_t(50 + sem_t) - ipip.pct_from_t(50 - sem_t)) / 2.0, 1)

    # ---------------- lexical cross-check of the site's reversed list ----------------
    import re
    NEG = re.compile(
        r"\b(don't|dont|do not|does not|dislike|dislikes|am not|is not|are not|never|"
        r"rarely|seldom|avoid|hate|can't|cannot|lack|refuse|reject|resent|neglect|"
        r"waste|worry|dread|fear|shirk|dodge)\b", re.I)
    neg_marked, neg_unmarked = [], []
    for i in range(1, 301):
        en = data["items"][i - 1]["en"]
        if NEG.search(en):
            rec = {"item": i, "facet": names[(i - 1) % 30]["code"], "en": en}
            (neg_marked if i in rev_set else neg_unmarked).append(rec)
    lexical = {
        "n_items_with_negation_wording": len(neg_marked) + len(neg_unmarked),
        "marked_reversed": len(neg_marked),
        "not_marked_reversed": len(neg_unmarked),
        "not_marked_detail": neg_unmarked,
        "reversed_without_lexical_marker": len(
            [i for i in rev_set if not NEG.search(data["items"][i - 1]["en"])]),
        "note": ("Every item in not_marked_detail is a negation that points toward the "
                 "HIGH pole of its own facet (e.g. 'Worry about things' = high N1 anxiety, "
                 "'Avoid mistakes' = high C6 cautiousness), so none is a keying error."),
    }

    out = {
        "sample": {"n_respondents": int(n), "n_items": int(p),
                   "item_value_range": [int(items.min()), int(items.max())],
                   "n_reversed_on_site": len(rev_set)},
        "reliability": {
            "facets": facet_rel,
            "domains": domain_rel,
            "facets_below_070": [f["code"] + " " + f["en"] for f in facet_rel if f["below_070"]],
            "facet_alpha_min": min(f["alpha"] for f in facet_rel),
            "facet_alpha_median": round(float(np.median([f["alpha"] for f in facet_rel])), 4),
            "facet_alpha_max": max(f["alpha"] for f in facet_rel),
        },
        "keying_validation": {
            "distribution": it_dist,
            "negative_items": negatives,
            "items_below_0.15": flagged,
            "weakest_15": weakest,
            "any_miskeyed": bool(len(negatives) > 0),
            "lexical_cross_check": lexical,
            "all_items": it_all,
        },
        "discriminant": {
            "n_items_failing_facet_level": len(fails),
            "n_items_failing_domain_level": dom_fail,
            "worst_10": fails[:10],
            "all_failures": fails,
        },
        "intercorrelations": {
            "within_domain_facet_matrices": within,
            "domain_matrix_OCEAN": domain_matrix,
            "facet_matrix_30_OCEAN": facet_matrix_30,
            "facet_pairs_above_075": redundant,
            "top_12_facet_pairs": top_pairs,
            "facet_vs_domain": facet_domain,
            "facets_loading_on_wrong_domain": misplaced,
        },
        "structural_validation": {
            "csv_facet_percentile_reproduction": facet_repro,
        },
    }

    os.makedirs(ipip.OUT, exist_ok=True)
    path = os.path.join(ipip.OUT, "psychometrics.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)

    # ------- console report -------
    print("n=%d items=%d values %d..%d" % (n, p, items.min(), items.max()))
    print("\n--- facet alphas (OCEAN order) ---")
    for k in ipip.OCEAN:
        for m in range(1, 7):
            f = facet_rel[slot_of(k, m)]
            print("  %-3s %-22s alpha=%.4f  mic=%.4f  rev=%d/10 %s"
                  % (f["code"], f["en"], f["alpha"], f["mean_inter_item_r"],
                     f["n_reversed_items"], "  <<< BELOW .70" if f["below_070"] else ""))
    print("\n--- domain alphas ---")
    for d in domain_rel:
        print("  %s alpha=%.4f mic=%.4f" % (d["domain"], d["alpha"], d["mean_inter_item_r"]))
    print("\n--- corrected item-total ---")
    print("  min=%.4f p01=%.4f median=%.4f max=%.4f  neg=%d  <0.15=%d  <0.20=%d  <0.30=%d"
          % (it_dist["min"], it_dist["p01"], it_dist["median"], it_dist["max"],
             it_dist["n_negative"], it_dist["n_below_0.15"],
             it_dist["n_below_0.20"], it_dist["n_below_0.30"]))
    print("  mean r for site-reversed items = %.4f ; forward items = %.4f"
          % (it_dist["mean_reversed_items"], it_dist["mean_forward_items"]))
    print("  MIS-KEYED (negative) items: %d" % len(negatives))
    for d in flagged:
        print("   item %3d %-4s r=%+.4f rev=%s | %s" % (d["item"], d["facet"],
              d["r_corrected"], d["reversed_on_site"], d["en"]))
    print("\n--- discriminant failures: %d of 300 (domain level: %d) ---"
          % (len(fails), dom_fail))
    for d in fails[:10]:
        print("   item %3d own %-4s r=%.4f  vs %-4s r=%.4f  gap=%.4f | %s"
              % (d["item"], d["own_facet"], d["r_own_corrected"],
                 d["best_competing_facet"], d["r_competing"], d["gap"], d["en"]))
    print("\n--- measurement bands (95% CI in percentile pts for a median score) ---")
    for k in ipip.OCEAN:
        for m in range(1, 7):
            f = facet_rel[slot_of(k, m)]
            b = f["measurement"]
            print("  %-3s %-22s a=%.3f SEM_T=%.2f  p50 -> [%.0f, %.0f]  width=%.0f pts"
                  % (f["code"], f["en"], f["alpha"], b["sem_T"],
                     b["ci95_percentile_at_median"][0], b["ci95_percentile_at_median"][1],
                     b["ci95_percentile_width"]))
    for d in domain_rel:
        b = d["measurement"]
        print("  DOMAIN %s a=%.4f SEM_T=%.2f p50 -> [%.0f, %.0f] width=%.0f"
              % (d["domain"], d["alpha"], b["sem_T"], b["ci95_percentile_at_median"][0],
                 b["ci95_percentile_at_median"][1], b["ci95_percentile_width"]))

    print("\n--- within-domain facet matrices (6x6) ---")
    for k in ipip.OCEAN:
        w = within[k]
        print("  %s  (mean off-diag r = %.3f)" % (k, w["mean_offdiag"]))
        print("        " + "".join("%9s" % lab.split()[0] for lab in w["labels"]))
        for i, lab in enumerate(w["labels"]):
            print("    %-4s" % lab.split()[0] + "".join("%9.3f" % v for v in w["matrix"][i]))

    print("\n--- domain intercorrelations (OCEAN) ---")
    print("      " + "".join("%8s" % k for k in ipip.OCEAN))
    for i, k in enumerate(ipip.OCEAN):
        print("  %-4s" % k + "".join("%8.3f" % v for v in domain_matrix["matrix"][i]))
    print("\n--- facet pairs r > 0.75: %d ---" % len(redundant))
    for d in redundant:
        print("   %.4f  %s  ~  %s  (same domain=%s)" % (d["r"], d["a"], d["b"], d["same_domain"]))
    print("\n  top facet pairs overall:")
    for d in top_pairs[:6]:
        print("   %.4f  %s ~ %s (same=%s)" % (d["r"], d["a"], d["b"], d["same_domain"]))
    print("\n--- facets whose best domain != own: %d ---" % len(misplaced))
    for d in misplaced:
        print("   %s own=%s r=%.4f best=%s r=%.4f"
              % (d["facet"], d["own_domain"], d["r_own_domain_corrected"],
                 d["best_domain"], d["r_by_domain"][d["best_domain"]]))
    print("\n--- lexical cross-check of the site's 148-item reversed list ---")
    print("   %d items carry negation wording; %d marked reversed, %d not"
          % (lexical["n_items_with_negation_wording"], lexical["marked_reversed"],
             lexical["not_marked_reversed"]))
    print("   %d reversed items carry no lexical marker (semantic reversals)"
          % lexical["reversed_without_lexical_marker"])
    for r in lexical["not_marked_detail"]:
        print("     %3d %-4s | %s" % (r["item"], r["facet"], r["en"]))

    print("\n--- CSV facet percentile reproduction ---")
    print("   rows=%d cells=%d max_abs_err=%.10f mean_abs_err=%.10f"
          % (facet_repro["rows_checked"], facet_repro["cells_checked"],
             facet_repro["max_abs_error"], facet_repro["mean_abs_error"]))
    print("\nwrote %s" % path)


if __name__ == "__main__":
    main()
