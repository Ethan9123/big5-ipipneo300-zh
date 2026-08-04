# -*- coding: utf-8 -*-
"""qa2_voice_probe2.py -- 只读探查 cons 语料，为代价判定设计关键词。"""
import json, re, io, sys, collections
sys.stdout.reconfigure(encoding='utf-8')
RAW = r"C:\Users\kids1\Downloads\bigfive\tools\out\profiles_raw.json"
data = json.load(io.open(RAW, encoding='utf-8'))

LEV = {"低": 0, "中": 1, "高": 2}
def parse(cell):
    m = re.findall(r"([OCEAN])([低中高])", cell)
    return {k: v for k, v in m}

groups = {"N低": ("N", "低"), "A高": ("A", "高"), "C低": ("C", "低")}
for name, (dim, lev) in groups.items():
    sel = [p for p in data if parse(p["cell"]).get(dim) == lev]
    print("\n######## %s  n=%d" % (name, len(sel)))
    cnt = collections.Counter()
    for p in sel:
        for c in p["cons"]:
            cnt[c] += 1
    print("  distinct cons items:", len(cnt), "total:", sum(cnt.values()))
    for k, v in cnt.most_common():
        print("   %2d  %s" % (v, k))
