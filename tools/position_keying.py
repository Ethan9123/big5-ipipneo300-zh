# -*- coding: utf-8 -*-
"""Is there a position x keying confound in IPIP-NEO-300?

The worry: reverse-keyed items are back-loaded (blocks 9-10 are 100% reversed, blocks 1-2
are 100% positive). If respondents drift as they tire, and the late items are all reversed,
the drift stops being noise and becomes a DIRECTIONAL bias after recoding:

  drift toward agreement, late  ->  higher keypress on reversed items  ->  lower facet score
  drift toward disagreement     ->  higher facet score

The dataset ships items already recoded, so everything here is done in KEYPRESS space:
un-recode the 148 reversed items first, then look at raw button presses by position.

Note on design: facet j gets items j+1, j+31, ..., j+271 -- exactly one per block of 30.
So position is perfectly balanced ACROSS facets. The confound is not which facet, it is
which keying sits at which position.
"""
import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

z = ipip.load()
items_recoded = z["items"].astype(np.int16)          # as stored: already recoded
data = ipip.site_data()
rev = np.array(sorted(data["reversed"]), dtype=np.int32) - 1   # 0-based columns

# back to what the respondent actually pressed
keypress = items_recoded.copy()
keypress[:, rev] = 6 - keypress[:, rev]

n, K = keypress.shape
is_rev = np.zeros(K, dtype=bool)
is_rev[rev] = True
block = np.arange(K) // 30                            # 0..9

print("样本 %d 人 x %d 题" % (n, K))
print("每 30 题一块，各块反向题数：",
      [int(is_rev[block == b].sum()) for b in range(10)])

# ---------------------------------------------------------------- 1 mean keypress
print("\n" + "=" * 74)
print("1  平均按键值（1-5），按位置块 x 键控方向")
print("=" * 74)
print("  块   题号范围     正向题                反向题")
print("                  n题  均值   选3率      n题  均值   选3率")
rows = []
for b in range(10):
    m = block == b
    line = "  %2d   %3d-%3d " % (b + 1, b * 30 + 1, b * 30 + 30)
    rec = {"block": b + 1}
    for lab, sel in (("pos", m & ~is_rev), ("rev", m & is_rev)):
        k = int(sel.sum())
        if k == 0:
            line += "    -      -       -   "
            rec[lab] = None
            continue
        vals = keypress[:, sel]
        mean = float(vals.mean())
        mid = float((vals == 3).mean())
        line += "  %3d  %.3f  %5.1f%%  " % (k, mean, 100 * mid)
        rec[lab] = {"n_items": k, "mean": mean, "mid_rate": mid}
    print(line)
    rows.append(rec)

# ---------------------------------------------------------------- 2 clean trends
print("\n" + "=" * 74)
print("2  分离位置效应与键控效应")
print("=" * 74)
pos_blocks = [r for r in rows if r["pos"]]
rev_blocks = [r for r in rows if r["rev"]]
print("  正向题只存在于第 %d-%d 块；反向题只存在于第 %d-%d 块"
      % (pos_blocks[0]["block"], pos_blocks[-1]["block"],
         rev_blocks[0]["block"], rev_blocks[-1]["block"]))


def trend(seq, key):
    x = np.array([r["block"] for r in seq], dtype=float)
    y = np.array([r[key]["mean"] for r in seq])
    w = np.array([r[key]["n_items"] for r in seq], dtype=float)
    # weight by item count so a block with 1 item does not dominate
    b, a = np.polyfit(x, y, 1, w=np.sqrt(w))
    ym = np.array([r[key]["mid_rate"] for r in seq])
    bm, _ = np.polyfit(x, ym, 1, w=np.sqrt(w))
    return b, bm


bp, bmp = trend(pos_blocks, "pos")
br, bmr = trend(rev_blocks, "rev")
print("\n  正向题：每往后一块，平均按键 %+.4f，选 3 率 %+.4f%%/块" % (bp, 100 * bmp))
print("  反向题：每往后一块，平均按键 %+.4f，选 3 率 %+.4f%%/块" % (br, 100 * bmr))
print("\n  解读：若两者斜率同号且相近 -> 是纯位置效应（与题目内容无关）")
print("        若两者斜率异号     -> 更像是题目内容/键控差异，不是疲劳")

# overlap region: blocks where BOTH keyings exist -> the only place they can be compared
both = [r for r in rows if r["pos"] and r["rev"]]
print("\n  两种键控同时存在的块：%s" % [r["block"] for r in both])
if len(both) >= 3:
    bp2, bmp2 = trend(both, "pos")
    br2, bmr2 = trend(both, "rev")
    print("  只在重叠区内：正向 %+.4f/块，反向 %+.4f/块（按键值）" % (bp2, br2))
    print("                正向 %+.4f%%/块，反向 %+.4f%%/块（选 3 率）" % (100 * bmp2, 100 * bmr2))

# ---------------------------------------------------------------- 3 within-person
print("\n" + "=" * 74)
print("3  被试内检验：同一个人，前段 vs 后段（只看正向题，剔除键控混淆）")
print("=" * 74)
pos_cols = np.where(~is_rev)[0]
pos_block = block[pos_cols]
early = pos_cols[pos_block <= 1]      # blocks 1-2: 60 items, all positive
mid_ = pos_cols[(pos_block >= 2) & (pos_block <= 4)]
late = pos_cols[pos_block >= 5]
print("  正向题分段： 第1-2块 %d 题 / 第3-5块 %d 题 / 第6块以后 %d 题"
      % (len(early), len(mid_), len(late)))
for lab, cols in (("前段", early), ("中段", mid_), ("后段", late)):
    v = keypress[:, cols]
    print("    %s  均值 %.3f   选3率 %5.2f%%   选1或5率 %5.2f%%   人内SD %.3f"
          % (lab, v.mean(), 100 * (v == 3).mean(),
             100 * ((v == 1) | (v == 5)).mean(), v.std(axis=1).mean()))

# same for reversed items, which only exist late
rev_cols = np.where(is_rev)[0]
rev_block = block[rev_cols]
print("\n  反向题分段（只存在于中后段）：")
for lab, sel in (("第3-5块", (rev_block >= 2) & (rev_block <= 4)),
                 ("第6-8块", (rev_block >= 5) & (rev_block <= 7)),
                 ("第9-10块", rev_block >= 8)):
    cols = rev_cols[sel]
    v = keypress[:, cols]
    print("    %-8s %3d 题  均值 %.3f   选3率 %5.2f%%   选1或5率 %5.2f%%"
          % (lab, len(cols), v.mean(), 100 * (v == 3).mean(),
             100 * ((v == 1) | (v == 5)).mean()))

json.dump({"blocks": rows,
           "trend_positive_mean_per_block": bp,
           "trend_reversed_mean_per_block": br,
           "trend_positive_mid_per_block": bmp,
           "trend_reversed_mid_per_block": bmr},
          io.open(os.path.join(ipip.OUT, "position_keying.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\nwrote out/position_keying.json")
