# -*- coding: utf-8 -*-
"""Part 2: match the claimed operating point, add chance baselines, test the cheap
position-aware RUN_CUT variant, and check the reading-arithmetic constants."""
import io
import os
import re
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
items = z["items"].astype(np.int8)
sex, age = z["sex"], z["age"]
N, K = items.shape
data = ipip.site_data()
rev0 = np.array(sorted(data["reversed"]), dtype=np.int64) - 1
raw = items.copy()
raw[:, rev0] = 6 - raw[:, rev0]
keyed = items.astype(np.float32)
slot_items = {j: np.array(ipip.facet_items(j)) for j in range(30)}
masks = ipip.group_masks(sex, age)
COH = ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]
cohort_of = np.full(N, -1, np.int8)
for ci, c in enumerate(COH):
    cohort_of[masks[c]] = ci
ok = cohort_of >= 0


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
    A = A.astype(np.float64)
    B = B.astype(np.float64)
    a = A - A.mean(1, keepdims=True)
    b = B - B.mean(1, keepdims=True)
    num = (a * b).sum(1)
    den = np.sqrt((a * a).sum(1) * (b * b).sum(1))
    out = np.full(len(A), np.nan)
    g = den > 1e-9
    out[g] = num[g] / den[g]
    return out


RUN_CUT = np.array([0, 6, 9, 10, 14, 9], np.int16)


def longest_runs(a, lo=0, hi=None):
    hi = a.shape[1] if hi is None else hi
    n = a.shape[0]
    best = np.zeros((n, 6), np.int16)
    cur = np.ones(n, np.int16)
    prev = a[:, lo].astype(np.int16)
    np.put_along_axis(best, prev[:, None].astype(np.intp), np.ones((n, 1), np.int16), 1)
    for i in range(lo + 1, hi):
        same = a[:, i] == prev
        cur = np.where(same, cur + 1, 1)
        prev = a[:, i].astype(np.int16)
        idx = prev[:, None].astype(np.intp)
        cb = np.take_along_axis(best, idx, 1)[:, 0]
        np.put_along_axis(best, idx, np.maximum(cb, cur)[:, None], 1)
    return best


halfA = np.stack([keyed[:, slot_items[j][0::2]].sum(1) for j in range(30)], 1)
halfB = np.stack([keyed[:, slot_items[j][1::2]].sum(1) for j in range(30)], 1)
EO = rowcorr(halfA, halfB)

sub = rng.choice(N, 40000, replace=False)
X = keyed[sub] - keyed[sub].mean(0)
sd = X.std(0)
C = (X.T @ X) / len(sub) / np.outer(sd, sd)
np.fill_diagonal(C, 0.0)
iu = np.triu_indices(K, 1)
vals = C[iu]


def take_pairs(order, n_pairs, want_sign):
    used, pa, pb, rr = set(), [], [], []
    for t in order:
        i, j = int(iu[0][t]), int(iu[1][t])
        r = float(vals[t])
        if (want_sign > 0 and r <= 0) or (want_sign < 0 and r >= 0):
            break
        if i in used or j in used:
            continue
        used.add(i); used.add(j); pa.append(i); pb.append(j); rr.append(r)
        if len(pa) >= n_pairs:
            break
    return np.array(pa), np.array(pb), np.array(rr)


syn_a, syn_b, _ = take_pairs(np.argsort(vals)[::-1], 30, +1)
ant_a, ant_b, _ = take_pairs(np.argsort(vals), 30, -1)
SYN = rowcorr(keyed[:, syn_a], keyed[:, syn_b])
ANT = rowcorr(keyed[:, ant_a], keyed[:, ant_b])

# composite score: standardise each index (higher = more suspect), take the max
def zbad(v, invert):
    v = np.nan_to_num(v, nan=np.nanmin(v) if invert else np.nanmax(v))
    s = -v if invert else v
    return (s - s.mean()) / s.std()


COMP = np.maximum(np.maximum(zbad(EO, True), zbad(SYN, True)), zbad(ANT, False))
run_flag = (longest_runs(raw)[:, 1:] > RUN_CUT[1:]).any(1)

hr("A  calibrate the composite to EXACTLY 1.8% on the real sample (the claimed operating point)")
thr = np.quantile(COMP, 1 - 0.018)
comp_flag = COMP >= thr
say("  composite threshold z = %.3f -> flags %.2f%% of the real sample" % (thr, 100 * comp_flag.mean()))
say("  overlap with RUN_CUT: %.1f%% of composite-flagged are also RUN_CUT-flagged"
    % (100 * (comp_flag & run_flag).sum() / comp_flag.sum()))

M = 20000
pick = rng.choice(N, M, replace=False)
raw_base = raw[pick].copy()


def own_marginal(rowsraw, n, r):
    out = np.zeros((len(rowsraw), n), np.int8)
    for k in range(len(rowsraw)):
        p = np.bincount(rowsraw[k], minlength=6)[1:].astype(np.float64)
        p /= p.sum()
        out[k] = r.choice(np.arange(1, 6), size=n, p=p)
    return out


def to_keyed(rawmat):
    kk = rawmat.astype(np.float32).copy()
    kk[:, rev0] = 6 - kk[:, rev0]
    return kk


scen = {}
scen["S1 all-300 uniform random"] = rng.integers(1, 6, (M, K)).astype(np.int8)
s = raw_base.copy(); s[:, 200:] = rng.integers(1, 6, (M, 100)).astype(np.int8)
scen["S2 last-100 uniform random"] = s
scen["S3 all-300 own-habit random"] = own_marginal(raw_base, K, rng)
for p in (0.3, 0.5):
    d = own_marginal(raw_base, K, rng)
    m = rng.random((M, K)) < p
    scen["S4 %d%% of items inattentive" % int(p * 100)] = np.where(m, d, raw_base).astype(np.int8)
s = raw_base.copy()
for k in range(M):
    mode = int(np.bincount(raw_base[k], minlength=6)[1:].argmax() + 1)
    st = int(rng.integers(0, K - 60))
    s[k, st:st + 60] = mode
scen["S5 straightline 60 items"] = s
s = raw_base.copy()
for k in range(M):
    st = int(rng.integers(0, K - 40))
    s[k, st:st + 40] = np.tile([4, 4, 3, 4, 5], 8)
scen["S6 repeating 4-4-3-4-5 pattern x40"] = s

say("")
say("  detection at the fixed 1.8% operating point:")
say("    %-34s %11s %9s" % ("scenario", "composite", "RUN_CUT"))
for nm, rr in scen.items():
    kk = to_keyed(rr)
    hA = np.stack([kk[:, slot_items[j][0::2]].sum(1) for j in range(30)], 1)
    hB = np.stack([kk[:, slot_items[j][1::2]].sum(1) for j in range(30)], 1)
    eo = rowcorr(hA, hB)
    sy = rowcorr(kk[:, syn_a], kk[:, syn_b])
    an = rowcorr(kk[:, ant_a], kk[:, ant_b])
    # score against the REAL sample's moments so thresholds transfer
    def zb(v, ref, invert):
        v = np.nan_to_num(v, nan=np.nanmin(ref) if invert else np.nanmax(ref))
        s_ = -v if invert else v
        r_ = -ref if invert else ref
        r_ = np.nan_to_num(r_, nan=np.nanmax(r_))
        return (s_ - r_.mean()) / r_.std()
    cc = np.maximum(np.maximum(zb(eo, EO, True), zb(sy, SYN, True)), zb(an, ANT, False))
    rf = (longest_runs(rr)[:, 1:] > RUN_CUT[1:]).any(1)
    say("    %-34s %10.1f%% %8.1f%%" % (nm, 100 * (cc >= thr).mean(), 100 * rf.mean()))

hr("B  chance baseline for the flag-reproduction test")
setA = [j for j in range(30) if j % 2 == 0]
setB = [j for j in range(30) if j % 2 == 1]
EO_A = rowcorr(halfA[:, setA], halfB[:, setA])
EO_B = rowcorr(halfA[:, setB], halfB[:, setB])
for rate in (0.018, 0.05):
    a = EO_A <= np.nanquantile(EO_A, rate)
    b = EO_B <= np.nanquantile(EO_B, rate)
    obs = 100.0 * (a & b).sum() / (a | b).sum()
    chance = 100.0 * (rate * rate) / (2 * rate - rate * rate)
    say("  flag rate %.1f%%: observed reproduction %.1f%%, chance-if-independent %.1f%%, ratio %.1fx"
        % (100 * rate, obs, chance, obs / chance))
say("  ceiling check: a perfectly reliable index would reproduce 100%%.")

hr("C  cheap alternative to re-ordering: make RUN_CUT position-aware")
say("  variant 1: apply Johnson's cuts only to items 1-237 (before the 63-item reverse block)")
r237 = longest_runs(raw, 0, 237)
f237 = (r237[:, 1:] > RUN_CUT[1:]).any(1)
say("     flag rate %.2f%%  (was %.2f%%)" % (100 * f237.mean(), 100 * run_flag.mean()))
say("  variant 2: raise the cut inside the reverse block by the block length ratio")
say("  variant 3: drop the run rule entirely")

# does any variant identify genuinely worse protocols?
agreeB = np.zeros(N)
for j in setB:
    ii = slot_items[j]
    ta = tier(emp_pct(keyed[:, ii[0::2]].sum(1)))
    tb = tier(emp_pct(keyed[:, ii[1::2]].sum(1)))
    agreeB += (ta == tb)
agreeB /= len(setB)
say("")
say("  held-out two-form facet tier agreement (higher = better data), cohort rows only:")
say("     everyone                       %.4f  (n=%d)" % (agreeB[ok].mean(), ok.sum()))
for nm, f in [("RUN_CUT flagged (2.99%)", run_flag),
              ("RUN_CUT flagged, items 1-237 only", f237),
              ("composite flagged (1.8%)", comp_flag)]:
    say("     %-34s %.4f  (n=%d)" % (nm, agreeB[ok & f].mean(), (ok & f).sum()))
say("  -> a flag that is doing its job should show a LOWER number for the flagged group.")

hr("D  what an honest 'suspect' set looks like: people the run rule catches OUTSIDE the reverse block")
# runs that both exceed the cut and start before item 238
say("  RUN_CUT flag rate restricted to runs inside items 1-237: %.2f%%" % (100 * f237.mean()))
say("  of the 2.99%% currently flagged, %.1f%% would still be flagged by the 1-237 rule"
    % (100 * (run_flag & f237).sum() / run_flag.sum()))
say("  agreement of the residual group (flagged now, not flagged by 1-237 rule): %.4f"
    % agreeB[ok & run_flag & ~f237].mean())

hr("E  the reading-arithmetic proposal: check its constants against the shipped page")
html = io.open(r"C:\Users\kids1\Downloads\bigfive\dist\index.html", encoding="utf-8").read()
mm = re.search(r'const DATA = (\{.*?\});\n', html, re.S)
import json
D = json.loads(mm.group(1))
say("  DATA keys: %s" % sorted(D.keys()))
if "notes" in D:
    notes = D["notes"]
    lens = [len(re.sub(r"\s", "", x)) for x in notes]
    say("  notes: n=%d, mean chars %.1f, SD %.1f, min %d, max %d, TOTAL %d"
        % (len(notes), np.mean(lens), np.std(lens), min(lens), max(lens), sum(lens)))
if "items" in D:
    it = D["items"]
    t = [len(re.sub(r"\s", "", x["t"] if isinstance(x, dict) and "t" in x else str(x))) for x in it]
    say("  item stems: n=%d, mean chars %.1f, TOTAL %d" % (len(t), np.mean(t), sum(t)))

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "refute2.txt")
io.open(path, "w", encoding="utf-8").write("\n".join(OUT))
print("\nwrote " + path)
