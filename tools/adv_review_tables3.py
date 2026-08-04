# -*- coding: utf-8 -*-
"""ADVERSARIAL review part 3: provenance of the encoding-stats row, empty-cell
split, exact-zero cells, and the 688-level ladder comparison."""
import io, json, math, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip

J = json.load(io.open(os.path.join(ipip.OUT, "pct_tables.json"), encoding="utf-8"))
cohorts, scales = J["cohorts"], J["scales"]
z = ipip.load()
masks = ipip.group_masks(z["sex"], z["age"])
facet_raw, domain_raw = z["facet_raw"], z["domain_raw"]

print("=" * 78)
print("E. EMPTY-CELL SPLIT domain vs facet (claim: 952 of 960 in domains, 8 of 7380 facet)")
print("=" * 78)
dom_empty = fac_empty = dom_cells = fac_cells = 0
zeros_exact = []
for g in cohorts:
    for nm in scales:
        m = masks[g]
        if len(nm) == 1:
            v = domain_raw[m, ipip.DOMAIN_ORDER.index(nm)]; lo, hi = 60, 300
        else:
            v = facet_raw[m, ipip.facet_slot(nm[0], int(nm[1]))]; lo, hi = 10, 50
        cnt = np.bincount(v - lo, minlength=hi - lo + 1)
        e = int((cnt == 0).sum())
        if len(nm) == 1:
            dom_empty += e; dom_cells += len(cnt)
        else:
            fac_empty += e; fac_cells += len(cnt)
        ex = np.array(J["tables"][g][nm]["pct_exact"])
        if (ex <= 0).any():
            zeros_exact.append((g, nm, int((ex <= 0).sum()), J["tables"][g][nm]["observed_raw_range"]))
print("domain cells %d  empty %d" % (dom_cells, dom_empty))
print("facet  cells %d  empty %d" % (fac_cells, fac_empty))
print("total empty %d" % (dom_empty + fac_empty))
print()
print("rows whose pct_exact contains a value <= 0 (JSON is rounded to 6dp):", zeros_exact)
for g, nm, k, rr in zeros_exact:
    q = np.array(J["tables"][g][nm]["pct_quantised"])
    print("   %s %s: first 5 pct_exact %s ; first 5 pct_quantised %s ; min quantised %.6f"
          % (g, nm, J["tables"][g][nm]["pct_exact"][:5], list(q[:5]), q.min()))
print("=> these are the ladder floor 0.0005 after quantisation, not literal zeros in the shipped table")

print()
print("=" * 78)
print("F. PROVENANCE: recompute the encoding stats under the REJECTED 688-level ladder")
print("=" * 78)
LADDERS = {
    "safe025x_shipped": [(0, .001), (0.1, .01), (0.75, .05), (5.25, .25), (94.75, .05), (99.25, .01), (99.9, .001)],
    "safe025_688": [(0, .01), (0.75, .05), (5.25, .25), (94.75, .05), (99.25, .01)],
}


def ladder_levels(spec):
    vals = []
    for i, (st, sp) in enumerate(spec):
        en = spec[i + 1][0] if i + 1 < len(spec) else 100.0
        n = int(round((en - st) / sp))
        for k in range(n):
            vals.append(st + (k + 0.5) * sp)
    return np.round(np.array(vals, dtype=np.float64), 6)


def quantise(p, levels):
    p = np.clip(p, levels[0], levels[-1])
    idx = np.clip(np.searchsorted(levels, p), 1, len(levels) - 1)
    lo, hi = levels[idx - 1], levels[idx]
    return np.where(p - lo < hi - p - 1e-9, idx - 1, idx).astype(np.int64)


EX = {(g, nm): np.array(J["tables"][g][nm]["pct_exact"]) for g in cohorts for nm in scales}
import brotli, gzip
for name, spec in LADDERS.items():
    levels = ladder_levels(spec)
    q = {k: quantise(EX[k], levels) for k in EX}
    firsts, deltas = [], []
    for nm in scales:
        for g in cohorts:
            a = q[(g, nm)]
            firsts.append(int(a[0])); deltas.extend(int(x) for x in np.diff(a))
    firsts = np.array(firsts); deltas = np.array(deltas)
    two = int((firsts >= 48).sum() + (deltas >= 48).sum())
    # collisions
    coll = pairs = 0
    for g in cohorts:
        for nm in scales:
            m = masks[g]
            if len(nm) == 1:
                v = domain_raw[m, ipip.DOMAIN_ORDER.index(nm)]; lo, hi = 60, 300
            else:
                v = facet_raw[m, ipip.facet_slot(nm[0], int(nm[1]))]; lo, hi = 10, 50
            cnt = np.bincount(v - lo, minlength=hi - lo + 1)
            occ = np.nonzero(cnt)[0]
            qq = levels[q[(g, nm)]]
            for a, b in zip(occ[:-1], occ[1:]):
                pairs += 1
                if qq[a] == qq[b]:
                    coll += 1
    maxq = max(float(np.abs(levels[q[k]] - EX[k]).max()) for k in EX)
    print("%-18s levels=%4d two_char=%4d(%.2f%%) maxdelta=%3d meandelta=%.2f zero=%.2f%% "
          "chars/cell=%.5f maxqerr=%.4f collisions=%d/%d"
          % (name, len(levels), two, 100.0 * two / 14610, deltas.max(), deltas.mean(),
             100.0 * (deltas == 0).mean(), (14610 + two) / 14610.0, maxq, coll, pairs))

print()
print("=" * 78)
print("G. RESPONDENT ACCOUNTING")
print("=" * 78)
print("cohort_n:", J["cohort_n"])
print("M+F sum  : %d ; N sum : %d ; dataset rows : %d"
      % (J["cohort_n"]["M_lt21"] + J["cohort_n"]["M_gte21"] + J["cohort_n"]["F_lt21"] + J["cohort_n"]["F_gte21"],
         J["cohort_n"]["N_lt21"] + J["cohort_n"]["N_gte21"], len(z["sex"])))
print("sex values present:", np.unique(z["sex"]))
print("'10,177,160 values' = 145388 respondents x 35 scales x 2 cohort memberships = %d"
      % (145388 * 35 * 2))
print("distinct respondent-scale values = %d" % (145388 * 35))

print()
print("=" * 78)
print("H. build_tables.py DOCSTRING vs SHIPPED JSON")
print("=" * 78)
src = io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_tables.py"), encoding="utf-8").read()
import re
m = re.search(r"Gaps are short \(545\s+cells over (\d+) gaps", src)
print("docstring says gaps runs =", m.group(1) if m else "?", "; JSON says", J["empty_cell_policy"]["interior_gaps"])
print("docstring 'clipped to [0.01, 99.99]' present:", "[0.01, 99.99]" in src,
      "; actual JSON clip:", J["empty_cell_policy"]["clip"])
