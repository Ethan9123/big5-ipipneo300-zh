# -*- coding: utf-8 -*-
"""Does the China-vs-US gap replicate across Johnson's two datasets?

Same instrument family, same era, same website, same country labels. If the two
independent estimates of "how far Chinese respondents sit from the US norm" disagree by
a large fraction of the gap itself, the gap cannot be used to correct anyone's score.
"""
import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "refs")
CYC = ["N", "E", "O", "A", "C"]
GC = {"China", "Hong Kong", "Taiwan", "Macau"}
codes = ["%s%d" % (d, f) for d in CYC for f in range(1, 7)]


# Column layout differs between the two files (DAT120.doc / DAT300.doc):
#   120: 31-char prefix, country cols 22:31 (9 wide), items 31:151  -> line length 151
#   300: 33-char prefix, country cols 22:33 (11 wide), items 33:333 -> line length 333
LAYOUT = {120: (22, 31, 31), 300: (22, 33, 33)}


def load(path, n_items, c0, c1, i0):
    cs, xs, bad = [], [], 0
    with io.open(path, encoding="latin-1") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if len(line) < i0 + n_items:
                bad += 1; continue
            raw = line[i0:i0 + n_items]
            if len(raw) != n_items or any(ch not in "12345" for ch in raw):
                bad += 1; continue
            cs.append(line[c0:c1].strip())
            xs.append([int(ch) for ch in raw])
    return np.array(cs), np.array(xs, dtype=np.int8), bad


def facets(X, n_items):
    per = n_items // 30
    F = np.zeros((len(X), 30), dtype=np.int16)
    for j, code in enumerate(codes):
        cols = [i for i in range(n_items)
                if CYC[(i % 30) % 5] == code[0] and (i % 30) // 5 + 1 == int(code[1])]
        assert len(cols) == per
        F[:, j] = X[:, cols].sum(axis=1)
    return F


def gap(path, n_items):
    c0, c1, i0 = LAYOUT[n_items]
    C, X, _ = load(path, n_items, c0, c1, i0)
    F = facets(X, n_items).astype(float)
    a, b = F[np.isin(C, list(GC))], F[C == "USA"]
    pooled = np.sqrt(((len(a) - 1) * a.var(0, ddof=1) + (len(b) - 1) * b.var(0, ddof=1))
                     / (len(a) + len(b) - 2))
    d = (a.mean(0) - b.mean(0)) / pooled
    # SE of Cohen's d
    se = np.sqrt((len(a) + len(b)) / (len(a) * len(b)) + d ** 2 / (2 * (len(a) + len(b))))
    return d, se, len(a), len(b)


d120, se120, na120, nb120 = gap(os.path.join(REF, "IPIP120.dat"), 120)
d300, se300, na300, nb300 = gap(os.path.join(REF, "IPIP300.dat"), 300)
print("IPIP-120: 大中华区 %d vs 美国 %d" % (na120, nb120))
print("IPIP-300: 大中华区 %d vs 美国 %d" % (na300, nb300))

diff = d300 - d120
sed = np.sqrt(se120 ** 2 + se300 ** 2)
zz = diff / sed
data = ipip.site_data()

print("\n" + "=" * 82)
print("同一个「中国偏差」，两份独立数据分别估出来的值")
print("=" * 82)
print("  面向              d(120题)  d(300题)    差    差/抽样误差   符号")
flip = 0
for j, code in enumerate(codes):
    nm = data["facets"][code[0]][int(code[1]) - 1][0]
    s = "一致" if np.sign(d120[j]) == np.sign(d300[j]) else "变号"
    if s == "变号":
        flip += 1
    print("  %-4s %-10s %+7.3f  %+7.3f  %+6.3f   %6.2f      %s"
          % (code, nm, d120[j], d300[j], diff[j], zz[j], s))

print("\n  两份数据的 30 维 d 向量相关 r = %.3f" % np.corrcoef(d120, d300)[0, 1])
print("  符号不一致的面向：%d / 30" % flip)
print("  平均 |分歧| = %.3f SD   （待修正的平均偏差 |d| = %.3f SD）"
      % (np.abs(diff).mean(), np.abs(d120).mean()))
print("  分歧 / 信号 = %.0f%%" % (100 * np.abs(diff).mean() / np.abs(d120).mean()))
print("  分歧超出抽样误差（|z|>1.96）的面向：%d / 30" % (np.abs(zz) > 1.96).sum())

ok = [(codes[j], data["facets"][codes[j][0]][int(codes[j][1]) - 1][0], d120[j], d300[j])
      for j in range(30)
      if np.sign(d120[j]) == np.sign(d300[j]) and min(abs(d120[j]), abs(d300[j])) > 0.3]
print("\n" + "=" * 82)
print("两份数据都又大又同向的面向（|d|>0.3 且符号一致）—— 只有这些能写进页面")
print("=" * 82)
for c, nm, a, b in sorted(ok, key=lambda r: r[2]):
    print("  %-4s %-10s  d120=%+.3f  d300=%+.3f" % (c, nm, a, b))
print("  共 %d / 30 个面向可重复" % len(ok))

json.dump({"r": float(np.corrcoef(d120, d300)[0, 1]), "sign_flips": int(flip),
           "mean_disagreement": float(np.abs(diff).mean()),
           "mean_signal": float(np.abs(d120).mean()),
           "reproducible": [{"code": c, "name": n, "d120": a, "d300": b} for c, n, a, b in ok]},
          io.open(os.path.join(ipip.OUT, "china_gap_replication.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
