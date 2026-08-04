# -*- coding: utf-8 -*-
"""Targeted wording fixes flagged by the QA pass. Every edit is an exact-match
replacement that fails loudly if the source text has moved.

The first three are the ones that matter: they rank the reader's own cell against the
other 242, which is a verdict on the person rather than a description of behaviour --
and with a measured 47.2% retest rate, over half of those readers will not even be in
that cell next time.
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

RAW = os.path.join(ipip.OUT, "profiles_raw.json")
SHIP = os.path.join(ipip.OUT, "profiles_ordered.json")

# (cell, field, index_or_None, old_fragment, new_fragment, why)
# MARKERS: a short distinctive fragment that proves the edit is already in place.
# The revision agents sometimes re-tweak the wording around a fix, so an exact match on
# the full replacement is too brittle to detect "already applied".
MARKERS = {
    ("O低C低E高A低N高", "lead"): "当场爆发、回家重播",
    # love/work were rewritten wholesale by the extraversion pass; these markers track the
    # surviving substance, and verify_corpus.py's red lines are the real authority on
    # whether the original problem came back.
    ("O中C中E中A低N高", "love"): "你既敏感又不肯先退",
    ("O低C高E低A低N高", "summary"): "最费力的地方",
    # keep markers short: the revision agents re-tweak wording around a fix
    # (「常常」 -> 「常」), and an over-specific marker reads that as a lost edit.
    ("O中C中E高A中N高", "work"): "你重新推起来的",
    ("O中C高E高A低N低", "work"): "停滞的事常常由你重",
    ("O低C中E低A高N低", "summary"): "几乎总在等对方先开口",
    ("O高C高E中A低N低", "practice"): "每月固定一天各发一条消息",
    # the reviser reached the same fix independently ("所以你总差一点，也停不下来"),
    # so match on the outcome rather than on my exact phrasing
    ("O高C高E高A高N高", "summary"): "总差一点",
}

EDITS = [
    ("O低C低E高A低N高", "lead", None,
     "现场爆发、事后反刍、怨气还在，破坏面积最大的一格",
     "当场爆发、回家重播，怨气比事情活得久",
     "把「243 格里最具破坏性」的全局排名去掉，只留行为序列"),

    ("O中C中E中A低N高", "love", None,
     "你在关系里既敏感又不肯先退，这两样凑一起破坏力最大。",
     "你在关系里既敏感又不肯先退，这两样最容易互相放大。",
     "同上，去掉排名式定性"),

    ("O低C高E低A低N高", "summary", None,
     "是这一格最吃力的部分：",
     "是最费力的地方：",
     "同上"),

    ("O中C中E高A中N高", "work", None,
     "你在会上敢说、对外能扛，是推进型的人。",
     "你在会上敢说、对外能扛，停下来的事常常是你重新推起来的。",
     "「X型的人」是规格明令禁止的自造类型名，全语料唯一一处"),

    ("O中C高E高A低N低", "work", None,
     "你是推动者，能把停滞的事重新启动，也乐意承担责任。",
     "停滞的事常常由你重新启动，你也乐意承担责任。",
     "裸身份名词贴标签，改成行为句"),

    ("O低C中E低A高N低", "summary", None,
     "只是永远在等对方先开口",
     "只是几乎总在等对方先开口",
     "全语料 31 处「永远」里唯一一处修饰读者本人，接近永久性断言"),

    ("O高C高E中A低N低", "practice", 2,
     "把重要关系写进日程，定期主动联系，别靠感觉。",
     "把三个最重要的人写进日程，每月固定一天各发一条消息，不看当时想不想。",
     "「定期」没有间隔，是 729 条 practice 中唯一实测不可执行的一条"),

    # 返工引入的
    ("O高C高E高A高N高", "summary", None,
     "它没有上限，所以你永远差一点，永远不能停，",
     "它没有上限，所以只要这条规矩还在，你就总差一点、停不下来，",
     "「你永远」是规格禁止的永久性断言；改成以「那条规矩」为条件，"
     "含义不变但不再是对人的定性——这句落在高神经质读者眼里尤其要紧"),
]

profiles = json.load(io.open(RAW, encoding="utf-8"))
by_cell = {p["cell"]: p for p in profiles}

applied = 0
for cell, field, idx, old, new, why in EDITS:
    p = by_cell.get(cell)
    if p is None:
        sys.exit("no such cell: %s" % cell)
    whole = p[field] if isinstance(p[field], str) else " ".join(p[field])
    cur = p[field] if idx is None else p[field][idx]
    if old not in cur:
        # idempotent: already applied is fine; anything else is a real failure
        if MARKERS.get((cell, field), new) in whole:
            print("%-16s %-9s 已应用，跳过" % (cell, field))
            continue
        sys.exit("FAILED on %s.%s -- expected fragment not present:\n  want: %s\n  have: %s"
                 % (cell, field, old, cur))
    upd = cur.replace(old, new, 1)
    if idx is None:
        p[field] = upd
    else:
        p[field][idx] = upd
    applied += 1
    print("%-16s %-9s %s" % (cell, field, why))
    print("   -  %s" % old)
    print("   +  %s\n" % new)

print("applied %d/%d edits" % (applied, len(EDITS)))

io.open(RAW, "w", encoding="utf-8").write(json.dumps(profiles, ensure_ascii=False, indent=1))
ship = [{k: v for k, v in p.items() if k != "cell"} for p in profiles]
io.open(SHIP, "w", encoding="utf-8").write(json.dumps(ship, ensure_ascii=False, separators=(",", ":")))
print("rewrote profiles_raw.json and profiles_ordered.json")

# guard: the ranking phrasings must be gone from the whole corpus
blob = json.dumps(profiles, ensure_ascii=False)
for bad in ["破坏面积最大", "破坏力最大", "最吃力的部分", "型的人", "你是推动者"]:
    n = blob.count(bad)
    print("  residual %-10s : %d" % (bad, n))
