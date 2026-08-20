# -*- coding: utf-8 -*-
"""Sample-free checks on the 300 Chinese item translations.

The one class of translation error that silently corrupts every score is a reverse-keyed
item whose Chinese rendering lost its negation: the scorer still flips it, but the
sentence no longer means the opposite, so the flip is wrong. That is checkable without
any respondent data, by comparing the negation polarity of the English source and the
Chinese target item by item.
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

data = ipip.site_data()
items = data["items"]
rev = set(data["reversed"])

# Negation detection is crude by nature. Two fixes over the first pass, both found by
# reading its own false positives:
#   - "n't" must not carry a leading  (in "Can't" the char before n is a word char,
#     so n't never matches) -- this silently missed every contraction.
#   - Chinese renders "avoid" as 避开/回避, which carries the negation without 不/没.
# Idioms whose 不/无 is lexical rather than propositional (一成不变, 无家可归, 马不停蹄)
# are stripped before matching. The output is a shortlist for human reading, not a verdict.
EN_NEG = re.compile(r"(\bnot\b|n't\b|\b(never|rarely|seldom|hardly|dislikes?|avoids?"
                    r"|refuses?|lacks?|without|unable|fails?|hates?|no)\b)", re.I)
ZH_NEG = re.compile(r"不|没|无|从不|很少|难以|拒绝|避免|避开|回避|懒得|讨厌|缺乏|绝不|毫无")
ZH_IDIOM = re.compile(r"一成不变|无家可归|马不停蹄|不同|招架不住|忍不住"
                      r"|咄咄逼人|不由自主|情不自禁|迫不及待|数不清|不得不|不知不觉")

rows = []
for it in items:
    qid, en, zh = it["id"], it["en"], it["zh"]
    e_neg = bool(EN_NEG.search(en))
    zh_stripped = ZH_IDIOM.sub("", zh)
    z_neg = bool(ZH_NEG.search(zh_stripped))
    rows.append({"id": qid, "en": en, "zh": zh, "reversed": qid in rev,
                 "en_neg": e_neg, "zh_neg": z_neg, "mismatch": e_neg != z_neg})

def hr(t):
    print("\n" + "=" * 76 + "\n" + t + "\n" + "=" * 76)

hr("1  否定极性：英文原题 vs 中文译文")
mis = [r for r in rows if r["mismatch"]]
print("  300 题中，否定标记不一致的：%d" % len(mis))
print("  英文有否定词的：%d   中文有否定词的：%d"
      % (sum(r["en_neg"] for r in rows), sum(r["zh_neg"] for r in rows)))
print("\n  英文有否定、中文没有（最危险的一类，可能丢了否定）：")
a = [r for r in mis if r["en_neg"] and not r["zh_neg"]]
print("    共 %d 条" % len(a))
for r in a[:15]:
    print("      #%3d %-2s  %s" % (r["id"], "反" if r["reversed"] else "正", r["en"][:44]))
    print("           %s" % r["zh"][:44])
print("\n  中文有否定、英文没有（可能是中文改写，需人工判断）：")
b = [r for r in mis if r["zh_neg"] and not r["en_neg"]]
print("    共 %d 条" % len(b))
for r in b[:15]:
    print("      #%3d %-2s  %s" % (r["id"], "反" if r["reversed"] else "正", r["en"][:44]))
    print("           %s" % r["zh"][:44])

hr("2  否定与反向计分的交叉表")
tab = {}
for r in rows:
    k = ("反向" if r["reversed"] else "正向", "英否" if r["en_neg"] else "英肯",
         "中否" if r["zh_neg"] else "中肯")
    tab[k] = tab.get(k, 0) + 1
for k in sorted(tab):
    print("  %-4s %-4s %-4s : %3d" % (k[0], k[1], k[2], tab[k]))
print("""
  读法：IPIP 的反向题不一定含否定词（例如「Know the answers to many questions」
  是 A5 谦逊的反向题，肯定句），所以「反向+英肯」是正常的。真正要查的是
  英文与中文的否定极性不一致——那可能是翻译丢了或加了否定。""")

hr("3  中文译文的长度与可读性")
zl = sorted(len(re.sub(r"\s", "", r["zh"])) for r in rows)
print("  中文题目字数：min %d  中位 %d  max %d" % (zl[0], zl[150], zl[-1]))
longest = sorted(rows, key=lambda r: -len(r["zh"]))[:5]
for r in longest:
    print("    #%3d (%2d字) %s" % (r["id"], len(r["zh"]), r["zh"]))

hr("4  双重否定与模糊表达")
dbl = [r for r in rows if len(ZH_NEG.findall(r["zh"])) >= 2]
print("  中文里出现两个及以上否定词的：%d" % len(dbl))
for r in dbl[:12]:
    print("    #%3d %-2s %s" % (r["id"], "反" if r["reversed"] else "正", r["zh"]))

hr("5  文化敏感内容（跨文化研究点名过的高风险面向）")
RISK = {"O6 自由主义": r"政治|宗教|保守|自由派|信仰|投票|上帝|教堂|选举|犯罪|税",
        "E5 寻求刺激": r"冒险|刺激|危险|疯狂",
        "N5 放纵": r"酒|喝|吃太多|克制|欲望|忍不住"}
for name, rx in RISK.items():
    hit = [r for r in rows if re.search(rx, r["zh"])]
    print("\n  %s —— 命中 %d 条" % (name, len(hit)))
    for r in hit[:6]:
        print("    #%3d %s" % (r["id"], r["zh"][:50]))

json.dump({"n": len(rows), "polarity_mismatch": len(mis),
           "en_neg_zh_pos": len(a), "zh_neg_en_pos": len(b),
           "double_negation": len(dbl),
           "mismatches": [{k: r[k] for k in ("id", "en", "zh", "reversed", "en_neg", "zh_neg")} for r in mis]},
          io.open(os.path.join(ipip.OUT, "translation_check.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\nwrote out/translation_check.json")
