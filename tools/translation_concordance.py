# -*- coding: utf-8 -*-
"""Compare the site's 300 Chinese items against an independent Mandarin translation.

The site's own translation has no external check of any kind. There is exactly one
independent reference in existence: the Mandarin IPIP-NEO-120 done by five undergraduates
at East China Normal University (supervisor Ya Zhang) and hosted on IPIP. It ships the
English source, the Chinese target, per-facet alphas and per-item item-total correlations
from a real Chinese sample (N=131). Frozen into tools/refs/ecnu_ipipneo120.json.

118 of its 120 English items are byte-identical to items in the site's 300, which makes a
three-way comparison possible with no respondent data of our own:

    English source | site Chinese | ECNU Chinese | ECNU item-total (ZH, N=131)
                                                | Johnson item-total (EN, N=145,388)

What this can show:  an item whose Chinese behaves nothing like its English.
What this cannot show: that the site's translation is valid. Two teams reading the same
English the same way is translation convergence, not construct equivalence. That would
need respondent data, and connect-src 'none' means the site will never have any.

  python tools/translation_concordance.py [--gate]
"""
import io
import json
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "refs", "ecnu_ipipneo120.json")
GATE = "--gate" in sys.argv

ref = json.load(io.open(REF, encoding="utf-8"))
data = ipip.site_data()
rev = set(data["reversed"])
site = {it["id"]: it for it in data["items"]}


def key(s):
    return re.sub(r"[^a-z]", "", s.lower())


by_en = {}
for qid, it in site.items():
    by_en.setdefault(key(it["en"]), []).append(qid)


def facet_of(qid):
    slot = (qid - 1) % 30
    return ipip.DOMAIN_ORDER[slot % 5] + str(slot // 5 + 1)


rows, unmatched = [], []
for r in ref["items"]:
    hits = by_en.get(key(r["en"]))
    if not hits:
        unmatched.append(r)
        continue
    q = hits[0]
    rows.append({"ecnu": r["i"], "qid": q, "en": r["en"], "facet": facet_of(q),
                 "reversed": q in rev, "zh_site": site[q]["zh"], "zh_ecnu": r["zh"],
                 "itc_zh": r["item_total"]})


def hr(t):
    print("\n" + "=" * 78 + "\n" + t + "\n" + "=" * 78)


hr("1  英文原题的逐字匹配")
print("  参照译本 120 题，与本站 300 题英文原题完全相同的：%d" % len(rows))
print("  未命中 %d 条（120 题版改写过的题）：" % len(unmatched))
for r in unmatched:
    print("      ECNU#%-3d %s" % (r["i"], r["en"]))
from collections import Counter  # noqa: E402
cov = Counter(r["facet"] for r in rows)
print("  覆盖子面向 %d/30；每面向题数不足 4 的：%s"
      % (len(cov), {k: v for k, v in sorted(cov.items()) if v != 4}))
print("  其中反向计分题 %d 条" % sum(1 for r in rows if r["reversed"]))

# ---------------------------------------------------------------- 2 item-total profile
# ECNU publishes UNCORRECTED item-total correlations. Reproduce the same statistic on the
# English norm sample using the SAME 4-item facet subsets, so the two are comparable.
z = ipip.load()
items = z["items"].astype(np.float64)
by_facet = {}
for r in rows:
    by_facet.setdefault(r["facet"], []).append(r)
for f, rs in by_facet.items():
    cols = [r["qid"] - 1 for r in rs]
    tot = items[:, cols].sum(axis=1)
    for r in rs:
        r["itc_en"] = float(np.corrcoef(items[:, r["qid"] - 1], tot)[0, 1])

ok = [r for r in rows if r["itc_zh"] is not None]
a = np.array([r["itc_zh"] for r in ok])
b = np.array([r["itc_en"] for r in ok])
res = a - b
zs = (res - res.mean()) / res.std(ddof=1)
for r, s in zip(ok, zs):
    r["z"] = float(s)

hr("2  逐题 item-total：中文样本(N=131) vs 英文常模样本(N=145,388)，同一批 4 题子集")
print("  可比较的题目 %d 条；剖面相关 r = %.3f" % (len(ok), np.corrcoef(a, b)[0, 1]))
print("  中文均值 %.3f   英文均值 %.3f   差值均值 %+.3f   差值标准差 %.3f"
      % (a.mean(), b.mean(), res.mean(), res.std(ddof=1)))
order = np.argsort([r["z"] for r in ok])
print("\n  残差最负的 6 条（中文表现远差于英文）：")
for i in order[:6]:
    r = ok[i]
    print("    #%-4d %-3s z=%+5.2f   中文 %+.3f   英文 %+.3f   %s"
          % (r["qid"], r["facet"], r["z"], r["itc_zh"], r["itc_en"], r["en"]))
    print("           本站译文：%s" % r["zh_site"])
    print("           参照译文：%s" % r["zh_ecnu"])

# ---------------------------------------------------------------- 3 facet alpha
hr("3  子面向 α：中文 4 题版 vs 英文同一 4 题子集 vs 本站 10 题版")
alpha_site = json.loads(
    '{"O1":0.855,"O2":0.811,"O3":0.788,"O4":0.817,"O5":0.852,"O6":0.784,'
    '"C1":0.829,"C2":0.858,"C3":0.801,"C4":0.84,"C5":0.894,"C6":0.846,'
    '"E1":0.89,"E2":0.891,"E3":0.862,"E4":0.725,"E5":0.849,"E6":0.844,'
    '"A1":0.885,"A2":0.789,"A3":0.839,"A4":0.774,"A5":0.778,"A6":0.785,'
    '"N1":0.865,"N2":0.914,"N3":0.916,"N4":0.832,"N5":0.784,"N6":0.86}')


def alpha(x):
    k = x.shape[1]
    return k / (k - 1.0) * (1 - x.var(axis=0, ddof=1).sum() / x.sum(axis=1).var(ddof=1))


country = pd.read_csv(os.path.join(ipip.OUT, "meta.csv"))["country"].to_numpy()
GC = np.isin(country, ["China", "Hong Kong", "Taiwan", "Singapore"])
tab = []
for f, rs in sorted(by_facet.items()):
    c = [r["qid"] - 1 for r in rs]
    tab.append((f, ref["alpha"].get(f), float(alpha(items[:, c])),
                float(alpha(items[GC][:, c])), alpha_site[f], len(c)))
print("  面向  中文4题  英文同4题  英文同4题(华语区)  本站10题  (题数)")
for f, az, ae, ag, asite, n in sorted(tab, key=lambda x: (x[1] if x[1] is not None else 9)):
    print("  %-4s  %s     %.3f        %.3f          %.3f     (%d)"
          % (f, ("%.3f" % az) if az is not None else "  -  ", ae, ag, asite, n))

# The comparison that isolates language from population: same 4 items, Chinese-language
# N=131 sample vs English-language Greater-China sample. Only the 29 facets with all
# 4 items shared are usable; O6 has 2 and is excluded.
cmp4 = [(f, az, ag) for f, az, ae, ag, asite, n in tab if az is not None and n == 4]
diff = np.array([az - ag for _, az, ag in cmp4])
lo = [f for f, az, ag in cmp4 if az < ag - 0.05]
hi = [f for f, az, ag in cmp4 if az > ag + 0.05]
print("\n  中文(N=131) - 英文·华语区(N=%d)，同一 4 题：均值 %+.3f  中位 %+.3f  n=%d"
      % (GC.sum(), diff.mean(), np.median(diff), len(cmp4)))
print("  差超过 0.05 的共 %d 个：中文更低 %d（%s），中文更高 %d（%s）"
      % (len(lo) + len(hi), len(lo), " ".join(lo), len(hi), " ".join(hi)))
print("  —— 就内部一致性而言，中文作答没有比同一批人用英文作答损失什么。")
print("     （这只说明题目内部还抱团，测不出整体偏移或构念不等价。）")

out = {"matched": len(rows), "unmatched": [r["en"] for r in unmatched],
       "facet_coverage": dict(sorted(cov.items())),
       "profile_r": float(np.corrcoef(a, b)[0, 1]),
       "rows": rows, "source": ref["source"], "urls": ref["urls"],
       "sample": ref["sample"], "fetched": ref["fetched"]}
io.open(os.path.join(ipip.OUT, "translation_concordance.json"), "w", encoding="utf-8").write(
    json.dumps(out, ensure_ascii=False, indent=1))
print("\nwrote out/translation_concordance.json")

# ---------------------------------------------------------------- gate
if GATE:
    bad = []
    if len(rows) != 118:
        bad.append("英文逐字匹配数从 118 变成 %d —— 有人改了英文原题" % len(rows))
    if len(cov) != 30:
        bad.append("面向覆盖从 30 掉到 %d" % len(cov))
    worst = min(ok, key=lambda r: r["z"])
    if worst["qid"] != 256:
        bad.append("最差残差不再是 #256 而是 #%d —— 页面上写死的例子要跟着改" % worst["qid"])
    if bad:
        for x in bad:
            print("  x " + x)
        sys.exit(1)
    print("gate: ok")
