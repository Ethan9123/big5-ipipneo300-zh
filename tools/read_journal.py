# -*- coding: utf-8 -*-
"""Pull one agent's full return value out of the workflow journal."""
import io
import json
import sys

PATH = (r"C:\Users\kids1\.claude\projects\C--Users-kids1-Downloads-bigfive"
        r"\3f3dea16-3b73-4559-8359-8360df8000b2\subagents\workflows"
        r"\wf_42de793d-2cc\journal.jsonl")

want = sys.argv[1] if len(sys.argv) > 1 else None
field = sys.argv[2] if len(sys.argv) > 2 else None

for line in io.open(PATH, encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    try:
        rec = json.loads(line)
    except ValueError:
        continue
    if rec.get("type") != "result":
        continue
    label = rec.get("agentId", "")
    if want and want not in label:
        continue
    val = rec.get("result", rec.get("value"))
    if isinstance(val, str):
        try:
            val = json.loads(val)
        except ValueError:
            pass
    print("\n" + "#" * 78)
    print("# AGENT:", label)
    print("#" * 78)
    if field and isinstance(val, dict) and field in val:
        print(json.dumps(val[field], ensure_ascii=False, indent=1))
    else:
        print(json.dumps(val, ensure_ascii=False, indent=1))
