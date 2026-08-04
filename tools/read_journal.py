# -*- coding: utf-8 -*-
"""Pull one agent's full return value out of the workflow journal."""
import io
import json
import os
import sys

# Point this at a workflow run's journal.jsonl:
#   set CLAUDE_WORKFLOW_JOURNAL=...\subagents\workflows\<run-id>\journal.jsonl
PATH = os.environ.get("CLAUDE_WORKFLOW_JOURNAL", "")
if not PATH or not os.path.exists(PATH):
    sys.exit("set CLAUDE_WORKFLOW_JOURNAL to a workflow journal.jsonl path")

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
