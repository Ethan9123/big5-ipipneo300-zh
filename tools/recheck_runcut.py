# -*- coding: utf-8 -*-
"""Settle the flag-rate discrepancy: 2.99% vs 7.02% vs 1.19%.

The site's rule (site/index.html, longestRuns + RUN_CUT) runs over answers[1..300] in
ADMINISTRATION order, in the space of what the respondent actually pressed. Flag if the
longest run of consecutive identical option v exceeds RUN_CUT[v].

The dataset ships items already recoded, so "keypress space" = un-recode the 148 reversed
items. The three candidate numbers must come from three different definitions; this prints
all of them side by side so the right one is unambiguous.
"""
import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

RUN_CUT = [0, 6, 9, 10, 14, 9]          # index = option 1..5, as shipped
z = ipip.load()
recoded = z["items"].astype(np.int8)
rev = np.array(sorted(ipip.site_data()["reversed"]), dtype=np.int32) - 1
keypress = recoded.copy()
keypress[:, rev] = 6 - keypress[:, rev]
n = len(recoded)


def longest_runs(mat):
    """for each row, the longest run of each option 1..5, in column order"""
    n_, k = mat.shape
    best = np.zeros((n_, 6), dtype=np.int16)
    cur = np.ones(n_, dtype=np.int16)
    prev = mat[:, 0].astype(np.int16)
    np.maximum.at(best, (np.arange(n_), prev), 1)
    for j in range(1, k):
        v = mat[:, j].astype(np.int16)
        same = v == prev
        cur = np.where(same, cur + 1, 1)
        prev = v
        # best[i, v[i]] = max(best[i, v[i]], cur[i])
        idx = (np.arange(n_), v)
        np.maximum.at(best, idx, cur)
    return best


for label, mat in (("原始键位（还原反向题，= 站点实际规则）", keypress),
                   ("数据集存储值（已重编码，非站点口径）", recoded)):
    best = longest_runs(mat)
    per = {}
    flag_any = np.zeros(n, dtype=bool)
    for v in range(1, 6):
        f = best[:, v] > RUN_CUT[v]
        per[v] = (int(f.sum()), 100.0 * f.mean(), int(best[:, v].max()))
        flag_any |= f
    print("\n" + "=" * 74)
    print(label)
    print("=" * 74)
    print("  总标记率 : %d / %d = %.4f%%" % (flag_any.sum(), n, 100.0 * flag_any.mean()))
    print("  选项  阈值   标记数     标记率    观测到的最长连击")
    for v in range(1, 6):
        c, pct, mx = per[v]
        print("   %d    >%2d   %7d   %7.4f%%        %2d" % (v, RUN_CUT[v], c, pct, mx))

# ---- is the site's own implementation subtly different? ----
print("\n" + "=" * 74)
print("站点实现的一个细节：初始 prev=0，且 best 数组含索引 0")
print("=" * 74)
print("""  site 的 longestRuns：
      let cur = 0, prev = 0;
      for (i=1..300) { if (a[i]===prev) cur++; else { cur=1; prev=a[i]; }
                       if (cur > best[prev]) best[prev] = cur; }
  第一题必然走 else 分支（选项 1..5 不等于 0），所以起始状态无影响。
  与上面的向量化实现等价。""")

# ---- what actually drives the flag: option 1 only? ----
best = longest_runs(keypress)
f1 = best[:, 1] > RUN_CUT[1]
fx = np.zeros(n, dtype=bool)
for v in range(2, 6):
    fx |= best[:, v] > RUN_CUT[v]
print("\n  仅选项 1 触发 : %d (%.4f%%)" % ((f1 & ~fx).sum(), 100.0 * (f1 & ~fx).mean()))
print("  选项 2-5 触发 : %d (%.4f%%)" % (fx.sum(), 100.0 * fx.mean()))
print("  两者都触发    : %d" % (f1 & fx).sum())

# ---- is it a high-score detector? ----
print("\n" + "=" * 74)
print("被标记者是不是「高分者」而不是「乱答者」")
print("=" * 74)
dom = z["domain_raw"].astype(np.float64)
zs = (dom - dom.mean(axis=0)) / dom.std(axis=0, ddof=1)
overall = np.abs(zs).mean(axis=1)              # 画像整体离均程度
flag = best[:, 1] > RUN_CUT[1]
for lab, m in (("被标记", flag), ("未标记", ~flag)):
    print("  %s  n=%6d   |标准分|均值 %.3f" % (lab, m.sum(), overall[m].mean()))
q = np.quantile(overall, [0.5, 0.99])
top1 = overall >= q[1]
mid = (overall >= np.quantile(overall, 0.25)) & (overall <= np.quantile(overall, 0.75))
print("  画像最极端的 1%%：标记率 %.1f%%" % (100.0 * flag[top1].mean()))
print("  中间 50%%      ：标记率 %.1f%%" % (100.0 * flag[mid].mean()))
print("  相关 r(标记, |标准分|均值) = %+.4f"
      % np.corrcoef(flag.astype(float), overall)[0, 1])

json.dump({"keypress_flag_pct": float(100.0 * (best[:, 1:] > np.array(RUN_CUT[1:])).any(axis=1).mean()),
           "per_option": {str(v): float(100.0 * (best[:, v] > RUN_CUT[v]).mean()) for v in range(1, 6)}},
          io.open(os.path.join(ipip.OUT, "recheck_runcut.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
