# -*- coding: utf-8 -*-
"""Calibrate qa_structure's thresholds against the two APPROVED samples in
profile_spec.md. A QA tool that fails known-good content has bad thresholds.
Any failure printed here is either a harness bug or a spec self-contradiction."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qa_structure import n_cjk, BANDS, FILLER_RE, CONCRETE_RE, dims_in  # noqa

S1 = {
    "cell": "O中C中E中A中N中",
    "lead": "五个维度都落在中间，行为更多由场合决定",
    "summary": "五个维度都落在人群中间地带。这不是“没有性格”，而是你的行为更多由场合决定，"
               "而不是由某个突出的倾向决定——同一件事，换个环境你可能给出完全不同的反应，"
               "这在高分或低分的人身上要少见得多。代价是你缺少一个“默认设置”，做选择时容易"
               "反复权衡，因为没有哪个倾向强到能帮你直接排除选项。",
    "friends": "你在大多数群体里都待得住，但也很少成为核心。朋友对你的评价往往是“挺好相处”"
               "而不是某个具体标签。要留意的是：中等外向的人最容易高估自己社交上的主动性——"
               "你觉得“我们常联系”的朋友，可能已经半年没收到你消息了。",
    "practice": ["给自己造一个人为的极端：挑一件事刻意做到过头，用外部规则补上你天生没有的那股劲。"],
}
S2 = {
    "cell": "O高C低E高A低N高",
    "lead": "想法很多、情绪很满、收尾很差",
    "summary": "你的组合里有三股力量在互相拽：开放性和外向性推着你不断开始新东西，低尽责性"
               "让你收不了尾，高神经质让每一次收不了尾都变成一次自我攻击。你不是懒，你是"
               "启动成本极低而维持成本极高。",
    "love": "你会是热烈的追求者和难缠的伴侣。高神经质让你把对方的小反应放大，低宜人性让你"
            "在争执里不肯先退。最该练的一句话是“我现在情绪上来了，等我半小时再聊”——"
            "这一句能挡掉你大半的破坏性冲突。",
    "practice": ["把承诺和兴奋分开：兴奋的当下不要答应任何事，隔 24 小时还想做再答应。"],
}

print("=== LENGTH vs spec bands ===")
for s in (S1, S2):
    print("-- %s" % s["cell"])
    for f in ("lead", "summary", "friends", "love"):
        if f not in s:
            continue
        c = n_cjk(s[f])
        lo, hi = BANDS[f]
        print("   %-8s %3d chars   band %3d-%3d   %s"
              % (f, c, lo, hi, "OK" if lo <= c <= hi else "*** OUT OF BAND ***"))
    for i, p in enumerate(s["practice"]):
        c = n_cjk(p)
        lo, hi = BANDS["practice"]
        print("   practice[%d] %3d chars band %d-%d  %s"
              % (i, c, lo, hi, "OK" if lo <= c <= hi else "*** OUT OF BAND ***"))

print("\n=== PRACTICE executability detector ===")
for s in (S1, S2):
    for p in s["practice"]:
        hits = [pat for pat, rx in FILLER_RE if rx.search(p)]
        conc = bool(CONCRETE_RE.search(p))
        verdict = "PASS" if (not hits and conc) else "FAIL"
        print("  [%s] %s  filler=%s concrete=%s" % (verdict, s["cell"], hits, conc))
        if verdict == "FAIL":
            print("        -> harness would reject an APPROVED sample: %s" % p)

print("\n=== SUMMARY interaction detector ===")
for s in (S1, S2):
    d = dims_in(s["summary"])
    print("  %s dims=%s  %s" % (s["cell"], sorted(d),
                                "PASS" if len(d) >= 2 else "*** FAIL (<2) ***"))

print("\n=== HARD-BAN phrases (spec section 硬性禁止) in the approved samples ===")
BANS = ["你天生", "你注定", "你就是", "内向者", "外向者",
        "抑郁症", "焦虑症", "多动症", "自闭", "强迫症"]
for s in (S1, S2):
    for f, v in s.items():
        texts = v if isinstance(v, list) else [v]
        for t in texts:
            if not isinstance(t, str):
                continue
            for b in BANS:
                if b in t:
                    print("  !! %s.%s contains banned phrase '%s'" % (s["cell"], f, b))
                    print("     %s" % t)
