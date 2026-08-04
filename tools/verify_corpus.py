# -*- coding: utf-8 -*-
"""Acceptance gate for the 243 profiles. Read-only. Exit non-zero on any blocker.

Consolidates what the four QA agents established, so the revised corpus can be
re-checked in one command instead of another workflow round.

  python tools/verify_corpus.py [path/to/profiles_raw.json]
"""
import io
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

LV = ["低", "中", "高"]
KEYS = ["O", "C", "E", "A", "N"]
DIM_ZH = {"O": "开放性", "C": "尽责性", "E": "外向性", "A": "宜人性", "N": "神经质"}
BODY = ["life", "friends", "love", "work"]
SPEC = {"lead": (18, 28), "summary": (110, 160),
        "life": (80, 120), "friends": (80, 120), "love": (80, 120), "work": (80, 120)}
SPEC_LIST = {"pros": (8, 20), "cons": (8, 20), "practice": (20, 45)}

path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ipip.OUT, "profiles_raw.json")
profiles = json.load(io.open(path, encoding="utf-8"))
blockers, warnings = [], []


def clen(s):
    return sum(1 for ch in s if not ch.isspace())


def idx_of(cell):
    n = 0
    for i, k in enumerate(KEYS):
        if cell[i * 2] != k:
            return None
        n = n * 3 + LV.index(cell[i * 2 + 1])
    return n


def band(cell, k):
    return cell[KEYS.index(k) * 2 + 1]


def hr(t):
    print("\n" + "=" * 72 + "\n" + t + "\n" + "=" * 72)


# ---------------------------------------------------------------- 1 completeness
hr("1  完整性")
cells = [p.get("cell") for p in profiles]
print("  条目数            : %d" % len(profiles))
dups = [c for c, n in Counter(cells).items() if n > 1]
bad_name = [c for c in cells if not c or len(c) != 10 or idx_of(c) is None]
seen = {idx_of(c) for c in cells if c and idx_of(c) is not None}
missing = [i for i in range(243) if i not in seen]
print("  重复 / 命名不合规 / 缺格 : %d / %d / %d" % (len(dups), len(bad_name), len(missing)))
if len(profiles) != 243 or dups or bad_name or missing:
    blockers.append("完整性: %d 条, 重复 %d, 命名错 %d, 缺 %d" % (len(profiles), len(dups), len(bad_name), len(missing)))

for f in list(SPEC) + list(SPEC_LIST):
    empty = [p["cell"] for p in profiles if not p.get(f)]
    if empty:
        blockers.append("字段 %s 为空: %s" % (f, empty[:5]))
for f in SPEC_LIST:
    wrong = [p["cell"] for p in profiles if not isinstance(p.get(f), list) or len(p[f]) != 3]
    if wrong:
        blockers.append("字段 %s 不是 3 元素数组: %s" % (f, wrong[:5]))

# ---------------------------------------------------------------- 2 lengths
hr("2  字数（剔空白，含标点）")
over = []
for f, (lo, hi) in SPEC.items():
    ls = [(clen(p[f]), p["cell"]) for p in profiles]
    bad = [(n, c) for n, c in ls if n < lo or n > hi]
    vals = sorted(n for n, _ in ls)
    print("  %-8s min %3d 中位 %3d max %3d   越界 %3d/243 (%.1f%%)"
          % (f, vals[0], vals[121], vals[-1], len(bad), 100.0 * len(bad) / 243))
    over += [(f, n, c) for n, c in bad]
for f, (lo, hi) in SPEC_LIST.items():
    ls = [(clen(x), p["cell"]) for p in profiles for x in p[f]]
    bad = [(n, c) for n, c in ls if n < lo or n > hi]
    vals = sorted(n for n, _ in ls)
    print("  %-8s min %3d 中位 %3d max %3d   越界 %3d/729 (%.1f%%)"
          % (f, vals[0], vals[364], vals[-1], len(bad), 100.0 * len(bad) / 729))
    over += [(f, n, c) for n, c in bad]
sev = [(f, n, c) for f, n, c in over
       if n < (SPEC.get(f) or SPEC_LIST[f])[0] * 0.75 or n > (SPEC.get(f) or SPEC_LIST[f])[1] * 1.25]
print("  严重越界(>±25%%) : %d" % len(sev))
for f, n, c in sorted(sev)[:8]:
    print("     %-16s %-8s %d 字" % (c, f, n))
if len(sev) > 20:
    blockers.append("严重越界 %d 处" % len(sev))
elif sev:
    warnings.append("严重越界 %d 处" % len(sev))

# block-level body length (the O高C高 defect)
hr("2b 按 (O,C) 分块的正文密度")
for o in LV:
    for c in LV:
        blk = [p for p in profiles if band(p["cell"], "O") == o and band(p["cell"], "C") == c]
        if not blk:
            continue
        avg = sum(clen(p[f]) for p in blk for f in BODY) / (len(blk) * 4)
        flag = "  <-- 低于规格下限 80" if avg < 80 else ""
        print("  O%sC%s  正文均 %5.1f 字%s" % (o, c, avg, flag))
        if avg < 80:
            blockers.append("O%sC%s 正文均 %.1f 字，低于下限" % (o, c, avg))

# ---------------------------------------------------------------- 3 safety
hr("3  安全红线")
RED = {
    "临床词汇": r"抑郁症|焦虑症|强迫症|躁郁|双相|ADHD|多动症|自闭|亚斯伯格|人格障碍|心理疾病|病态|确诊|精神科|这是病",
    "决定论": r"你天生|你注定|你就是这样|你永远|你这辈子|必然会|一定会变|改不了|与生俱来|骨子里",
    "吹捧星座腔": r"独一无二|天赋异禀|命中注定|魅力四射|出类拔萃|正能量",
    "自造类型名": r"[一-鿿]{2,4}型的人|你是[一-鿿]{0,4}(者|家)[，。]",
    "身份标签": r"内向者|外向者|宜人者|尽责者",
    "英文残留": r"Conscientiousness|Neuroticism|Openness|Extraversion|Agreeableness|Big Five|MBTI",
    "全局负面排名": r"最大的一格|破坏力最大|破坏面积最大|最吃力的部分|243 ?格里最",
    "占位残留": r"占位文本|占位 summary|占位优点|占位缺点|占位练习|真实文案由写作工作流",
    "HTML 特殊字符": r"[<>&]",
}
for name, pat in RED.items():
    hits = []
    for p in profiles:
        for f in list(SPEC) + list(SPEC_LIST):
            texts = [p[f]] if isinstance(p[f], str) else p[f]
            for t in texts:
                for m in re.finditer(pat, t):
                    hits.append((p["cell"], f, m.group(0)))
    print("  %-14s %d" % (name, len(hits)))
    for h in hits[:4]:
        print("      %-16s %-8s %s" % h)
    if hits:
        blockers.append("红线 %s: %d 处" % (name, len(hits)))

# ---------------------------------------------------------------- 4 formula
hr("4  「(维度名)让…」解释句式（规格要求每篇 ≤2）")
pat = re.compile(r"(开放性|尽责性|外向性|宜人性|神经质)[^。；]{0,6}让")
counts = [(len(pat.findall(" ".join([p[f] for f in SPEC]))), p["cell"]) for p in profiles]
tot = sum(n for n, _ in counts)
worst = sorted(counts, reverse=True)[:6]
over2 = [c for n, c in counts if n > 2]
print("  总出现 %d 次，覆盖 %d/243 篇" % (tot, sum(1 for n, _ in counts if n)))
print("  超过 2 次的篇数 : %d" % len(over2))
print("  最多的几篇      : %s" % ", ".join("%s(%d)" % (c, n) for n, c in worst))
if len(over2) > 40:
    blockers.append("「维度让」句式超标 %d 篇" % len(over2))
elif over2:
    warnings.append("「维度让」句式超标 %d 篇" % len(over2))

# ---------------------------------------------------------------- 5 discriminability
hr("5  判别性：只看文字能否还原档位（随机基线 33.3%）")
# A keyword list used to live here and it was wrong -- it scored 「桌上常年摊着三四样
# 学到一半的东西」 as containing no openness behaviour. Measuring recovery directly is
# both more honest and harder to game by tuning a word list.
import subprocess  # noqa: E402
dsc = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   "discriminability.py"), path],
                     capture_output=True, text=True, encoding="utf-8", errors="replace")
accs = {}
for line in (dsc.stdout or "").splitlines():
    m = re.match(r"\s+([OCEAN]) \S+\s+([\d.]+)%", line)
    if m:
        accs[m.group(1)] = float(m.group(2))
    if "全部还原正确" in line:
        print("  " + line.strip())
for k in KEYS:
    a = accs.get(k)
    if a is None:
        warnings.append("判别性未能测得 %s" % k)
        continue
    print("  %s %-4s %5.1f%%" % (k, DIM_ZH[k], a))
    if a < 60:
        blockers.append("%s 判别性仅 %.1f%%（接近随机，该维度没有驱动内容）" % (DIM_ZH[k], a))
    elif a < 85:
        warnings.append("%s 判别性 %.1f%%，低于其余维度" % (DIM_ZH[k], a))
print("  （逐字段拆解见 tools/discriminability.py）")

# ---------------------------------------------------------------- 6 neighbour similarity
hr("6  邻居区分度（3-gram Jaccard，用相对基线判定）")


def grams(s, n=3):
    s = re.sub(r"[^一-鿿]", "", s)
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


by_idx = {idx_of(p["cell"]): p for p in profiles}
def text(p, fs): return " ".join(p[f] for f in fs)


def jac(a, b):
    return len(a & b) / len(a | b) if (a | b) else 0.0


FIELDS5 = ["summary"] + BODY
G = {i: grams(text(by_idx[i], FIELDS5)) for i in by_idx}
pairs = []
for i in by_idx:
    d = [(i // 81) % 3, (i // 27) % 3, (i // 9) % 3, (i // 3) % 3, i % 3]
    for pos in range(5):
        for nv in range(3):
            if nv == d[pos]:
                continue
            d2 = d[:]; d2[pos] = nv
            j = d2[0] * 81 + d2[1] * 27 + d2[2] * 9 + d2[3] * 3 + d2[4]
            if j > i:
                pairs.append((i, j, KEYS[pos], jac(G[i], G[j])))
vals = sorted(x[3] for x in pairs)
base = []
import random
random.seed(7)
for _ in range(3000):
    a, b = random.sample(list(by_idx), 2)
    base.append(jac(G[a], G[b]))
base.sort()
bmed = base[len(base) // 2]
print("  邻居对 %d，中位 %.4f  p90 %.4f  max %.4f" % (len(pairs), vals[len(vals) // 2], vals[int(len(vals) * .9)], vals[-1]))
print("  非邻居基线中位 %.4f  →  判定线 = 11x = %.4f" % (bmed, bmed * 11))
cut = bmed * 11
flag = [x for x in pairs if x[3] >= cut]
print("  超线的邻居对 : %d" % len(flag))
bydim = Counter(x[2] for x in flag)
print("  按差异维度   : %s" % dict(bydim))
for i, j, k, v in sorted(flag, key=lambda x: -x[3])[:6]:
    print("     %.3f  %s | %s   (差 %s)" % (v, by_idx[i]["cell"], by_idx[j]["cell"], k))
if len(flag) > 20:
    blockers.append("邻居区分度超线 %d 对" % len(flag))
elif flag:
    warnings.append("邻居区分度超线 %d 对" % len(flag))

# ---------------------------------------------------------------- 7 near-dup phrases
hr("7  pros/cons/practice 近似重复")


def ratio(a, b):
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


for f in SPEC_LIST:
    items = sorted({x for p in profiles for x in p[f]})
    total = sum(len(p[f]) for p in profiles)
    dup = total - len(items)
    near = 0
    worst = []
    for a in range(len(items)):
        for b in range(a + 1, len(items)):
            if abs(len(items[a]) - len(items[b])) > 6:
                continue
            r = ratio(items[a], items[b])
            if r > 0.8:
                near += 1
                if len(worst) < 3:
                    worst.append((round(r, 3), items[a], items[b]))
    print("  %-9s 唯一 %d/%d (%.1f%%)  完全重复 %d  近似(>0.8) %d 对"
          % (f, len(items), total, 100.0 * len(items) / total, dup, near))
    for r, a, b in worst:
        print("      %.3f  %s  ||  %s" % (r, a, b))
    if near > 30:
        warnings.append("%s 近似重复 %d 对" % (f, near))

# ---------------------------------------------------------------- verdict
hr("结论")
if blockers:
    print("BLOCKERS (%d):" % len(blockers))
    for b in blockers:
        print("   x " + b)
if warnings:
    print("WARNINGS (%d):" % len(warnings))
    for w in warnings:
        print("   ! " + w)
if not blockers and not warnings:
    print("全部通过")
elif not blockers:
    print("\n无阻断项，可以打包。")
sys.exit(1 if blockers else 0)
