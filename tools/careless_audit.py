# -*- coding: utf-8 -*-
"""Adversarial re-test of the proposed careless-responding detectors.

Question asked of every proposal:  on OUR data, under OUR constraints, does it survive?
"""
import io
import json
import os
import sys

import numpy as np

TOOLS = r"C:\Users\kids1\Downloads\bigfive\tools"
sys.path.insert(0, TOOLS)
import ipip  # noqa: E402

OUT = []


def say(s=""):
    OUT.append(s)
    try:
        print(s)
    except UnicodeEncodeError:
        print(s.encode("ascii", "replace").decode("ascii"))


def hr(t):
    say("")
    say("=" * 78)
    say(t)
    say("=" * 78)


rng = np.random.default_rng(11)
z = ipip.load()
items = z["items"].astype(np.int8)          # keyed / scoring space (already recoded)
sex, age = z["sex"], z["age"]
N, K = items.shape
data = ipip.site_data()
rev0 = np.array(sorted(data["reversed"]), dtype=np.int64) - 1
raw = items.copy()
raw[:, rev0] = 6 - raw[:, rev0]             # the actual key the respondent pressed
keyed = items.astype(np.float32)

masks = ipip.group_masks(sex, age)
COH = ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]
cohort_of = np.full(N, -1, np.int8)
for ci, c in enumerate(COH):
    cohort_of[masks[c]] = ci
ok = cohort_of >= 0
slot_items = {j: np.array(ipip.facet_items(j)) for j in range(30)}
DOM = ipip.DOMAIN_ORDER

say("N = %d, items = %d, reversed = %d, usable cohort rows = %d" % (N, K, len(rev0), ok.sum()))


def emp_pct(x):
    x = np.asarray(x, np.float64)
    out = np.full(len(x), np.nan)
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
    return (p >= 30).astype(np.int8) + (p >= 70).astype(np.int8)


def rowcorr(A, B):
    """Pearson r per row between two (N,m) matrices. NaN where a row is constant."""
    A = A.astype(np.float64)
    B = B.astype(np.float64)
    a = A - A.mean(1, keepdims=True)
    b = B - B.mean(1, keepdims=True)
    num = (a * b).sum(1)
    den = np.sqrt((a * a).sum(1) * (b * b).sum(1))
    out = np.full(len(A), np.nan)
    good = den > 1e-9
    out[good] = num[good] / den[good]
    return out


# ---------------------------------------------------------------- 0  RUN_CUT baseline
hr("0  reproduce the shipped RUN_CUT flag")
RUN_CUT = [0, 6, 9, 10, 14, 9]


def longest_runs(a):
    """a: (N,300) int8 of raw key presses -> (N,6) longest run per option."""
    n = a.shape[0]
    best = np.zeros((n, 6), np.int16)
    cur = np.ones(n, np.int16)
    prev = a[:, 0].astype(np.int16)
    np.put_along_axis(best, prev[:, None].astype(np.intp), np.ones((n, 1), np.int16), 1)
    for i in range(1, a.shape[1]):
        same = a[:, i] == prev
        cur = np.where(same, cur + 1, 1)
        prev = a[:, i].astype(np.int16)
        idx = prev[:, None].astype(np.intp)
        curbest = np.take_along_axis(best, idx, 1)[:, 0]
        np.put_along_axis(best, idx, np.maximum(curbest, cur)[:, None], 1)
    return best


runs = longest_runs(raw)
cut = np.array(RUN_CUT, np.int16)
run_flag = (runs[:, 1:] > cut[1:]).any(1)
say("  RUN_CUT flag rate on the norm sample: %.3f%%  (n=%d)" % (100 * run_flag.mean(), run_flag.sum()))
per_opt = [(v, float((runs[:, v] > RUN_CUT[v]).mean() * 100)) for v in range(1, 6)]
say("  by option: " + "  ".join("opt%d %.3f%%" % t for t in per_opt))


# ---------------------------------------------------------------- 1  build the indices
hr("1  build even-odd consistency and psychometric synonym/antonym indices")

halfA = np.stack([keyed[:, slot_items[j][0::2]].sum(1) for j in range(30)], 1)
halfB = np.stack([keyed[:, slot_items[j][1::2]].sum(1) for j in range(30)], 1)
EO = rowcorr(halfA, halfB)
EO_sb = 2 * EO / (1 + EO)
say("  even-odd (30 facet pairs, 5+5 items): mean r = %.3f, median = %.3f, SD = %.3f, NaN = %d"
    % (np.nanmean(EO), np.nanmedian(EO), np.nanstd(EO), int(np.isnan(EO).sum())))
say("  Meade & Craig (2012) reported mean even-odd .79 in their careful class; ours = %.3f" % np.nanmean(EO))

# item correlation matrix (keyed space) for synonym / antonym pair selection
sub = rng.choice(N, 40000, replace=False)
X = keyed[sub]
X = X - X.mean(0)
sd = X.std(0)
C = (X.T @ X) / len(sub) / np.outer(sd, sd)
np.fill_diagonal(C, 0.0)
iu = np.triu_indices(K, 1)
vals = C[iu]
order_pos = np.argsort(vals)[::-1]
order_neg = np.argsort(vals)
say("  item-pair correlations (keyed space): max = %.3f, min = %.3f" % (vals.max(), vals.min()))


def take_pairs(order, n_pairs, want_sign):
    used = set()
    pa, pb, rr = [], [], []
    for t in order:
        i, j = int(iu[0][t]), int(iu[1][t])
        r = float(vals[t])
        if want_sign > 0 and r <= 0:
            break
        if want_sign < 0 and r >= 0:
            break
        if i in used or j in used:
            continue
        used.add(i)
        used.add(j)
        pa.append(i)
        pb.append(j)
        rr.append(r)
        if len(pa) >= n_pairs:
            break
    return np.array(pa), np.array(pb), np.array(rr)


syn_a, syn_b, syn_r = take_pairs(order_pos, 30, +1)
ant_a, ant_b, ant_r = take_pairs(order_neg, 30, -1)
say("  synonym pairs: n=%d, r range %.3f .. %.3f (mean %.3f)" % (len(syn_r), syn_r.min(), syn_r.max(), syn_r.mean()))
say("  antonym pairs: n=%d, r range %.3f .. %.3f (mean %.3f)" % (len(ant_r), ant_r.min(), ant_r.max(), ant_r.mean()))

SYN = rowcorr(keyed[:, syn_a], keyed[:, syn_b])
ANT = rowcorr(keyed[:, ant_a], keyed[:, ant_b])
say("  psych-synonym index: mean %.3f, SD %.3f, NaN %d" % (np.nanmean(SYN), np.nanstd(SYN), int(np.isnan(SYN).sum())))
say("  psych-antonym  index: mean %.3f, SD %.3f, NaN %d" % (np.nanmean(ANT), np.nanstd(ANT), int(np.isnan(ANT).sum())))

# a composite exactly like the proposal: flag if EO low OR SYN low OR ANT high
def flag_at_rate(score, rate, lower_is_worse=True):
    s = np.where(np.isnan(score), -np.inf if lower_is_worse else np.inf, score)
    q = np.nanquantile(s[np.isfinite(s)], rate if lower_is_worse else 1 - rate)
    return (s <= q) if lower_is_worse else (s >= q)


# ---------------------------------------------------------------- 2  reliability of the index
hr("2  is the index itself reliable enough to judge one person? (split-facet reproduction)")

setA = [j for j in range(30) if j % 2 == 0]
setB = [j for j in range(30) if j % 2 == 1]
EO_A = rowcorr(halfA[:, setA], halfB[:, setA])
EO_B = rowcorr(halfA[:, setB], halfB[:, setB])
good = ~np.isnan(EO_A) & ~np.isnan(EO_B)
r_split = np.corrcoef(EO_A[good], EO_B[good])[0, 1]
say("  EO computed on 15 facets vs the other 15 facets: r = %.3f  (Spearman-Brown -> %.3f)"
    % (r_split, 2 * r_split / (1 + r_split)))

for rate in (0.018, 0.03, 0.05, 0.10):
    fa = flag_at_rate(EO_A, rate)
    fb = flag_at_rate(EO_B, rate)
    both = (fa & fb).sum()
    either = (fa | fb).sum()
    say("    at a %.1f%% flag rate: both halves flag %d, either flags %d -> reproduction %.1f%%"
        % (100 * rate, both, either, 100.0 * both / max(either, 1)))

SYN_A = rowcorr(keyed[:, syn_a[0::2]], keyed[:, syn_b[0::2]])
SYN_B = rowcorr(keyed[:, syn_a[1::2]], keyed[:, syn_b[1::2]])
g2 = ~np.isnan(SYN_A) & ~np.isnan(SYN_B)
rs = np.corrcoef(SYN_A[g2], SYN_B[g2])[0, 1]
say("  synonym index on 15 pairs vs the other 15: r = %.3f (SB -> %.3f)" % (rs, 2 * rs / (1 + rs)))
for rate in (0.018, 0.03, 0.05):
    fa = flag_at_rate(SYN_A, rate)
    fb = flag_at_rate(SYN_B, rate)
    say("    at a %.1f%% flag rate: reproduction %.1f%%"
        % (100 * rate, 100.0 * (fa & fb).sum() / max((fa | fb).sum(), 1)))


# ---------------------------------------------------------------- 3  flat-profile confound
hr("3  what kind of person does the index flag? (profile flatness confound)")

F = np.stack([keyed[:, slot_items[j]].sum(1) for j in range(30)], 1)
Fz = (F - F.mean(0)) / F.std(0)
prof_sd = Fz.std(1)                       # how differentiated this person's profile is
say("  r(EO, profile SD across 30 z-scored facets) = %.3f" % np.corrcoef(EO[~np.isnan(EO)], prof_sd[~np.isnan(EO)])[0, 1])
say("  r(SYN, profile SD) = %.3f" % np.corrcoef(SYN[~np.isnan(SYN)], prof_sd[~np.isnan(SYN)])[0, 1])

for rate in (0.018, 0.05):
    fl = flag_at_rate(EO, rate)
    dec = np.quantile(prof_sd, np.linspace(0, 1, 11))
    say("  EO flag rate at overall %.1f%%, by decile of profile differentiation (1 = flattest):" % (100 * rate))
    line = []
    for d in range(10):
        m = (prof_sd >= dec[d]) & (prof_sd <= dec[d + 1])
        line.append("D%d %.2f%%" % (d + 1, 100 * fl[m].mean()))
    say("     " + "  ".join(line))

# how extreme are flagged people's scores?
fl = flag_at_rate(EO, 0.018)
dom = np.stack([F[:, [j for j in range(30) if j % 5 == d]].sum(1) for d in range(5)], 1)
say("")
say("  domain z-scores of EO-flagged vs rest (order N,E,O,A,C):")
dz = (dom - dom.mean(0)) / dom.std(0)
say("     flagged: " + "  ".join("%s %+.3f" % (DOM[d], dz[fl, d].mean()) for d in range(5)))
say("     rest   : " + "  ".join("%s %+.3f" % (DOM[d], dz[~fl, d].mean()) for d in range(5)))
say("  mean age flagged %.1f vs rest %.1f ; %% female flagged %.1f vs rest %.1f"
    % (age[fl].mean(), age[~fl].mean(),
       100 * (sex[fl] == 2).mean(), 100 * (sex[~fl] == 2).mean()))
say("  overlap with RUN_CUT: %d of %d EO-flagged are also RUN_CUT-flagged (%.1f%%)"
    % ((fl & run_flag).sum(), fl.sum(), 100.0 * (fl & run_flag).sum() / max(fl.sum(), 1)))


# ---------------------------------------------------------------- 4  non-circular payoff
hr("4  non-circular payoff: does flagging actually raise the reproducibility of what we show?")

# index built on facet set A only; criterion measured on facet set B only
EO_idx = EO_A
tierA = {}
tierB = {}
agreeB = np.zeros(N, np.float64)
cnt = 0
for j in setB:
    ii = slot_items[j]
    a = keyed[:, ii[0::2]].sum(1)
    b = keyed[:, ii[1::2]].sum(1)
    ta, tb = tier(emp_pct(a)), tier(emp_pct(b))
    agreeB += (ta == tb)
    cnt += 1
agreeB /= cnt
say("  criterion = mean two-parallel-form facet tier agreement over the 15 held-out facets")
say("  overall mean agreement (cohort rows): %.4f" % agreeB[ok].mean())
say("  r(EO on held-in facets, agreement on held-out facets) = %.3f"
    % np.corrcoef(EO_idx[ok & ~np.isnan(EO_idx)], agreeB[ok & ~np.isnan(EO_idx)])[0, 1])
for rate in (0.018, 0.03, 0.05, 0.10, 0.20):
    fl2 = flag_at_rate(EO_idx, rate)
    keep = ok & ~fl2
    say("    drop worst %.0f%% by EO -> agreement %.4f (was %.4f), gain %+.4f ; dropped group agreement %.4f"
        % (100 * rate, agreeB[keep].mean(), agreeB[ok].mean(),
           agreeB[keep].mean() - agreeB[ok].mean(), agreeB[ok & fl2].mean()))
say("  same, using RUN_CUT as the filter:")
keep = ok & ~run_flag
say("    drop RUN_CUT-flagged (%.2f%%) -> agreement %.4f, gain %+.4f ; dropped group %.4f"
    % (100 * run_flag.mean(), agreeB[keep].mean(), agreeB[keep].mean() - agreeB[ok].mean(),
       agreeB[ok & run_flag].mean()))


# ---------------------------------------------------------------- 5  synthetic positives
hr("5  the '97% detection' number: how much of it is the straw man?")

M = 20000
pick = rng.choice(N, M, replace=False)
base = keyed[pick].copy()
raw_base = raw[pick].copy()


def own_marginal_draw(rowsraw, n_items, r):
    """draw responses iid from each person's own observed option distribution (raw space)"""
    out = np.zeros((len(rowsraw), n_items), np.int8)
    for k in range(len(rowsraw)):
        p = np.bincount(rowsraw[k], minlength=6)[1:].astype(np.float64)
        p /= p.sum()
        out[k] = r.choice(np.arange(1, 6), size=n_items, p=p)
    return out


def to_keyed(rawmat, cols):
    kk = rawmat.astype(np.float32).copy()
    revmask = np.isin(cols, rev0)
    kk[:, revmask] = 6 - kk[:, revmask]
    return kk


allcols = np.arange(K)
scen = {}

# S1 uniform random over all 300 (the straw man)
s = rng.integers(1, 6, size=(M, K)).astype(np.int8)
scen["S1 全300题均匀随机"] = (to_keyed(s, allcols), s)

# S2 real first 200, uniform random last 100
s = raw_base.copy()
s[:, 200:] = rng.integers(1, 6, size=(M, 100)).astype(np.int8)
scen["S2 后100题均匀随机"] = (to_keyed(s, allcols), s)

# S3 own-marginal random over all 300 (style-preserving, content-free)
s = own_marginal_draw(raw_base, K, rng)
scen["S3 全300题按自己的按键习惯随机"] = (to_keyed(s, allcols), s)

# S4 partial effort: with prob p replace the real answer by an own-marginal draw
for p in (0.3, 0.5, 0.7):
    d = own_marginal_draw(raw_base, K, rng)
    m = rng.random((M, K)) < p
    s = np.where(m, d, raw_base).astype(np.int8)
    scen["S4 %d%% 的题走神（按自己习惯乱答）" % int(p * 100)] = (to_keyed(s, allcols), s)

# S5 straightlining a 60-item stretch at the person's modal key
s = raw_base.copy()
for k in range(M):
    mode = int(np.bincount(raw_base[k], minlength=6)[1:].argmax() + 1)
    st = int(rng.integers(0, K - 60))
    s[k, st:st + 60] = mode
scen["S5 连续60题直线作答"] = (to_keyed(s, allcols), s)


def index_set(kk, rr):
    hA = np.stack([kk[:, slot_items[j][0::2]].sum(1) for j in range(30)], 1)
    hB = np.stack([kk[:, slot_items[j][1::2]].sum(1) for j in range(30)], 1)
    eo = rowcorr(hA, hB)
    sy = rowcorr(kk[:, syn_a], kk[:, syn_b])
    an = rowcorr(kk[:, ant_a], kk[:, ant_b])
    rn = longest_runs(rr)
    rf = (rn[:, 1:] > cut[1:]).any(1)
    return eo, sy, an, rf


# thresholds calibrated so the REAL sample is flagged at 1.8%
thr_eo = np.nanquantile(EO, 0.018)
thr_sy = np.nanquantile(SYN, 0.018)
thr_an = np.nanquantile(ANT, 1 - 0.018)
comp_real = (np.nan_to_num(EO, nan=-1) <= thr_eo) | (np.nan_to_num(SYN, nan=-1) <= thr_sy) | (np.nan_to_num(ANT, nan=1) >= thr_an)
say("  thresholds fixed at EO<=%.3f, SYN<=%.3f, ANT>=%.3f -> composite flags %.2f%% of the REAL sample"
    % (thr_eo, thr_sy, thr_an, 100 * comp_real.mean()))
say("  (RUN_CUT flags %.2f%% of the real sample)" % (100 * run_flag.mean()))
say("")
say("  detection rate of each synthetic 'careless' scenario at those fixed thresholds:")
say("    %-34s  %8s %8s %8s" % ("scenario", "EO+SYN+ANT", "EO only", "RUN_CUT"))
for nm, (kk, rr) in scen.items():
    eo, sy, an, rf = index_set(kk, rr)
    comp = (np.nan_to_num(eo, nan=-1) <= thr_eo) | (np.nan_to_num(sy, nan=-1) <= thr_sy) | (np.nan_to_num(an, nan=1) >= thr_an)
    say("    %-34s  %7.1f%% %7.1f%% %7.1f%%"
        % (nm, 100 * comp.mean(), 100 * (np.nan_to_num(eo, nan=-1) <= thr_eo).mean(), 100 * rf.mean()))


# ---------------------------------------------------------------- 6  PPV arithmetic
hr("6  positive predictive value at plausible base rates")
say("  Meade & Craig (2012) even-odd: sensitivity .644 at their operating point.")
say("  Take specificity from our own data: at a 1.8% flag rate on a sample assumed b% careless,")
say("  the implied numbers are:")
for base_rate in (0.03, 0.05, 0.11, 0.15):
    for sens in (0.644, 0.90):
        # what specificity would produce our observed 1.8% overall flag rate?
        spec = 1 - (0.018 - base_rate * sens) / (1 - base_rate)
        if spec > 1 or spec < 0:
            say("    base %.0f%%, sens %.2f -> IMPOSSIBLE: a %.1f%% overall flag rate is below base*sens = %.1f%%"
                % (100 * base_rate, sens, 1.8, 100 * base_rate * sens))
            continue
        ppv = base_rate * sens / 0.018
        say("    base %.0f%%, sens %.2f -> required specificity %.4f, PPV %.1f%%, caught %.0f%% of the careless"
            % (100 * base_rate, sens, spec, 100 * ppv, 100 * sens))

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "refute_validity.txt")
io.open(path, "w", encoding="utf-8").write("\n".join(OUT))
print("\nwrote " + path)
