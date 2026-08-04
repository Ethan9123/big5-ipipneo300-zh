# -*- coding: utf-8 -*-
"""Completeness-critic pass 5: three loose ends.

1. Which facets' printed median is furthest from the promised 50?
2. Keying balance per facet -> acquiescence contamination.  A facet whose 10 items
   are all keyed the same direction cannot cancel a respondent's yea-/nay-saying
   style; a 5/5 facet can.  Measured against an acquiescence index built from the
   CLICKED responses (the CSV ships items pre-recoded, so reverse items are un-recoded
   first, exactly as validity_thresholds.py established).
3. PER_PAGE / page count, for the payload note.

Writes tools/out/gaps_extra.json.
"""
import io
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402


def main():
    data = ipip.site_data()
    html = io.open(ipip.SITE, encoding="utf-8").read()
    per_page = int(re.search(r"PER_PAGE\s*=\s*(\d+)", html).group(1))
    facet_names = {k: [f[0] for f in data["facets"][k]] for k in ipip.DOMAIN_ORDER}

    z = ipip.load()
    items = z["items"].astype(np.float64)
    facet_raw = z["facet_raw"].astype(np.float64)
    domain_raw = z["domain_raw"].astype(np.float64)
    sex, age = z["sex"], z["age"]
    n = len(sex)
    masks = ipip.group_masks(sex, age)

    fT = np.zeros((n, 30)); dT = np.zeros((n, 5))
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
    fP = ipip.pct_from_t(fT); dP = ipip.pct_from_t(dT)

    med = []
    for slot in range(30):
        dom = ipip.DOMAIN_ORDER[slot % 5]; fno = slot // 5 + 1
        med.append({"scale": "%s%d %s" % (dom, fno, facet_names[dom][fno - 1]),
                    "printed_median": round(float(np.median(fP[:, slot])), 2),
                    "bias_vs_50": round(float(np.median(fP[:, slot]) - 50), 2),
                    "share_pinned_1": round(float((fP[:, slot] <= 1).mean()), 4),
                    "share_pinned_99": round(float((fP[:, slot] >= 99).mean()), 4)})
    for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
        med.append({"scale": dom, "printed_median": round(float(np.median(dP[:, d_i])), 2),
                    "bias_vs_50": round(float(np.median(dP[:, d_i]) - 50), 2),
                    "share_pinned_1": round(float((dP[:, d_i] <= 1).mean()), 4),
                    "share_pinned_99": round(float((dP[:, d_i] >= 99).mean()), 4)})
    med.sort(key=lambda r: -abs(r["bias_vs_50"]))

    # ---------- keying balance / acquiescence ----------
    rev = set(int(i) for i in data["reversed"])          # 1-based item ids
    bal = []
    for slot in range(30):
        cols = ipip.facet_items(slot)                    # 0-based
        nrev = sum(1 for c in cols if (c + 1) in rev)
        bal.append(nrev)
    bal = np.array(bal)

    # un-recode the published columns to recover the clicked responses
    clicked = items.copy()
    for c in range(300):
        if (c + 1) in rev:
            clicked[:, c] = 6 - clicked[:, c]
    acq = clicked.mean(axis=1)                            # yea-saying index
    acq_z = (acq - acq.mean()) / acq.std(ddof=1)

    rows = []
    for slot in range(30):
        dom = ipip.DOMAIN_ORDER[slot % 5]; fno = slot // 5 + 1
        r = float(np.corrcoef(facet_raw[:, slot], acq)[0, 1])
        rows.append({"scale": "%s%d %s" % (dom, fno, facet_names[dom][fno - 1]),
                     "n_reverse_keyed_of_10": int(bal[slot]),
                     "r_with_acquiescence": round(r, 4),
                     "pct_pts_at_median_per_1sd_acq": round(
                         float(ipip.pct_from_t(np.array([50 + 10 * r]))[0] - 50), 2)})
    rows.sort(key=lambda x: -abs(x["r_with_acquiescence"]))

    balcount = {int(k): int(v) for k, v in zip(*np.unique(bal, return_counts=True))}
    # domain level
    dom_rows = []
    for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
        slots = [s for s in range(30) if s % 5 == d_i]
        nrev = int(bal[slots].sum())
        r = float(np.corrcoef(domain_raw[:, d_i], acq)[0, 1])
        dom_rows.append({"domain": dom, "n_reverse_keyed_of_60": nrev,
                         "r_with_acquiescence": round(r, 4)})

    out = {"per_page": per_page, "n_pages": 300 // per_page,
           "printed_median_bias": med,
           "keying_balance_counts_n_reverse_of_10": balcount,
           "facet_acquiescence": rows,
           "domain_acquiescence": dom_rows,
           "acq_index_mean": round(float(acq.mean()), 4),
           "acq_index_sd": round(float(acq.std(ddof=1)), 4)}
    with open(os.path.join(ipip.OUT, "gaps_extra.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("PER_PAGE =", per_page, " pages =", 300 // per_page)
    print("printed median furthest from the promised 50:")
    for r in med[:10]:
        print("   %-16s median %5.1f (bias %+5.1f)  pinned@1 %.2f%%  pinned@99 %.2f%%"
              % (r["scale"], r["printed_median"], r["bias_vs_50"],
                 100 * r["share_pinned_1"], 100 * r["share_pinned_99"]))
    print("keying balance across the 30 facets (n reverse-keyed of 10):", balcount)
    print("facets most contaminated by yea-saying:")
    for r in rows[:8]:
        print("   %-16s %2d/10 reversed  r=%+.3f  -> %+.1f printed pts per 1 SD of yea-saying"
              % (r["scale"], r["n_reverse_keyed_of_10"], r["r_with_acquiescence"],
                 r["pct_pts_at_median_per_1sd_acq"]))
    print("least contaminated:")
    for r in rows[-4:]:
        print("   %-16s %2d/10 reversed  r=%+.3f" % (r["scale"], r["n_reverse_keyed_of_10"],
                                                     r["r_with_acquiescence"]))
    print("domains:", [(d["domain"], d["n_reverse_keyed_of_60"], d["r_with_acquiescence"])
                       for d in dom_rows])


if __name__ == "__main__":
    main()
