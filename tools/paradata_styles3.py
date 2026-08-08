# -*- coding: utf-8 -*-
"""Controls for paradata_styles2.py + the decision-relevant reordering estimate.

E1  the B3 subgroup-drift result needs a control: groups differ in TRAIT level, and the
    late items have different content, so a group difference in a position contrast is
    NOT automatically a position effect.  Build a same-position pseudo-contrast with
    matched item counts and see how big a group difference pure content produces.
E2  if we disperse the 63-item reverse block (the earlier proposal), how much would
    facet scores move?  Propagate the item-level position slope with an item bootstrap.
E3  per-item option distribution vs position, option by option, within keying.
"""
import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

REPORT = []
rng = np.random.default_rng(7)


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
DOM = ipip.DOMAIN_ORDER
slots = list(range(30))
slot_label = {j: "%s%d" % (DOM[j % 5], j // 5 + 1) for j in slots}
slot_items = {j: np.array(ipip.facet_items(j)) for j in slots}
masks = ipip.group_masks(sex, age)
COH = ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]
cohort_of = np.full(N, -1, np.int8)
for ci, c in enumerate(COH):
    cohort_of[masks[c]] = ci
ok = cohort_of >= 0


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


def d_between(x, a, b):
    xa, xb = x[a], x[b]
    sp = np.sqrt(((len(xa) - 1) * xa.var(ddof=1) + (len(xb) - 1) * xb.var(ddof=1))
                 / (len(xa) + len(xb) - 2))
    return float((xb.mean() - xa.mean()) / sp)


# ============================================================== E1 subgroup control
hr("E1  『分组漂移差』的对照：同位置伪对比能造出多大的组间差？")
say("")
say("  警告（对 paradata_styles2 的 B3 的自我更正）：位置对比的组间差 **不是** 内容无关的。")
say("  内容对每个人贡献同一个常数，所以它不产生人与人之间的协方差 —— B2 的信度检验因此")
say("  是干净的。但不同群体在这些题目的**内容**上本来就有不同的特质水平，所以组间均值差")
say("  会把『晚段题恰好考的东西上男女不同』误读成『男女的位置漂移不同』。下面做对照。")

pos_e = np.array([c for c in range(K) if not is_rev[c] and block[c] <= 4])
pos_l = np.array([c for c in range(K) if not is_rev[c] and block[c] >= 5])
M = (sex == 1)
F = (sex == 2)
Y = masks["N_lt21"]
A = masks["N_gte21"]
ERS = ((kp == 1) | (kp == 5)).mean(1)
q = np.percentile(ERS, [25, 75])
GRPS = [("男 vs 女", M, F), ("<21 vs >=21", Y, A), ("ERS低四分位 vs 高四分位", ERS <= q[0], ERS >= q[1])]


def mid(sel):
    return (kp[:, sel] == 3).mean(1)


def mn(sel):
    return kpf[:, sel].mean(1)


for nm, fn in [("选3率", mid), ("平均按键值", mn)]:
    real = fn(pos_l) - fn(pos_e)
    say("")
    say("  %s" % nm)
    say("     分组                      真实漂移的 d     同位置伪对比 d（200 次抽样）")
    null_d = {g[0]: [] for g in GRPS}
    for _ in range(200):
        p = rng.permutation(pos_e)
        pseudo = fn(p[:len(pos_l)]) - fn(p[len(pos_l):])
        for gn, ga, gb in GRPS:
            null_d[gn].append(d_between(pseudo, ga, gb))
    for gn, ga, gb in GRPS:
        dr = d_between(real, ga, gb)
        nd = np.array(null_d[gn])
        say("     %-24s %+.3f          均值 %+.3f  |d| 的 P95 = %.3f"
            % (gn, dr, nd.mean(), np.percentile(np.abs(nd), 95)))
say("")
say("  读法：只要真实漂移的 |d| 落在伪对比 |d| 的 P95 以内，就没有证据说这个组的位置漂移不同。")

# ============================================================== E2 reordering
hr("E2  把第 238-300 题那 63 道连续反向题打散，分数会动多少？")
say("")
say("  做法：用题目层模型 平均按键值_i = a + b*位置_i + c*反向_i 里的 b（位置斜率），")
say("  把每道题从旧位置搬到新位置，按 b*Δ位置/100 预测按键值变化，再翻回重编码空间累加到")
say("  面向分上。b 的不确定性用**题目自助法**（对题目重抽样）传播 —— 误差项必须是题目之间")
say("  的离散度，不是 14 万人。")

y_mean = kpf.mean(0)
X = np.column_stack([np.ones(K), np.arange(1, K + 1) / 100.0, is_rev.astype(float)])
b_hat = np.linalg.lstsq(X, y_mean, rcond=None)[0]
say("")
say("  点估计 b = %+.4f 按键点 / 每 100 题（反向题系数 %+.4f）" % (b_hat[1], b_hat[2]))

# proposed reordering: interleave so that reverse-item density is uniform.
# keep each facet's block membership (facet j owns one item per block) -- we只重排块内顺序
# 与块之间的整体位置，做法：按 (是否反向) 交错排列全部 300 题。
order_new = np.empty(K, dtype=np.int64)
pos_ids = np.flatnonzero(~is_rev)
rev_ids = np.flatnonzero(is_rev)
# stripe them: p r p r ... so reverse density is ~49.3% everywhere
seq = []
pi = ri = 0
for t in range(K):
    take_rev = (ri / max(1, len(rev_ids))) <= (pi / max(1, len(pos_ids)))
    if take_rev and ri < len(rev_ids):
        seq.append(rev_ids[ri]); ri += 1
    elif pi < len(pos_ids):
        seq.append(pos_ids[pi]); pi += 1
    else:
        seq.append(rev_ids[ri]); ri += 1
seq = np.array(seq)
newpos = np.empty(K, np.int64)
newpos[seq] = np.arange(1, K + 1)
oldpos = np.arange(1, K + 1)
dpos = (newpos - oldpos) / 100.0
say("  重排方案：正/反向题条纹式交错，反向题密度处处 ≈ 49%%。")
say("  反向题的平均位置从 %.0f 变成 %.0f；正向题从 %.0f 变成 %.0f"
    % (oldpos[is_rev].mean(), newpos[is_rev].mean(), oldpos[~is_rev].mean(), newpos[~is_rev].mean()))

facet_sd = np.array([items[:, slot_items[j]].astype(np.float32).sum(1).std(ddof=1) for j in slots])


def facet_shift(b):
    """predicted raw-score shift per facet (recoded space)."""
    dk = b * dpos                       # keypress change per item
    drec = np.where(is_rev, -dk, dk)    # recoded change
    return np.array([drec[slot_items[j]].sum() for j in slots])


sh = facet_shift(b_hat[1])
boot = []
for _ in range(2000):
    idx = rng.integers(0, K, K)
    bb = np.linalg.lstsq(X[idx], y_mean[idx], rcond=None)[0][1]
    boot.append(bb)
boot = np.array(boot)
lo, hi = np.percentile(boot, [2.5, 97.5])
say("  b 的题目自助 95%% CI = [%+.4f, %+.4f]" % (lo, hi))
say("")
say("  预测的面向原始分位移（30 个面向）：")
say("     点估计 平均 %+.3f 原始分（= %.3f 个面向 SD）；最大 %+.3f"
    % (sh.mean(), np.abs(sh / facet_sd).mean(), sh[np.argmax(np.abs(sh))]))
for nm, bv in [("下界", lo), ("上界", hi)]:
    s2 = facet_shift(bv)
    say("     %s 平均 %+.3f 原始分（%.3f 个面向 SD）" % (nm, s2.mean(), np.abs(s2 / facet_sd).mean()))


def pct_against(x, ref_sorted):
    """percentile of x against a FIXED reference distribution (the existing norm table)."""
    lo_ = np.searchsorted(ref_sorted, x, "left")
    hi_ = np.searchsorted(ref_sorted, x, "right")
    return 100.0 * (lo_ + 0.5 * (hi_ - lo_)) / len(ref_sorted)


def flip_rate(shift):
    """Respondents move by `shift` but are still scored against the UNSHIFTED norm.

    Facet raw scores are integers, so a bare shift of +0.18 would push everybody past
    their entire tie group and manufacture a huge flip rate out of nothing.  Add a fixed
    U(-.5,.5) continuity jitter to both the reference and the shifted score so the
    comparison is between two genuinely continuous distributions.
    """
    out = []
    g = np.random.default_rng(11)
    for j in slots:
        r = items[:, slot_items[j]].astype(np.float32).sum(1).astype(np.float64)
        r = r + g.uniform(-0.5, 0.5, size=N)
        ch = []
        for ci in range(len(COH)):
            m = cohort_of == ci
            ref = np.sort(r[m])
            t1 = tier(pct_against(r[m], ref))
            t2 = tier(pct_against(r[m] + shift[j], ref))
            ch.append(t1 != t2)
        out.append(float(np.concatenate(ch).mean()))
    return out


say("")
say("  受试者被搬动、但仍然对着**没搬动**的旧常模计分 —— 这才是真实的代价：")
flips = flip_rate(sh)
say("  按点估计的位移，面向档位翻转率： 平均 %.2f%%，最大 %.2f%%"
    % (100 * np.mean(flips), 100 * np.max(flips)))
sh_hi = facet_shift(lo if abs(lo) > abs(hi) else hi)
flips_hi = flip_rate(sh_hi)
say("  按 95%% CI 的坏端（b=%+.4f），翻转率： 平均 %.2f%%，最大 %.2f%%"
    % (lo if abs(lo) > abs(hi) else hi, 100 * np.mean(flips_hi), 100 * np.max(flips_hi)))
say("  参考：重新在新题序下采一份常模就完全消掉这个代价 —— 但我们采不到，所以这是上界。")

# ============================================================== E3 option x position
hr("E3  逐题选项分布随位置怎么变（按选项分开，键控固定）")
rate = np.stack([(kp == v).mean(0) for v in range(1, 6)], 0)   # (5,300)
say("")
say("  正向题（152 道，位置 1-237）：每 100 题的斜率")
for v in range(5):
    x = (np.flatnonzero(~is_rev) + 1) / 100.0
    y = rate[v][~is_rev]
    b = np.polyfit(x, y, 1)
    yh = np.polyval(b, x)
    se = np.sqrt(((y - yh) ** 2).sum() / (len(y) - 2) / ((x - x.mean()) ** 2).sum())
    say("     选 %d ： 均值 %5.2f%%   斜率 %+.4f ± %.4f   t=%+.2f" % (v + 1, 100 * y.mean(), b[0], se, b[0] / se))
say("  反向题（148 道，位置 69-300）：")
for v in range(5):
    x = (np.flatnonzero(is_rev) + 1) / 100.0
    y = rate[v][is_rev]
    b = np.polyfit(x, y, 1)
    yh = np.polyval(b, x)
    se = np.sqrt(((y - yh) ** 2).sum() / (len(y) - 2) / ((x - x.mean()) ** 2).sum())
    say("     选 %d ： 均值 %5.2f%%   斜率 %+.4f ± %.4f   t=%+.2f" % (v + 1, 100 * y.mean(), b[0], se, b[0] / se))

say("")
say("  被试内版本（每人自己的选项使用率，正向题 块1-5 vs 块6-8）：")
for v in range(5):
    a = (kp[:, pos_e] == v + 1).mean(1)
    b_ = (kp[:, pos_l] == v + 1).mean(1)
    say("     选 %d ： 早 %5.2f%%  晚 %5.2f%%  差 %+.2f 个百分点"
        % (v + 1, 100 * a.mean(), 100 * b_.mean(), 100 * (b_.mean() - a.mean())))

io.open(os.path.join(ipip.OUT, "paradata_styles3.txt"), "w", encoding="utf-8").write("\n".join(REPORT))
json.dump({"b_position": float(b_hat[1]), "b_ci": [float(lo), float(hi)],
           "facet_shift_point": sh.tolist(), "facet_sd": facet_sd.tolist(),
           "tier_flip_point": flips, "tier_flip_ci_bad": flips_hi},
          io.open(os.path.join(ipip.OUT, "paradata_styles3.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n[wrote out/paradata_styles3.{txt,json}]")
