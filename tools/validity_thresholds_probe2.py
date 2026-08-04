# -*- coding: utf-8 -*-
"""Probe 2: run-length histograms (is there a screening cliff?), where the long
runs sit in the questionnaire, and the keying/position confound in the fatigue test."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

rng = np.random.default_rng(20260802)
RUN_CUT = [0, 6, 9, 10, 14, 9]


def runs_and_end(items, v):
    """max run of v per person, and the END column index of that max run."""
    n, k = items.shape
    cur = np.zeros(n, dtype=np.int16)
    best = np.zeros(n, dtype=np.int16)
    end = np.full(n, -1, dtype=np.int16)
    for c in range(k):
        cur = np.where(items[:, c] == v, cur + 1, 0)
        upd = cur > best
        best = np.where(upd, cur, best)
        end = np.where(upd, c, end)
    return best, end


d = ipip.load()
rec = d["items"].astype(np.int16)
rev0 = np.array(ipip.site_data()["reversed"], dtype=int) - 1
raw = rec.copy()
raw[:, rev0] = 6 - raw[:, rev0]
n = len(raw)
is_rev = np.zeros(300, dtype=bool)
is_rev[rev0] = True

perm = np.take_along_axis(raw, np.argsort(rng.random(raw.shape), axis=1), axis=1)

print("=== run-length histograms, RAW string (counts at each max-run length) ===")
print("opt |" + "".join("%7d" % L for L in range(4, 16)) + "   cut")
for v in range(1, 6):
    b, _ = runs_and_end(raw, v)
    h = np.bincount(b, minlength=16)
    print("%3d |" % v + "".join("%7d" % h[L] for L in range(4, 16)) + "   %d" % RUN_CUT[v])
print("\n--- same for the within-person permutation null (no sequence structure) ---")
for v in range(1, 6):
    b, _ = runs_and_end(perm, v)
    h = np.bincount(b, minlength=24)
    print("%3d |" % v + "".join("%7d" % h[L] for L in range(4, 16))
          + "   max %d" % np.nonzero(h)[0].max())

print("\n=== RECODED string maxima (for reference) ===")
for v in range(1, 6):
    b, _ = runs_and_end(rec, v)
    print("  opt %d  max %2d   n>cut(%2d) = %d" % (v, b.max(), RUN_CUT[v],
                                                   int((b > RUN_CUT[v]).sum())))

# where do the flagged option-1 runs sit?
b1, e1 = runs_and_end(raw, 1)
fl = b1 > 6
start = e1[fl] - b1[fl] + 1
print("\n=== the 4350 option-1 flags: where in the 300 items does the run sit? ===")
print("  run START position, quartile blocks 1-75/76-150/151-225/226-300: %s"
      % [int(((start >= a) & (start < b)).sum()) for a, b in
         [(0, 75), (75, 150), (150, 225), (225, 300)]])
print("  share of the run's items that are reverse-keyed: mean %.3f"
      % np.mean([is_rev[s:s + L].mean() for s, L in
                 zip(start[:4000], b1[fl][:4000])]))
print("  median run start item: %d" % (np.median(start) + 1))
print("  reverse-keyed items by quartile block: %s"
      % [int(is_rev[a:b].sum()) for a, b in [(0, 75), (75, 150), (150, 225), (225, 300)]])

# ---- fatigue, disentangled from keying ------------------------------------
mid = raw == 3
print("\n=== midpoint (option 3) rate by cycle, split by item keying ===")
print(" cycle | n_pos n_rev | midpoint%%_pos  midpoint%%_rev  midpoint%%_all")
for i in range(10):
    sl = slice(i * 30, (i + 1) * 30)
    pos = np.where(~is_rev[sl])[0] + i * 30
    rv = np.where(is_rev[sl])[0] + i * 30
    mp = mid[:, pos].mean() * 100 if len(pos) else float("nan")
    mr = mid[:, rv].mean() * 100 if len(rv) else float("nan")
    print("  %4d | %5d %5d |     %6.2f        %6.2f         %6.2f"
          % (i, len(pos), len(rv), mp, mr, mid[:, sl].mean() * 100))

# positive-keyed items only: early (cycles 0-3) vs late (cycles 5-9)
pos_all = np.where(~is_rev)[0]
early = pos_all[pos_all < 120]
late = pos_all[pos_all >= 150]
print("\n  positive-keyed only: cycles 0-3 (n=%d items) midpoint %.2f%%  vs "
      "items>=151 (n=%d) midpoint %.2f%%"
      % (len(early), mid[:, early].mean() * 100, len(late), mid[:, late].mean() * 100))
rev_all = np.where(is_rev)[0]
re_e = rev_all[(rev_all >= 120) & (rev_all < 210)]
re_l = rev_all[rev_all >= 210]
print("  reverse-keyed only: items 121-210 (n=%d) midpoint %.2f%%  vs "
      "items 211-300 (n=%d) midpoint %.2f%%"
      % (len(re_e), mid[:, re_e].mean() * 100, len(re_l), mid[:, re_l].mean() * 100))

# within-facet, within-keying: same facet slot, early vs late repetition
diffs = []
for j in range(30):
    cols = np.arange(j, 300, 30)
    kp = cols[~is_rev[cols]]
    if len(kp) >= 4:
        h = len(kp) // 2
        diffs.append(mid[:, kp[h:]].mean() - mid[:, kp[:h]].mean())
print("  within-facet, positive-keyed items only, later-half minus earlier-half "
      "midpoint rate: mean %+.4f over %d facets (%d with a rise)"
      % (np.mean(diffs), len(diffs), int(np.sum(np.array(diffs) > 0))))
