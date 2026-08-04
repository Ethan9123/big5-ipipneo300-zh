# -*- coding: utf-8 -*-
"""Probes backing tools/validity_thresholds.py:
  A. is the site's DATA.reversed the real key?  (item-total correlation sign)
  B. does this norm sample still contain straightliners, or was it pre-screened?
     (compare observed max-run distribution against a within-person permutation null)
  C. what do sec/minute/hour encode?
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

rng = np.random.default_rng(20260802)


def max_run_per_option(items):
    n, k = items.shape
    best = np.zeros((n, 6), dtype=np.int16)
    for v in range(1, 6):
        cur = np.zeros(n, dtype=np.int16)
        bv = np.zeros(n, dtype=np.int16)
        for c in range(k):
            cur = np.where(items[:, c] == v, cur + 1, 0)
            np.maximum(bv, cur, out=bv)
        best[:, v] = bv
    return best


def max_run_any(items):
    n, k = items.shape
    cur = np.ones(n, dtype=np.int16)
    best = np.ones(n, dtype=np.int16)
    for c in range(1, k):
        cur = np.where(items[:, c] == items[:, c - 1], cur + 1, 1)
        np.maximum(best, cur, out=best)
    return best


d = ipip.load()
items_rec = d["items"].astype(np.int16)
n = len(items_rec)
rev0 = np.array(ipip.site_data()["reversed"], dtype=int) - 1
items_raw = items_rec.copy()
items_raw[:, rev0] = 6 - items_raw[:, rev0]

# ---- A. keying check -------------------------------------------------------
facet = d["facet_raw"].astype(np.float64)
is_rev = np.zeros(300, dtype=bool)
is_rev[rev0] = True
corr_rec = np.zeros(300)
corr_raw = np.zeros(300)
for c in range(300):
    slot = c % 30
    tot = facet[:, slot] - items_rec[:, c]          # rest-of-facet total
    corr_rec[c] = np.corrcoef(items_rec[:, c].astype(np.float64), tot)[0, 1]
    corr_raw[c] = np.corrcoef(items_raw[:, c].astype(np.float64), tot)[0, 1]
print("A. keying check (item vs rest-of-facet total)")
print("   recoded: all 300 positive? %s   min r = %+.3f  mean r = %+.3f"
      % (bool((corr_rec > 0).all()), corr_rec.min(), corr_rec.mean()))
print("   raw    : %d/%d flagged-reversed items go negative; %d/%d keyed-positive "
      "items stay positive"
      % (int((corr_raw[is_rev] < 0).sum()), int(is_rev.sum()),
         int((corr_raw[~is_rev] > 0).sum()), int((~is_rev).sum())))
print("   reversed items per cycle (30-item block): %s"
      % [int(is_rev[i * 30:(i + 1) * 30].sum()) for i in range(10)])
print("   reversed items per facet slot: min %d max %d"
      % (min(int(is_rev[j::30].sum()) for j in range(30)),
         max(int(is_rev[j::30].sum()) for j in range(30))))

# ---- B. straightliner presence --------------------------------------------
obs_any = max_run_any(items_raw)
obs_opt = max_run_per_option(items_raw)
# within-person permutation null: same 300 responses, order destroyed
perm = items_raw.copy()
idx = np.argsort(rng.random(perm.shape), axis=1)
perm = np.take_along_axis(perm, idx, axis=1)
null_any = max_run_any(perm)
null_opt = max_run_per_option(perm)

print("\nB. straightliners present?  observed vs within-person permutation null")
print("   max-run-ANY   obs: mean %.3f p99 %d p99.9 %d p99.99 %d max %d"
      % (obs_any.mean(), np.percentile(obs_any, 99), np.percentile(obs_any, 99.9),
         np.percentile(obs_any, 99.99), obs_any.max()))
print("   max-run-ANY  null: mean %.3f p99 %d p99.9 %d p99.99 %d max %d"
      % (null_any.mean(), np.percentile(null_any, 99), np.percentile(null_any, 99.9),
         np.percentile(null_any, 99.99), null_any.max()))
print("   n with max-run-ANY >= 15 : obs %d   null %d"
      % (int((obs_any >= 15).sum()), int((null_any >= 15).sum())))
print("   n with max-run-ANY >= 20 : obs %d   null %d"
      % (int((obs_any >= 20).sum()), int((null_any >= 20).sum())))
print("   n with zero variance     : obs %d" % int((items_raw.std(axis=1) == 0).sum()))
RUN_CUT = [0, 6, 9, 10, 14, 9]
for v in range(1, 6):
    print("   opt %d  max obs %2d (null %2d)   n>cut(%2d): obs %6d  null %6d"
          % (v, obs_opt[:, v].max(), null_opt[:, v].max(), RUN_CUT[v],
             int((obs_opt[:, v] > RUN_CUT[v]).sum()),
             int((null_opt[:, v] > RUN_CUT[v]).sum())))

# how much of the option-1 exceedance is chance rather than straightlining?
print("   option-1 run>6: obs %.4f%%  null %.4f%%  -> excess %.4f%%"
      % (100 * (obs_opt[:, 1] > 6).mean(), 100 * (null_opt[:, 1] > 6).mean(),
         100 * ((obs_opt[:, 1] > 6).mean() - (null_opt[:, 1] > 6).mean())))
print("   option-1 share of all responses (raw): %.4f" % (items_raw == 1).mean())
print("   option share raw 1..5: %s"
      % [round(float((items_raw == v).mean()), 4) for v in range(1, 6)])
print("   option share recoded 1..5: %s"
      % [round(float((items_rec == v).mean()), 4) for v in range(1, 6)])

# ---- C. time fields --------------------------------------------------------
sec, mnt, hr = d["sec"].astype(int), d["minute"].astype(int), d["hour"].astype(int)
print("\nC. time fields")
for nm, a, m in (("sec", sec, 60), ("minute", mnt, 60), ("hour", hr, 24)):
    cnt = np.bincount(a, minlength=m)[:m]
    print("   %-6s range %d..%d  distinct %d  flattest/peak bin %d/%d  "
          "chi2 vs uniform %.1f (df %d)"
          % (nm, a.min(), a.max(), len(np.unique(a)), cnt.min(), cnt.max(),
             ((cnt - cnt.mean()) ** 2 / cnt.mean()).sum(), m - 1))
print("   hour histogram: %s" % np.bincount(hr, minlength=24).tolist())
print("   -> a duration field cannot be uniform on 0..59 for both sec and minute "
      "and diurnal on 0..23 for hour; these are wall-clock completion times.")
