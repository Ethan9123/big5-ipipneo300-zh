# -*- coding: utf-8 -*-
"""ADVERSARIAL review part 2: encoding stats, old-vs-new regression, railing,
adjacent-raw collisions, and 5 real respondents scored both ways."""
import io, json, math, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip

J = json.load(io.open(os.path.join(ipip.OUT, "pct_tables.json"), encoding="utf-8"))
cohorts, scales = J["cohorts"], J["scales"]
z = ipip.load()
masks = ipip.group_masks(z["sex"], z["age"])
facet_raw, domain_raw = z["facet_raw"], z["domain_raw"]
data = ipip.site_data()

EX = {(g, nm): np.array(J["tables"][g][nm]["pct_exact"]) for g in cohorts for nm in scales}
QV = {(g, nm): np.array(J["tables"][g][nm]["pct_quantised"]) for g in cohorts for nm in scales}
IDX = {(g, nm): np.array(J["tables"][g][nm]["levels"], dtype=np.int64) for g in cohorts for nm in scales}


def raws_for(g, nm):
    m = masks[g]
    if len(nm) == 1:
        return domain_raw[m, ipip.DOMAIN_ORDER.index(nm)], 60
    return facet_raw[m, ipip.facet_slot(nm[0], int(nm[1]))], 10


print("=" * 78)
print("A. ENCODING STATISTICS (claim: 82 two-char cells, max delta 71, mean 9.48, 9.5% zero)")
print("=" * 78)
first_vals, deltas = [], []
for nm in scales:                      # scale-major, cohort inner: the encoder's order
    for g in cohorts:
        q = IDX[(g, nm)]
        first_vals.append(int(q[0]))
        deltas.extend(int(x) for x in np.diff(q))
first_vals = np.array(first_vals); deltas = np.array(deltas)
two_char = int((first_vals >= 48).sum() + (deltas >= 48).sum())
print("rows (first values)      : %d   of which >=48 (2-char): %d   max first value %d"
      % (len(first_vals), int((first_vals >= 48).sum()), first_vals.max()))
print("deltas                   : %d   of which >=48 (2-char): %d"
      % (len(deltas), int((deltas >= 48).sum())))
print("TOTAL two-char cells     : %d  (%.3f%% of 14610)   <-- claim says 82 (0.56%%)"
      % (two_char, 100.0 * two_char / 14610))
print("max delta                : %d      <-- claim says 71" % deltas.max())
print("mean delta               : %.4f  <-- claim says 9.48" % deltas.mean())
print("zero deltas              : %d / %d = %.2f%%   <-- claim says 9.5%%"
      % (int((deltas == 0).sum()), len(deltas), 100.0 * (deltas == 0).mean()))
print("table-segment chars      : %d = 14610 + %d" % (14610 + two_char, two_char))
print("chars per cell           : %.5f  <-- claim says ~1.005 / 'within 0.5%% of one byte'"
      % ((14610 + two_char) / 14610.0))

print()
print("=" * 78)
print("B. ADJACENT ATTAINED RAW SCORES SHARING A PERCENTILE (claim: 5 of 13,440)")
print("=" * 78)
coll = 0; pairs = 0; examples = []
for g in cohorts:
    for nm in scales:
        v, lo = raws_for(g, nm)
        hi = lo + len(EX[(g, nm)]) - 1
        cnt = np.bincount(v - lo, minlength=hi - lo + 1)
        occ = np.nonzero(cnt)[0]
        q = QV[(g, nm)]
        for a, b in zip(occ[:-1], occ[1:]):
            pairs += 1
            if q[a] == q[b]:
                coll += 1
                if len(examples) < 8:
                    examples.append((g, nm, int(a) + lo, int(b) + lo, int(cnt[a]), int(cnt[b]),
                                     float(q[a]), float(EX[(g, nm)][a]), float(EX[(g, nm)][b])))
print("adjacent occupied raw pairs : %d   sharing a quantised percentile: %d (%.4f%%)"
      % (pairs, coll, 100.0 * coll / pairs))
for e in examples:
    print("   ", e)

print()
print("=" * 78)
print("C. OLD CUBIC vs NEW TABLES over all respondent values")
print("=" * 78)
scale_kind = {nm: ("domain" if len(nm) == 1 else "facet") for nm in scales}
tot = 0
s_new_old = s_new_truth = s_old_truth = 0.0
disp = band = 0
worst = (0.0, None)
per_cohort = {}
old_rail = 0
new_floor = new_ceil = 0
disp0 = disp100 = 0
old_disp0 = old_disp100 = 0
rail_span = []
levels0, levels1 = J["quantisation"]["min_level"], J["quantisation"]["max_level"]
for g in cohorts:
    ns = np.array(data["norms"][g]["ns"], dtype=np.float64)
    ca = cn = 0.0
    for nm in scales:
        v, lo = raws_for(g, nm)
        newp = QV[(g, nm)][v - lo]
        truth = EX[(g, nm)][v - lo]
        if scale_kind[nm] == "domain":
            mu, sd = ns[ipip.DOMAIN_INDEX[nm]], ns[ipip.DOMAIN_INDEX[nm] + 5]
        else:
            a, b = ipip.FACET_OFFSET[nm[0]]
            f = int(nm[1])
            mu, sd = ns[f + a], ns[f + b]
        t = 50.0 + 10.0 * (v - mu) / sd
        oldp = ipip.pct_from_t(t)
        d = np.abs(newp - oldp)
        s_new_old += d.sum(); s_new_truth += np.abs(newp - truth).sum(); s_old_truth += np.abs(oldp - truth).sum()
        tot += len(v)
        disp += int((np.floor(newp + .5) != np.floor(oldp + .5)).sum())
        bn = np.where(np.trunc(newp) < 45, 0, np.where(np.trunc(newp) <= 55, 1, 2))
        bo = np.where(np.trunc(oldp) < 45, 0, np.where(np.trunc(oldp) <= 55, 1, 2))
        band += int((bn != bo).sum())
        railed = (oldp == 1.0) | (oldp == 99.0)
        old_rail += int(railed.sum())
        if railed.any():
            rail_span.append((float(truth[railed].max() - truth[railed].min()),
                              float(np.abs(t[railed]).size)))
        new_floor += int((newp <= levels0 + 1e-12).sum())
        new_ceil += int((newp >= levels1 - 1e-12).sum())
        disp0 += int((np.floor(newp + .5) == 0).sum()); disp100 += int((np.floor(newp + .5) == 100).sum())
        old_disp0 += int((np.floor(oldp + .5) == 0).sum()); old_disp100 += int((np.floor(oldp + .5) == 100).sum())
        ca += d.sum(); cn += len(v)
        mx = float(d.max())
        if mx > worst[0]:
            worst = (mx, (g, nm, int(v[np.argmax(d)])))
    per_cohort[g] = ca / cn
print("values compared              : %d      <-- claim 10,177,160" % tot)
print("MAE new vs old               : %.4f   <-- claim 2.9394" % (s_new_old / tot))
print("MAE new vs empirical truth   : %.4f   <-- claim 0.0571" % (s_new_truth / tot))
print("MAE old cubic vs truth       : %.4f   <-- claim 2.9382" % (s_old_truth / tot))
print("error reduction factor       : %.1fx  <-- claim 51x" % ((s_old_truth / tot) / (s_new_truth / tot)))
print("displayed integer changes    : %.2f%%  <-- claim 87.64%%" % (100.0 * disp / tot))
print("level band flips             : %.2f%%  <-- claim 8.15%%" % (100.0 * band / tot))
print("worst single |new-old|       : %.3f at %s   <-- claim 17.181 at F_lt21 x N5" % worst)
for g in cohorts:
    print("   %-9s MAE new vs old %.4f" % (g, per_cohort[g]))
print()
print("OLD railing  : %d values pinned to 1 or 99 = %.3f%%   <-- claim 457,278 / 4.493%%"
      % (old_rail, 100.0 * old_rail / tot))
print("NEW at floor %.4f: %d   at ceiling %.4f: %d   total %.6f%%   <-- claim 8 + 9 = 0.00017%%"
      % (levels0, new_floor, levels1, new_ceil, 100.0 * (new_floor + new_ceil) / tot))
print("NEW displayed integer 0  : %d values   (OLD: %d)" % (disp0, old_disp0))
print("NEW displayed integer 100: %d values   (OLD: %d)" % (disp100, old_disp100))

print()
print("=" * 78)
print("D. FIVE REAL RESPONDENTS, all 35 scales, old cubic vs new table")
print("=" * 78)
rng = np.random.default_rng(7)
sex, age, case = z["sex"], z["age"], z["case"]
elig = np.nonzero((sex == 1) | (sex == 2))[0]
pick = rng.choice(elig, size=5, replace=False)
for r in pick:
    g = ("M" if sex[r] == 1 else "F") + ("_lt21" if age[r] < 21 else "_gte21")
    ns = np.array(data["norms"][g]["ns"], dtype=np.float64)
    m = masks[g]
    pos = int(np.nonzero(m)[0].searchsorted(r))   # index of r inside the cohort
    print("\n  case=%d  sex=%d age=%d  cohort=%s (n=%d)" % (case[r], sex[r], age[r], g, m.sum()))
    print("    %-4s %5s %7s %8s %8s %8s %8s  %s"
          % ("scale", "raw", "T", "OLD pct", "NEW pct", "OLDdisp", "NEWdisp", "band old->new"))
    big = []
    for nm in scales:
        if len(nm) == 1:
            raw = int(domain_raw[r, ipip.DOMAIN_ORDER.index(nm)]); lo = 60
            mu, sd = ns[ipip.DOMAIN_INDEX[nm]], ns[ipip.DOMAIN_INDEX[nm] + 5]
        else:
            raw = int(facet_raw[r, ipip.facet_slot(nm[0], int(nm[1]))]); lo = 10
            a, b = ipip.FACET_OFFSET[nm[0]]
            mu, sd = ns[int(nm[1]) + a], ns[int(nm[1]) + b]
        t = 50.0 + 10.0 * (raw - mu) / sd
        oldp = float(ipip.pct_from_t(np.array([t]))[0])
        newp = float(QV[(g, nm)][raw - lo])
        tru = float(EX[(g, nm)][raw - lo])
        bnd = lambda p: "low" if math.trunc(p) < 45 else ("avg" if math.trunc(p) <= 55 else "high")
        flag = ""
        if abs(newp - oldp) >= 8: flag = "  <== large shift"
        print("    %-4s %5d %7.2f %8.3f %8.3f %8d %8d  %-4s -> %-4s%s"
              % (nm, raw, t, oldp, newp, math.floor(oldp + .5), math.floor(newp + .5), bnd(oldp), bnd(newp), flag))
        if abs(newp - oldp) >= 8:
            big.append((nm, oldp, newp, tru))
    if big:
        print("    large shifts (>=8 pts): " + ", ".join(
            "%s old=%.1f new=%.1f truth=%.1f" % (a, b, c, d) for a, b, c, d in big))
