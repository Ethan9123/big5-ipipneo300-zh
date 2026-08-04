# -*- coding: utf-8 -*-
"""qa2_voice_probe.py -- 只读探查：为 qa2_voice.py 的白名单/黑名单做准备。不产出结论。"""
import json, re, io, os, sys, collections

sys.stdout.reconfigure(encoding='utf-8')
RAW = r"C:\Users\kids1\Downloads\bigfive\tools\out\profiles_raw.json"
data = json.load(io.open(RAW, encoding='utf-8'))
TEXT = ["lead", "summary", "life", "friends", "love", "work"]
LIST = ["pros", "cons", "practice"]


def iter_units(p):
    for f in TEXT:
        yield f, p.get(f, "") or ""
    for f in LIST:
        for i, s in enumerate(p.get(f, []) or []):
            yield "%s[%d]" % (f, i), s


allt = []
for p in data:
    for f, s in iter_units(p):
        allt.append((p["cell"], f, s))
print("units:", len(allt), "profiles:", len(data))

CJK = r"[\u4e00-\u9fff]"

def tally(pat, label, n=200):
    c = collections.Counter()
    for cell, f, s in allt:
        for m in re.finditer(pat, s):
            c[m.group(0)] += 1
    print("\n==== %s :: distinct=%d total=%d" % (label, len(c), sum(c.values())))
    for k, v in c.most_common(n):
        print("   %-14s %d" % (k, v))

tally(CJK + r"{1,4}型", "X型")
tally(CJK + r"{1,4}者", "X者")
tally(CJK + r"{1,4}家(?!庭|里|人|务|具|乡|长|中)", "X家")
tally(r"完美" + CJK + r"{0,3}", "完美*")
tally(CJK + r"{0,4}永远", "*永远")
tally(CJK + r"{0,3}必然" + CJK + r"{0,2}", "必然")
tally(CJK + r"{0,3}一定会", "一定会")
tally(r"焦虑" + CJK + r"{0,2}", "焦虑*")
tally(r"抑郁" + CJK + r"{0,2}", "抑郁*")
tally(CJK + r"{0,3}障碍", "障碍")
tally(CJK + r"{0,2}病" + CJK + r"{0,2}", "病")
tally(CJK + r"{0,2}症" + CJK + r"{0,2}", "症")
tally(r"[A-Za-z]{3,}", "latin>=3")
tally(CJK + r"{0,3}天生" + CJK + r"{0,3}", "天生")
tally(CJK + r"{0,3}注定" + CJK + r"{0,3}", "注定")
tally(CJK + r"{0,2}你就是" + CJK + r"{0,4}", "你就是")
tally(CJK + r"{0,3}(懒|不负责任|自私|幼稚|无能|靠不住|不可靠|散漫)" + CJK + r"{0,3}", "moral")
tally(r"(筛选|筛掉|排除|试探|评价|考验|识别|挑人|挑选)" + CJK + r"{0,4}", "judge-others")
tally(CJK + r"{0,3}(治疗|就医|看医生|心理咨询|咨询师|专业帮助|吃药|确诊|诊断)" + CJK + r"{0,3}", "clinical-hint")
tally(r"(内向|外向|宜人|尽责|开放|神经质)" + CJK + r"{0,2}", "dim words")
tally(r"(天赋|异禀|独一无二|上天|命中注定|魅力四射|与生俱来|得天独厚|上帝)", "astro")
