# -*- coding: utf-8 -*-
"""Build empirical percentile lookup tables to replace the cubic+rails map.

Outputs
-------
tools/out/pct_tables.json          human-readable, full precision (exact + quantised)
tools/out/pct_tables_encoded.txt   the compact self-describing payload for the page
tools/out/decoder.js               the JS decoder (written by this script so it can
                                   never drift from the encoder)

Method
------
For every (cohort, scale) and every attainable raw score r we store the mid-rank
empirical percentile

    p(r) = 100 * (#{x < r} + 0.5 * #{x == r}) / n

which is exactly the ground truth the percentile-map audit measured against.
Mid-rank is automatically monotone non-decreasing in r, so no smoothing of
occupied cells is needed and none is done: occupied cells are reported verbatim.

Empty cells (960 of 14610, 6.57% -- almost all of them in the domain tables,
which span 241 raw values) are filled as follows:

  * interior gaps (empty cells that sit between two occupied raw scores):
    linear interpolation in raw score between the bounding occupied cells.
    Rationale: the mid-rank formula would return the same number for every raw
    score in the gap (a flat plateau), i.e. two people 6 raw points apart would
    be told they are at an identical percentile.  Linear interpolation is the
    minimal assumption that keeps the function strictly increasing across the
    gap and reproduces the occupied endpoints exactly.  Gaps are short (545
    cells over 175 gaps in the whole build), so curvature within a gap is
    negligible.

  * lower tail (raw below the lowest score anyone in the cohort attained):
    p(r) = p(r_lo) * Phi((r-mu)/sd) / Phi((r_lo-mu)/sd)
    upper tail (raw above the highest attained score):
    p(r) = 100 - (100-p(r_hi)) * Q((r-mu)/sd) / Q((r_hi-mu)/sd),  Q = 1-Phi
    with mu, sd the cohort/scale sample mean and SD (the same pair shipped for
    the T score).  Rationale: there is no data out there, so *something* has to
    be modelled.  This form (a) is continuous at the anchor -- it reproduces the
    empirical value at the last occupied cell exactly, (b) is strictly
    increasing, so a lower raw score never returns a higher percentile, and
    (c) decays at the rate of the normal tail rather than jumping to a hard
    rail.  Multiplying by a *ratio* means the empirical anchor, not the normal
    model, sets the level; the model only supplies the shape.  These cells hold
    zero respondents by construction, so this choice cannot affect any accuracy
    number measured against the sample -- it only decides what a hypothetical
    extreme scorer is shown.

Everything is finally clipped to [0.01, 99.99] and passed through
np.maximum.accumulate as a belt-and-braces monotonicity guarantee.
"""
import io
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
assert len(ALPHABET) == 64 and len(set(ALPHABET)) == 64
SEP = "~"

# Candidate quantisation ladders: list of (breakpoint, step), implicit end at 100.
# Levels are CELL-CENTRED: start + (k + 0.5) * step.  That matters: it puts every
# integer and every .5 boundary exactly half-way between two levels, so quantising
# can never move a value across a Math.round or Math.trunc boundary (ties are broken
# upward, matching JS Math.round(x.5) === x+1).  A grid whose points sit ON the
# integers/halves -- the obvious choice -- silently changes the number the user sees
# for ~23% of values (measured; see sweep_ladders.py).
#
# For that guarantee to hold at a region breakpoint b as well as inside a region,
# the spec has to satisfy three conditions (checked by ladder_levels):
#   1. 0.5 / step is an integer          -> levels never land on a .0 or .5 boundary
#   2. start is a multiple of step       -> the cell centres stay anchored to 0
#   3. b clears every .0/.5 boundary by more than |step_left - step_right| / 4
#      -> the asymmetric tie window either side of b cannot reach a boundary
# "safe*" ladders satisfy all three; the "bad*" ones are kept only to show the cost.
LADDERS = {
    # chosen: 0.001 steps in the deep tails so the ladder resolves a single
    # respondent even in the largest cohort (grain 100*0.5/82670 = 0.0006)
    "safe025x": [(0, .001), (0.1, .01), (0.75, .05), (5.25, .25),
                 (94.75, .05), (99.25, .01), (99.9, .001)],
    "safe025": [(0, .01), (0.75, .05), (5.25, .25), (94.75, .05), (99.25, .01)],
    "safe050": [(0, .01), (0.75, .05), (5.5, .5), (94.5, .05), (99.25, .01)],
    "bad_025": [(0, .01), (0.5, .05), (2, .1), (5, .25), (95, .1), (98, .05), (99.5, .01)],
    "bad_050": [(0, .01), (0.5, .05), (2, .1), (5, .5), (95, .1), (98, .05), (99.5, .01)],
    "bad_020": [(0, .01), (0.5, .05), (2, .1), (5, .2), (95, .1), (98, .05), (99.5, .01)],
    "bad_100": [(0, .01), (0.5, .05), (2, .1), (5, 1.), (95, .1), (98, .05), (99.5, .01)],
}
CHOICE = os.environ.get("LADDER", "safe025x")


def ladder_audit(spec):
    """Report which of the three parity conditions a spec violates."""
    bad = []
    for i, (start, step) in enumerate(spec):
        end = spec[i + 1][0] if i + 1 < len(spec) else 100.0
        if abs(round(0.5 / step) - 0.5 / step) > 1e-9:
            bad.append("step %g does not divide 0.5" % step)
        if abs(round(start / step) - start / step) > 1e-9:
            bad.append("start %g not a multiple of step %g" % (start, step))
        if abs(round((end - start) / step) - (end - start) / step) > 1e-9:
            bad.append("region [%g,%g) not a whole number of %g steps" % (start, end, step))
        if i:
            sL = spec[i - 1][1]
            clear = min(abs(start - round(start * 2) / 2.0), 0.5)
            if clear <= abs(sL - step) / 4.0 + 1e-12:
                bad.append("breakpoint %g clears .0/.5 by %g, needs > %g"
                           % (start, clear, abs(sL - step) / 4.0))
    return bad


# ---------------------------------------------------------------- ladder ----
def ladder_levels(spec):
    """spec -> strictly increasing float array of representable percentiles."""
    vals = []
    for i, (start, step) in enumerate(spec):
        end = spec[i + 1][0] if i + 1 < len(spec) else 100.0
        n = int(round((end - start) / step))
        for k in range(n):
            vals.append(start + (k + 0.5) * step)
    v = np.round(np.array(vals, dtype=np.float64), 6)
    assert np.all(np.diff(v) > 0), "ladder not strictly increasing"
    return v


def ladder_text(spec):
    def f(x):
        s = ("%.10f" % x).rstrip("0").rstrip(".")
        return s if s else "0"
    return "|".join("%s:%s" % (f(a), f(b)) for a, b in spec)


def quantise(p, levels):
    """Nearest-level index, TIES BROKEN UPWARD; monotone because levels is increasing.

    The 1e-9 slack matters: a value sitting exactly on a boundary (e.g. p == 4.0,
    equidistant from levels 3.975 and 4.025) must round UP so that Math.trunc and
    Math.round of the quantised value match those of the original.  Without the
    slack, binary representation error decides the tie and the guarantee breaks
    for a handful of exactly-representable percentiles.
    """
    p = np.clip(p, levels[0], levels[-1])
    idx = np.clip(np.searchsorted(levels, p), 1, len(levels) - 1)
    lo, hi = levels[idx - 1], levels[idx]
    return np.where(p - lo < hi - p - 1e-9, idx - 1, idx).astype(np.int32)


# -------------------------------------------------------------- encoding ----
def enc_val(v, out):
    """0..47 in one char; 48..1071 in two.  (6-bit alphabet, 1-char fast path.)"""
    if v < 48:
        out.append(ALPHABET[v])
    else:
        w = v - 48
        if w >= 1024:
            raise ValueError("value %d too large for 2-char code" % v)
        out.append(ALPHABET[48 + (w >> 6)])
        out.append(ALPHABET[w & 63])


def enc_u18(v, out):
    """fixed 3 chars, 0..262143 -- used for the mean/sd companion."""
    if not (0 <= v < 1 << 18):
        raise ValueError("u18 out of range: %d" % v)
    out.append(ALPHABET[(v >> 12) & 63])
    out.append(ALPHABET[(v >> 6) & 63])
    out.append(ALPHABET[v & 63])


# ------------------------------------------------------------------ build ----
SQRT2 = math.sqrt(2.0)


def phi(z):
    return np.array([0.5 * math.erfc(-x / SQRT2) for x in np.atleast_1d(z)], dtype=np.float64)


def sf(z):
    return np.array([0.5 * math.erfc(x / SQRT2) for x in np.atleast_1d(z)], dtype=np.float64)


def build_cell(v, lo, hi, mu, sd):
    """v: raw scores of one cohort for one scale.  Returns (pct[hi-lo+1], counts, stats)."""
    n = len(v)
    cnt = np.bincount(v - lo, minlength=hi - lo + 1).astype(np.float64)
    below = np.cumsum(cnt) - cnt
    p = 100.0 * (below + 0.5 * cnt) / n
    raws = np.arange(lo, hi + 1, dtype=np.float64)

    occ = np.nonzero(cnt)[0]
    r_lo, r_hi = occ[0], occ[-1]
    filled = p.copy()

    # interior gaps -> linear interpolation between bounding occupied cells
    if r_hi > r_lo:
        seg = slice(r_lo, r_hi + 1)
        filled[seg] = np.interp(raws[seg], raws[occ], p[occ])

    # lower tail -> normal-shaped decay anchored at the lowest occupied cell
    n_lo = int(r_lo)
    if n_lo > 0:
        z = (raws[:n_lo] - mu) / sd
        za = (raws[r_lo] - mu) / sd
        denom = phi(np.array([za]))[0]
        filled[:n_lo] = p[r_lo] * (phi(z) / denom if denom > 0 else 0.0)

    # upper tail
    n_hi = len(p) - 1 - int(r_hi)
    if n_hi > 0:
        z = (raws[r_hi + 1:] - mu) / sd
        za = (raws[r_hi] - mu) / sd
        denom = sf(np.array([za]))[0]
        filled[r_hi + 1:] = 100.0 - (100.0 - p[r_hi]) * (sf(z) / denom if denom > 0 else 0.0)

    filled = np.clip(filled, 0.0, 100.0)
    filled = np.maximum.accumulate(filled)
    return filled, cnt, (int(r_lo) + lo, int(r_hi) + lo)


def main():
    z = ipip.load()
    masks = ipip.group_masks(z["sex"], z["age"])
    facet_raw, domain_raw = z["facet_raw"], z["domain_raw"]
    scales = ipip.scale_index()
    scale_names = [d if k == "domain" else "%s%d" % (d, f) for k, d, f in scales]

    exact = {}      # (cohort, scale) -> float array
    norms = {}      # (cohort, scale) -> (mean, sd)
    rawvals = {}    # (cohort, scale) -> raw vector (for the respondent-level comparison)
    obs_range = {}
    n_gaps = n_gap_cells = n_tail_cells = 0

    for g in ipip.GROUPS:
        m = masks[g]
        for (kind, dom, fno), nm in zip(scales, scale_names):
            if kind == "domain":
                v = domain_raw[m, ipip.DOMAIN_ORDER.index(dom)]
                lo, hi = ipip.DOMAIN_RAW_MIN, ipip.DOMAIN_RAW_MAX
            else:
                v = facet_raw[m, ipip.facet_slot(dom, fno)]
                lo, hi = ipip.FACET_RAW_MIN, ipip.FACET_RAW_MAX
            mu = float(v.mean())
            sd = float(v.std(ddof=1))
            p, cnt, rng = build_cell(v, lo, hi, mu, sd)
            exact[(g, nm)] = p
            norms[(g, nm)] = (mu, sd)
            rawvals[(g, nm)] = v
            obs_range[(g, nm)] = rng
            occ = np.nonzero(cnt)[0]
            inner = cnt[occ[0]:occ[-1] + 1]
            n_gap_cells += int((inner == 0).sum())
            n_tail_cells += int((cnt == 0).sum()) - int((inner == 0).sum())
            d = np.diff((inner > 0).astype(int))
            n_gaps += int((d < 0).sum())

    total_cells = sum(len(v) for v in exact.values())

    # ---- ladder sweep -----------------------------------------------------
    import brotli
    import gzip

    def jsround(x):                       # JS Math.round: half away from zero (up)
        return np.floor(np.asarray(x, dtype=np.float64) + 0.5)

    def display_parity(qv):
        """fraction of real respondent values where round() or trunc() would change."""
        nr = nt = tot = 0
        for k in exact:
            lo = 60 if len(k[1]) == 1 else 10
            i = rawvals[k] - lo
            a, b = exact[k][i], qv[k][i]
            nr += int((jsround(a) != jsround(b)).sum())
            nt += int((np.trunc(a) != np.trunc(b)).sum())
            tot += len(i)
        return 100.0 * nr / tot, 100.0 * nt / tot

    print("%-8s %6s %9s %9s %8s %7s %7s %9s %9s %s"
          % ("ladder", "levels", "maxqerr", "meanqerr", "raw", "brotli", "gzip",
             "round!=%", "trunc!=%", "parity-safe"))
    for name, spec in sorted(LADDERS.items()):
        levels = ladder_levels(spec)
        if len(levels) > 1072:
            print("%-8s %6d  skipped (too many levels for the 2-char code)" % (name, len(levels)))
            continue
        q = {k: quantise(exact[k], levels) for k in exact}
        qv = {k: levels[q[k]] for k in exact}
        payload = encode(scale_names, levels, spec, q, norms)
        pr, pt = display_parity(qv)
        aud = ladder_audit(spec)
        print("%-8s %6d %9.5f %9.5f %8d %7d %7d %9.5f %9.5f %s"
              % (name, len(levels),
                 max(float(np.abs(qv[k] - exact[k]).max()) for k in exact),
                 float(np.mean([np.abs(qv[k] - exact[k]).mean() for k in exact])),
                 len(payload), len(brotli.compress(payload.encode(), quality=11)),
                 len(gzip.compress(payload.encode(), 9)), pr, pt,
                 "yes" if not aud else "NO: " + aud[0]))

    spec = LADDERS[CHOICE]
    levels = ladder_levels(spec)
    quant = {k: quantise(exact[k], levels) for k in exact}
    qval = {k: levels[quant[k]] for k in exact}

    # ---- monotonicity check ----------------------------------------------
    mono_exact = all(bool(np.all(np.diff(exact[k]) >= 0)) for k in exact)
    mono_quant = all(bool(np.all(np.diff(quant[k]) >= 0)) for k in quant)
    max_qerr = max(float(np.abs(qval[k] - exact[k]).max()) for k in exact)
    mean_qerr = float(np.mean([np.abs(qval[k] - exact[k]).mean() for k in exact]))
    par_round, par_trunc = display_parity(qval)
    # dense independent check of the round/trunc-preserving property of the ladder
    scan = np.arange(0, 100.0000001, 0.0005)
    sq = levels[quantise(scan, levels)]
    dense_bad_r = int((jsround(np.clip(scan, levels[0], levels[-1])) != jsround(sq)).sum())
    dense_bad_t = int((np.trunc(np.clip(scan, levels[0], levels[-1])) != np.trunc(sq)).sum())

    payload = encode(scale_names, levels, spec, quant, norms)
    out_txt = os.path.join(ipip.OUT, "pct_tables_encoded.txt")
    io.open(out_txt, "w", encoding="ascii", newline="").write(payload)

    # ---- JSON -------------------------------------------------------------
    doc = {
        "schema": "bigfive-empirical-percentile-tables/1",
        "source": "IPIP300-SCORES.csv (Johnson 2014), n=145388, items used as-is (already recoded)",
        "definition": "mid-rank empirical percentile 100*(count_below + 0.5*count_equal)/n within cohort",
        "empty_cell_policy": {
            "interior_gap": "linear interpolation in raw score between bounding occupied cells",
            "lower_tail": "p(r_lo) * Phi((r-mu)/sd) / Phi((r_lo-mu)/sd)",
            "upper_tail": "100 - (100-p(r_hi)) * Q((r-mu)/sd) / Q((r_hi-mu)/sd)",
            "clip": [float(levels[0]), float(levels[-1])],
            "empty_cells_total": n_gap_cells + n_tail_cells,
            "interior_gap_cells": n_gap_cells,
            "tail_cells": n_tail_cells,
            "interior_gaps": n_gaps,
        },
        "quantisation": {
            "ladder_name": CHOICE,
            "ladder_spec": [[a, b] for a, b in spec],
            "ladder_text": ladder_text(spec),
            "n_levels": len(levels),
            "cell_centred": True,
            "min_level": float(levels[0]),
            "max_level": float(levels[-1]),
            "max_error_pct_points": max_qerr,
            "mean_abs_error_pct_points": mean_qerr,
            "pct_respondent_values_whose_Math_round_changes": par_round,
            "pct_respondent_values_whose_Math_trunc_changes": par_trunc,
            "dense_scan_round_mismatches": dense_bad_r,
            "dense_scan_trunc_mismatches": dense_bad_t,
        },
        "raw_ranges": {"domain": [ipip.DOMAIN_RAW_MIN, ipip.DOMAIN_RAW_MAX],
                       "facet": [ipip.FACET_RAW_MIN, ipip.FACET_RAW_MAX]},
        "cohorts": ipip.GROUPS,
        "cohort_n": {g: int(masks[g].sum()) for g in ipip.GROUPS},
        "scales": scale_names,
        "norms": {g: {nm: {"mean": round(norms[(g, nm)][0], 6),
                           "sd": round(norms[(g, nm)][1], 6),
                           "mean_encoded": round(norms[(g, nm)][0], 2),
                           "sd_encoded": round(norms[(g, nm)][1], 2)}
                      for nm in scale_names} for g in ipip.GROUPS},
        "tables": {g: {nm: {
            "raw_min": 60 if len(nm) == 1 else 10,
            "observed_raw_range": list(obs_range[(g, nm)]),
            "pct_exact": [round(float(x), 6) for x in exact[(g, nm)]],
            "pct_quantised": [round(float(x), 6) for x in qval[(g, nm)]],
            "levels": [int(x) for x in quant[(g, nm)]],
        } for nm in scale_names} for g in ipip.GROUPS},
    }
    out_json = os.path.join(ipip.OUT, "pct_tables.json")
    io.open(out_json, "w", encoding="utf-8", newline="\n").write(
        json.dumps(doc, ensure_ascii=False, indent=1))

    write_decoder(os.path.join(ipip.OUT, "decoder.js"))

    # ---- sizes ------------------------------------------------------------
    dec_src = io.open(os.path.join(ipip.OUT, "decoder.js"), encoding="utf-8").read()
    dec_min = minified_decoder_len()
    site = io.open(ipip.SITE, encoding="utf-8").read().encode("utf-8")
    added = (payload + "\n" + dec_src).encode("utf-8")
    br_site = len(brotli.compress(site, quality=11))
    br_both = len(brotli.compress(site + added, quality=11))
    gz_site = len(gzip.compress(site, 9))
    gz_both = len(gzip.compress(site + added, 9))

    print()
    print("=== SIZES ===")
    print("encoded payload raw       : %d bytes" % len(payload))
    print("encoded payload brotli(11): %d bytes" % len(brotli.compress(payload.encode(), quality=11)))
    print("encoded payload gzip(9)   : %d bytes" % len(gzip.compress(payload.encode(), 9)))
    print("decoder.js raw            : %d bytes  (minified-ish %d)" % (len(dec_src.encode()), dec_min))
    print("payload + decoder raw     : %d bytes" % len(added))
    print("site now  raw/brotli      : %d / %d" % (len(site), br_site))
    print("site+added raw/brotli     : %d / %d" % (len(site) + len(added), br_both))
    print("BROTLI DELTA              : %d bytes" % (br_both - br_site))
    print("GZIP DELTA                : %d bytes" % (gz_both - gz_site))
    print("json bytes                : %d" % os.path.getsize(out_json))

    print()
    print("=== TABLE PROPERTIES ===")
    print("cells                     : %d" % total_cells)
    print("empty cells               : %d (interior gaps %d in %d runs, tail %d)"
          % (n_gap_cells + n_tail_cells, n_gap_cells, n_gaps, n_tail_cells))
    print("levels                    : %d" % len(levels))
    print("max quantisation error    : %.6f pct points" % max_qerr)
    print("mean quantisation error   : %.6f pct points" % mean_qerr)
    print("monotone (exact / quant)  : %s / %s" % (mono_exact, mono_quant))
    print("displayed round() changed : %.6f%% of respondent values" % par_round)
    print("displayed trunc() changed : %.6f%% of respondent values" % par_trunc)
    print("dense scan 0..100 @0.0005 : round mismatches %d / trunc mismatches %d of %d"
          % (dense_bad_r, dense_bad_t, len(scan)))

    # ---- respondent-level comparison vs the shipped cubic ----------------
    compare(z, masks, scales, scale_names, exact, qval, rawvals)


def encode(scale_names, levels, spec, quant, norms):
    parts = ["B5PCT1", ",".join(ipip.GROUPS), ",".join(scale_names), ladder_text(spec)]
    nbuf = []
    for g in ipip.GROUPS:
        for nm in scale_names:
            mu, sd = norms[(g, nm)]
            enc_u18(int(round(mu * 100)), nbuf)
            enc_u18(int(round(sd * 100)), nbuf)
    parts.append("".join(nbuf))
    # SCALE-MAJOR: the six cohort rows for one scale sit next to each other and are
    # near-duplicates, which is worth ~200 brotli bytes over cohort-major ordering.
    tbuf = []
    for nm in scale_names:
        for g in ipip.GROUPS:
            q = quant[(g, nm)]
            enc_val(int(q[0]), tbuf)
            for d in np.diff(q):
                enc_val(int(d), tbuf)
    parts.append("".join(tbuf))
    return SEP.join(parts)


DECODER_JS = r"""/* Empirical percentile tables -- decoder.  No dependencies.
   Generated by tools/build_tables.py; do not edit by hand.

   decodePctTables(payload) -> {
     cohorts:[..], scales:[..], levels:Float64Array,
     pct:   {cohort: {scale: Float64Array}},   // index = raw - rawMin
     norms: {cohort: {scale: {mean, sd}}},
     rawMin: s => s.length === 1 ? 60 : 10,
     lookup(cohort, scale, raw) -> percentile
   }                                                                        */
var A = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
var IX = {}; for (var _i = 0; _i < 64; _i++) IX[A[_i]] = _i;

function decodePctTables(payload) {
  var S = payload.split("~");
  if (S[0] !== "B5PCT1") throw new Error("bad payload");
  var cohorts = S[1].split(","), scales = S[2].split(",");

  // ladder "start:step|start:step|..." -> array of representable percentiles.
  // Cell-centred: start + (k + 0.5) * step, so no level ever sits on an integer or
  // a .5 boundary and quantising cannot change Math.round / Math.trunc of the value.
  var spec = S[3].split("|").map(function (t) { var a = t.split(":"); return [+a[0], +a[1]]; });
  var lv = [];
  for (var i = 0; i < spec.length; i++) {
    var st = spec[i][0], sp = spec[i][1], en = i + 1 < spec.length ? spec[i + 1][0] : 100;
    var n = Math.round((en - st) / sp);
    for (var k = 0; k < n; k++) lv.push(Math.round((st + (k + 0.5) * sp) * 1e6) / 1e6);
  }
  var levels = new Float64Array(lv);

  var rawMin = function (s) { return s.length === 1 ? 60 : 10; };
  var cells = function (s) { return s.length === 1 ? 241 : 41; };

  // norms: two fixed-width 18-bit ints per (cohort, scale), value = x/100
  var nS = S[4], np = 0, norms = {};
  var u18 = function () { var v = (IX[nS[np]] << 12) | (IX[nS[np + 1]] << 6) | IX[nS[np + 2]]; np += 3; return v; };
  for (var c = 0; c < cohorts.length; c++) {
    var o = norms[cohorts[c]] = {};
    for (var s = 0; s < scales.length; s++) o[scales[s]] = { mean: u18() / 100, sd: u18() / 100 };
  }

  // tables: per row, first level index then non-negative deltas.
  // 0..47 -> one char; 48..1071 -> two chars (first char index >= 48).
  var tS = S[5], tp = 0, pct = {};
  var val = function () {
    var a = IX[tS[tp++]];
    if (a < 48) return a;
    return 48 + ((a - 48) << 6) + IX[tS[tp++]];
  };
  for (var c2 = 0; c2 < cohorts.length; c2++) pct[cohorts[c2]] = {};
  for (var s2 = 0; s2 < scales.length; s2++) {          // scale-major, cohort inner
    var m = cells(scales[s2]);
    for (var c3 = 0; c3 < cohorts.length; c3++) {
      var out = new Float64Array(m), q = val();
      out[0] = levels[q];
      for (var r = 1; r < m; r++) { q += val(); out[r] = levels[q]; }
      pct[cohorts[c3]][scales[s2]] = out;
    }
  }

  return {
    cohorts: cohorts, scales: scales, levels: levels, pct: pct, norms: norms, rawMin: rawMin,
    lookup: function (cohort, scale, raw) {
      var a = pct[cohort][scale], i = raw - rawMin(scale);
      return a[i < 0 ? 0 : (i >= a.length ? a.length - 1 : i)];
    },
    tscore: function (cohort, scale, raw) {
      var n = norms[cohort][scale];
      return 50 + 10 * (raw - n.mean) / n.sd;
    }
  };
}

if (typeof module !== "undefined" && module.exports) module.exports = { decodePctTables: decodePctTables };
"""


def write_decoder(path):
    io.open(path, "w", encoding="utf-8", newline="\n").write(DECODER_JS)


def minified_decoder_len():
    """crude estimate: strip comments and leading whitespace."""
    out = []
    in_block = False
    for line in DECODER_JS.splitlines():
        s = line.strip()
        if in_block:
            if "*/" in s:
                in_block = False
                s = s.split("*/", 1)[1].strip()
            else:
                continue
        if s.startswith("/*"):
            if "*/" in s:
                s = s.split("*/", 1)[1].strip()
            else:
                in_block = True
                continue
        if s.startswith("//") or not s:
            continue
        out.append(s)
    return len(" ".join(out).encode())


def compare(z, masks, scales, scale_names, exact, qval, rawvals):
    """new empirical percentile vs the shipped cubic+rails map, over real respondents."""
    data = ipip.site_data()
    tot = 0
    s_abs_new_old = 0.0
    s_abs_new_truth = 0.0
    s_abs_old_truth = 0.0
    disp_diff = 0
    band_flip = 0
    worst = (0.0, None)
    per_cohort = {}

    def band(p):
        v = math.trunc(p)
        return 0 if v < 45 else (1 if v <= 55 else 2)

    for g in ipip.GROUPS:
        m = masks[g]
        ns = np.array(data["norms"][g]["ns"], dtype=np.float64)
        ca = cn = 0.0
        for (kind, dom, fno), nm in zip(scales, scale_names):
            v = rawvals[(g, nm)]
            lo = 60 if kind == "domain" else 10
            newp = qval[(g, nm)][v - lo]
            truth = exact[(g, nm)][v - lo]           # exact table == mid-rank truth on occupied cells
            if kind == "domain":
                mu, sd = ns[ipip.DOMAIN_INDEX[dom]], ns[ipip.DOMAIN_INDEX[dom] + 5]
            else:
                a, b = ipip.FACET_OFFSET[dom]
                mu, sd = ns[fno + a], ns[fno + b]
            t = 50.0 + 10.0 * (v - mu) / sd
            oldp = ipip.pct_from_t(t)
            d = np.abs(newp - oldp)
            s_abs_new_old += d.sum()
            s_abs_new_truth += np.abs(newp - truth).sum()
            s_abs_old_truth += np.abs(oldp - truth).sum()
            tot += len(v)
            disp_diff += int((np.round(newp) != np.round(oldp)).sum())
            bn = np.where(np.trunc(newp) < 45, 0, np.where(np.trunc(newp) <= 55, 1, 2))
            bo = np.where(np.trunc(oldp) < 45, 0, np.where(np.trunc(oldp) <= 55, 1, 2))
            band_flip += int((bn != bo).sum())
            ca += d.sum(); cn += len(v)
            mx = float(d.max())
            if mx > worst[0]:
                worst = (mx, (g, nm))
        per_cohort[g] = ca / cn
    print()
    print("=== USER-VISIBLE CHANGE (new empirical vs shipped cubic+rails) ===")
    print("values compared           : %d" % tot)
    print("MAE new vs old            : %.4f pct points" % (s_abs_new_old / tot))
    print("MAE new vs empirical truth: %.4f pct points   (was %.4f for the cubic)"
          % (s_abs_new_truth / tot, s_abs_old_truth / tot))
    print("displayed integer changes : %.2f%% of values" % (100.0 * disp_diff / tot))
    print("level band flips          : %.2f%% of values" % (100.0 * band_flip / tot))
    print("worst single |new-old|    : %.3f  at %s" % worst)
    for g, v in per_cohort.items():
        print("   %-9s MAE new vs old %.4f" % (g, v))


if __name__ == "__main__":
    main()
