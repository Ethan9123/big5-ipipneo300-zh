# -*- coding: utf-8 -*-
"""Follow-ups to paradata_styles.py that break the position/content confound.

The whole sample answered the SAME 300 items in the SAME order, so at the item level
position is perfectly confounded with wording.  But item content contributes an IDENTICAL
constant to every respondent.  Therefore anything computed on BETWEEN-PERSON variation of
a position contrast (its reliability, its correlation with another position contrast, its
subgroup differences) is content-free.  That is the only clean handle on "does position do
something to people", and it is what part B does.

Also here:
  A  a fairer reliability for the acquiescence index + reproducibility of an ARS correction
  C  does ipsatization buy anything measurable (criterion + tier reproducibility)?
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
rng = np.random.default_rng(20260809)


def say(s=""):
    REPORT.append(s)
    try:
        print(s)
    except UnicodeEncodeError:
        print(s.encode("ascii", "replace").decode("ascii"))


def hr(t):
    say("")
    say("=" * 78)
    say(t)
    say("=" * 78)


z = ipip.load()
items = z["items"].astype(np.int8)
sex, age = z["sex"], z["age"]
N, K = items.shape
data = ipip.site_data()
rev0 = np.array(sorted(data["reversed"]), dtype=np.int64) - 1
is_rev = np.zeros(K, bool)
is_rev[rev0] = True
kp = items.copy()
kp[:, rev0] = 6 - kp[:, rev0]
kpf = kp.astype(np.float32)
block = np.arange(K) // 30
sign = np.where(is_rev, -1.0, 1.0).astype(np.float32)

DOM = ipip.DOMAIN_ORDER
slots = list(range(30))
slot_label = {j: "%s%d" % (DOM[j % 5], j // 5 + 1) for j in slots}
slot_items = {j: np.array(ipip.facet_items(j)) for j in slots}
slot_nrev = {j: int(is_rev[slot_items[j]].sum()) for j in slots}
balanced = [j for j in slots if slot_nrev[j] == 5]

masks = ipip.group_masks(sex, age)
COH = ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]
cohort_of = np.full(N, -1, np.int8)
for ci, c in enumerate(COH):
    cohort_of[masks[c]] = ci
ok = cohort_of >= 0


def corr(a, b):
    a = np.asarray(a, np.float64) - np.mean(a)
    b = np.asarray(b, np.float64) - np.mean(b)
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else np.nan


def pcorr(a, b, c):
    """partial correlation of a,b controlling c."""
    ra = a - np.polyval(np.polyfit(c, a, 1), c)
    rb = b - np.polyval(np.polyfit(c, b, 1), c)
    return corr(ra, rb)


def emp_pct(x):
    x = np.asarray(x, np.float64)
    out = np.full(N, np.nan)
    for ci in range(len(COH)):
        m = cohort_of == ci
        v = x[m]
        o = np.argsort(v, kind="mergesort")
        vs = v[o]
        n = len(vs)
        lo = np.searchsorted(vs, vs, "left")
        hi = np.searchsorted(vs, vs, "right")
        p = 100.0 * (lo + 0.5 * (hi - lo)) / n
        r = np.empty(n)
        r[o] = p
        out[m] = r
    return out


def tier(p):
    return np.where(p < 30, 0, np.where(p > 70, 2, 1))


def sb(r, k=2.0):
    return k * r / (1 + (k - 1) * r)


# ================================================================= A  ARS reliability
hr("A  默许指数到底测得准不准（两种拆半，一个偏低一个偏高，都给）")

# A1 content-matched split: inside each balanced facet, 2pos+2rev vs 3pos+3rev
ha, hb = [], []
for j in balanced:
    ii = slot_items[j]
    p = ii[~is_rev[ii]]
    r = ii[is_rev[ii]]
    ha += list(p[:2]) + list(r[:2])
    hb += list(p[2:]) + list(r[2:])
ha, hb = np.sort(np.array(ha)), np.sort(np.array(hb))
a1, a2 = kpf[:, ha].mean(1), kpf[:, hb].mean(1)
r_cm = corr(a1, a2)
# halves are unequal length (60 vs 90); Spearman-Brown to the full 150-item index
say("")
say("  A1 内容配平拆半（每个平衡面向内 2正2反 vs 3正3反，%d 题 vs %d 题）" % (len(ha), len(hb)))
say("     半分相关 %.3f  ->  SB 校正到 150 题 ≈ %.3f" % (r_cm, sb(r_cm, 150.0 / 75.0)))
say("     这一版把『面向内容』固定住，只让题目不同，是默许倾向本身的上界估计。")

# A2 facet-split (from script 1) is the lower bound: content differs between halves
oa = np.sort(np.concatenate([slot_items[j] for j in balanced if j % 2 == 0]))
ob = np.sort(np.concatenate([slot_items[j] for j in balanced if j % 2 == 1]))
r_fs = corr(kpf[:, oa].mean(1), kpf[:, ob].mean(1))
say("")
say("  A2 跨面向拆半（奇/偶面向，%d vs %d 题）：半分相关 %.3f -> SB %.3f"
    % (len(oa), len(ob), r_fs, sb(r_fs)))
say("     这一版要求默许倾向跨内容一致，是下界估计。真值落在 %.2f - %.2f 之间。"
    % (sb(r_fs), sb(r_cm, 2.0)))

# reproducibility of the correction's verdict
hr("A3  ARS 校正的『判决』能不能被独立复现")
raw_A2 = items[:, slot_items[8]].astype(np.float32).sum(1)      # A2 = worst-contaminated
say("")
say("  用 A2（30 个面向里被默许污染最重的一个）做实验：")
base_t = tier(emp_pct(raw_A2.astype(np.float64)))
verd = []
for nm, a in [("ARS-半A", a1), ("ARS-半B", a2)]:
    res = raw_A2.astype(np.float64).copy()
    for ci in range(len(COH)):
        m = cohort_of == ci
        b = np.polyfit(a[m], res[m], 1)
        res[m] -= b[0] * a[m] + b[1]
    verd.append(tier(emp_pct(res)))
ch = [(v[ok] != base_t[ok]) for v in verd]
say("     用半A的默许指数校正 -> %.2f%% 的人档位变了" % (100 * ch[0].mean()))
say("     用半B的默许指数校正 -> %.2f%% 的人档位变了" % (100 * ch[1].mean()))
say("     两次判决不一致的人： %.2f%%" % (100 * (verd[0][ok] != verd[1][ok]).mean()))
both = (ch[0] & ch[1]).mean()
either = (ch[0] | ch[1]).mean()
say("     两次都判『该翻』的人 %.2f%%，至少一次判『该翻』的 %.2f%%  ->  复现率 %.1f%%"
    % (100 * both, 100 * either, 100 * both / either))
say("     读法：即使在最该校正的那个面向上，也有近一半的『翻转』换一批题就不成立了。")

# ================================================================= B  content-free drift
hr("B  位置效应的『无内容混淆』检验")
say("")
say("  逻辑：全样本题序相同 -> 题目内容对每个人贡献同一个常数 -> 位置对比的")
say("  人与人之间的差异、相关、分组差，完全不含内容混淆。")

pos_e = np.array([c for c in range(K) if not is_rev[c] and block[c] <= 4])
pos_l = np.array([c for c in range(K) if not is_rev[c] and block[c] >= 5])
rev_e = np.array([c for c in range(K) if is_rev[c] and block[c] <= 4])
rev_l = np.array([c for c in range(K) if is_rev[c] and block[c] >= 8])
say("")
say("  早/晚题组： 正向 早%d题(块1-5) 晚%d题(块6-8) ；反向 早%d题(块3-5) 晚%d题(块9-10)"
    % (len(pos_e), len(pos_l), len(rev_e), len(rev_l)))


def mid(sel):
    return (kp[:, sel] == 3).mean(1)


def ext(sel):
    return ((kp[:, sel] == 1) | (kp[:, sel] == 5)).mean(1)


def mn(sel):
    return kpf[:, sel].mean(1)


drift = {}
for nm, fn in [("选3率", mid), ("选1/5率", ext), ("平均按键值", mn)]:
    dp = fn(pos_l) - fn(pos_e)
    dr = fn(rev_l) - fn(rev_e)
    lvl = fn(np.arange(K))
    r_raw = corr(dp, dr)
    r_par = pcorr(dp.astype(np.float64), dr.astype(np.float64), lvl.astype(np.float64))
    # null: same-position pseudo-contrast with matched item counts
    pe = rng.permutation(pos_e)
    re_ = rng.permutation(np.concatenate([rev_e, rev_l]))
    dpn = fn(pe[:len(pos_l)]) - fn(pe[len(pos_l):])
    drn = fn(re_[:len(rev_l)]) - fn(re_[len(rev_l):])
    rn = corr(dpn, drn)
    rn_par = pcorr(dpn.astype(np.float64), drn.astype(np.float64), lvl.astype(np.float64))
    drift[nm] = {"d_pos": float(dp.mean()), "d_rev": float(dr.mean()),
                 "r_raw": r_raw, "r_partial": r_par, "r_null": rn, "r_null_partial": rn_par,
                 "dp": dp, "dr": dr}
    say("")
    say("  %s ：正向题 晚-早 = %+.4f ；反向题 晚-早 = %+.4f" % (nm, dp.mean(), dr.mean()))
    say("     r(正向漂移, 反向漂移) = %+.3f   控制总体水平后 = %+.3f" % (r_raw, r_par))
    say("     同位置伪对比的零假设基线            = %+.3f   控制后 = %+.3f" % (rn, rn_par))

say("")
say("  B2  漂移分数本身有没有信度（把晚段题拆两半，看同一人两个漂移估计的相关）")
for nm, fn in [("选3率", mid), ("平均按键值", mn)]:
    la, lb = pos_l[0::2], pos_l[1::2]
    ea, eb = pos_e[0::2], pos_e[1::2]
    d1 = fn(la) - fn(ea)
    d2 = fn(lb) - fn(eb)
    r = corr(d1, d2)
    say("     %-10s 两个独立半估计的相关 %.3f  ->  SB 校正 %.3f" % (nm, r, sb(r)))

say("")
say("  B3  分组差（内容常数对所有组相同，组间差 = 纯粹的人 x 位置交互）")
grp = [("男 vs 女", masks["M_lt21"] | masks["M_gte21"], masks["F_lt21"] | masks["F_gte21"]),
       ("<21 vs >=21", masks["N_lt21"], masks["N_gte21"])]
ERS = ((kp == 1) | (kp == 5)).mean(1)
q = np.percentile(ERS, [25, 75])
grp.append(("ERS 低四分位 vs 高四分位", ERS <= q[0], ERS >= q[1]))
# a crude effort proxy: longest same-option run
run = np.zeros(N, np.int16)
cur = np.ones(N, np.int16)
for c in range(1, K):
    same = kp[:, c] == kp[:, c - 1]
    cur = np.where(same, cur + 1, 1).astype(np.int16)
    run = np.maximum(run, cur)
q2 = np.percentile(run, [50, 90])
grp.append(("最长同选项串 <=中位 vs >=P90", run <= q2[0], run >= q2[1]))

for nm, fn in [("选3率", mid), ("平均按键值", mn)]:
    dp = drift[nm]["dp"]
    say("     -- %s 的正向题漂移（晚-早）" % nm)
    for gn, ga, gb in grp:
        xa, xb = dp[ga], dp[gb]
        sp = np.sqrt(((len(xa) - 1) * xa.var(ddof=1) + (len(xb) - 1) * xb.var(ddof=1))
                     / (len(xa) + len(xb) - 2))
        say("        %-28s %+.4f vs %+.4f   差 %+.4f   d=%+.3f"
            % (gn, xa.mean(), xb.mean(), xb.mean() - xa.mean(), (xb.mean() - xa.mean()) / sp))

say("")
say("  B4  『晚段整体漂移』这个平均值本身有多可靠？（题目抽样误差）")
for nm, fn in [("选3率", mid), ("平均按键值", mn)]:
    per_item_e = np.array([fn(np.array([c])).mean() for c in pos_e])
    per_item_l = np.array([fn(np.array([c])).mean() for c in pos_l])
    se = np.sqrt(per_item_e.var(ddof=1) / len(pos_e) + per_item_l.var(ddof=1) / len(pos_l))
    d = per_item_l.mean() - per_item_e.mean()
    say("     %-10s 晚-早 = %+.4f，按题目抽样算的 SE = %.4f，t = %+.2f"
        % (nm, d, se, d / se))
say("     （题目层 SE 用的是同键控组内题目之间的离散度：这才是『换一批同类题目还会不会")
say("      看到同样的漂移』的正确误差项，而不是 14 万人给出的那个虚假的小 SE。）")

# ================================================================= C  ipsatization payoff
hr("C  ipsatization 有没有买到任何可测量的东西")
pm = kpf.mean(1, keepdims=True)
ps = kpf.std(1, keepdims=True)
ps[ps < 1e-6] = 1e-6
ipz = ((kpf - pm) / ps) * sign
raw_items = items.astype(np.float32)

F_raw = np.stack([raw_items[:, slot_items[j]].sum(1) for j in slots], 1)
F_ips = np.stack([ipz[:, slot_items[j]].sum(1) for j in slots], 1)

say("")
say("  C1  外部效标（这份数据只有性别和年龄两个外部变量）")
sub = (sex == 1) | (sex == 2)


def multiR(X, y, m):
    Xm = np.column_stack([np.ones(m.sum()), X[m]])
    yy = y[m].astype(np.float64)
    beta, *_ = np.linalg.lstsq(Xm, yy, rcond=None)
    yh = Xm @ beta
    return float(np.sqrt(1 - ((yy - yh) ** 2).sum() / ((yy - yy.mean()) ** 2).sum()))


for nm, y in [("性别", (sex == 2).astype(np.float64)), ("年龄", age.astype(np.float64))]:
    r1 = multiR(F_raw, y, sub)
    r2 = multiR(F_ips, y, sub)
    say("     30 个面向预测%s的多重 R： 原始 %.4f  ->  ipsatized %.4f  (%+.4f)"
        % (nm, r1, r2, r2 - r1))

say("")
say("  C2  档位的可复现性（把每个面向的 10 题拆成两个 5 题平行式，看两式给出的档位一致率）")
odd_b = [j for j in range(10) if j % 2 == 0]
res_c2 = {}
for nm, M in [("原始", raw_items), ("ipsatized", ipz)]:
    agree, agree_d = [], []
    for j in slots:
        ii = slot_items[j]
        a = M[:, ii[0::2]].sum(1).astype(np.float64)
        b = M[:, ii[1::2]].sum(1).astype(np.float64)
        ta, tb = tier(emp_pct(a)), tier(emp_pct(b))
        agree.append(float((ta[ok] == tb[ok]).mean()))
    res_c2[nm] = agree
    say("     %-10s 30 个面向的两式档位一致率： 平均 %.3f  中位 %.3f  最低 %.3f"
        % (nm, np.mean(agree), np.median(agree), np.min(agree)))
say("     逐面向差（ipsatized − 原始）： 平均 %+.4f，变好的 %d 个 / 变差的 %d 个"
    % (np.mean(np.array(res_c2["ipsatized"]) - np.array(res_c2["原始"])),
       int((np.array(res_c2["ipsatized"]) > np.array(res_c2["原始"])).sum()),
       int((np.array(res_c2["ipsatized"]) < np.array(res_c2["原始"])).sum())))

say("")
say("  C3  五维组合的两式一致率（本站真正展示的那个东西）")
for nm, M in [("原始", raw_items), ("ipsatized", ipz)]:
    ca = np.zeros(N, np.int32)
    cb = np.zeros(N, np.int32)
    for d, dk in enumerate(DOM):
        ii = np.sort(np.concatenate([slot_items[j] for j in slots if j % 5 == d]))
        a = M[:, ii[0::2]].sum(1).astype(np.float64)
        b = M[:, ii[1::2]].sum(1).astype(np.float64)
        ca = ca * 3 + tier(emp_pct(a))
        cb = cb * 3 + tier(emp_pct(b))
    say("     %-10s 五维组合一致率 %.3f" % (nm, float((ca[ok] == cb[ok]).mean())))

# ================================================================= D  what ERS is
hr("D  ERS 到底是风格还是特质（它和分数的相关有多少是『真的』）")
say("")
say("  ERS 与 30 个面向分的相关（重编码空间）：")
ERSz = (ERS - ERS.mean()) / ERS.std()
rs = [(corr(ERS[ok], raw_items[:, slot_items[j]].sum(1)[ok]), slot_label[j]) for j in slots]
rs.sort(reverse=True)
say("     最正 5： " + "  ".join("%s %+.3f" % (l, r) for r, l in rs[:5]))
say("     最负 5： " + "  ".join("%s %+.3f" % (l, r) for r, l in rs[-5:]))
say("     平均 r = %+.3f，平均 |r| = %.3f" % (np.mean([r for r, _ in rs]), np.mean([abs(r) for r, _ in rs])))
mean_item = np.array([raw_items[:, slot_items[j]].mean() for j in slots])
rvec = np.array([r for r, _ in sorted(rs, key=lambda t: t[1])])
lab_sorted = sorted([l for _, l in rs])
mi = {slot_label[j]: raw_items[:, slot_items[j]].mean() for j in slots}
xx = np.array([mi[l] - 3 for l in lab_sorted])
say("     r( 面向均值离中点 , r(ERS,面向分) ) = %.3f   R² = %.3f"
    % (corr(xx, rvec), corr(xx, rvec) ** 2))
say("     -> ERS 与分数的相关几乎完全由『这个面向平均答得离中点多远』决定，")
say("        而不是由面向的内容决定。这就是它是风格而非特质的证据。")

io.open(os.path.join(OUT, "paradata_styles2.txt"), "w", encoding="utf-8").write("\n".join(REPORT))
res = {
    "ars_reliability": {"content_matched_half_r": r_cm, "content_matched_sb150": sb(r_cm, 2.0),
                        "facet_split_half_r": r_fs, "facet_split_sb": sb(r_fs)},
    "ars_correction_reproducibility": {"scale": "A2", "flip_halfA": float(ch[0].mean()),
                                       "flip_halfB": float(ch[1].mean()),
                                       "both": float(both), "either": float(either),
                                       "reproducibility": float(both / either)},
    "drift": {k: {kk: vv for kk, vv in v.items() if kk not in ("dp", "dr")}
              for k, v in drift.items()},
    "ips_tier_agreement": res_c2,
}
io.open(os.path.join(OUT, "paradata_styles2.json"), "w", encoding="utf-8").write(
    json.dumps(res, ensure_ascii=False, indent=1))
print("\n[wrote out/paradata_styles2.{txt,json}]")
