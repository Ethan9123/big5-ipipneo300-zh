# -*- coding: utf-8 -*-
"""Response styles (ARS / ERS / MRS) in Johnson's 145,388-person IPIP-NEO-300 norm sample.

Everything is computed in KEYPRESS space: the cached dataset ships the 148 reverse-keyed
items ALREADY recoded, so we undo that first (6 - x on DATA.reversed) to recover what the
respondent actually pressed.  Response styles only exist in keypress space.

Design facts that the analysis leans on (verified below, not assumed):
  * facet slot j (0..29) owns items j, j+30, ..., j+270  ->  EVERY block of 30 items
    contains exactly one item from every facet.  Block is therefore orthogonal to
    construct by design; only item wording and keying vary with position.
  * keying is heavily back-loaded: blocks 1-2 are 100% positive, blocks 9-10 are 100%
    reversed.  Position and keying are confounded at the item level and must be separated.
  * 15 of the 30 facets are exactly balanced (5 positive + 5 reversed).  On those, the
    person's mean keypress cancels the trait between-person and leaves acquiescence.

Outputs: prints a report (also written to out/paradata_styles.txt) and
out/paradata_styles.json.
"""
import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

OUT = ipip.OUT
REPORT = []


def say(s=""):
    REPORT.append(s)
    try:
        print(s)
    except UnicodeEncodeError:
        print(s.encode("ascii", "replace").decode("ascii"))


def hr(title):
    say("")
    say("=" * 78)
    say(title)
    say("=" * 78)


# --------------------------------------------------------------------------- load
z = ipip.load()
items = z["items"].astype(np.int8)                 # (N,300) 1..5, ALREADY recoded
sex, age = z["sex"], z["age"]
N, K = items.shape

data = ipip.site_data()
rev0 = np.array(sorted(data["reversed"]), dtype=np.int64) - 1
is_rev = np.zeros(K, dtype=bool)
is_rev[rev0] = True

kp = items.copy()
kp[:, rev0] = 6 - kp[:, rev0]                      # keypress space
sign = np.where(is_rev, -1.0, 1.0)                 # recoded = sign * centred keypress

pos_idx = np.flatnonzero(~is_rev)
rev_idx = np.flatnonzero(is_rev)
block = np.arange(K) // 30

# facet slot -> label / items
DOM = ipip.DOMAIN_ORDER                            # N,E,O,A,C
facet_names_en, facet_names_zh = {}, {}
for dkey in DOM:
    for i, (zh, en, _d) in enumerate(data["facets"][dkey]):
        facet_names_zh["%s%d" % (dkey, i + 1)] = zh
        facet_names_en["%s%d" % (dkey, i + 1)] = en

slots = list(range(30))
slot_label = {j: "%s%d" % (DOM[j % 5], j // 5 + 1) for j in slots}
slot_items = {j: np.array(ipip.facet_items(j)) for j in slots}
slot_nrev = {j: int(is_rev[slot_items[j]].sum()) for j in slots}
slot_d = {j: 10 - 2 * slot_nrev[j] for j in slots}          # n_pos - n_rev
balanced = [j for j in slots if slot_nrev[j] == 5]

hr("0  设计核查（不是假设，是核对）")
say("样本 %d 人 x %d 题；反向题 %d 道（%.1f%%）" % (N, K, is_rev.sum(), 100 * is_rev.mean()))
say("每 30 题一块，各块反向题数： %s" % [int(is_rev[block == b].sum()) for b in range(10)])
_ok = all(sorted(set(c % 30 for c in range(b * 30, b * 30 + 30))) == list(range(30)) for b in range(10))
_ok = _ok and all(sorted(block[slot_items[j]].tolist()) == list(range(10)) for j in slots)
say("每块是否恰好含全部 30 个面向各 1 题，且每个面向在每块恰好 1 题： %s" % _ok)
say("完全平衡（5 正 5 反）的面向 %d 个： %s"
    % (len(balanced), " ".join(slot_label[j] for j in balanced)))
say("最不平衡： %s"
    % "  ".join("%s(正%d反%d)" % (slot_label[j], 10 - slot_nrev[j], slot_nrev[j])
                for j in sorted(slots, key=lambda x: -abs(slot_d[x]))[:6]))

# --------------------------------------------------------------------------- helpers
kpf = kp.astype(np.float32)


def zscore(x):
    x = np.asarray(x, dtype=np.float64)
    return (x - x.mean()) / x.std(ddof=0)


def corr(a, b):
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else np.nan


def alpha(x):
    """Cronbach alpha for a (N,k) item matrix."""
    k = x.shape[1]
    vi = x.var(axis=0, ddof=1).sum()
    vt = x.sum(axis=1).var(ddof=1)
    return float(k / (k - 1.0) * (1.0 - vi / vt))


# empirical mid-rank percentile inside the site's four sex x age cohorts
masks = ipip.group_masks(sex, age)
COH = ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]
cohort_of = np.full(N, -1, dtype=np.int8)
for ci, c in enumerate(COH):
    cohort_of[masks[c]] = ci
has_coh = cohort_of >= 0


def emp_pct(x):
    """mid-rank empirical percentile within cohort; NaN where cohort unknown."""
    x = np.asarray(x, dtype=np.float64)
    out = np.full(N, np.nan)
    for ci in range(len(COH)):
        m = cohort_of == ci
        v = x[m]
        order = np.argsort(v, kind="mergesort")
        vs = v[order]
        n = len(vs)
        lo = np.searchsorted(vs, vs, side="left")
        hi = np.searchsorted(vs, vs, side="right")
        p = 100.0 * (lo + 0.5 * (hi - lo)) / n
        r = np.empty(n)
        r[order] = p
        out[m] = r
    return out


# the 35 scales
SCALES = []            # (label, item index array)
for d, dkey in enumerate(DOM):
    idx = np.concatenate([slot_items[j] for j in slots if j % 5 == d])
    SCALES.append((dkey, np.sort(idx)))
for j in slots:
    SCALES.append((slot_label[j], slot_items[j]))
SCALE_ORDER = [s[0] for s in SCALES]
scale_items = dict(SCALES)

raw = {lab: items[:, idx].astype(np.float32).sum(axis=1) for lab, idx in SCALES}
pct = {lab: emp_pct(raw[lab]) for lab in SCALE_ORDER}

# ============================================================ 1  style distributions
hr("1  三种作答风格的分布（按键空间）")

ARS_all = kpf.mean(axis=1)                                   # mean keypress, all 300
bal_items = np.concatenate([slot_items[j] for j in balanced])
ARS_bal = kpf[:, np.sort(bal_items)].mean(axis=1)            # trait-cancelling ARS
p45 = (kp >= 4).mean(axis=1)
p12 = (kp <= 2).mean(axis=1)
ERS = ((kp == 1) | (kp == 5)).mean(axis=1)
MRS = (kp == 3).mean(axis=1)
NET = p45 - p12
IRV = kpf.std(axis=1)                                        # within-person SD

STYLES = [
    ("ARS_bal  平衡面向平均按键值(1-5)", ARS_bal),
    ("ARS_all  全部300题平均按键值", ARS_all),
    ("p45      选4或5的比例", p45),
    ("p12      选1或2的比例", p12),
    ("NET      p45-p12 净默许", NET),
    ("ERS      选1或5的比例", ERS),
    ("MRS      选3的比例", MRS),
    ("IRV      被试内标准差", IRV),
]

say("")
say("  指标                              均值    SD     P5     P25    P50    P75    P95")
for lab, v in STYLES:
    q = np.percentile(v, [5, 25, 50, 75, 95])
    say("  %-32s %6.3f %6.3f %6.3f %6.3f %6.3f %6.3f %6.3f"
        % (lab, v.mean(), v.std(ddof=1), q[0], q[1], q[2], q[3], q[4]))

say("")
say("  选项边际分布（全部 145388 x 300 = %d 次作答）：" % (N * K))
cnt = np.array([(kp == v).mean() for v in range(1, 6)])
say("    1=%.2f%%  2=%.2f%%  3=%.2f%%  4=%.2f%%  5=%.2f%%   平均按键值 %.3f"
    % tuple(list(100 * cnt) + [ARS_all.mean()]))

# split-half reliability of each style index (odd vs even facets)
odd_f = [j for j in slots if j % 2 == 0]
even_f = [j for j in slots if j % 2 == 1]
oi = np.sort(np.concatenate([slot_items[j] for j in odd_f]))
ei = np.sort(np.concatenate([slot_items[j] for j in even_f]))
obal = np.sort(np.concatenate([slot_items[j] for j in balanced if j % 2 == 0]))
ebal = np.sort(np.concatenate([slot_items[j] for j in balanced if j % 2 == 1]))


def sb(r):
    return 2 * r / (1 + r)


rel = {}
for lab, a, b in [
    ("ARS_bal", kpf[:, obal].mean(1), kpf[:, ebal].mean(1)),
    ("ERS", ((kp[:, oi] == 1) | (kp[:, oi] == 5)).mean(1), ((kp[:, ei] == 1) | (kp[:, ei] == 5)).mean(1)),
    ("MRS", (kp[:, oi] == 3).mean(1), (kp[:, ei] == 3).mean(1)),
    ("p45", (kp[:, oi] >= 4).mean(1), (kp[:, ei] >= 4).mean(1)),
]:
    r = corr(a, b)
    rel[lab] = {"halfr": r, "sb": sb(r)}
say("")
say("  分半信度（奇/偶面向拆半，Spearman-Brown 校正）：")
for lab in ["ARS_bal", "p45", "ERS", "MRS"]:
    say("    %-8s 半分相关 %.3f  ->  SB 校正 %.3f" % (lab, rel[lab]["halfr"], rel[lab]["sb"]))
say("  读法：ARS 本身就是个噪声很大的量；ERS/MRS 是这份数据里除特质外最稳定的个体差异。")

say("")
say("  三种风格两两相关：")
pairs = [("ARS_bal", ARS_bal), ("NET", NET), ("ERS", ERS), ("MRS", MRS), ("IRV", IRV)]
say("            " + "".join("%9s" % p[0] for p in pairs))
for lab, v in pairs:
    say("    %-8s" % lab + "".join("%9.3f" % corr(v, w) for _, w in pairs))

# ============================================================ 2  ARS contamination
hr("2  ARS 对 35 个量表分的实际污染（干净指数 + 剔除部分-整体重叠）")
say("")
say("干净默许指数的构造：只用 15 个完全平衡面向的题（每个面向 5 正 5 反，被试内取均值时")
say("特质在人与人之间抵消），算某个量表时再把该量表自己的面向从指数里剔除。")


def ars_excluding(exclude_slots):
    keep = [j for j in balanced if j not in exclude_slots]
    idx = np.sort(np.concatenate([slot_items[j] for j in keep]))
    return kpf[:, idx].mean(axis=1), len(keep)


sec2 = {}
say("")
say("  量表   正/反   r(ARS_clean, 原始分)   每 +1SD 默许 = 百分位变化   ARS 方差占比")
for lab, idx in SCALES:
    if lab in DOM:
        excl = set(j for j in slots if j % 5 == DOM.index(lab))
        npos = int((~is_rev[idx]).sum())
    else:
        j0 = [j for j in slots if slot_label[j] == lab][0]
        excl = {j0}
        npos = 10 - slot_nrev[j0]
    a, nkeep = ars_excluding(excl)
    r = corr(a, raw[lab])
    # percentile points per SD of acquiescence
    az = zscore(a)
    ok = has_coh
    b_pct = float(np.polyfit(az[ok], pct[lab][ok], 1)[0])
    sec2[lab] = {"r": r, "r2": r * r, "pct_per_sd": b_pct,
                 "n_pos": npos, "n_rev": len(idx) - npos, "n_ars_facets": nkeep}
    say("  %-5s  %3d/%-3d      %+.3f                    %+6.2f 分位点          %5.2f%%"
        % (lab, npos, len(idx) - npos, r, b_pct, 100 * r * r))

order = sorted([l for l in SCALE_ORDER if l not in DOM], key=lambda l: -abs(sec2[l]["r"]))
say("")
say("  污染最重的 6 个面向： " + "  ".join(
    "%s%s r=%+.3f" % (l, facet_names_zh[l], sec2[l]["r"]) for l in order[:6]))
say("  污染最轻的 6 个面向： " + "  ".join(
    "%s%s r=%+.3f" % (l, facet_names_zh[l], sec2[l]["r"]) for l in order[-6:]))
say("  30 个面向 |r| 的中位数 %.3f，最大 %.3f，方差占比中位 %.2f%%、最大 %.2f%%"
    % (np.median([abs(sec2[l]["r"]) for l in order]),
       max(abs(sec2[l]["r"]) for l in order),
       100 * np.median([sec2[l]["r2"] for l in order]),
       100 * max(sec2[l]["r2"] for l in order)))

# what happens if we actually correct for it
hr("2b  真的做 ARS 校正会改变多少人的档位？")
LO, HI = 30.0, 70.0


def tier(p):
    return np.where(p < LO, 0, np.where(p > HI, 2, 1))


flips = {}
tier_before = {}
tier_after = {}
for lab, idx in SCALES:
    if lab in DOM:
        excl = set(j for j in slots if j % 5 == DOM.index(lab))
    else:
        excl = {[j for j in slots if slot_label[j] == lab][0]}
    a, _ = ars_excluding(excl)
    resid = raw[lab].astype(np.float64).copy()
    for ci in range(len(COH)):
        m = cohort_of == ci
        b = np.polyfit(a[m], resid[m], 1)
        resid[m] = resid[m] - (b[0] * a[m] + b[1])
    p2 = emp_pct(resid)
    t1, t2 = tier(pct[lab]), tier(p2)
    ok = has_coh
    flips[lab] = float((t1[ok] != t2[ok]).mean())
    tier_before[lab], tier_after[lab] = t1, t2

say("")
say("  35 个量表的档位翻转率（低/中/高 切在 30/70）：")
say("    维度： " + "  ".join("%s %.2f%%" % (l, 100 * flips[l]) for l in DOM))
fl = sorted([(flips[l], l) for l in SCALE_ORDER if l not in DOM], reverse=True)
say("    面向最高 5： " + "  ".join("%s %.2f%%" % (l, 100 * v) for v, l in fl[:5]))
say("    面向最低 5： " + "  ".join("%s %.2f%%" % (l, 100 * v) for v, l in fl[-5:]))
say("    面向中位 %.2f%%" % (100 * np.median([v for v, _ in fl])))

combo_before = np.zeros(N, dtype=np.int32)
combo_after = np.zeros(N, dtype=np.int32)
for d, dkey in enumerate(DOM):
    combo_before = combo_before * 3 + tier_before[dkey]
    combo_after = combo_after * 3 + tier_after[dkey]
ok = has_coh
say("  五维组合（243 格）被 ARS 校正改变的人： %.2f%%" % (100 * (combo_before[ok] != combo_after[ok]).mean()))

# reliability of the ARS index itself vs the size of the correction
r_half = rel["ARS_bal"]["halfr"]
say("")
say("  对照：ARS 指数自身的分半信度只有 SB=%.3f。用两个独立半样本的 ARS 分别校正同一个量表，"
    % rel["ARS_bal"]["sb"])
lab_worst = order[0]
j0 = [j for j in slots if slot_label[j] == lab_worst][0]
a1 = kpf[:, np.sort(np.concatenate([slot_items[j] for j in balanced if j % 2 == 0 and j != j0]))].mean(1)
a2 = kpf[:, np.sort(np.concatenate([slot_items[j] for j in balanced if j % 2 == 1 and j != j0]))].mean(1)
tt = []
for a in (a1, a2):
    resid = raw[lab_worst].astype(np.float64).copy()
    for ci in range(len(COH)):
        m = cohort_of == ci
        b = np.polyfit(a[m], resid[m], 1)
        resid[m] = resid[m] - (b[0] * a[m] + b[1])
    tt.append(tier(emp_pct(resid)))
disagree = float((tt[0][ok] != tt[1][ok]).mean())
say("  两者对 %s 的档位判断有 %.2f%% 不一致；而『校正 vs 不校正』只改变 %.2f%%。"
    % (lab_worst, 100 * disagree, 100 * flips[lab_worst]))
say("  即：校正注入的噪声 %s 它去掉的偏差。"
    % ("大于" if disagree > flips[lab_worst] else "小于"))

# ============================================================ 3  balance
hr("3  正反向不平衡 -> ARS 污染更重？")
dvec = np.array([slot_d[j] for j in slots], dtype=np.float64)
rvec = np.array([sec2[slot_label[j]]["r"] for j in slots], dtype=np.float64)
rr = corr(dvec, rvec)
bfit = np.polyfit(dvec, rvec, 1)
say("")
say("  面向配平度 d = 正向题数 - 反向题数（范围 %+d .. %+d）" % (dvec.min(), dvec.max()))
say("  r( d , r(ARS,面向分) ) = %.3f    R² = %.3f    斜率 %.4f / 每单位 d" % (rr, rr * rr, bfit[0]))
say("  截距 %.4f（d=0 时残留的默许相关，理论上应为 0）" % bfit[1])
mb = np.mean([abs(sec2[slot_label[j]]["r"]) for j in slots if slot_d[j] == 0])
mu = np.mean([abs(sec2[slot_label[j]]["r"]) for j in slots if slot_d[j] != 0])
say("")
say("  平衡面向（d=0，n=%d）  平均 |r| = %.3f" % (sum(1 for j in slots if slot_d[j] == 0), mb))
say("  不平衡面向（d≠0，n=%d） 平均 |r| = %.3f   （比值 %.1f 倍）"
    % (sum(1 for j in slots if slot_d[j] != 0), mu, mu / mb if mb > 0 else np.nan))
for dv in sorted(set(int(x) for x in dvec)):
    ls = [slot_label[j] for j in slots if slot_d[j] == dv]
    rs = [sec2[l]["r"] for l in ls]
    say("    d=%+3d  n=%2d   平均 r = %+.3f   %s" % (dv, len(ls), np.mean(rs), " ".join(ls)))

# ============================================================ 4  position effects
hr("4  位置效应：把『第几题』和『反向题密度』拆开")

per_item = {
    "mid": (kp == 3).mean(axis=0),
    "ext": ((kp == 1) | (kp == 5)).mean(axis=0),
    "mean": kpf.mean(axis=0),
    "p45": (kp >= 4).mean(axis=0),
}

say("")
say("4a  按 75 题一段的四分段（原始的、混淆的画面）")
say("     段        题号      反向题占比   选3率     选1或5率   平均按键值")
quart = []
for q in range(4):
    m = (np.arange(K) // 75) == q
    quart.append({
        "q": q + 1, "rev_share": float(is_rev[m].mean()),
        "mid": float(per_item["mid"][m].mean()), "ext": float(per_item["ext"][m].mean()),
        "mean": float(per_item["mean"][m].mean())})
    say("     Q%d     %3d-%3d      %5.1f%%     %5.2f%%    %5.2f%%     %.3f"
        % (q + 1, q * 75 + 1, q * 75 + 75, 100 * is_rev[m].mean(),
           100 * per_item["mid"][m].mean(), 100 * per_item["ext"][m].mean(),
           per_item["mean"][m].mean()))
say("     -> 选3率从 %.2f%% 掉到 %.2f%%（−%.2f 个百分点），但反向题占比同时从 %.0f%% 涨到 %.0f%%。"
    % (100 * quart[0]["mid"], 100 * quart[3]["mid"],
       100 * (quart[0]["mid"] - quart[3]["mid"]),
       100 * quart[0]["rev_share"], 100 * quart[3]["rev_share"]))
say("     这一步不能得结论 —— 两者完全混淆。")

say("")
say("4b  同一张表，按键控方向拆开")
say("     段        正向题                       反向题")
say("              n题   选3率   选1/5率  均值   n题   选3率   选1/5率  均值")
for q in range(4):
    m = (np.arange(K) // 75) == q
    line = "     Q%d   " % (q + 1)
    for sel in (m & ~is_rev, m & is_rev):
        k = int(sel.sum())
        if k == 0:
            line += "   0     -       -       -   "
        else:
            line += " %3d  %5.2f%%  %5.2f%%  %.3f " % (
                k, 100 * per_item["mid"][sel].mean(), 100 * per_item["ext"][sel].mean(),
                per_item["mean"][sel].mean())
    say(line)

say("")
say("4c  题目层回归：选3率 ~ 位置 + 是否反向（n=300 题）")
X = np.column_stack([np.ones(K), np.arange(1, K + 1) / 100.0, is_rev.astype(float)])
for key, nm in [("mid", "选3率"), ("ext", "选1/5率"), ("mean", "平均按键值")]:
    y = per_item[key]
    beta, res, *_ = np.linalg.lstsq(X, y, rcond=None)
    yhat = X @ beta
    ss = ((y - y.mean()) ** 2).sum()
    r2 = 1 - ((y - yhat) ** 2).sum() / ss
    # SE of the position coefficient
    dof = K - 3
    s2 = ((y - yhat) ** 2).sum() / dof
    cov = s2 * np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    say("     %-10s  位置系数 %+.5f ± %.5f / 每100题 (t=%+.2f)   反向题系数 %+.5f ± %.5f   R²=%.3f"
        % (nm, beta[1], se[1], beta[1] / se[1], beta[2], se[2], r2))
say("     注意：题目层残差 SD（= 题目内容差异）是 %.4f，是位置斜率的 %.1f 倍/百题。"
    % (np.std(per_item["mid"] - X @ np.linalg.lstsq(X, per_item["mid"], rcond=None)[0], ddof=3),
       np.std(per_item["mid"] - X @ np.linalg.lstsq(X, per_item["mid"], rcond=None)[0], ddof=3)
       / abs(np.linalg.lstsq(X, per_item["mid"], rcond=None)[0][1])))

say("")
say("4d  只看正向题（152 题，位置 1-%d）—— 键控恒定，位置纯净" % (pos_idx.max() + 1))
for key, nm in [("mid", "选3率"), ("ext", "选1/5率"), ("mean", "平均按键值")]:
    y = per_item[key][pos_idx]
    x = (pos_idx + 1) / 100.0
    b = np.polyfit(x, y, 1)
    yh = np.polyval(b, x)
    r2 = 1 - ((y - yh) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    se = np.sqrt(((y - yh) ** 2).sum() / (len(y) - 2) / ((x - x.mean()) ** 2).sum())
    say("     %-10s 斜率 %+.5f ± %.5f / 每100题  t=%+.2f  R²=%.3f" % (nm, b[0], se, b[0] / se, r2))

say("")
say("     只看反向题（148 题，位置 %d-300）" % (rev_idx.min() + 1))
for key, nm in [("mid", "选3率"), ("ext", "选1/5率"), ("mean", "平均按键值")]:
    y = per_item[key][rev_idx]
    x = (rev_idx + 1) / 100.0
    b = np.polyfit(x, y, 1)
    yh = np.polyval(b, x)
    r2 = 1 - ((y - yh) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    se = np.sqrt(((y - yh) ** 2).sum() / (len(y) - 2) / ((x - x.mean()) ** 2).sum())
    say("     %-10s 斜率 %+.5f ± %.5f / 每100题  t=%+.2f  R²=%.3f" % (nm, b[0], se, b[0] / se, r2))

say("")
say("4e  只在前 150 题内部比较（该段反向题仅 %d 道），正向题 1-75 vs 76-150"
    % int(is_rev[:150].sum()))
a_ = pos_idx[pos_idx < 75]
b_ = pos_idx[(pos_idx >= 75) & (pos_idx < 150)]
for key, nm in [("mid", "选3率"), ("ext", "选1/5率"), ("mean", "平均按键值")]:
    va, vb = per_item[key][a_], per_item[key][b_]
    sp = np.sqrt((va.var(ddof=1) * (len(va) - 1) + vb.var(ddof=1) * (len(vb) - 1)) / (len(va) + len(vb) - 2))
    d = (vb.mean() - va.mean()) / sp
    say("     %-10s 前75 %.4f  vs  76-150 %.4f   差 %+.4f   题目层 Cohen d %+.2f"
        % (nm, va.mean(), vb.mean(), vb.mean() - va.mean(), d))

say("")
say("4f  被试内检验（每人自己跟自己比，正向题：块1-5 vs 块6-8）")
pa = pos_idx[block[pos_idx] <= 4]
pb = pos_idx[block[pos_idx] >= 5]
say("     早段正向题 %d 道，晚段正向题 %d 道" % (len(pa), len(pb)))
for key, fn in [("选3率", lambda s: (kp[:, s] == 3).mean(1)),
                ("选1/5率", lambda s: ((kp[:, s] == 1) | (kp[:, s] == 5)).mean(1)),
                ("平均按键值", lambda s: kpf[:, s].mean(1))]:
    ea, eb = fn(pa), fn(pb)
    dlt = eb - ea
    say("     %-10s 早 %.4f  晚 %.4f  被试内差 %+.4f ± %.4f(SD)   %.1f%% 的人晚段更高"
        % (key, ea.mean(), eb.mean(), dlt.mean(), dlt.std(ddof=1), 100 * (dlt > 0).mean()))

say("")
say("4g  区分力随位置的变化（每块恰好含全部 30 个面向各 1 题，构念完全配平）")
say("     块  题号     n正/n反   校正后题-总相关（正向题） （反向题）   选3率(正) 选3率(反)")
itc = np.zeros(K)
for j in slots:
    ii = slot_items[j]
    tot = items[:, ii].astype(np.float32).sum(1)
    for c in ii:
        rest = tot - items[:, c]
        itc[c] = corr(items[:, c].astype(np.float64), rest.astype(np.float64))
blk_rows = []
for b in range(10):
    m = block == b
    mp, mr = m & ~is_rev, m & is_rev
    row = {"block": b + 1, "n_pos": int(mp.sum()), "n_rev": int(mr.sum()),
           "itc_pos": float(itc[mp].mean()) if mp.sum() else None,
           "itc_rev": float(itc[mr].mean()) if mr.sum() else None,
           "mid_pos": float(per_item["mid"][mp].mean()) if mp.sum() else None,
           "mid_rev": float(per_item["mid"][mr].mean()) if mr.sum() else None}
    blk_rows.append(row)
    say("     %2d  %3d-%3d   %2d/%-2d     %s        %s      %s   %s"
        % (b + 1, b * 30 + 1, b * 30 + 30, row["n_pos"], row["n_rev"],
           "%.3f" % row["itc_pos"] if row["itc_pos"] is not None else "  -  ",
           "%.3f" % row["itc_rev"] if row["itc_rev"] is not None else "  -  ",
           "%5.2f%%" % (100 * row["mid_pos"]) if row["mid_pos"] is not None else "   -  ",
           "%5.2f%%" % (100 * row["mid_rev"]) if row["mid_rev"] is not None else "   -  "))
pb_ = [r for r in blk_rows if r["itc_pos"] is not None]
rb_ = [r for r in blk_rows if r["itc_rev"] is not None]
sl_p = np.polyfit([r["block"] for r in pb_], [r["itc_pos"] for r in pb_], 1)[0]
sl_r = np.polyfit([r["block"] for r in rb_], [r["itc_rev"] for r in rb_], 1)[0]
say("     题-总相关随块的斜率：正向题 %+.4f/块，反向题 %+.4f/块" % (sl_p, sl_r))

say("")
say("4h  位置效应会不会扭曲侧写？")
say("     每个面向在每一块都恰好有 1 道题 —— 位置对 30 个面向的暴露完全相同。")
say("     所以位置效应不改变面向之间的相对高低，只能整体平移 + 改变信度。")
say("     但它和键控绑在一起：反向题全在后段，晚段的任何漂移都会被 6-x 翻成方向性偏差。")

# ============================================================ 5  ERS/MRS -> percentiles
hr("5  ERS / MRS 高的人，35 个百分位怎么系统性偏移")

sec5 = {}
say("")
say("  量表   均值(重编码后每题)  离中点3的距离   ERS每+1SD的百分位变化   MRS每+1SD")
ersz, mrsz = zscore(ERS), zscore(MRS)
ok = has_coh
for lab, idx in SCALES:
    mean_item = float(items[:, idx].astype(np.float32).mean())
    be = float(np.polyfit(ersz[ok], pct[lab][ok], 1)[0])
    bm = float(np.polyfit(mrsz[ok], pct[lab][ok], 1)[0])
    sec5[lab] = {"mean_item": mean_item, "dist": mean_item - 3.0, "ers_pct_per_sd": be,
                 "mrs_pct_per_sd": bm}
    say("  %-5s      %.3f            %+.3f            %+6.2f              %+6.2f"
        % (lab, mean_item, mean_item - 3.0, be, bm))

fl_ = [l for l in SCALE_ORDER if l not in DOM]
dx = np.array([sec5[l]["dist"] for l in fl_])
dy = np.array([sec5[l]["ers_pct_per_sd"] for l in fl_])
b5 = np.polyfit(dx, dy, 1)
r5 = corr(dx, dy)
say("")
say("  30 个面向上：ERS 的百分位位移 ~ 该面向均值离中点的距离")
say("    r = %.3f   R² = %.3f   斜率 %.2f 个百分位点 / 每量表点" % (r5, r5 * r5, b5[0]))
say("    截距 %.2f（均值恰在中点 3 的面向，ERS 不推动百分位）" % b5[1])
dy2 = np.array([sec5[l]["mrs_pct_per_sd"] for l in fl_])
r5m = corr(dx, dy2)
say("    MRS 版本： r = %.3f   R² = %.3f   斜率 %.2f" % (r5m, r5m * r5m, np.polyfit(dx, dy2, 1)[0]))

say("")
say("  ERS 十分位 x 档位计数（每人 30 个面向里判『高』/『中』/『低』的个数）")
tiers30 = np.stack([tier(pct[l]) for l in fl_], axis=1)
nhigh = (tiers30 == 2).sum(1).astype(np.float64)
nmid = (tiers30 == 1).sum(1).astype(np.float64)
nlow = (tiers30 == 0).sum(1).astype(np.float64)
dec = np.full(N, -1)
dec[ok] = np.clip((emp_pct(ERS)[ok] / 10).astype(int), 0, 9)
say("    ERS十分位   ERS均值   判高个数  判中个数  判低个数")
dec_rows = []
for q in range(10):
    m = dec == q
    dec_rows.append({"decile": q + 1, "ers": float(ERS[m].mean()),
                     "high": float(nhigh[m].mean()), "mid": float(nmid[m].mean()),
                     "low": float(nlow[m].mean())})
    say("       D%-2d      %5.1f%%     %5.2f     %5.2f     %5.2f"
        % (q + 1, 100 * ERS[m].mean(), nhigh[m].mean(), nmid[m].mean(), nlow[m].mean()))
say("    r(ERS, 判高个数) = %+.3f      r(ERS, 判低个数) = %+.3f      r(ERS, 判中个数) = %+.3f"
    % (corr(ERS[ok], nhigh[ok]), corr(ERS[ok], nlow[ok]), corr(ERS[ok], nmid[ok])))
say("    r(MRS, 判高个数) = %+.3f      r(MRS, 判低个数) = %+.3f      r(MRS, 判中个数) = %+.3f"
    % (corr(MRS[ok], nhigh[ok]), corr(MRS[ok], nlow[ok]), corr(MRS[ok], nmid[ok])))

# ============================================================ 6  ipsatization
hr("6  被试内 ipsatization（每人减自己的均值、除自己的标准差）前后对比")

pm = kpf.mean(axis=1, keepdims=True)
ps = kpf.std(axis=1, keepdims=True)
ps[ps < 1e-6] = 1e-6
ipz = ((kpf - pm) / ps) * sign.astype(np.float32)      # recoded, ipsatized
raw_items = items.astype(np.float32)

say("")
say("  A) 内部一致性 alpha")
say("     量表    原始     ipsatized    差")
a_before, a_after = {}, {}
for lab, idx in SCALES:
    a1 = alpha(raw_items[:, idx])
    a2 = alpha(ipz[:, idx])
    a_before[lab], a_after[lab] = a1, a2
    if lab in DOM:
        say("     %-6s  %.4f    %.4f     %+.4f" % (lab, a1, a2, a2 - a1))
fa = [l for l in SCALE_ORDER if l not in DOM]
d_alpha = np.array([a_after[l] - a_before[l] for l in fa])
say("     30 个面向： 原始 alpha 中位 %.4f，ipsatized 中位 %.4f，中位变化 %+.4f"
    % (np.median([a_before[l] for l in fa]), np.median([a_after[l] for l in fa]), np.median(d_alpha)))
say("     变好的面向 %d 个，变差的 %d 个；最大改善 %+.4f (%s)，最大恶化 %+.4f (%s)"
    % ((d_alpha > 0).sum(), (d_alpha < 0).sum(), d_alpha.max(), fa[int(np.argmax(d_alpha))],
       d_alpha.min(), fa[int(np.argmin(d_alpha))]))

say("")
say("  B) 区分度：面向之间的相关（越低越能分开）")
F1 = np.stack([raw_items[:, slot_items[j]].sum(1) for j in slots], axis=1)
F2 = np.stack([ipz[:, slot_items[j]].sum(1) for j in slots], axis=1)


def facet_struct(F):
    C = np.corrcoef(F, rowvar=False)
    iu = np.triu_indices(30, 1)
    same = np.array([(slots[i] % 5) == (slots[j] % 5) for i, j in zip(*iu)])
    return {"mean_abs_r": float(np.abs(C[iu]).mean()),
            "within_domain_r": float(C[iu][same].mean()),
            "cross_domain_r": float(C[iu][~same].mean()),
            "cross_domain_absr": float(np.abs(C[iu][~same]).mean()),
            "C": C}


s1, s2 = facet_struct(F1), facet_struct(F2)
say("                       原始      ipsatized")
for k, nm in [("mean_abs_r", "全部 435 对平均|r|"), ("within_domain_r", "同维度内平均 r"),
              ("cross_domain_r", "跨维度平均 r"), ("cross_domain_absr", "跨维度平均|r|")]:
    say("     %-20s %+.4f    %+.4f   (%+.4f)" % (nm, s1[k], s2[k], s2[k] - s1[k]))
say("     区分比 = 同维度内 r / 跨维度|r|： 原始 %.2f  ->  ipsatized %.2f"
    % (s1["within_domain_r"] / s1["cross_domain_absr"], s2["within_domain_r"] / s2["cross_domain_absr"]))


def simple_structure(C):
    w, v = np.linalg.eigh(C)
    idx = np.argsort(w)[::-1][:5]
    L = v[:, idx] * np.sqrt(np.maximum(w[idx], 0))
    # varimax
    L = L.copy()
    d = 0
    for _ in range(200):
        u, s, vt = np.linalg.svd(L.T @ (L ** 3 - L @ np.diag(np.diag(L.T @ L)) / 30.0))
        R = u @ vt
        L = L @ R
        d2 = s.sum()
        if d2 < d * (1 + 1e-9):
            break
        d = d2
    hit = 0
    for j in range(30):
        best = int(np.argmax(np.abs(L[j])))
        hit += 1
        # map component -> majority domain
    # assign each component to the domain with the largest summed |loading|
    domidx = np.array([j % 5 for j in slots])
    comp_dom = []
    for c in range(5):
        sums = [np.abs(L[domidx == d, c]).sum() for d in range(5)]
        comp_dom.append(int(np.argmax(sums)))
    correct = 0
    for j in range(30):
        c = int(np.argmax(np.abs(L[j])))
        if comp_dom[c] == domidx[j]:
            correct += 1
    var5 = float(np.sort(np.linalg.eigvalsh(C))[::-1][:5].sum() / 30.0)
    return correct, var5


c1, v1 = simple_structure(s1["C"])
c2, v2 = simple_structure(s2["C"])
say("     5 因子解：最大载荷落在正确维度上的面向数  原始 %d/30，ipsatized %d/30" % (c1, c2))
say("     前 5 个成分解释的方差比例  原始 %.1f%%，ipsatized %.1f%%" % (100 * v1, 100 * v2))

say("")
say("  C) 与原始分的一致性 / 档位改变")
p_ips = {}
flip_ips = {}
for lab, idx in SCALES:
    sc = ipz[:, idx].sum(1)
    p2 = emp_pct(sc.astype(np.float64))
    p_ips[lab] = p2
    flip_ips[lab] = float((tier(pct[lab])[ok] != tier(p2)[ok]).mean())
rr_ = {lab: corr(raw[lab][ok], ipz[:, scale_items[lab]].sum(1)[ok]) for lab in SCALE_ORDER}
say("     r(原始分, ipsatized分)： 维度 " + " ".join("%s %.3f" % (l, rr_[l]) for l in DOM))
say("     面向中位 %.3f，最低 %.3f (%s)"
    % (np.median([rr_[l] for l in fa]), min(rr_[l] for l in fa),
       fa[int(np.argmin([rr_[l] for l in fa]))]))
say("     档位翻转率： 维度 " + " ".join("%s %.1f%%" % (l, 100 * flip_ips[l]) for l in DOM)
    + "；面向中位 %.1f%%" % (100 * np.median([flip_ips[l] for l in fa])))
cb, ca = np.zeros(N, np.int32), np.zeros(N, np.int32)
for dkey in DOM:
    cb = cb * 3 + tier(pct[dkey])
    ca = ca * 3 + tier(p_ips[dkey])
say("     五维组合被 ipsatization 改变的人： %.1f%%" % (100 * (cb[ok] != ca[ok]).mean()))

say("")
say("  D) 已知效应还在不在（性别差异 d，男-女，>=21 岁）")
mm = masks["M_gte21"]
ff = masks["F_gte21"]


def cohen_d(x, a, b):
    xa, xb = x[a], x[b]
    sp = np.sqrt(((len(xa) - 1) * xa.var(ddof=1) + (len(xb) - 1) * xb.var(ddof=1)) / (len(xa) + len(xb) - 2))
    return float((xa.mean() - xb.mean()) / sp)


say("     量表   原始 d    ipsatized d")
sexd = {}
for lab in DOM + fa:
    d1 = cohen_d(raw[lab].astype(np.float64), mm, ff)
    d2 = cohen_d(ipz[:, scale_items[lab]].sum(1).astype(np.float64), mm, ff)
    sexd[lab] = {"raw": d1, "ips": d2}
    if lab in DOM:
        say("     %-6s %+.3f     %+.3f" % (lab, d1, d2))
say("     30 个面向 |d| 平均： 原始 %.3f，ipsatized %.3f"
    % (np.mean([abs(sexd[l]["raw"]) for l in fa]), np.mean([abs(sexd[l]["ips"]) for l in fa])))

say("")
say("  E) ipsatization 到底去掉了什么")
for nm, v in [("ARS_bal", ARS_bal), ("ERS", ERS), ("MRS", MRS)]:
    before = np.mean([abs(corr(v[ok], raw[l][ok])) for l in fa])
    after = np.mean([abs(corr(v[ok], ipz[:, scale_items[l]].sum(1)[ok])) for l in fa])
    say("     30 个面向与 %s 的平均 |r|： %.3f  ->  %.3f" % (nm, before, after))

# --------------------------------------------------------------------------- dump
res = {
    "n": int(N),
    "design": {
        "n_reversed": int(is_rev.sum()),
        "rev_per_block": [int(is_rev[block == b].sum()) for b in range(10)],
        "balanced_facets": [slot_label[j] for j in balanced],
        "facet_nrev": {slot_label[j]: slot_nrev[j] for j in slots},
    },
    "styles": {lab.split()[0]: {"mean": float(v.mean()), "sd": float(v.std(ddof=1)),
                                "p5": float(np.percentile(v, 5)), "p50": float(np.percentile(v, 50)),
                                "p95": float(np.percentile(v, 95))}
               for lab, v in STYLES},
    "style_reliability": rel,
    "style_corr": {a[0]: {b[0]: corr(a[1], b[1]) for b in pairs} for a in pairs},
    "option_marginals": {str(v + 1): float(cnt[v]) for v in range(5)},
    "ars_contamination": sec2,
    "ars_correction_tier_flip": flips,
    "ars_correction_combo_flip": float((combo_before[ok] != combo_after[ok]).mean()),
    "ars_noise_check": {"scale": lab_worst, "disagreement_between_two_ars_halves": disagree,
                        "flip_vs_nocorrection": flips[lab_worst]},
    "balance": {"r_d_vs_r": rr, "r2": rr * rr, "slope": float(bfit[0]), "intercept": float(bfit[1]),
                "mean_absr_balanced": float(mb), "mean_absr_unbalanced": float(mu)},
    "position": {
        "quartiles": quart,
        "blocks": blk_rows,
        "per_item": {k: v.tolist() for k, v in per_item.items()},
        "itc": itc.tolist(),
        "itc_slope_per_block": {"pos": float(sl_p), "rev": float(sl_r)},
    },
    "ers_mrs_shift": sec5,
    "ers_deciles": dec_rows,
    "ers_dist_regression": {"r": r5, "r2": r5 * r5, "slope": float(b5[0]), "intercept": float(b5[1]),
                            "mrs_r": r5m},
    "ipsatization": {
        "alpha_before": a_before, "alpha_after": a_after,
        "struct_before": {k: v for k, v in s1.items() if k != "C"},
        "struct_after": {k: v for k, v in s2.items() if k != "C"},
        "simple_structure": {"before": c1, "after": c2, "var5_before": v1, "var5_after": v2},
        "r_with_raw": rr_, "tier_flip": flip_ips,
        "combo_flip": float((cb[ok] != ca[ok]).mean()),
        "sex_d": sexd,
    },
}
io.open(os.path.join(OUT, "paradata_styles.json"), "w", encoding="utf-8").write(
    json.dumps(res, ensure_ascii=False, indent=1))
io.open(os.path.join(OUT, "paradata_styles.txt"), "w", encoding="utf-8").write("\n".join(REPORT))
print("\n[wrote out/paradata_styles.json and out/paradata_styles.txt]")
