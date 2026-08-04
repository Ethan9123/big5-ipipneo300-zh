# -*- coding: utf-8 -*-
"""Verify the facet column order of ref_facet_pct, and reproduce all 30 facet
percentiles from raw scores + shipped norms.

The CSV's facet_* columns are the ground truth produced by five-factor-e.  If the site's
facet-slot mapping and the norm-vector offsets are right, we must reproduce them exactly.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

# order of the facet_* columns as they appear in the CSV
CSV_FACET_ORDER = (
    [("O", i) for i in range(1, 7)] + [("C", i) for i in range(1, 7)] +
    [("E", i) for i in range(1, 7)] + [("A", i) for i in range(1, 7)] +
    [("N", i) for i in range(1, 7)]
)


def main():
    z = ipip.load()
    data = ipip.site_data()
    facet_raw, sex, age = z["facet_raw"], z["sex"], z["age"]
    ref = z["ref_facet_pct"]
    masks = ipip.group_masks(sex, age)

    pred = np.full(ref.shape, np.nan)
    for g in ("M_lt21", "M_gte21", "F_lt21", "F_gte21"):
        ns, mask = data["norms"][g]["ns"], masks[g]
        for col, (dom, fno) in enumerate(CSV_FACET_ORDER):
            slot = ipip.facet_slot(dom, fno)
            mo, so = ipip.FACET_OFFSET[dom]
            t = 50.0 + 10.0 * (facet_raw[mask, slot] - ns[fno + mo]) / ns[fno + so]
            pred[mask, col] = ipip.pct_from_t(t)

    ok = ~np.isnan(pred[:, 0])
    err = np.abs(pred[ok] - ref[ok])
    print("rows checked: %d   values: %d" % (ok.sum(), err.size))
    print("max abs error : %.10f" % err.max())
    print("mean abs error: %.10f" % err.mean())
    print("cells within 1e-9: %.4f%%" % (100.0 * (err < 1e-9).mean()))

    print("\nper-facet max error:")
    per = err.max(axis=0)
    for col, (dom, fno) in enumerate(CSV_FACET_ORDER):
        name = data["facets"][dom][fno - 1]
        flag = "" if per[col] < 1e-9 else "   <-- MISMATCH"
        print("  %s%d %-24s %-12s  %.10f%s" % (dom, fno, name[1], name[0], per[col], flag))

    if err.max() < 1e-9:
        print("\nCONFIRMED: facet column order is O1-6, C1-6, E1-6, A1-6, N1-6,")
        print("and the site's facet-slot mapping + norm offsets reproduce five-factor-e exactly.")
    else:
        print("\nFACET ORDER OR MAPPING IS WRONG -- do not trust downstream facet analysis.")
        sys.exit(1)


if __name__ == "__main__":
    main()
