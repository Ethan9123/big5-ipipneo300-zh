# -*- coding: utf-8 -*-
"""ADVERSARIAL independent review of the empirical percentile tables.
Nothing here imports build_tables.py; every number is recomputed from scratch.
"""
import io, json, math, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip

J = json.load(io.open(os.path.join(ipip.OUT, "pct_tables.json"), encoding="utf-8"))
PAY = io.open(os.path.join(ipip.OUT, "pct_tables_encoded.txt"), encoding="ascii").read()

print("=" * 78)
print("1. COVERAGE")
print("=" * 78)
cohorts = J["cohorts"]; scales = J["scales"]
exp_cohorts = ["M_lt21", "M_gte21", "F_lt21", "F_gte21", "N_lt21", "N_gte21"]
exp_scales = ["N", "E", "O", "A", "C"] + ["%s%d" % (d, f) for d in ["N", "E", "O", "A", "C"] for f in range(1, 7)]
print("cohorts match expected set:", sorted(cohorts) == sorted(exp_cohorts), cohorts)
print("scales  match expected set:", sorted(scales) == sorted(exp_scales), "n=%d" % len(scales))

cells = 0; bad_len = []; missing = []
for g in exp_cohorts:
    if g not in J["tables"]:
        missing.append(g); continue
    for nm in exp_scales:
        if nm not in J["tables"][g]:
            missing.append((g, nm)); continue
        t = J["tables"][g][nm]
        want = 241 if len(nm) == 1 else 41
        wmin = 60 if len(nm) == 1 else 10
        for key in ("pct_exact", "pct_quantised", "levels"):
            if len(t[key]) != want:
                bad_len.append((g, nm, key, len(t[key]), want))
        if t["raw_min"] != wmin:
            bad_len.append((g, nm, "raw_min", t["raw_min"], wmin))
        cells += len(t["pct_exact"])
print("missing cohort/scale entries :", missing)
print("wrong-length rows            :", bad_len)
print("total cells counted          : %d  (expected 6*(5*241 + 30*41) = %d)"
      % (cells, 6 * (5 * 241 + 30 * 41)))
print("rows                         : %d" % (len(exp_cohorts) * len(exp_scales)))

print()
print("=" * 78)
print("2. LADDER + QUANTISATION, recomputed independently")
print("=" * 78)
spec = [tuple(x) for x in J["quantisation"]["ladder_spec"]]
lv = []
for i, (st, sp) in enumerate(spec):
    en = spec[i + 1][0] if i + 1 < len(spec) else 100.0
    n = int(round((en - st) / sp))
    for k in range(n):
        lv.append(round(st + (k + 0.5) * sp, 6))
levels = np.array(lv, dtype=np.float64)
print("levels recomputed: %d  (json says %d)  strictly increasing: %s"
      % (len(levels), J["quantisation"]["n_levels"], bool(np.all(np.diff(levels) > 0))))
print("min/max level: %.6f / %.6f  (json %.6f / %.6f)"
      % (levels[0], levels[-1], J["quantisation"]["min_level"], J["quantisation"]["max_level"]))
# no level lands on an integer or a .5
on_grid = int(np.sum(np.abs(levels * 2 - np.round(levels * 2)) < 1e-9))
print("levels sitting exactly on a .0 or .5 boundary: %d" % on_grid)
# distance of nearest level to each integer/half boundary
b = np.arange(0, 200.5, 1.0) / 2.0
d = np.abs(levels[None, :] - b[:, None]).min(axis=1)
print("min distance from any .0/.5 boundary to nearest level: %.9f" % d.min())

# check pct_quantised == levels[levels_idx]
mm = 0.0; nmm = 0
for g in cohorts:
    for nm in scales:
        t = J["tables"][g][nm]
        idx = np.array(t["levels"], dtype=np.int64)
        if idx.min() < 0 or idx.max() >= len(levels):
            print("  OUT OF RANGE level index at", g, nm, idx.min(), idx.max())
        q = levels[idx]
        e = np.abs(q - np.array(t["pct_quantised"])).max()
        mm = max(mm, e); nmm += int(np.sum(np.abs(q - np.array(t["pct_quantised"])) > 5e-7))
print("max |levels[idx] - pct_quantised| over all cells: %.3e (mismatch count %d)" % (mm, nmm))

print()
print("=" * 78)
print("3. MONOTONICITY (independent)")
print("=" * 78)
viol_e = viol_q = viol_i = 0
worst_row = None
for g in cohorts:
    for nm in scales:
        t = J["tables"][g][nm]
        e = np.array(t["pct_exact"]); q = np.array(t["pct_quantised"]); i2 = np.array(t["levels"])
        ve = int((np.diff(e) < -1e-12).sum()); vq = int((np.diff(q) < -1e-12).sum()); vi = int((np.diff(i2) < 0).sum())
        viol_e += ve; viol_q += vq; viol_i += vi
        if ve or vq or vi:
            worst_row = (g, nm, ve, vq, vi)
print("non-monotone steps: pct_exact %d, pct_quantised %d, level index %d" % (viol_e, viol_q, viol_i))
print("example violating row:", worst_row)
print("rows checked: %d" % (len(cohorts) * len(scales)))
# encodable deltas
maxd = 0; ndelta2 = 0; nzero = 0; ndelt = 0; sdelt = 0
for nm in scales:
    for g in cohorts:
        idx = np.array(J["tables"][g][nm]["levels"], dtype=np.int64)
        d2 = np.diff(idx)
        maxd = max(maxd, int(d2.max()) if len(d2) else 0, int(idx[0]))
        ndelta2 += int((d2 >= 48).sum()) + (1 if idx[0] >= 48 else 0)
        nzero += int((d2 == 0).sum()); ndelt += len(d2); sdelt += int(d2.sum())
print("max encoded value %d (limit 1071); 2-char cells %d; zero deltas %d/%d (%.1f%%); mean delta %.2f"
      % (maxd, ndelta2, nzero, ndelt, 100.0 * nzero / ndelt, sdelt / ndelt))

print()
print("=" * 78)
print("4. PERCENTILE CORRECTNESS -- recomputed from scored.npz for EVERY cell")
print("=" * 78)
z = ipip.load()
masks = ipip.group_masks(z["sex"], z["age"])
facet_raw, domain_raw = z["facet_raw"], z["domain_raw"]


def raws_for(g, nm):
    m = masks[g]
    if len(nm) == 1:
        return domain_raw[m, ipip.DOMAIN_ORDER.index(nm)], 60, 300
    return facet_raw[m, ipip.facet_slot(nm[0], int(nm[1]))], 10, 50


worst_occ = (0.0, None); worst_gap = (0.0, None); worst_tail = (0.0, None)
n_occ = n_gapc = n_tailc = 0
n_sparse = {}
sparse_examples = []
tail_zero = []; ceil_hits = []; floor_hits = []
rng = np.random.default_rng(20260802)
sample_cells = []
per_cell_n = {}
gap_runs = 0
for g in cohorts:
    for nm in scales:
        v, lo, hi = raws_for(g, nm)
        n = len(v)
        cnt = np.bincount(v - lo, minlength=hi - lo + 1).astype(np.float64)
        below = np.cumsum(cnt) - cnt
        midrank = 100.0 * (below + 0.5 * cnt) / n
        tab = np.array(J["tables"][g][nm]["pct_exact"])
        occ = np.nonzero(cnt)[0]
        r_lo, r_hi = occ[0], occ[-1]
        per_cell_n[(g, nm)] = cnt
        # occupied cells must equal mid-rank verbatim
        d = np.abs(tab[occ] - midrank[occ])
        n_occ += len(occ)
        if d.max() > worst_occ[0]:
            worst_occ = (float(d.max()), (g, nm, int(occ[np.argmax(d)]) + lo))
        # observed range in json
        assert J["tables"][g][nm]["observed_raw_range"] == [int(r_lo) + lo, int(r_hi) + lo], (g, nm)
        # interior gaps -> claimed linear interpolation
        inner = np.arange(r_lo, r_hi + 1)
        gaps = inner[cnt[inner] == 0]
        n_gapc += len(gaps)
        d2 = np.diff((cnt[r_lo:r_hi + 1] > 0).astype(int))
        gap_runs += int((d2 < 0).sum())
        if len(gaps):
            raws = np.arange(lo, hi + 1, dtype=np.float64)
            want = np.interp(raws[gaps], raws[occ], midrank[occ])
            e = np.abs(tab[gaps] - want)
            if e.max() > worst_gap[0]:
                worst_gap = (float(e.max()), (g, nm, int(gaps[np.argmax(e)]) + lo))
        # tails
        tails = np.concatenate([np.arange(0, r_lo), np.arange(r_hi + 1, hi - lo + 1)])
        n_tailc += len(tails)
        if len(tails):
            mu = float(v.mean()); sd = float(v.std(ddof=1))
            raws = np.arange(lo, hi + 1, dtype=np.float64)
            want = np.empty(len(tails))
            for ii, rr in enumerate(tails):
                zz = (raws[rr] - mu) / sd
                if rr < r_lo:
                    za = (raws[r_lo] - mu) / sd
                    den = 0.5 * math.erfc(-za / math.sqrt(2))
                    want[ii] = midrank[r_lo] * (0.5 * math.erfc(-zz / math.sqrt(2)) / den) if den > 0 else 0.0
                else:
                    za = (raws[r_hi] - mu) / sd
                    den = 0.5 * math.erfc(za / math.sqrt(2))
                    want[ii] = 100.0 - (100.0 - midrank[r_hi]) * (0.5 * math.erfc(zz / math.sqrt(2)) / den) if den > 0 else 100.0
            want = np.clip(want, 0.0, 100.0)
            want = np.maximum.accumulate(np.concatenate([want[tails < r_lo], [np.nan]]))[:0] if False else want
            e = np.abs(tab[tails] - want)
            # np.maximum.accumulate in the builder can lift lower-tail values; compare loosely
            if e.max() > worst_tail[0]:
                worst_tail = (float(e.max()), (g, nm, int(tails[np.argmax(e)]) + lo))
        # sparse occupied cells
        sp = occ[(cnt[occ] > 0) & (cnt[occ] < 30)]
        n_sparse[(g, nm)] = len(sp)
        for r in sp[:2]:
            sparse_examples.append((g, nm, int(r) + lo, int(cnt[r]), float(tab[r]),
                                    float(np.array(J["tables"][g][nm]["pct_quantised"])[r])))
        # exact 0 / 100 cells
        qv = np.array(J["tables"][g][nm]["pct_quantised"])
        if (tab <= 0).any(): tail_zero.append((g, nm, int(np.sum(tab <= 0))))
        floor_hits.append(int(np.sum(qv <= levels[0] + 1e-12)))
        ceil_hits.append(int(np.sum(qv >= levels[-1] - 1e-12)))
        sample_cells.append((g, nm))

print("occupied cells checked        : %d" % n_occ)
print("max |table - recomputed midrank| on OCCUPIED cells: %.3e  at %s" % worst_occ)
print("interior gap cells            : %d in %d runs  (json says %d / %d)"
      % (n_gapc, gap_runs, J["empty_cell_policy"]["interior_gap_cells"], J["empty_cell_policy"]["interior_gaps"]))
print("max |table - my linear interp| on GAP cells      : %.3e  at %s" % worst_gap)
print("tail cells                    : %d  (json says %d)" % (n_tailc, J["empty_cell_policy"]["tail_cells"]))
print("max |table - my normal-tail formula| on TAIL cells: %.3e  at %s" % worst_tail)
print("total empty cells             : %d (json %d)" % (n_gapc + n_tailc, J["empty_cell_policy"]["empty_cells_total"]))
print("rows with a pct_exact <= 0    :", tail_zero[:10], "n=%d" % len(tail_zero))
print("cells pinned at ladder floor %.4f: %d ; at ceiling %.4f: %d"
      % (levels[0], sum(floor_hits), levels[-1], sum(ceil_hits)))

print()
print("--- 40-cell random spot check (fully independent recomputation) ---")
pick = rng.choice(len(sample_cells), size=45, replace=False)
worst = 0.0
rows = []
for pi in pick:
    g, nm = sample_cells[pi]
    v, lo, hi = raws_for(g, nm)
    r = int(rng.integers(lo, hi + 1))
    n = len(v)
    below = int((v < r).sum()); eq = int((v == r).sum())
    mine = 100.0 * (below + 0.5 * eq) / n
    tab = J["tables"][g][nm]["pct_exact"][r - lo]
    q = J["tables"][g][nm]["pct_quantised"][r - lo]
    d = abs(mine - tab) if eq > 0 else float("nan")
    if eq > 0:
        worst = max(worst, abs(mine - tab))
    rows.append((g, nm, r, n, eq, mine, tab, q))
for rr in rows[:45]:
    print("  %-8s %-3s raw=%3d n=%6d n_at=%6d  midrank=%9.5f  table=%9.5f  quant=%9.5f  %s"
          % (rr[0], rr[1], rr[2], rr[3], rr[4], rr[5], rr[6], rr[7],
             "EMPTY-CELL(filled)" if rr[4] == 0 else "d=%.2e" % abs(rr[5] - rr[6])))
print("max discrepancy on occupied sampled cells: %.3e" % worst)

print()
print("=" * 78)
print("5. TAILS / SPARSE CELLS")
print("=" * 78)
print("min/max attainable raw values, per cohort, for a few scales:")
for g in cohorts:
    for nm in ["N", "C", "N1", "C6"]:
        t = J["tables"][g][nm]
        lo = t["raw_min"]; hi = lo + len(t["pct_exact"]) - 1
        print("  %-8s %-3s  p(%d)=%.6f  p(%d)=%.6f  observed range %s"
              % (g, nm, lo, t["pct_exact"][0], hi, t["pct_exact"][-1], t["observed_raw_range"]))
print()
print("cells claiming exactly 0 or exactly 100 in pct_exact:",
      sum(1 for g in cohorts for nm in scales for x in J["tables"][g][nm]["pct_exact"] if x <= 0.0 or x >= 100.0))
print("cells claiming exactly 0 or 100 in pct_quantised   :",
      sum(1 for g in cohorts for nm in scales for x in J["tables"][g][nm]["pct_quantised"] if x <= 0.0 or x >= 100.0))
tot_sparse = sum(n_sparse.values())
print("occupied cells with n<30 respondents: %d" % tot_sparse)
print("  15 spot checks (cohort, scale, raw, n_at_that_raw, pct_exact, pct_quantised):")
for e in sparse_examples[:15]:
    print("   ", e)

print()
print("=" * 78)
print("6. SIZES (measured here)")
print("=" * 78)
import brotli, gzip
pay_b = PAY.encode("ascii")
dec = io.open(os.path.join(ipip.OUT, "decoder.js"), encoding="utf-8").read().encode("utf-8")
site = io.open(ipip.SITE, encoding="utf-8").read().encode("utf-8")
added = pay_b + b"\n" + dec
print("payload raw      : %d  (file size %d)" % (len(pay_b), os.path.getsize(os.path.join(ipip.OUT, "pct_tables_encoded.txt"))))
print("payload brotli11 : %d" % len(brotli.compress(pay_b, quality=11)))
print("payload gzip9    : %d" % len(gzip.compress(pay_b, 9)))
print("decoder.js raw   : %d" % len(dec))
print("added raw total  : %d" % len(added))
print("site raw/brotli11/gzip9 : %d / %d / %d"
      % (len(site), len(brotli.compress(site, quality=11)), len(gzip.compress(site, 9))))
b0 = len(brotli.compress(site, quality=11)); b1 = len(brotli.compress(site + added, quality=11))
g0 = len(gzip.compress(site, 9)); g1 = len(gzip.compress(site + added, 9))
print("site+added brotli11 : %d   DELTA %d" % (b1, b1 - b0))
print("site+added gzip9    : %d   DELTA %d" % (g1, g1 - g0))
print("chars per cell   : %.4f" % (len(pay_b) / 14610.0))

print()
print("=" * 78)
print("7. DISPLAY FIDELITY of quantisation over all respondent values")
print("=" * 78)


def jsround(x):
    return np.floor(np.asarray(x, dtype=np.float64) + 0.5)


nr = nt = tot = 0
band_ch = 0
worstq = 0.0; sumq = 0.0
for g in cohorts:
    for nm in scales:
        v, lo, hi = raws_for(g, nm)
        e = np.array(J["tables"][g][nm]["pct_exact"])[v - lo]
        q = np.array(J["tables"][g][nm]["pct_quantised"])[v - lo]
        nr += int((jsround(e) != jsround(q)).sum())
        nt += int((np.trunc(e) != np.trunc(q)).sum())
        be = np.where(np.trunc(e) < 45, 0, np.where(np.trunc(e) <= 55, 1, 2))
        bq = np.where(np.trunc(q) < 45, 0, np.where(np.trunc(q) <= 55, 1, 2))
        band_ch += int((be != bq).sum())
        a = np.abs(e - q)
        worstq = max(worstq, float(a.max())); sumq += float(a.sum())
        tot += len(v)
print("respondent values          : %d" % tot)
print("Math.round differs         : %d" % nr)
print("Math.trunc differs         : %d" % nt)
print("level band differs         : %d" % band_ch)
print("max quantisation error     : %.6f   mean %.6f" % (worstq, sumq / tot))
# dense scan
scan = np.arange(0, 100.0 + 1e-9, 0.0005)
sc = np.clip(scan, levels[0], levels[-1])
idx = np.clip(np.searchsorted(levels, sc), 1, len(levels) - 1)
loL, hiL = levels[idx - 1], levels[idx]
qi = np.where(sc - loL < hiL - sc - 1e-9, idx - 1, idx)
qs = levels[qi]
print("dense scan %d points: round mismatches %d, trunc mismatches %d"
      % (len(scan), int((jsround(sc) != jsround(qs)).sum()), int((np.trunc(sc) != np.trunc(qs)).sum())))
