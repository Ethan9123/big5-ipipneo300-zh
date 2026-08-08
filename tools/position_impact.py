# -*- coding: utf-8 -*-
"""Does the position drift actually move the numbers the site prints?

Johnson interleaves: facet j takes items j+1, j+31, ..., j+271 -- exactly one per block of
30. So position is balanced across facets by design. This checks whether that balance
really neutralises the drift, by scoring each facet twice: once from its 5 early items,
once from its 5 late items, and comparing.

Both halves are scored in RECODED space (the dataset's native form), so the comparison is
of trait estimates, not keypresses.
"""
import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

z = ipip.load()
items = z["items"].astype(np.float64)      # recoded
n = len(items)
data = ipip.site_data()
rev = set(data["reversed"])

LV = ["N", "E", "O", "A", "C"]
print("样本 %d 人" % n)

rows = []
for slot in range(30):
    cols = [i * 30 + slot for i in range(10)]        # one per block, ascending position
    early, late = cols[:5], cols[5:]
    dom = LV[slot % 5]
    fno = slot // 5 + 1
    name = data["facets"][dom][fno - 1][0]
    e = items[:, early].sum(axis=1)
    l = items[:, late].sum(axis=1)
    nrev_e = sum(1 for c in early if c + 1 in rev)
    nrev_l = sum(1 for c in late if c + 1 in rev)
    r = float(np.corrcoef(e, l)[0, 1])
    rows.append({
        "facet": "%s%d" % (dom, fno), "name": name,
        "early_mean": float(e.mean()), "late_mean": float(l.mean()),
        "diff": float(l.mean() - e.mean()),
        "early_sd": float(e.std(ddof=1)), "late_sd": float(l.std(ddof=1)),
        "rev_early": nrev_e, "rev_late": nrev_l,
        "halves_r": r,
    })

print("\n" + "=" * 88)
print("每个面向：前 5 题（早位置）vs 后 5 题（晚位置），均在 recode 空间")
print("=" * 88)
print("  面向  名称        反向数     前半均值  后半均值    差值    前半SD  后半SD   两半相关")
for x in sorted(rows, key=lambda r: -abs(r["diff"]))[:12]:
    print("  %-5s %-10s %d/5→%d/5   %6.2f   %6.2f  %+6.2f    %5.2f   %5.2f    %.3f"
          % (x["facet"], x["name"][:10], x["rev_early"], x["rev_late"],
             x["early_mean"], x["late_mean"], x["diff"],
             x["early_sd"], x["late_sd"], x["halves_r"]))
print("  ... (按 |差值| 排序，只显示最大的 12 个)")

d = np.array([x["diff"] for x in rows])
sd_e = np.array([x["early_sd"] for x in rows])
sd_l = np.array([x["late_sd"] for x in rows])
rr = np.array([x["halves_r"] for x in rows])
print("\n  30 个面向汇总：")
print("    后半 − 前半 的均值差：均值 %+.3f 分，绝对值中位 %.3f，最大 %+.3f（%s）"
      % (d.mean(), np.median(np.abs(d)), d[np.argmax(np.abs(d))],
         rows[int(np.argmax(np.abs(d)))]["facet"]))
print("    后半 SD / 前半 SD：均值 %.3f  （>1 表示后段作答更分散，与极端化一致）"
      % (sd_l / sd_e).mean())
print("    两半相关（5 题 vs 5 题）：中位 %.3f" % np.median(rr))

# ---- what does that mean in the units the site prints? ----
print("\n" + "=" * 88)
print("换算成站点显示的百分位")
print("=" * 88)
facet_raw, sex, age = z["facet_raw"], z["sex"], z["age"]
tables = json.load(io.open(os.path.join(ipip.OUT, "pct_tables.json"), encoding="utf-8"))
cohort = np.char.add(np.where(sex == 1, "M", "F"),
                     np.where(age < 21, "_lt21", "_gte21"))

# a 10-item facet score built as 2x the early half vs 2x the late half, mapped through
# the shipped tables -- crude but it puts the drift on the printed scale
shifts = []
for slot in range(30):
    dom, fno = LV[slot % 5], slot // 5 + 1
    key = "%s%d" % (dom, fno)
    cols = [i * 30 + slot for i in range(10)]
    e2 = np.clip(np.rint(items[:, cols[:5]].sum(axis=1) * 2), 10, 50).astype(int)
    l2 = np.clip(np.rint(items[:, cols[5:]].sum(axis=1) * 2), 10, 50).astype(int)
    pe = np.empty(n); pl = np.empty(n)
    for g in ("M_lt21", "M_gte21", "F_lt21", "F_gte21"):
        m = cohort == g
        arr = np.asarray(tables["tables"][g][key]["pct_quantised"], dtype=np.float64)
        lo = tables["tables"][g][key]["raw_min"]
        pe[m] = arr[np.clip(e2[m] - lo, 0, len(arr) - 1)]
        pl[m] = arr[np.clip(l2[m] - lo, 0, len(arr) - 1)]
    shifts.append({"facet": key, "mean_shift": float((pl - pe).mean()),
                   "mean_abs": float(np.abs(pl - pe).mean())})

ms = np.array([s["mean_shift"] for s in shifts])
ma = np.array([s["mean_abs"] for s in shifts])
print("  只用后半 5 题 vs 只用前半 5 题，百分位的系统性偏移：")
print("    30 个面向的平均偏移：%+.2f 个百分位（负=后半分数偏低）" % ms.mean())
print("    偏移绝对值最大的面向：%s %+.2f" % (shifts[int(np.argmax(np.abs(ms)))]["facet"],
                                            ms[int(np.argmax(np.abs(ms)))]))
print("    个人层面的平均绝对差：%.1f 个百分位" % ma.mean())
print("\n  对照：站点已知的噪声水平——面向百分位的 95%% 置信区间宽约 53 个百分位。")

json.dump({"facets": rows, "percentile_shift": shifts},
          io.open(os.path.join(ipip.OUT, "position_impact.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\nwrote out/position_impact.json")
