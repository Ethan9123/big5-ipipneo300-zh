# -*- coding: utf-8 -*-
"""Merge a revision workflow's journal into profiles_raw.json.

Cells the workflow did not return are left exactly as they are, so a failed block is a
no-op rather than a hole. Prints which blocks were touched and which were not.

  python tools/merge_revision.py <run-id>
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

RUN = sys.argv[1] if len(sys.argv) > 1 else "wf_bc76ce5b-de3"
JOURNAL = (r"C:\Users\kids1\.claude\projects\C--Users-kids1-Downloads-bigfive"
           r"\3f3dea16-3b73-4559-8359-8360df8000b2\subagents\workflows\%s\journal.jsonl" % RUN)
RAW = os.path.join(ipip.OUT, "profiles_raw.json")
SHIP = os.path.join(ipip.OUT, "profiles_ordered.json")
LV = ["低", "中", "高"]
KEYS = ["O", "C", "E", "A", "N"]
FIELDS = ["lead", "summary", "life", "friends", "love", "work", "pros", "cons", "practice"]


def idx_of(cell):
    if not isinstance(cell, str) or len(cell) != 10:
        return None
    n = 0
    for i, k in enumerate(KEYS):
        if cell[i * 2] != k:
            return None
        try:
            n = n * 3 + LV.index(cell[i * 2 + 1])
        except ValueError:
            return None
    return n


current = json.load(io.open(RAW, encoding="utf-8"))
by_cell = {p["cell"]: p for p in current}

revised, logs = {}, []
for line in io.open(JOURNAL, encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    try:
        rec = json.loads(line)
    except ValueError:
        continue
    if rec.get("type") != "result":
        continue
    val = rec.get("result")
    if isinstance(val, str):
        try:
            val = json.loads(val)
        except ValueError:
            continue
    if not isinstance(val, dict) or not isinstance(val.get("profiles"), list):
        continue
    logs += val.get("changeLog") or []
    for p in val["profiles"]:
        if idx_of(p.get("cell")) is None:
            print("  skipping unparseable cell: %r" % p.get("cell"))
            continue
        missing = [f for f in FIELDS if not p.get(f)]
        if missing:
            print("  skipping %s (missing %s)" % (p["cell"], ",".join(missing)))
            continue
        revised[p["cell"]] = p

blocks = {}
for c in revised:
    blocks.setdefault(c[:4], 0)
    blocks[c[:4]] += 1
print("blocks returned by the workflow:")
for o in LV:
    for cc in LV:
        b = "O%sC%s" % (o, cc)
        n = blocks.get(b, 0)
        print("   %-8s %2d/27%s" % (b, n, "" if n == 27 else "   <-- 未返工，保留原稿"))

changed = 0
for cell, new in revised.items():
    old = by_cell.get(cell)
    if old is None:
        print("  unknown cell from workflow: %s" % cell)
        continue
    if any(old[f] != new[f] for f in FIELDS):
        changed += 1
    for f in FIELDS:
        old[f] = new[f]

print("\ncells replaced : %d" % len(revised))
print("cells actually changed : %d" % changed)
print("cells left untouched   : %d" % (243 - len(revised)))
print("change-log entries     : %d" % len(logs))

io.open(RAW, "w", encoding="utf-8").write(json.dumps(current, ensure_ascii=False, indent=1))
ship = [{k: v for k, v in p.items() if k != "cell"} for p in current]
io.open(SHIP, "w", encoding="utf-8").write(json.dumps(ship, ensure_ascii=False, separators=(",", ":")))
io.open(os.path.join(ipip.OUT, "revision_changelog.txt"), "w", encoding="utf-8").write("\n".join(logs))
print("rewrote profiles_raw.json / profiles_ordered.json / revision_changelog.txt")

# the seven hand-applied wording fixes must have survived the merge
GUARD = [("O低C低E高A低N高", "lead", "当场爆发、回家重播"),
         ("O中C中E中A低N高", "love", "最容易互相放大"),
         ("O低C高E低A低N高", "summary", "最费力的地方"),
         ("O中C中E高A中N高", "work", "停下来的事常常是你重新推起来的"),
         ("O中C高E高A低N低", "work", "停滞的事常常由你重新启动"),
         ("O低C中E低A高N低", "summary", "几乎总在等对方先开口"),
         ("O高C高E中A低N低", "practice", "每月固定一天各发一条消息")]
print("\n手工修改是否被返工覆盖：")
lost = 0
for cell, field, frag in GUARD:
    p = by_cell[cell]
    hay = p[field] if isinstance(p[field], str) else " ".join(p[field])
    ok = frag in hay
    if not ok:
        lost += 1
    print("   %-16s %-9s %s" % (cell, field, "保留" if ok else "已被覆盖 —— 需复查"))
if lost:
    print("\n注意：%d 处被返工覆盖，verify_corpus.py 的红线检查会判断新措辞是否仍然安全。" % lost)
