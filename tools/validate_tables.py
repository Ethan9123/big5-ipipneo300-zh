# -*- coding: utf-8 -*-
"""Final validation of the shipped tables: coverage, railing, tails, resolution."""
import io, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip

doc = json.load(io.open(os.path.join(ipip.OUT, "pct_tables.json"), encoding="utf-8"))
cohorts, scales = doc["cohorts"], doc["scales"]

# ---- coverage ----------------------------------------------------------
cells = 0
for g in cohorts:
    for s in scales:
        t = doc["tables"][g][s]
        want = 241 if len(s) == 1 else 41
        assert len(t["pct_quantised"]) == want == len(t["pct_exact"]), (g, s)
        assert t["raw_min"] == (60 if len(s) == 1 else 10)
        cells += want
print("coverage: %d cells over %d cohorts x %d scales (expected 14610) -> %s"
      % (cells, len(cohorts), len(scales), cells == 14610))
assert len(doc["norms"]) == 6 and all(len(doc["norms"][g]) == 35 for g in cohorts)
print("norms companion: %d cohort x scale mean/sd pairs" % (6 * 35))

lo_lv = doc["quantisation"]["min_level"]
hi_lv = doc["quantisation"]["max_level"]

# ---- railing, over real respondents ------------------------------------
z = ipip.load()
masks = ipip.group_masks(z["sex"], z["age"])
sc = ipip.scale_index()
names = [d if k == "domain" else "%s%d" % (d, f) for k, d, f in sc]
tot = at_floor = at_ceil = old_rail = 0
adj_equal_new = adj_equal_pairs = 0
for g in cohorts:
    m = masks[g]
    ns = np.array(ipip.site_data()["norms"][g]["ns"], dtype=np.float64)
    for (kind, dom, fno), nm in zip(sc, names):
        v = (z["domain_raw"][m, ipip.DOMAIN_ORDER.index(dom)] if kind == "domain"
             else z["facet_raw"][m, ipip.facet_slot(dom, fno)])
        base = 60 if kind == "domain" else 10
        tab = np.array(doc["tables"][g][nm]["pct_quantised"])
        p = tab[v - base]
        tot += len(v)
        at_floor += int((p <= lo_lv + 1e-12).sum())
        at_ceil += int((p >= hi_lv - 1e-12).sum())
        if kind == "domain":
            mu, sd = ns[ipip.DOMAIN_INDEX[dom]], ns[ipip.DOMAIN_INDEX[dom] + 5]
        else:
            a, b = ipip.FACET_OFFSET[dom]
            mu, sd = ns[fno + a], ns[fno + b]
        t = 50.0 + 10.0 * (v - mu) / sd
        old_rail += int(((t < 32) | (t > 73)).sum())
        # resolution: adjacent attainable raw scores that map to the same percentile
        occ = np.unique(v - base)
        d = np.diff(tab[occ])
        adj_equal_new += int((d == 0).sum())
        adj_equal_pairs += len(d)
print("\nrailing over %d respondent values:" % tot)
print("  old cubic pinned to 1 or 99 : %d (%.3f%%)" % (old_rail, 100.0 * old_rail / tot))
print("  new at floor %.3f            : %d (%.5f%%)" % (lo_lv, at_floor, 100.0 * at_floor / tot))
print("  new at ceiling %.3f         : %d (%.5f%%)" % (hi_lv, at_ceil, 100.0 * at_ceil / tot))
print("  adjacent OCCUPIED raw scores sharing a percentile: %d of %d (%.3f%%)"
      % (adj_equal_new, adj_equal_pairs, 100.0 * adj_equal_new / adj_equal_pairs))

# ---- worst tail: F_lt21 O domain (min observed raw 117) ----------------
t = doc["tables"]["F_lt21"]["O"]
print("\nF_lt21 / O domain, observed raw range %s:" % t["observed_raw_range"])
q = t["pct_quantised"]
for r in (60, 70, 80, 90, 100, 110, 116, 117, 118, 130, 296, 297, 300):
    print("   raw %3d -> %.3f%s" % (r, q[r - 60],
          "   <- lowest attained" if r == t["observed_raw_range"][0] else ""))
strict = all(q[i] < q[i + 1] for i in range(0, t["observed_raw_range"][0] - 60))
print("   strictly increasing below the lowest attained score: %s" % strict)

# ---- monotonicity of every shipped row ---------------------------------
bad = 0
for g in cohorts:
    for s in scales:
        a = doc["tables"][g][s]["pct_quantised"]
        bad += sum(1 for i in range(1, len(a)) if a[i] < a[i - 1])
print("\nnon-monotone steps across all %d shipped rows: %d" % (6 * 35, bad))
