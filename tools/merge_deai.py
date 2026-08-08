# -*- coding: utf-8 -*-
"""Merge the de-AI rewrite into profiles_raw.json.

This workflow returned only the six prose fields (cell/lead/summary/life/friends/love/
work); pros/cons/practice are untouched by design. A backup of the pre-merge corpus is
written next to the target so the change is reversible.
"""
import io
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

RUN = sys.argv[1] if len(sys.argv) > 1 else "wf_5ac70b74-786"
JOURNAL = os.environ.get("CLAUDE_WORKFLOW_JOURNAL") or os.path.join(
    os.path.expanduser("~"), ".claude", "projects",
    "C--Users-kids1-Downloads-bigfive", "3f3dea16-3b73-4559-8359-8360df8000b2",
    "subagents", "workflows", RUN, "journal.jsonl")
RAW = os.path.join(ipip.OUT, "profiles_raw.json")
SHIP = os.path.join(ipip.OUT, "profiles_ordered.json")
PROSE = ["lead", "summary", "life", "friends", "love", "work"]
LV = ["低", "中", "高"]
KEYS = ["O", "C", "E", "A", "N"]


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

revised = {}
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
    v = rec.get("result")
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            continue
    if not isinstance(v, dict) or not isinstance(v.get("profiles"), list):
        continue
    for p in v["profiles"]:
        if idx_of(p.get("cell")) is None:
            print("  skip unparseable cell %r" % p.get("cell"))
            continue
        missing = [f for f in PROSE if not p.get(f)]
        if missing:
            print("  skip %s (missing %s)" % (p["cell"], ",".join(missing)))
            continue
        revised[p["cell"]] = p

blocks = {}
for c in revised:
    blocks[c[:4]] = blocks.get(c[:4], 0) + 1
print("blocks:")
for o in LV:
    for cc in LV:
        b = "O%sC%s" % (o, cc)
        n = blocks.get(b, 0)
        print("   %-8s %2d/27%s" % (b, n, "" if n == 27 else "   <-- INCOMPLETE"))
if len(revised) != 243:
    sys.exit("expected 243 rewritten profiles, got %d -- aborting, nothing written" % len(revised))

backup = RAW.replace(".json", ".before_deai.json")
shutil.copy2(RAW, backup)
print("backup: %s" % os.path.basename(backup))

changed = 0
kept = 0
for cell, new in revised.items():
    old = by_cell[cell]
    if any(old[f] != new[f] for f in PROSE):
        changed += 1
    for f in PROSE:
        old[f] = new[f]
    # hard guarantee: the three lists were not touched
    kept += 1

io.open(RAW, "w", encoding="utf-8").write(json.dumps(current, ensure_ascii=False, indent=1))
ship = [{k: v for k, v in p.items() if k != "cell"} for p in current]
io.open(SHIP, "w", encoding="utf-8").write(json.dumps(ship, ensure_ascii=False, separators=(",", ":")))
print("prose fields replaced in %d/243 cells (%d actually differ)" % (kept, changed))
print("pros/cons/practice untouched by construction (fields never assigned)")
