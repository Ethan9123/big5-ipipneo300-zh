# -*- coding: utf-8 -*-
"""Part 3: strictly non-circular criterion, extremity control, composite trait bias,
and the page-text constants."""
import io
import json
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
DOM = ipip.DOMAIN_ORDER


def rowcorr(A, B):
    A = A.astype(np.float64); B = B.astype(np.float64)
    a = A - A.mean(1, keepdims=True); b = B - B.mean(1, keepdims=True)
    num = (a * b).sum(1); den = np.sqrt((a * a).sum(1) * (b * b).sum(1))
    out = np.full(len(A), np.nan); g = den > 1e-9
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


run_flag = (longest_runs(raw)[:, 1:] > RUN_CUT[1:]).any(1)
f237 = (longest_runs(raw, 0, 237)[:, 1:] > RUN_CUT[1:]).any(1)

halfA = np.stack([keyed[:, slot_items[j][0::2]].sum(1) for j in range(30)], 1)
halfB = np.stack([keyed[:, slot_items[j][1::2]].sum(1) for j in range(30)], 1)
setA = [j for j in range(30) if j % 2 == 0]
setB = [j for j in range(30) if j % 2 == 1]

EO_A = rowcorr(halfA[:, setA], halfB[:, setA])        # index: built on setA facets only
zA = (halfA[:, setB] - halfA[:, setB].mean(0)) / halfA[:, setB].std(0)
zB = (halfB[:, setB] - halfB[:, setB].mean(0)) / halfB[:, setB].std(0)
DISC = np.abs(zA - zB).mean(1)                        # criterion: setB facets only, no cut points
F = np.stack([keyed[:, slot_items[j]].sum(1) for j in range(30)], 1)
Fz = (F - F.mean(0)) / F.std(0)
EXTREME = np.abs(Fz[:, setB]).mean(1)                 # how far from average this person is (setB)

hr("A  strictly non-circular criterion: half-form discrepancy on HELD-OUT facets")
say("  index  = even-odd consistency computed on the 15 setA facets")
say("  criterion = mean |z(halfA) - z(halfB)| over the 15 setB facets (no cut points, no tiers)")
say("  overall mean discrepancy = %.4f SD units" % DISC[ok].mean())
g = ok & ~np.isnan(EO_A)
say("  r(EO_setA, discrepancy_setB) = %.3f" % np.corrcoef(EO_A[g], DISC[g])[0, 1])
say("  r(extremity_setB, discrepancy_setB) = %.3f   <- the confound" % np.corrcoef(EXTREME[ok], DISC[ok])[0, 1])

hr("B  do the flags mark worse protocols, before and after controlling for extremity?")
qs = np.quantile(EXTREME[ok], np.linspace(0, 1, 6))


def strat_report(name, flag):
    m = ok & flag
    raw_gap = DISC[m].mean() - DISC[ok & ~flag].mean()
    parts = []
    w, tot = 0.0, 0.0
    for s in range(5):
        lo, hi = qs[s], qs[s + 1]
        st = ok & (EXTREME >= lo) & (EXTREME <= hi)
        a = DISC[st & flag]
        b = DISC[st & ~flag]
        if len(a) < 30:
            parts.append("Q%d n/a" % (s + 1))
            continue
        d = a.mean() - b.mean()
        parts.append("Q%d %+.4f" % (s + 1, d))
        w += d * st.sum(); tot += st.sum()
    say("  %-38s n=%6d  raw gap %+.4f   extremity-stratified gap %+.4f"
        % (name, m.sum(), raw_gap, w / tot))
    say("       by extremity quintile (1=most average person): " + "  ".join(parts))


for nm, fl in [("RUN_CUT (shipped, 2.99%)", run_flag),
               ("RUN_CUT items 1-237 only (1.92%)", f237),
               ("even-odd worst 1.8% (setA-built)", EO_A <= np.nanquantile(EO_A, 0.018)),
               ("even-odd worst 5% (setA-built)", EO_A <= np.nanquantile(EO_A, 0.05))]:
    strat_report(nm, fl)
say("  (positive gap = flagged protocols really are less consistent; ~0 = the flag is noise)")

hr("C  how much does filtering buy, in the units the site actually shows?")
say("  the site shows facet tiers cut at percentile 30/70.")
say("  two-parallel-form facet tier agreement over setB facets:")
tierA = np.zeros((N, len(setB)), np.int8)
tierB = np.zeros((N, len(setB)), np.int8)


def emp_pct(x):
    x = np.asarray(x, np.float64)
    out = np.full(len(x), np.nan)
    for ci in range(len(COH)):
        m = cohort_of == ci
        v = x[m]; o = np.argsort(v, kind="mergesort"); vs = v[o]; n = len(vs)
        lo = np.searchsorted(vs, vs, "left"); hi = np.searchsorted(vs, vs, "right")
        p = 100.0 * (lo + 0.5 * (hi - lo)) / n
        r = np.empty(n); r[o] = p; out[m] = r
    return out


for c, j in enumerate(setB):
    ii = slot_items[j]
    pa = emp_pct(keyed[:, ii[0::2]].sum(1)); pb = emp_pct(keyed[:, ii[1::2]].sum(1))
    tierA[:, c] = (pa >= 30).astype(np.int8) + (pa >= 70).astype(np.int8)
    tierB[:, c] = (pb >= 30).astype(np.int8) + (pb >= 70).astype(np.int8)
agree = (tierA == tierB).mean(1)
base = agree[ok].mean()
say("     everyone: %.4f" % base)
for rate in (0.018, 0.05, 0.10):
    fl = EO_A <= np.nanquantile(EO_A, rate)
    say("     after removing the worst %.1f%% by even-odd: %.4f  (%+.4f pp)"
        % (100 * rate, agree[ok & ~fl].mean(), 100 * (agree[ok & ~fl].mean() - base)))
say("     after removing RUN_CUT-flagged: %.4f  (%+.4f pp)"
    % (agree[ok & ~run_flag].mean(), 100 * (agree[ok & ~run_flag].mean() - base)))
say("  reference noise floor already on the page: single-domain retest 83-88%%, five-domain 47.2%%,")
say("  facet percentile 95%% CI ~53 points wide.")

hr("D  who gets told their answers may be invalid (composite at 1.8%)")
sub = rng.choice(N, 40000, replace=False)
X = keyed[sub] - keyed[sub].mean(0); sd = X.std(0)
C = (X.T @ X) / len(sub) / np.outer(sd, sd)
np.fill_diagonal(C, 0.0)
iu = np.triu_indices(K, 1); vals = C[iu]


def take_pairs(order, n_pairs, want_sign):
    used, pa, pb = set(), [], []
    for t in order:
        i, j = int(iu[0][t]), int(iu[1][t]); r = float(vals[t])
        if (want_sign > 0 and r <= 0) or (want_sign < 0 and r >= 0):
            break
        if i in used or j in used:
            continue
        used.add(i); used.add(j); pa.append(i); pb.append(j)
        if len(pa) >= n_pairs:
            break
    return np.array(pa), np.array(pb)


syn_a, syn_b = take_pairs(np.argsort(vals)[::-1], 30, +1)
ant_a, ant_b = take_pairs(np.argsort(vals), 30, -1)
EO = rowcorr(halfA, halfB)
SYN = rowcorr(keyed[:, syn_a], keyed[:, syn_b])
ANT = rowcorr(keyed[:, ant_a], keyed[:, ant_b])


def zbad(v, invert):
    v = np.nan_to_num(v, nan=np.nanmin(v) if invert else np.nanmax(v))
    s = -v if invert else v
    return (s - s.mean()) / s.std()


COMP = np.maximum(np.maximum(zbad(EO, True), zbad(SYN, True)), zbad(ANT, False))
cf = COMP >= np.quantile(COMP, 1 - 0.018)
dom = np.stack([F[:, [j for j in range(30) if j % 5 == d]].sum(1) for d in range(5)], 1)
dz = (dom - dom.mean(0)) / dom.std(0)
say("  domain z of composite-flagged: " + "  ".join("%s %+.3f" % (DOM[d], dz[cf, d].mean()) for d in range(5)))
say("  domain z of everyone else    : " + "  ".join("%s %+.3f" % (DOM[d], dz[~cf, d].mean()) for d in range(5)))
say("  mean age %.1f vs %.1f ; %%female %.1f vs %.1f"
    % (age[cf].mean(), age[~cf].mean(), 100 * (sex[cf] == 2).mean(), 100 * (sex[~cf] == 2).mean()))
prof_sd = Fz.std(1)
dec = np.quantile(prof_sd, np.linspace(0, 1, 11))
say("  composite flag rate by decile of profile differentiation (D1 = flattest profile):")
say("     " + "  ".join("D%d %.2f%%" % (d + 1, 100 * cf[(prof_sd >= dec[d]) & (prof_sd <= dec[d + 1])].mean())
                        for d in range(10)))
say("  same for RUN_CUT:")
say("     " + "  ".join("D%d %.2f%%" % (d + 1, 100 * run_flag[(prof_sd >= dec[d]) & (prof_sd <= dec[d + 1])].mean())
                        for d in range(10)))

hr("E  page-text constants behind the 'reading arithmetic' proposal")
html = io.open(r"C:\Users\kids1\Downloads\bigfive\dist\index.html", encoding="utf-8").read()
mm = re.search(r'const DATA = (\{.*?\});\n', html, re.S)
D = json.loads(mm.group(1))
notes = D["notes"]
lens = [len(re.sub(r"\s", "", x if isinstance(x, str) else json.dumps(x, ensure_ascii=False))) for x in notes]
say("  notes: n=%d mean %.1f SD %.1f min %d max %d TOTAL %d chars"
    % (len(notes), np.mean(lens), np.std(lens), min(lens), max(lens), sum(lens)))
it = D["items"]
say("  items[0] = %s" % json.dumps(it[0], ensure_ascii=False)[:200])
if isinstance(it[0], dict):
    key = "t" if "t" in it[0] else sorted(it[0].keys())[0]
    tl = [len(re.sub(r"\s", "", str(x[key]))) for x in it]
else:
    tl = [len(re.sub(r"\s", "", str(x))) for x in it]
say("  stems: n=%d mean %.1f TOTAL %d chars" % (len(tl), np.mean(tl), sum(tl)))
tot = sum(lens) + sum(tl)
say("  hints mode total on-screen chars = %d ; at 300-400 chars/min silent reading = %.0f-%.0f minutes"
    % (tot, tot / 400.0, tot / 300.0))
say("  standard mode (stems only) = %d chars = %.1f-%.1f minutes of reading"
    % (sum(tl), sum(tl) / 400.0, sum(tl) / 300.0))

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "refute3.txt")
io.open(path, "w", encoding="utf-8").write("\n".join(OUT))
print("\nwrote " + path)
