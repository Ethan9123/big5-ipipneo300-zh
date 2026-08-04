# -*- coding: utf-8 -*-
"""Draw real respondents from the norm sample, with their TRUE empirical percentiles,
so the patched page can be scored against ground truth rather than against a model."""
import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

N_DRAW = 400
rng = np.random.default_rng(20260802)

z = ipip.load()
items, facet_raw, domain_raw = z["items"], z["facet_raw"], z["domain_raw"]
sex, age = z["sex"], z["age"]
masks = ipip.group_masks(sex, age)

# mid-rank empirical percentile within cohort, per scale -- the same definition the
# tables were built on, recomputed here independently.
def emp_pct(values, cohort_values):
    order = np.sort(cohort_values)
    below = np.searchsorted(order, values, side="left")
    equal = np.searchsorted(order, values, side="right") - below
    return 100.0 * (below + 0.5 * equal) / len(order)


idx = rng.choice(len(items), size=N_DRAW, replace=False)
rows = []
for i in idx:
    cohort = ("M" if sex[i] == 1 else "F") + ("_lt21" if age[i] < 21 else "_gte21")
    m = masks[cohort]
    truth = {}
    for d, key in enumerate(ipip.DOMAIN_ORDER):
        truth[key] = float(emp_pct(np.array([domain_raw[i, d]]), domain_raw[m, d])[0])
        for f in range(1, 7):
            slot = ipip.facet_slot(key, f)
            truth[key + str(f)] = float(emp_pct(np.array([facet_raw[i, slot]]), facet_raw[m, slot])[0])
    rows.append({"sex": int(sex[i]), "age": int(age[i]),
                 "items": [int(v) for v in items[i]], "truth": truth})

io.open(os.path.join(ipip.OUT, "sample_rows.json"), "w", encoding="utf-8").write(
    json.dumps({"n": len(rows), "seed": 20260802,
                "note": "items are AS STORED (already reverse-keyed); truth = mid-rank empirical percentile within the respondent's M/F cohort",
                "rows": rows}, ensure_ascii=False))
print("wrote out/sample_rows.json with %d respondents" % len(rows))
