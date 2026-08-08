# -*- coding: utf-8 -*-
"""Part 4: principled keying-aware run rule, verify the shipped flag text, fix char counts."""
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
    say(""); say("=" * 78); say(t); say("=" * 78)


z = ipip.load()
items = z["items"].astype(np.int8)
sex, age = z["sex"], z["age"]
N, K = items.shape
data = ipip.site_data()
rev0 = np.array(sorted(data["reversed"]), dtype=np.int64) - 1
is_rev = np.zeros(K, bool); is_rev[rev0] = True
raw = items.copy(); raw[:, rev0] = 6 - raw[:, rev0]
keyed = items.astype(np.float32)
slot_items = {j: np.array(ipip.facet_items(j)) for j in range(30)}
masks = ipip.group_masks(sex, age)
COH = ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]
cohort_of = np.full(N, -1, np.int8)
for ci, c in enumerate(COH):
    cohort_of[masks[c]] = ci
ok = cohort_of >= 0
RUN_CUT = np.array([0, 6, 9, 10, 14, 9], np.int16)

hr("0  keying layout: where do the same-keyed stretches sit?")
runs_key = []
s = 0
for i in range(1, K + 1):
    if i == K or is_rev[i] != is_rev[s]:
        runs_key.append((s + 1, i, bool(is_rev[s]), i - s))
        s = i
long_stretch = sorted(runs_key, key=lambda t: -t[3])[:6]
say("  longest same-keyed stretches (start,end,reversed,len): %s" % long_stretch)
say("  reverse items in 238-300: %d of 63" % is_rev[237:300].sum())
say("  reverse items in 1-237  : %d of 237" % is_rev[:237].sum())


def run_segments(a_row):
    """yield (start, end_exclusive, value, length) for maximal constant runs in one row"""
    out = []
    s = 0
    for i in range(1, K + 1):
        if i == K or a_row[i] != a_row[s]:
            out.append((s, i, int(a_row[s]), i - s))
            s = i
    return out


hr("1  three run-rule variants, evaluated on the same criterion")

# vectorised: for each row, find the longest run per option AND whether it crosses a keying change
def analyse(a):
    n = a.shape[0]
    best_all = np.zeros((n, 6), np.int16)
    best_mixed = np.zeros((n, 6), np.int16)   # runs that span at least one keying change
    best_pre = np.zeros((n, 6), np.int16)     # runs entirely inside items 1-237
    keychg = np.zeros(K, bool)
    keychg[1:] = is_rev[1:] != is_rev[:-1]
    start = np.zeros(n, np.int32)
    cur = np.ones(n, np.int16)
    prev = a[:, 0].astype(np.int16)
    crossed = np.zeros(n, bool)
    for i in range(1, K + 1):
        if i < K:
            same = a[:, i] == prev
        else:
            same = np.zeros(n, bool)
        # close out runs that end here
        ending = ~same
        if ending.any():
            idx = prev[:, None].astype(np.intp)
            cb = np.take_along_axis(best_all, idx, 1)[:, 0]
            np.put_along_axis(best_all, idx, np.where(ending, np.maximum(cb, cur), cb)[:, None], 1)
            cm = np.take_along_axis(best_mixed, idx, 1)[:, 0]
            np.put_along_axis(best_mixed, idx,
                              np.where(ending & crossed, np.maximum(cm, cur), cm)[:, None], 1)
            cp = np.take_along_axis(best_pre, idx, 1)[:, 0]
            inpre = ending & (start + cur <= 237)
            np.put_along_axis(best_pre, idx, np.where(inpre, np.maximum(cp, cur), cp)[:, None], 1)
        if i < K:
            cur = np.where(same, cur + 1, 1)
            crossed = np.where(same, crossed | keychg[i], False)
            start = np.where(same, start, i)
            prev = a[:, i].astype(np.int16)
    return best_all, best_mixed, best_pre


bA, bM, bP = analyse(raw)
f_all = (bA[:, 1:] > RUN_CUT[1:]).any(1)
f_mixed = (bM[:, 1:] > RUN_CUT[1:]).any(1)
f_pre = (bP[:, 1:] > RUN_CUT[1:]).any(1)
say("  shipped rule (any run)                       flag rate %.2f%%" % (100 * f_all.mean()))
say("  keying-aware (run must cross a keying change) flag rate %.2f%%" % (100 * f_mixed.mean()))
say("  positional  (run must sit inside items 1-237) flag rate %.2f%%" % (100 * f_pre.mean()))
say("  option mix, shipped rule : " + "  ".join("opt%d %.2f%%" % (v, 100 * (bA[:, v] > RUN_CUT[v]).mean()) for v in range(1, 6)))
say("  option mix, keying-aware : " + "  ".join("opt%d %.2f%%" % (v, 100 * (bM[:, v] > RUN_CUT[v]).mean()) for v in range(1, 6)))

hr("2  verify the sentence already on the page ('97% of flagged runs start after item 150')")
sample = np.where(f_all)[0]
rng = np.random.default_rng(3)
samp = rng.choice(sample, 4000, replace=False)
starts = []
for k in samp:
    for (s0, e0, v, L) in run_segments(raw[k]):
        if v >= 1 and L > RUN_CUT[v]:
            starts.append(s0 + 1)
starts = np.array(starts)
say("  flagged runs sampled: %d ; %.1f%% start after item 150 ; %.1f%% start after item 237"
    % (len(starts), 100 * (starts > 150).mean(), 100 * (starts > 237).mean()))
say("  median start position = %d" % int(np.median(starts)))

hr("3  same criterion as before: half-form discrepancy on held-out facets")
halfA = np.stack([keyed[:, slot_items[j][0::2]].sum(1) for j in range(30)], 1)
halfB = np.stack([keyed[:, slot_items[j][1::2]].sum(1) for j in range(30)], 1)
setB = [j for j in range(30) if j % 2 == 1]
zA = (halfA[:, setB] - halfA[:, setB].mean(0)) / halfA[:, setB].std(0)
zB = (halfB[:, setB] - halfB[:, setB].mean(0)) / halfB[:, setB].std(0)
DISC = np.abs(zA - zB).mean(1)
F = np.stack([keyed[:, slot_items[j]].sum(1) for j in range(30)], 1)
Fz = (F - F.mean(0)) / F.std(0)
EXTREME = np.abs(Fz[:, setB]).mean(1)
qs = np.quantile(EXTREME[ok], np.linspace(0, 1, 6))


def strat(name, flag):
    m = ok & flag
    w, tot = 0.0, 0.0
    for s in range(5):
        st = ok & (EXTREME >= qs[s]) & (EXTREME <= qs[s + 1])
        a, b = DISC[st & flag], DISC[st & ~flag]
        if len(a) < 30:
            continue
        w += (a.mean() - b.mean()) * st.sum(); tot += st.sum()
    say("  %-46s n=%6d  rate %.2f%%  extremity-adj gap %+.4f"
        % (name, m.sum(), 100 * m.sum() / ok.sum(), w / tot))


say("  base mean discrepancy = %.4f SD units" % DISC[ok].mean())
strat("shipped run rule", f_all)
strat("keying-aware run rule", f_mixed)
strat("positional run rule (1-237)", f_pre)
strat("released by keying-aware rule (was flagged)", f_all & ~f_mixed)
strat("released by positional rule (was flagged)", f_all & ~f_pre)

prof_sd = Fz.std(1)
dec = np.quantile(prof_sd, np.linspace(0, 1, 11))
for nm, fl in [("shipped", f_all), ("keying-aware", f_mixed)]:
    say("  %s flag rate by profile-differentiation decile (D1=flattest): " % nm
        + "  ".join("D%d %.2f%%" % (d + 1, 100 * fl[(prof_sd >= dec[d]) & (prof_sd <= dec[d + 1])].mean())
                    for d in range(10)))

hr("4  page text: correct character counts (zh field)")
html = io.open(r"C:\Users\kids1\Downloads\bigfive\dist\index.html", encoding="utf-8").read()
D = json.loads(re.search(r'const DATA = (\{.*?\});\n', html, re.S).group(1))
zh = [re.sub(r"\s", "", x["zh"]) for x in D["items"]]
nt = [re.sub(r"\s", "", x if isinstance(x, str) else str(x)) for x in D["notes"]]
say("  stems (zh): n=%d mean %.1f SD %.1f min %d max %d TOTAL %d"
    % (len(zh), np.mean([len(s) for s in zh]), np.std([len(s) for s in zh]),
       min(len(s) for s in zh), max(len(s) for s in zh), sum(len(s) for s in zh)))
say("  notes     : n=%d mean %.1f SD %.1f min %d max %d TOTAL %d"
    % (len(nt), np.mean([len(s) for s in nt]), np.std([len(s) for s in nt]),
       min(len(s) for s in nt), max(len(s) for s in nt), sum(len(s) for s in nt)))
tot = sum(len(s) for s in zh) + sum(len(s) for s in nt)
say("  hints mode on-screen total = %d chars -> %.0f-%.0f min at 300-400 char/min, %.0f min at 600"
    % (tot, tot / 400, tot / 300, tot / 600))
say("  standard mode total = %d chars -> %.0f-%.0f min at 300-400 char/min"
    % (sum(len(s) for s in zh), sum(len(s) for s in zh) / 400, sum(len(s) for s in zh) / 300))
say("  ratio note:stem chars = %.1f : 1" % (sum(len(s) for s in nt) / sum(len(s) for s in zh)))

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "refute4.txt")
io.open(path, "w", encoding="utf-8").write("\n".join(OUT))
print("\nwrote " + path)
