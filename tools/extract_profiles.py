# -*- coding: utf-8 -*-
"""Pull the 243 written profiles out of the workflow journal and land them on disk.

The workflow sandbox has no filesystem access, so the writing agents' output only exists
in their return values. journal.jsonl carries one {"type":"result"} line per agent.
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

JOURNAL = (r"C:\Users\kids1\.claude\projects\C--Users-kids1-Downloads-bigfive"
           r"\3f3dea16-3b73-4559-8359-8360df8000b2\subagents\workflows"
           r"\wf_63077d4b-d49\journal.jsonl")

LV = ["低", "中", "高"]
KEYS = ["O", "C", "E", "A", "N"]
FIELDS = ["cell", "lead", "summary", "life", "friends", "love", "work", "pros", "cons", "practice"]


def cell_name(idx):
    lv = []
    for i in range(5):
        lv.append(idx // (3 ** (4 - i)) % 3)
    return "".join(k + LV[v] for k, v in zip(KEYS, lv))


def cell_index(name):
    """Parse 'O中C高E高A高N低' back to 0..242."""
    if not isinstance(name, str) or len(name) != 10:
        return None
    idx = 0
    for i, k in enumerate(KEYS):
        if name[i * 2] != k:
            return None
        try:
            idx = idx * 3 + LV.index(name[i * 2 + 1])
        except ValueError:
            return None
    return idx


collected = []
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
    if isinstance(val, dict) and isinstance(val.get("profiles"), list):
        collected.append((rec.get("agentId", "?"), val["profiles"]))

print("agents returning profiles: %d" % len(collected))
for aid, ps in collected:
    cells = [p.get("cell", "?") for p in ps]
    print("   %s  n=%-3d  %s ... %s" % (aid[:12], len(ps), cells[0], cells[-1]))

flat = [p for _, ps in collected for p in ps]
print("\ntotal profiles: %d" % len(flat))

# --------------------------------------------------------------- validate + order
ordered = [None] * 243
problems = []
for p in flat:
    name = p.get("cell")
    idx = cell_index(name)
    if idx is None:
        problems.append("unparseable cell: %r" % (name,))
        continue
    if ordered[idx] is not None:
        problems.append("duplicate cell %s" % name)
        continue
    missing = [f for f in FIELDS if f not in p or p[f] in (None, "", [])]
    if missing:
        problems.append("%s missing fields: %s" % (name, ",".join(missing)))
    ordered[idx] = p

gaps = [cell_name(i) for i, v in enumerate(ordered) if v is None]
print("filled: %d / 243   gaps: %d" % (243 - len(gaps), len(gaps)))
if gaps:
    print("  missing cells:", ", ".join(gaps[:20]))
if problems:
    print("problems (%d):" % len(problems))
    for x in problems[:20]:
        print("   " + x)

if gaps:
    sys.exit("refusing to write an incomplete set")

# raw: with cell field, for QA
raw_path = os.path.join(ipip.OUT, "profiles_raw.json")
io.open(raw_path, "w", encoding="utf-8").write(json.dumps(ordered, ensure_ascii=False, indent=1))
print("\nwrote %s  (%d bytes)" % (raw_path, os.path.getsize(raw_path)))

# ordered: cell stripped, index IS the identity -- this is what ships
ship = [{k: v for k, v in p.items() if k != "cell"} for p in ordered]
ship_path = os.path.join(ipip.OUT, "profiles_ordered.json")
io.open(ship_path, "w", encoding="utf-8").write(json.dumps(ship, ensure_ascii=False, separators=(",", ":")))
print("wrote %s  (%d bytes)" % (ship_path, os.path.getsize(ship_path)))

# --------------------------------------------------------------- quick shape report
def clen(s):
    return sum(1 for ch in s if not ch.isspace())


print("\nfield lengths (Chinese chars, whitespace stripped):")
for f in ["lead", "summary", "life", "friends", "love", "work"]:
    ls = sorted(clen(p[f]) for p in ordered)
    print("  %-8s min %3d  median %3d  max %3d" % (f, ls[0], ls[len(ls) // 2], ls[-1]))
for f in ["pros", "cons", "practice"]:
    ls = sorted(clen(x) for p in ordered for x in p[f])
    uniq = len({x for p in ordered for x in p[f]})
    print("  %-8s min %3d  median %3d  max %3d   unique %d/%d (%.1f%%)"
          % (f, ls[0], ls[len(ls) // 2], ls[-1], uniq, len(ls), 100.0 * uniq / len(ls)))

placeholder = sum(1 for p in ordered if "占位" in json.dumps(p, ensure_ascii=False))
print("\nentries containing 占位: %d  (must be 0)" % placeholder)
