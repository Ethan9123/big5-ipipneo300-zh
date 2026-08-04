# -*- coding: utf-8 -*-
"""Clean acquiescence check.

The crude index (mean of all 300 clicked responses) is trait-loaded, so it is
replaced by a balanced-set index: the 15 facets that are keyed exactly 5 forward /
5 reverse contribute 150 items in which content cancels by construction.  For each
target facet the index is recomputed with that facet's own items removed, so the
correlation cannot be inflated by part-whole overlap.

Writes tools/out/gaps_acq.json.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402


def main():
    data = ipip.site_data()
    facet_names = {k: [f[0] for f in data["facets"][k]] for k in ipip.DOMAIN_ORDER}
    z = ipip.load()
    items = z["items"].astype(np.float64)
    facet_raw = z["facet_raw"].astype(np.float64)
    rev = set(int(i) for i in data["reversed"])

    clicked = items.copy()
    for c in range(300):
        if (c + 1) in rev:
            clicked[:, c] = 6 - clicked[:, c]

    nrev = np.array([sum(1 for c in ipip.facet_items(s) if (c + 1) in rev) for s in range(30)])
    balanced = [s for s in range(30) if nrev[s] == 5]
    bal_cols = [c for s in balanced for c in ipip.facet_items(s)]
    print("balanced facets (5/5): %d -> %d items" % (len(balanced), len(bal_cols)))

    rows = []
    for slot in range(30):
        own = set(ipip.facet_items(slot))
        cols = [c for c in bal_cols if c not in own]
        idx = clicked[:, cols].mean(axis=1)
        r = float(np.corrcoef(facet_raw[:, slot], idx)[0, 1])
        dom = ipip.DOMAIN_ORDER[slot % 5]; fno = slot // 5 + 1
        rows.append({"scale": "%s%d %s" % (dom, fno, facet_names[dom][fno - 1]),
                     "n_reverse_of_10": int(nrev[slot]),
                     "imbalance": int(abs(nrev[slot] - 5)),
                     "index_items_used": len(cols),
                     "r_with_balanced_acq_index": round(r, 4),
                     "printed_pct_pts_at_median_per_1sd": round(
                         float(ipip.pct_from_t(np.array([50 + 10 * r]))[0] - 50), 2)})
    imb = np.array([x["imbalance"] for x in rows], dtype=float)
    rr = np.array([abs(x["r_with_balanced_acq_index"]) for x in rows])
    sgn = np.array([x["r_with_balanced_acq_index"] for x in rows])
    dev = np.array([5 - x["n_reverse_of_10"] for x in rows], dtype=float)
    out = {
        "n_balanced_facets": len(balanced),
        "corr_imbalance_vs_abs_r": round(float(np.corrcoef(imb, rr)[0, 1]), 4),
        "corr_signed_keying_dev_vs_r": round(float(np.corrcoef(dev, sgn)[0, 1]), 4),
        "mean_abs_r_balanced_facets": round(float(rr[imb == 0].mean()), 4),
        "mean_abs_r_imbalanced_facets": round(float(rr[imb > 0].mean()), 4),
        "max_abs_r": round(float(rr.max()), 4),
        "facets": sorted(rows, key=lambda x: -abs(x["r_with_balanced_acq_index"])),
        "acq_index_sd_in_response_units": round(
            float(clicked[:, bal_cols].mean(axis=1).std(ddof=1)), 4),
    }
    # domain-level
    dom_rows = []
    for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
        slots = [s for s in range(30) if s % 5 == d_i]
        own = set(c for s in slots for c in ipip.facet_items(s))
        cols = [c for c in bal_cols if c not in own]
        idx = clicked[:, cols].mean(axis=1)
        draw = facet_raw[:, slots].sum(axis=1)
        r = float(np.corrcoef(draw, idx)[0, 1])
        dom_rows.append({"domain": dom, "n_reverse_of_60": int(nrev[slots].sum()),
                         "r_with_balanced_acq_index": round(r, 4)})
    out["domains"] = dom_rows

    with open(os.path.join(ipip.OUT, "gaps_acq.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("corr(|keying imbalance|, |r with style index|) = %.3f" % out["corr_imbalance_vs_abs_r"])
    print("corr(signed keying deviation 5-nrev, signed r) = %.3f" % out["corr_signed_keying_dev_vs_r"])
    print("mean |r|: balanced facets %.3f, imbalanced facets %.3f, max %.3f"
          % (out["mean_abs_r_balanced_facets"], out["mean_abs_r_imbalanced_facets"], out["max_abs_r"]))
    print("acq index SD = %.3f response-scale points" % out["acq_index_sd_in_response_units"])
    for r in out["facets"][:10]:
        print("   %-16s %d/10 rev (imb %d)  r=%+.3f -> %+.1f printed pts per 1 SD"
              % (r["scale"], r["n_reverse_of_10"], r["imbalance"],
                 r["r_with_balanced_acq_index"], r["printed_pct_pts_at_median_per_1sd"]))
    print("domains:", [(d["domain"], d["n_reverse_of_60"], d["r_with_balanced_acq_index"])
                       for d in dom_rows])


if __name__ == "__main__":
    main()
