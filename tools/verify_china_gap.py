# -*- coding: utf-8 -*-
"""Independently re-derive the China-vs-US norm gap from Johnson's raw IPIP-NEO-120 data.

A research agent reported this gap and proposed changing the site's copy on the strength
of it. Copy that goes in front of users gets re-derived here from the source file, not
taken on report. Layout per DAT120.doc: COUNTRY cols 23-31 (A9), I1-I120 cols 32-151.
Items ship already reverse-recoded, so facet scores are plain sums.
"""
import io
import json
import os
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

DAT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "refs", "IPIP120.dat")
CYC = ["N", "E", "O", "A", "C"]

country, items = [], []
bad = 0
with io.open(DAT, encoding="latin-1") as fh:
    for line in fh:
        line = line.rstrip("\r\n")
        if len(line) < 151:
            bad += 1
            continue
        c = line[22:31].strip()
        raw = line[31:151]
        if len(raw) != 120 or any(ch not in "12345" for ch in raw):
            bad += 1
            continue
        country.append(c)
        items.append([int(ch) for ch in raw])

X = np.array(items, dtype=np.int8)
C = np.array(country)
print("完整作答 %d 行（跳过不完整/含缺失 %d 行）" % (len(X), bad))

top = Counter(C).most_common(12)
print("\n人数最多的国家：")
for k, v in top:
    print("   %-14s %6d" % (k, v))

GC = {"China", "Hong Kong", "Taiwan", "Macau"}
gc = np.isin(C, list(GC))
us = C == "USA"
print("\n大中华区完整作答：%d  （%s）" % (gc.sum(),
      ", ".join("%s %d" % (k, int((C == k).sum())) for k in sorted(GC) if (C == k).sum())))
print("美国完整作答    ：%d" % us.sum())

# IPIP-NEO-120: item i (1-based) -> facet cyc[(i-1)%30]; 4 items per facet
facet_of = [(CYC[(i % 30) % 5], (i % 30) // 5 + 1) for i in range(120)]
codes = ["%s%d" % (d, f) for d in CYC for f in range(1, 7)]
F = np.zeros((len(X), 30), dtype=np.int16)
for j, code in enumerate(codes):
    cols = [i for i in range(120) if "%s%d" % facet_of[i] == code]
    assert len(cols) == 4, (code, len(cols))
    F[:, j] = X[:, cols].sum(axis=1)

print("\n每个面向恰好 4 题：确认。面向分范围 %d-%d" % (F.min(), F.max()))

a, b = F[gc].astype(float), F[us].astype(float)
pooled = np.sqrt(((len(a) - 1) * a.var(0, ddof=1) + (len(b) - 1) * b.var(0, ddof=1))
                 / (len(a) + len(b) - 2))
d = (a.mean(0) - b.mean(0)) / pooled
sdr = a.std(0, ddof=1) / b.std(0, ddof=1)

print("\n" + "=" * 74)
print("大中华区 vs 美国，30 个面向的 Cohen's d（负 = 中国样本更低）")
print("=" * 74)
data = ipip.site_data()
rows = []
for j, code in enumerate(codes):
    nm = data["facets"][code[0]][int(code[1]) - 1][0]
    rows.append((code, nm, float(d[j]), float(sdr[j])))
for code, nm, dd, sr in sorted(rows, key=lambda r: r[2]):
    flag = "  <<<" if abs(dd) > 0.3 else ""
    print("  %-4s %-10s d=%+.3f   SD比=%.3f%s" % (code, nm, dd, sr, flag))

print("\n  平均 |d| = %.3f" % np.abs(d).mean())
print("  平均 SD 比（中/美） = %.3f  （<1 表示中国样本更集中）" % sdr.mean())
print("  |d| > 0.3 的面向数：%d / 30" % (np.abs(d) > 0.3).sum())

json.dump({"n_greater_china": int(gc.sum()), "n_usa": int(us.sum()),
           "mean_abs_d": float(np.abs(d).mean()), "mean_sd_ratio": float(sdr.mean()),
           "facets": [{"code": c, "name": n, "d": dd, "sd_ratio": sr} for c, n, dd, sr in rows]},
          io.open(os.path.join(ipip.OUT, "china_gap_120.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\nwrote out/china_gap_120.json")
