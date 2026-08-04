# -*- coding: utf-8 -*-
"""Short-form follow-up: (i) pull the alphas/CI of the k=4 short form so it can be
compared like-for-like against the 300-item form's OWN measurement error, and
(ii) test a domains-only short form (k=1,2,3 items per facet, domains reported,
facets suppressed), which is the honest product if facets don't survive.
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
    return k / (k - 1) * (1 - mat.var(axis=0, ddof=1).sum() / mat.sum(axis=1).var(ddof=1))


def main():
    j = json.load(open(os.path.join(ipip.OUT, "gaps_shortform.json"), encoding="utf-8"))
    for k in ["3", "4", "5"]:
        per = j["results"][k]["unit_weighted"]["per_facet"]
        a = np.array([p["alpha_short"] for p in per])
        print("k=%s alpha_short min %.3f med %.3f max %.3f | worst 5 facets by |dPct|: %s"
              % (k, a.min(), np.median(a), a.max(),
                 ", ".join("%s%d %s med%.1f" % (p["domain"], p["facet_no"], p["name"],
                                                p["median_abs_pct_error"])
                           for p in sorted(per, key=lambda x: -x["median_abs_pct_error"])[:5])))
        print("      best 5: %s" % ", ".join(
            "%s%d %s med%.1f" % (p["domain"], p["facet_no"], p["name"], p["median_abs_pct_error"])
            for p in sorted(per, key=lambda x: x["median_abs_pct_error"])[:5]))

    # CI width of the k=4 short form's printed facet percentile vs the full form's
    per4 = j["results"]["4"]["unit_weighted"]["per_facet"]
    a4 = np.array([p["alpha_short"] for p in per4])
    af = np.array([p["alpha_full"] for p in per4])
    ciw_short = ipip.pct_from_t(50 + 1.96 * 10 * np.sqrt(1 - a4)) - \
        ipip.pct_from_t(50 - 1.96 * 10 * np.sqrt(1 - a4))
    ciw_full = ipip.pct_from_t(50 + 1.96 * 10 * np.sqrt(1 - af)) - \
        ipip.pct_from_t(50 - 1.96 * 10 * np.sqrt(1 - af))
    print("CI95 width at p50: full-300 median %.1f pts, short-120 median %.1f pts (delta %.1f)"
          % (np.median(ciw_full), np.median(ciw_short), np.median(ciw_short) - np.median(ciw_full)))

    # ---------- domains-only short form ----------
    z = ipip.load()
    items = z["items"].astype(np.float64)
    facet_raw = z["facet_raw"].astype(np.float64)
    sex, age = z["sex"], z["age"]
    n = len(sex)
    rng = np.random.default_rng(SEED)
    perm = rng.permutation(n)
    tr, te = perm[: n // 2], perm[n // 2:]
    masks = ipip.group_masks(sex, age)
    cohort = np.full(n, -1)
    for gi, g in enumerate(["M_lt21", "M_gte21", "F_lt21", "F_gte21"]):
        cohort[masks[g]] = gi

    dom_full = np.zeros((n, 5))
    for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
        slots = [ipip.facet_slot(dom, f) for f in range(1, 7)]
        dom_full[:, d_i] = facet_raw[:, slots].sum(axis=1)
    fmu = np.zeros((4, 5)); fsd = np.zeros((4, 5))
    for gi in range(4):
        m = tr[cohort[tr] == gi]
        fmu[gi] = dom_full[m].mean(axis=0); fsd[gi] = dom_full[m].std(axis=0, ddof=1)
    refP = ipip.pct_from_t((dom_full[te] - fmu[cohort[te]]) / fsd[cohort[te]] * 10 + 50)

    # item selection for DOMAIN prediction: item-rest correlation against the domain total
    rows = []
    for k in [1, 2, 3, 4]:
        admin = []
        for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
            slots = [ipip.facet_slot(dom, f) for f in range(1, 7)]
            for slot in slots:
                cols = np.array(ipip.facet_items(slot))
                sub = items[np.ix_(tr, cols)]
                dtot = dom_full[tr, d_i]
                r = np.array([np.corrcoef(sub[:, jj], dtot - sub[:, jj])[0, 1] for jj in range(10)])
                admin += cols[np.argsort(-r)[:k]].tolist()
        admin = sorted(admin)
        sT = np.zeros((len(tr), 5)); sE = np.zeros((len(te), 5))
        for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
            slots = [ipip.facet_slot(dom, f) for f in range(1, 7)]
            cols = sorted(c for slot in slots for c in ipip.facet_items(slot) if c in set(admin))
            sT[:, d_i] = items[np.ix_(tr, cols)].sum(axis=1)
            sE[:, d_i] = items[np.ix_(te, cols)].sum(axis=1)
        smu = np.zeros((4, 5)); ssd = np.zeros((4, 5))
        for gi in range(4):
            m = cohort[tr] == gi
            smu[gi] = sT[m].mean(axis=0); ssd[gi] = sT[m].std(axis=0, ddof=1)
        sP = ipip.pct_from_t((sE - smu[cohort[te]]) / ssd[cohort[te]] * 10 + 50)
        e = np.abs(sP - refP)
        rr = [float(np.corrcoef(sE[:, d], dom_full[te, d])[0, 1]) for d in range(5)]
        aa = []
        for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
            slots = [ipip.facet_slot(dom, f) for f in range(1, 7)]
            cols = sorted(c for slot in slots for c in ipip.facet_items(slot) if c in set(admin))
            aa.append(float(alpha_of(items[np.ix_(te, cols)])))
        rows.append({"items_per_facet": k, "n_items": len(admin),
                     "domain_r_min": round(min(rr), 4), "domain_r_median": round(float(np.median(rr)), 4),
                     "alpha_min": round(min(aa), 4), "alpha_median": round(float(np.median(aa)), 4),
                     "median_abs_pct_error": round(float(np.median(e)), 2),
                     "p90_abs_pct_error": round(float(np.percentile(e, 90)), 2),
                     "share_gt10": round(float((e > 10).mean()), 4)})
        print("DOMAINS-ONLY k=%d (%d items): r %.3f..%.3f, alpha %.3f..%.3f, |dPct| med %.1f p90 %.1f, >10 %.1f%%"
              % (k, len(admin), min(rr), max(rr), min(aa), max(aa),
                 np.median(e), np.percentile(e, 90), 100 * (e > 10).mean()))

    json.dump({"domains_only": rows,
               "ci95_width_at_p50_full300_median": round(float(np.median(ciw_full)), 2),
               "ci95_width_at_p50_short120_median": round(float(np.median(ciw_short)), 2),
               "alpha_short120_facets_min": round(float(a4.min()), 4),
               "alpha_short120_facets_median": round(float(np.median(a4)), 4)},
              open(os.path.join(ipip.OUT, "gaps_shortform2.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
