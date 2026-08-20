# -*- coding: utf-8 -*-
"""How much does O6 Liberalism cost the Openness score for a Chinese respondent?

Two of O6's ten items ask which way you vote in a liberal/conservative contest, one asks
about tax money for artists. Those have little purchase in mainland China -- not a
translation problem, an item-content problem. This asks: if a facet's items were answered
at chance, how far does the parent domain move?

Everything is computed on the norm sample, in the site's own printed units.
"""
import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

rng = np.random.default_rng(20260809)
z = ipip.load()
items = z["items"].astype(np.int16)          # recoded
facet_raw, domain_raw = z["facet_raw"], z["domain_raw"]
sex, age = z["sex"], z["age"]
n = len(items)
data = ipip.site_data()
tables = json.load(io.open(os.path.join(ipip.OUT, "pct_tables.json"), encoding="utf-8"))
cohort = np.char.add(np.where(sex == 1, "M", "F"),
                     np.where(age < 21, "_lt21", "_gte21"))
LVD = ipip.DOMAIN_ORDER                      # N,E,O,A,C


def pct(raw, key):
    out = np.empty(len(raw))
    for g in ("M_lt21", "M_gte21", "F_lt21", "F_gte21"):
        m = cohort == g
        t = tables["tables"][g][key]
        arr = np.asarray(t["pct_quantised"], dtype=np.float64)
        out[m] = arr[np.clip(raw[m] - t["raw_min"], 0, len(arr) - 1)]
    return out


def hr(t):
    print("\n" + "=" * 74 + "\n" + t + "\n" + "=" * 74)


hr("1  开放性六个面向对总分的贡献")
o_idx = LVD.index("O")
base_dom_pct = pct(domain_raw[:, o_idx], "O")
print("  开放性总分 = 六个面向原始分之和（每个面向 10 题，1-5 分，即 10-50）")
print("  面向        均值    标准差   与总分相关   占总分方差")
o_slots = [ipip.facet_slot("O", f) for f in range(1, 7)]
tot = domain_raw[:, o_idx].astype(np.float64)
for f, slot in zip(range(1, 7), o_slots):
    v = facet_raw[:, slot].astype(np.float64)
    r = np.corrcoef(v, tot)[0, 1]
    share = v.var(ddof=1) / tot.var(ddof=1)
    name = data["facets"]["O"][f - 1][0]
    print("  O%d %-8s %6.2f  %6.2f     %.3f       %5.1f%%"
          % (f, name, v.mean(), v.std(ddof=1), r, 100 * share))

hr("2  如果 O6 自由主义整个面向是随机作答，开放性百分位偏多少")
o6 = ipip.facet_slot("O", 6)
o6_cols = ipip.facet_items(o6)
for label, mk in [
    ("整个 O6 随机（10 题）", lambda: rng.integers(1, 6, size=(n, 10))),
    ("整个 O6 全选中间档", lambda: np.full((n, 10), 3)),
    ("只有 3 道政治题随机", None),
]:
    alt = items.copy()
    if mk is not None:
        alt[:, o6_cols] = mk()
    else:
        pol = [c for c in o6_cols if (c + 1) in (28, 148, 178)]
        alt[:, pol] = rng.integers(1, 6, size=(n, len(pol)))
    f2, d2 = ipip.facet_and_domain_raw(alt.astype(np.int32))
    p2 = pct(d2[:, o_idx], "O")
    d = p2 - base_dom_pct
    print("  %-22s 开放性百分位：平均偏移 %+5.2f，平均绝对变化 %5.2f，|变化|>10 的占 %4.1f%%"
          % (label, d.mean(), np.abs(d).mean(), 100 * (np.abs(d) > 10).mean()))

hr("3  三道政治题在常模样本里本身的表现")
for q in (28, 148, 178, 118, 268):
    col = q - 1
    v = items[:, col].astype(np.float64)
    others = [c for c in o6_cols if c != col]
    rest = items[:, others].sum(axis=1).astype(np.float64)
    r = np.corrcoef(v, rest)[0, 1]
    en = data["items"][col]["en"]
    zh = data["items"][col]["zh"]
    print("  #%3d  校正题总相关 %.3f   %s" % (q, r, zh))
    print("        %s" % en)

hr("4  对照：把同样的破坏施加到其他面向")
print("  （整个面向随机作答后，其所属维度百分位的平均绝对变化）")
rows = []
for dom in ipip.DOMAIN_ORDER:
    di = LVD.index(dom)
    base = pct(domain_raw[:, di], dom)
    for f in range(1, 7):
        slot = ipip.facet_slot(dom, f)
        alt = items.copy()
        alt[:, ipip.facet_items(slot)] = rng.integers(1, 6, size=(n, 10))
        _, d2 = ipip.facet_and_domain_raw(alt.astype(np.int32))
        d = np.abs(pct(d2[:, di], dom) - base).mean()
        rows.append((dom + str(f), data["facets"][dom][f - 1][0], d))
rows.sort(key=lambda x: -x[2])
print("  影响最大的 6 个：")
for c, nm, d in rows[:6]:
    print("    %-4s %-10s %5.2f 个百分位" % (c, nm, d))
print("  影响最小的 6 个：")
for c, nm, d in rows[-6:]:
    print("    %-4s %-10s %5.2f 个百分位" % (c, nm, d))
o6row = [r for r in rows if r[0] == "O6"][0]
print("\n  O6 自由主义排在第 %d / 30 位，平均 %.2f 个百分位"
      % (rows.index(o6row) + 1, o6row[2]))

json.dump({"ranking": [{"facet": c, "name": nm, "mean_abs_shift": d} for c, nm, d in rows]},
          io.open(os.path.join(ipip.OUT, "o6_impact.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\nwrote out/o6_impact.json")
