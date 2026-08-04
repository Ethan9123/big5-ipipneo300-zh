# -*- coding: utf-8 -*-
"""Where do the 148 reverse-keyed items actually sit in Johnson's item order?

This matters: the site's careless-responding screen flags long runs of the same option,
and if the reverse-keyed items are back-loaded, a consistent responder will legitimately
press the same key many times in a row near the end.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

rev = set(ipip.site_data()["reversed"])
print("reverse-keyed items: %d of 300\n" % len(rev))

print("per block of 30 items:")
for b in range(10):
    lo, hi = b * 30 + 1, (b + 1) * 30
    k = sum(1 for q in range(lo, hi + 1) if q in rev)
    bar = "#" * k
    print("  items %3d-%3d : %2d/30  %s" % (lo, hi, k, bar))

print("\ncontiguous all-reversed tail:")
tail = 300
while tail >= 1 and tail in rev:
    tail -= 1
print("  items %d-300 are ALL reverse-keyed  (%d items)" % (tail + 1, 300 - tail))

print("\ncontiguous all-positive head:")
head = 1
while head <= 300 and head not in rev:
    head += 1
print("  items 1-%d are ALL keyed-positive  (%d items)" % (head - 1, head - 1))

print("\nlongest stretch with no reverse-keyed item, and longest all-reversed stretch:")
best_pos = best_rev = cur_pos = cur_rev = 0
for q in range(1, 301):
    if q in rev:
        cur_rev += 1; cur_pos = 0
    else:
        cur_pos += 1; cur_rev = 0
    best_pos, best_rev = max(best_pos, cur_pos), max(best_rev, cur_rev)
print("  longest run of keyed-positive items: %d" % best_pos)
print("  longest run of reverse-keyed items : %d" % best_rev)

# What does that imply for the site's run-length screen?
print("\nimplication for the site's validity screen:")
print("  A respondent who is genuinely LOW on the traits measured by the reverse-keyed")
print("  tail answers '很不符合' honestly and repeatedly there. The longest all-reversed")
print("  stretch is %d items, so an entirely sincere protocol can produce a same-option" % best_rev)
print("  run far above the option-1 cut of 6 without any careless responding.")
