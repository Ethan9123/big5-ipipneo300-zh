# -*- coding: utf-8 -*-
"""Decide whether IPIP300-SCORES.csv ships items already reverse-keyed.

Ground truth: the CSV carries its own precomputed domain percentiles, produced by
five-factor-e. Whichever keying reproduces those columns is the correct one.
"""
import io
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
SITE = os.path.join(os.path.dirname(HERE), "site", "index.html")
DOMAIN_ORDER = ["N", "E", "O", "A", "C"]
CUB = [210.335958661391, 16.7379362643389, 0.405936512733332, 0.00270624341822222]


def site_data():
    html = io.open(SITE, encoding="utf-8").read()
    start = html.index("const DATA = ") + len("const DATA = ")
    end = html.index("};\n", start) + 1
    return json.loads(html[start:end])


def cubic(t):
    return CUB[0] - CUB[1] * t + CUB[2] * t ** 2 - CUB[3] * t ** 3


def pct_from_t(t):
    p = cubic(t)
    p = np.where(t < 32, 1.0, p)
    p = np.where(t > 73, 99.0, p)
    return p


def main():
    data = site_data()
    z = np.load(os.path.join(OUT, "scored.npz"))
    items = z["items"].astype(np.int32)
    sex, age, ref_pct = z["sex"], z["age"], z["ref_pct"]
    rev_idx = np.array(sorted(data["reversed"]), dtype=np.int32) - 1

    def domains_for(raw_items):
        facet = np.zeros((len(raw_items), 30), dtype=np.int32)
        for j in range(30):
            facet[:, j] = raw_items[:, [i * 30 + j for i in range(10)]].sum(axis=1)
        dom = np.zeros((len(raw_items), 5), dtype=np.int32)
        for d in range(5):
            dom[:, d] = facet[:, [j for j in range(30) if j % 5 == d]].sum(axis=1)
        return facet, dom

    as_is = items
    reversed_once = items.copy()
    reversed_once[:, rev_idx] = 6 - reversed_once[:, rev_idx]

    groups = {
        "M_lt21": (sex == 1) & (age < 21), "M_gte21": (sex == 1) & (age >= 21),
        "F_lt21": (sex == 2) & (age < 21), "F_gte21": (sex == 2) & (age >= 21),
    }

    for label, arr in [("AS-IS (no reversal applied)", as_is),
                       ("REVERSED (site applies 6-x)", reversed_once)]:
        _facet, dom = domains_for(arr)
        print("\n" + "=" * 74)
        print(label)
        print("=" * 74)
        pred = np.full((len(dom), 5), np.nan)
        for gname, mask in groups.items():
            ns = data["norms"][gname]["ns"]
            for d in range(5):
                t = 10.0 * (dom[mask, d] - ns[1 + d]) / ns[6 + d] + 50.0
                pred[mask, d] = pct_from_t(t)
        known = ~np.isnan(pred[:, 0])
        err = np.abs(pred[known] - ref_pct[known])
        print("   sample SDs by domain:", " ".join(
            "%s=%.1f" % (DOMAIN_ORDER[d], dom[known, d].std(ddof=1)) for d in range(5)))
        print("   vs the CSV's own percentile columns (n=%d):" % known.sum())
        print("     max abs error : %.6f" % err.max())
        print("     mean abs error: %.6f" % err.mean())
        print("     %% within 0.001: %.2f%%" % (100.0 * (err < 1e-3).mean()))


if __name__ == "__main__":
    main()
