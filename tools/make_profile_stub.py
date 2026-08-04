# -*- coding: utf-8 -*-
"""Placeholder profiles_ordered.json so the page integration can be built and tested
before the real 243 land. Same shape, same index encoding, obviously fake text."""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

LV = ["低", "中", "高"]
OCEAN_ZH = {"O": "开放性", "C": "尽责性", "E": "外向性", "A": "宜人性", "N": "神经质"}
KEYS = ["O", "C", "E", "A", "N"]

out = []
for o in range(3):
    for c in range(3):
        for e in range(3):
            for a in range(3):
                for n in range(3):
                    lv = [o, c, e, a, n]
                    cell = "".join(k + LV[v] for k, v in zip(KEYS, lv))
                    out.append({
                        "lead": "占位文本 · " + cell,
                        "summary": "占位 summary，用于测试渲染与边界提示。" + cell +
                                   "。真实文案由写作工作流产出后替换。" * 2,
                        "life": "占位 生活 " + cell,
                        "friends": "占位 交友 " + cell,
                        "love": "占位 恋爱 " + cell,
                        "work": "占位 工作 " + cell,
                        "pros": ["占位优点一", "占位优点二", "占位优点三"],
                        "cons": ["占位缺点一", "占位缺点二", "占位缺点三"],
                        "practice": ["占位练习一", "占位练习二", "占位练习三"],
                    })

assert len(out) == 243
path = os.path.join(ipip.OUT, "profiles_ordered.json")
io.open(path, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
print("wrote %s (%d entries, %d bytes) -- PLACEHOLDER" % (path, len(out), os.path.getsize(path)))
print("index encoding: O*81 + C*27 + E*9 + A*3 + N,  低=0 中=1 高=2")
