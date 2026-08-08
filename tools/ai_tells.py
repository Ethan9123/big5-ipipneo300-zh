# -*- coding: utf-8 -*-
"""Measure the "AI feel" of the 243 profiles instead of guessing at it.

The tells that give away machine-written Chinese are structural and countable:
over-symmetrical constructions, dash abuse, uniform sentence length, every paragraph
landing on a summary line, and the same three metaphors reused 200 times.
This produces a per-pattern census so the rewrite brief can name specific offenders.
"""
import io
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ipip.OUT, "profiles_raw.json")
profiles = json.load(io.open(PATH, encoding="utf-8"))
PROSE = ["summary", "life", "friends", "love", "work"]
N = len(profiles)


def prose(p):
    return "".join(p[f] for f in PROSE)


all_text = "".join(prose(p) for p in profiles)
total_chars = len(all_text)
print("语料：%d 篇 x 5 段散文，共 %d 字\n" % (N, total_chars))

# ---------------------------------------------------------------- 1 句式模板
TEMPLATES = {
    "不是X，是Y / 不是X，而是Y": r"不是[^，。]{1,14}[，]\s*(而)?是",
    "与其说…不如说": r"与其说[^。]{1,20}不如说",
    "既…也/又…": r"既[^，。]{1,12}[，]?\s*[也又][^，。]{1,12}",
    "越…越…": r"越[^，。]{1,10}越",
    "不是A就是B": r"不是[^，。]{1,10}就是",
    "真正的X是": r"真正(的|让)[^，。]{0,12}",
    "问题(不)在于": r"问题(不)?(出)?在(于|你)",
    "代价是": r"代价(是|在)",
    "最该/最需要/最容易": r"最(该|需要|容易|大的|贵的|难的)",
    "这不算/这不是": r"这(并)?不(算|是|会)",
    "破折号——": r"——",
    "括号（）": r"（[^）]{2,30}）",
    "冒号引出": r"[：]",
}
print("=" * 74)
print("1  句式模板密度（每千字出现次数，以及覆盖多少篇）")
print("=" * 74)
tmpl_rows = []
for name, rx in TEMPLATES.items():
    hits = len(re.findall(rx, all_text))
    covered = sum(1 for p in profiles if re.search(rx, prose(p)))
    per_k = 1000.0 * hits / total_chars
    tmpl_rows.append({"pattern": name, "hits": hits, "per_1000": per_k,
                      "profiles": covered, "coverage_pct": 100.0 * covered / N})
    flag = "  <<<" if covered > N * 0.6 else ""
    print("  %-24s %5d 次  %5.2f/千字   覆盖 %3d/%d 篇 (%4.1f%%)%s"
          % (name, hits, per_k, covered, N, 100.0 * covered / N, flag))

# ---------------------------------------------------------------- 2 句长
print("\n" + "=" * 74)
print("2  句长分布（AI 写作的典型特征是句长过于均匀）")
print("=" * 74)
sents = [s for s in re.split(r"[。！？；]", all_text) if len(s.strip()) >= 2]
lens = sorted(len(s) for s in sents)
import statistics
mean_l = statistics.mean(lens)
sd_l = statistics.pstdev(lens)
print("  句子数 %d   均长 %.1f 字   标准差 %.1f   变异系数 %.3f"
      % (len(sents), mean_l, sd_l, sd_l / mean_l))
print("  分位：p10 %d / p25 %d / 中位 %d / p75 %d / p90 %d"
      % (lens[len(lens)//10], lens[len(lens)//4], lens[len(lens)//2],
         lens[3*len(lens)//4], lens[9*len(lens)//10]))
short = sum(1 for l in lens if l <= 8)
long_ = sum(1 for l in lens if l >= 40)
print("  ≤8 字的短句：%d (%.1f%%)     ≥40 字的长句：%d (%.1f%%)"
      % (short, 100.0*short/len(lens), long_, 100.0*long_/len(lens)))
print("  参考：人写的中文散文变异系数通常 0.6-0.8，短句占比 15-25%")

# ---------------------------------------------------------------- 3 段落收尾
print("\n" + "=" * 74)
print("3  段落收尾句式（每段都用总结句收口是很强的 AI 信号）")
print("=" * 74)
enders = Counter()
for p in profiles:
    for f in PROSE:
        ss = [s for s in re.split(r"[。！？]", p[f]) if s.strip()]
        if ss:
            tail = ss[-1].strip()
            # 取末句的前 4 字作为句式指纹
            enders[tail[:4]] += 1
print("  最常见的收尾开头（前 4 字）：")
for k, v in enders.most_common(12):
    print("     %-6s %4d 次 (%.1f%%)" % (k, v, 100.0 * v / (N * len(PROSE))))

# ---------------------------------------------------------------- 4 意象复用
print("\n" + "=" * 74)
print("4  意象与说法复用（同一个比喻用了多少遍）")
print("=" * 74)
IMAGES = ["反刍", "稀释", "重播", "回放", "过夜", "翻篇", "掉链子", "踩坑", "台阶",
          "耗尽", "内耗", "撑住", "扛", "绷", "塌", "沉底", "落空", "记一笔",
          "算总账", "先退", "收不了尾", "启动成本", "维持成本", "顺其自然"]
img_rows = []
for w in IMAGES:
    c = all_text.count(w)
    cov = sum(1 for p in profiles if w in prose(p))
    if c:
        img_rows.append((w, c, cov))
for w, c, cov in sorted(img_rows, key=lambda x: -x[2])[:16]:
    flag = "  <<<" if cov > N * 0.25 else ""
    print("  %-8s %4d 次   覆盖 %3d/%d 篇 (%4.1f%%)%s" % (w, c, cov, N, 100.0*cov/N, flag))

# ---------------------------------------------------------------- 5 高频 4-gram
print("\n" + "=" * 74)
print("5  跨篇复用的四字串（排除维度名，看有没有隐性模板）")
print("=" * 74)
STRIP = re.compile("开放性|尽责性|外向性|宜人性|神经质")
grams = Counter()
gram_profiles = {}
for p in profiles:
    t = STRIP.sub("", re.sub(r"[^一-鿿]", "", prose(p)))
    seen = set()
    for i in range(len(t) - 3):
        g = t[i:i+4]
        grams[g] += 1
        seen.add(g)
    for g in seen:
        gram_profiles[g] = gram_profiles.get(g, 0) + 1
top = [(g, c, gram_profiles[g]) for g, c in grams.items() if gram_profiles[g] >= 30]
top.sort(key=lambda x: -x[2])
for g, c, cov in top[:20]:
    print("  %-6s %4d 次   覆盖 %3d 篇 (%4.1f%%)" % (g, c, cov, 100.0*cov/N))
if not top:
    print("  没有四字串覆盖超过 30 篇")

# ---------------------------------------------------------------- 6 「你」
print("\n" + "=" * 74)
print("6  第二人称密度")
print("=" * 74)
you = all_text.count("你")
print("  「你」共 %d 次，每千字 %.1f 次" % (you, 1000.0*you/total_chars))
starts = sum(1 for p in profiles for f in PROSE
             for s in re.split(r"[。！？]", p[f]) if s.strip().startswith("你"))
tot_s = sum(1 for p in profiles for f in PROSE
            for s in re.split(r"[。！？]", p[f]) if s.strip())
print("  以「你」开头的句子：%d/%d = %.1f%%   （过高会显得机械）" % (starts, tot_s, 100.0*starts/tot_s))

json.dump({"n": N, "chars": total_chars, "templates": tmpl_rows,
           "sentence": {"n": len(sents), "mean": mean_l, "sd": sd_l, "cv": sd_l/mean_l,
                        "short_pct": 100.0*short/len(lens), "long_pct": 100.0*long_/len(lens)},
           "enders": enders.most_common(20),
           "images": [{"word": w, "hits": c, "profiles": cov} for w, c, cov in img_rows],
           "grams": [{"gram": g, "hits": c, "profiles": cov} for g, c, cov in top[:40]],
           "you_per_1000": 1000.0*you/total_chars,
           "you_sentence_start_pct": 100.0*starts/tot_s},
          io.open(os.path.join(ipip.OUT, "ai_tells.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\nwrote out/ai_tells.json")
